from typing import Dict, List, Any, Optional, Tuple, Callable
try:
    from .ftrace_file import TraceFile
    from .ftrace_models import Event
except ImportError:
    from ftrace_file import TraceFile
    from ftrace_models import Event
import statistics

class Analyzer:
    """高层次 analysis 接口"""
    
    def __init__(self, trace: TraceFile):
        self.trace = trace

    def detect_time_anomalies(self, threshold_us: float = 100) -> Dict[str, Any]:
        """检测时间异常（事件间隔过大）"""
        gaps = []
        last_event = None
        
        for event in self.trace.iter_events():
            if last_event:
                diff_us = (event.timestamp - last_event.timestamp) * 1000000
                if diff_us >= threshold_us:
                    gaps.append({
                        'prev_line_no': last_event.line_no,
                        'next_line_no': event.line_no,
                        'start': last_event.timestamp,
                        'end': event.timestamp,
                        'duration_us': diff_us,
                        'prev_event': str(last_event),
                        'next_event': str(event)
                    })
            last_event = event
            
        durations = [g['duration_us'] for g in gaps]
        return {
            'gaps': gaps,
            'summary': {
                'total_gaps': len(gaps),
                'max_gap_us': max(durations, default=0),
                'p95_gap_us': statistics.quantiles(durations, n=20)[18] if len(durations) >= 20 else (max(durations, default=0))
            }
        }

    def get_time_distribution(self, bin_size: float = 0.001) -> Dict[str, Any]:
        """获取时间分布（用于识别热点时段）"""
        start, end = self.trace.get_time_range()
        if start is None: return {}
        
        num_bins = int((end - start) / bin_size) + 1
        counts = [0] * num_bins
        cpu_usage = [set() for _ in range(num_bins)]
        
        for event in self.trace.iter_events():
            idx = int((event.timestamp - start) / bin_size)
            if 0 <= idx < num_bins:
                counts[idx] += 1
                if event.pid != 0:
                    cpu_usage[idx].add(event.cpu)
        
        cpu_util = [len(u) for u in cpu_usage]
        
        # 识别热点时段 (利用率 > 80% 的 CPU 数，或者事件密度远高于平均)
        avg_count = statistics.mean(counts) if counts else 0
        hotspots = []
        for i, count in enumerate(counts):
            if count > avg_count * 2:
                hotspots.append({
                    'start': start + i * bin_size,
                    'end': start + (i + 1) * bin_size,
                    'util': count / avg_count if avg_count > 0 else 0
                })
                    
        return {
            'bins': [start + i * bin_size for i in range(num_bins)],
            'event_counts': counts,
            'cpu_util': cpu_util,
            'hotspots': hotspots
        }

    def classify_contexts(self) -> Dict[str, Any]:
        """将事件按执行上下文分类"""
        stats = {
            'user_process': {'count': 0, 'pids': set(), 'comms': set()},
            'kernel_thread': {'count': 0, 'pids': set(), 'threads': set()},
            'idle': {'count': 0},
            'irq': {'count': 0},
            'softirq': {'count': 0}
        }
        
        for event in self.trace.iter_events():
            if event.pid == 0:
                stats['idle']['count'] += 1
            elif 'softirq' in event.event_type.lower() or 'softirq' in event.task:
                stats['softirq']['count'] += 1
            elif 'irq' in event.event_type.lower():
                stats['irq']['count'] += 1
            elif event.task.startswith('kworker'):
                stats['kernel_thread']['count'] += 1
                stats['kernel_thread']['pids'].add(event.pid)
                stats['kernel_thread']['threads'].add(event.task)
            else:
                stats['user_process']['count'] += 1
                stats['user_process']['pids'].add(event.pid)
                stats['user_process']['comms'].add(event.task)
                
        total = sum(s['count'] for s in stats.values())
        for k in stats:
            stats[k]['time_percent'] = round((stats[k]['count'] / total * 100), 2) if total > 0 else 0
            if 'pids' in stats[k]:
                stats[k]['processes'] = sorted(list(stats[k].pop('pids')))
            if 'comms' in stats[k]:
                stats[k]['comms'] = sorted(list(stats[k]['comms']))[:10]
            if 'threads' in stats[k]:
                stats[k]['threads'] = sorted(list(stats[k]['threads']))[:10]
                
        return stats

    def get_context_timeline(self, cpu: int) -> List[Dict[str, Any]]:
        """获取某个 CPU 的上下文切换时间线"""
        timeline = []
        last_event = None
        
        query = self.trace.query().cpu(cpu).event_type('sched_switch')
        for event in query.execute():
            if last_event:
                context = 'idle' if last_event.next_pid == 0 else \
                          'kernel_thread' if last_event.next_comm.startswith('kworker') else \
                          'user_process'
                
                timeline.append({
                    'start': last_event.timestamp,
                    'end': event.timestamp,
                    'context': context,
                    'pid': last_event.next_pid,
                    'comm': last_event.next_comm
                })
            last_event = event
        return timeline

    def check_process_running(self, pid: int, time_range: Tuple[float, float] = None) -> Dict[str, Any]:
        """检查进程是否在运行"""
        query = self.trace.query().pid(pid)
        if time_range:
            query.time_range(*time_range)
            
        events = query.execute()
        if not events:
            return {'is_running': False}
            
        run_time = 0
        last_in = None
        switches = 0
        gaps = []
        
        switch_query = self.trace.query().event_type('sched_switch')
        if time_range:
            switch_query.time_range(*time_range)
            
        for event in switch_query.execute():
            if event.next_pid == pid:
                if last_in is None:
                    # 记录长时间未运行的 gap
                    if switches > 0 and (event.timestamp - last_out) > 0.1: # 阈值 100ms
                        gaps.append({'start': last_out, 'end': event.timestamp, 'duration': event.timestamp - last_out})
                last_in = event.timestamp
                switches += 1
            elif event.prev_pid == pid and last_in:
                run_time += (event.timestamp - last_in)
                last_out = event.timestamp
                last_in = None
                
        duration = (time_range[1] - time_range[0]) if time_range else self.trace.get_duration()
        
        return {
            'is_running': True,
            'run_time': run_time,
            'run_percent': (run_time / duration * 100) if duration > 0 else 0,
            'sched_count': switches,
            'avg_timeslice_ms': (run_time * 1000 / switches) if switches > 0 else 0,
            'gaps': gaps
        }

    def compare_cpu_time(self, *pids: int) -> Dict[int, Dict[str, Any]]:
        """比较多个进程的 CPU 时间占用"""
        res = {}
        for pid in pids:
            stats = self.check_process_running(pid)
            res[pid] = {
                'time': stats.get('run_time', 0),
                'percent': stats.get('run_percent', 0)
            }
        return res

    def detect_time_gaps(self, pid: int = None, threshold_ms: float = 1.0) -> List[Dict[str, Any]]:
        """检测时间断层（用于发现"进程去哪了"）"""
        gaps = []
        last_event = None
        
        query = self.trace.query()
        if pid: query.pid(pid)
        
        for event in query.execute():
            if last_event:
                diff = (event.timestamp - last_event.timestamp) * 1000
                if diff >= threshold_ms:
                    # 分析这段时间内 CPU 在做什么
                    cpu_activity = self._analyze_cpu_activity(last_event.timestamp, event.timestamp, event.cpu)
                    
                    gaps.append({
                        'last_line_no': last_event.line_no,
                        'next_line_no': event.line_no,
                        'pid': pid or event.pid,
                        'comm': event.task,
                        'gap_start': last_event.timestamp,
                        'gap_end': event.timestamp,
                        'duration_ms': diff,
                        'last_seen': str(last_event),
                        'next_seen': str(event),
                        'cpu_activity': cpu_activity
                    })
            last_event = event
        return gaps

    def _analyze_cpu_activity(self, start: float, end: float, cpu: int) -> Dict[str, Any]:
        """分析指定时间内指定 CPU 的活动"""
        query = self.trace.query().cpu(cpu).time_range(start, end)
        events = query.execute()
        
        if not events:
            return {'dominant_context': 'unknown', 'processes': []}
            
        contexts = {}
        processes = set()
        for e in events:
            ctx = 'idle' if e.pid == 0 else 'kernel' if e.task.startswith('kworker') else 'user'
            contexts[ctx] = contexts.get(ctx, 0) + 1
            if e.pid != 0: processes.add(e.task)
            
        dominant = max(contexts, key=contexts.get) if contexts else 'unknown'
        return {
            'dominant_context': dominant,
            'processes': list(processes)[:5]
        }


    def get_process_scheduling_stats(self, comm: str = None, pid: int = None) -> Dict[str, Any]:
        """获取特定进程的调度统计"""
        query = self.trace.query()
        if comm:
            query.comm(comm)
        if pid:
            query.pid(pid)
            
        result = query.event_type('sched_switch').execute()
        
        if not result:
            return {}
            
        switches = 0
        total_runtime = 0
        last_in_ts = None
        
        for event in result:
            # 如果是切入该进程
            if (comm and event.next_comm == comm) or (pid and event.next_pid == pid):
                last_in_ts = event.timestamp
                switches += 1
            # 如果是切出该进程
            elif (comm and event.prev_comm == comm) or (pid and event.prev_pid == pid):
                if last_in_ts:
                    total_runtime += (event.timestamp - last_in_ts)
                    last_in_ts = None
                    
        return {
            'comm': comm or result[0].task,
            'pid': pid or result[0].pid,
            'switch_count': switches,
            'total_runtime_ms': total_runtime * 1000,
            'avg_timeslice_ms': (total_runtime * 1000 / switches) if switches > 0 else 0
        }
