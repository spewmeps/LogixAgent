import os
import re
import mmap
import pickle
from typing import List, Dict, Tuple, Optional, Any
from .ftrace_models import Event

class TraceFile:
    """
    Ftrace 日志文件的总接口
    提供文件元信息、索引构建和查询入口
    """
    
    # 匹配 ftrace 标准格式的正则
    PATTERN = re.compile(
        r'^\s*(?P<task>[\w\s/:.()<>!@#$%-]+?)-(?P<pid>\d+)\s+'
        r'\[(?P<cpu>\d+)\]\s+'
        r'(?P<irqs>[\w.]{5})\s+'
        r'(?P<timestamp>[\d.]+):\s+'
        r'(?P<event_type>\w+):\s+'
        r'(?P<details>.+)$'
    )
    
    # 匹配 sched_switch 详情的正则
    SCHED_SWITCH_PATTERN = re.compile(
        r'prev_comm=(?P<prev_comm>.+?) prev_pid=(?P<prev_pid>\d+) prev_prio=(?P<prev_prio>\d+) prev_state=(?P<prev_state>\S+) ==> next_comm=(?P<next_comm>.+?) next_pid=(?P<next_pid>\d+) next_prio=(?P<next_prio>\d+)'
    )

    def __init__(self, filepath: str, 
                 index_by: List[str] = ['timestamp', 'cpu', 'pid'],
                 lazy_load: bool = True):
        self.filepath = os.path.abspath(filepath)
        self.index_path = self.filepath + ".index"
        self._info = {}
        self._index = None
        self._lazy_load = lazy_load
        self._index_by = index_by
        
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Log file not found: {self.filepath}")
            
        if not lazy_load:
            self.build_index()

    def info(self) -> Dict[str, Any]:
        """获取文件元信息（快速，不解析全部内容）"""
        if not self._info:
            stats = os.stat(self.filepath)
            start, end = self.get_time_range()
            
            # 快速估算行数 (文件大小 / 平均行宽 ~100 字节)
            line_count_est = stats.st_size // 100
            
            # 获取一些基本统计信息（如果已索引则更快）
            event_types = set()
            cpus = set()
            pids = set()
            
            # 仅在需要时或已索引时获取精确统计
            if self.has_index():
                # 遍历一小部分样本获取事件类型
                sample_count = 0
                for event in self.iter_events():
                    event_types.add(event.event_type)
                    cpus.add(event.cpu)
                    pids.add(event.pid)
                    sample_count += 1
                    if sample_count > 1000: break
            
            self._info = {
                'filepath': self.filepath,
                'file_size': f"{stats.st_size / (1024*1024):.2f} MB",
                'line_count': line_count_est,
                'time_range': {
                    'start': start,
                    'end': end,
                    'duration': (end - start) if start and end else 0
                },
                'event_types': list(event_types) or ['unknown'],
                'cpu_count': len(cpus) or 'unknown',
                'process_count': len(pids) or 'unknown',
                'indexed': self.has_index()
            }
        return self._info

    def summary(self) -> str:
        """返回友好的文本摘要"""
        info = self.info()
        tr = info['time_range']
        
        if tr['start'] is None:
            return f"Ftrace 日志摘要: {os.path.basename(info['filepath'])} (空或无有效事件)"
            
        return f"""
Ftrace 日志摘要
===============
文件: {os.path.basename(info['filepath'])} ({info['file_size']})
时间范围: {tr['start']:.3f} - {tr['end']:.3f} ({tr['duration']:.2f} 秒)
事件数: ~{info['line_count']:,} 行
CPU 数: {info['cpu_count']}
进程数: {info['process_count']}
事件类型: {', '.join(info['event_types'][:5])}{'...' if len(info['event_types']) > 5 else ''}
索引: {'✓' if info['indexed'] else '✗'} ({', '.join(self._index_by)})
"""

    def get_duration(self) -> float:
        """获取总时长（秒）"""
        return self.info()['time_range']['duration']

    def get_event_count(self) -> int:
        """获取事件总数（精确值，需要扫描）"""
        count = 0
        for _ in self.iter_events():
            count += 1
        return count

    def get_cpus(self) -> List[int]:
        """获取涉及的 CPU 列表"""
        cpus = set()
        for event in self.iter_events():
            cpus.add(event.cpu)
        return sorted(list(cpus))

    def get_processes(self) -> List[Dict[str, Any]]:
        """获取所有进程信息"""
        procs = {}
        for event in self.iter_events():
            if event.pid not in procs:
                procs[event.pid] = {'pid': event.pid, 'comm': event.task}
        return sorted(list(procs.values()), key=lambda x: x['pid'])

    def get_process_types(self) -> Dict[str, List[Dict[str, Any]]]:
        """按类型分组返回进程"""
        procs = self.get_processes()
        types = {
            'user': [],
            'kernel_thread': [],
            'idle': [],
            'irq': [],
            'softirq': []
        }
        for p in procs:
            if p['pid'] == 0:
                types['idle'].append(p)
            elif p['comm'].startswith('kworker') or 'softirq' in p['comm']:
                types['kernel_thread'].append(p)
            else:
                types['user'].append(p)
        return types

    def get_time_range(self) -> Tuple[Optional[float], Optional[float]]:
        """通过读取文件头尾快速获取时间范围"""
        start_ts = None
        end_ts = None
        
        # 找开始时间
        with open(self.filepath, 'r') as f:
            for line in f:
                match = self.PATTERN.match(line)
                if match:
                    start_ts = float(match.group('timestamp'))
                    break
        
        # 找结束时间 (从末尾往前找)
        with open(self.filepath, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            chunk_size = min(size, 4096)
            f.seek(size - chunk_size)
            chunk = f.read(chunk_size).decode('utf-8', errors='ignore')
            lines = chunk.splitlines()
            for line in reversed(lines):
                match = self.PATTERN.match(line)
                if match:
                    end_ts = float(match.group('timestamp'))
                    break
                    
        return start_ts, end_ts

    def build_index(self, force: bool = False):
        """构建时间戳到文件偏移的索引"""
        if not force and self.has_index():
            with open(self.index_path, 'rb') as f:
                self._index = pickle.load(f)
            return

        print(f"Building index for {self.filepath}...")
        index = []
        
        with open(self.filepath, 'r') as f:
            offset = 0
            line_no = 0
            for line in f:
                line_no += 1
                match = self.PATTERN.match(line)
                if match:
                    ts = float(match.group('timestamp'))
                    if not index or ts - index[-1][0] >= 0.1:
                        index.append((ts, offset, line_no))
                offset += len(line.encode('utf-8'))
        
        self._index = index
        with open(self.index_path, 'wb') as f:
            pickle.dump(index, f)
        print("Index built.")

    def has_index(self) -> bool:
        return os.path.exists(self.index_path)

    def parse_line(self, line: str, line_no: Optional[int] = None) -> Optional[Event]:
        match = self.PATTERN.match(line)
        if not match:
            return None
            
        data = match.groupdict()
        event = Event(
            task=data['task'],
            pid=int(data['pid']),
            cpu=int(data['cpu']),
            irqs=data['irqs'],
            timestamp=float(data['timestamp']),
            event_type=data['event_type'],
            details=data['details'],
            raw_line=line,
            line_no=line_no
        )
        
        # 解析 sched_switch
        if event.event_type == 'sched_switch':
            m = self.SCHED_SWITCH_PATTERN.search(event.details)
            if m:
                d = m.groupdict()
                event.prev_comm = d['prev_comm']
                event.prev_pid = int(d['prev_pid'])
                event.prev_prio = int(d['prev_prio'])
                event.prev_state = d['prev_state']
                event.next_comm = d['next_comm']
                event.next_pid = int(d['next_pid'])
                event.next_prio = int(d['next_prio'])
                
        return event

    def query(self):
        from .ftrace_query import QueryBuilder
        return QueryBuilder(self)

    def iter_events(self, start_ts: float = None, end_ts: float = None):
        """流式迭代事件，利用索引加速"""
        start_offset = 0
        start_line_no = 1
        if start_ts and self._index:
            import bisect
            idx = bisect.bisect_left(self._index, (start_ts, 0))
            if idx > 0:
                entry = self._index[idx-1]
                start_offset = entry[1]
                start_line_no = entry[2] if len(entry) > 2 else None

        with open(self.filepath, 'r') as f:
            if start_offset > 0:
                f.seek(start_offset)
            
            current_line_no = start_line_no or 1
            for line in f:
                event = self.parse_line(line, current_line_no if start_line_no is not None else None)
                if not event:
                    continue
                
                if start_ts and event.timestamp < start_ts:
                    continue
                if end_ts and event.timestamp > end_ts:
                    break
                    
                yield event
                current_line_no += 1
