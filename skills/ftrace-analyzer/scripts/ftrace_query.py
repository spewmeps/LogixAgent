from typing import List, Dict, Any, Callable, Optional
from .ftrace_models import Event

class QueryResult:
    """查询结果容器"""
    def __init__(self, events: List[Event]):
        self._events = events

    def __len__(self) -> int:
        return len(self._events)

    def __getitem__(self, index):
        return self._events[index]

    def __iter__(self):
        return iter(self._events)

    @property
    def events(self) -> List[Event]:
        return self._events

    def summary(self) -> Dict[str, Any]:
        if not self._events:
            return {'count': 0}
            
        cpus = sorted(list(set(e.cpu for e in self._events)))
        pids = sorted(list(set(e.pid for e in self._events)))
        event_types = sorted(list(set(e.event_type for e in self._events)))
        
        # 状态分布
        states = {}
        for e in self._events:
            state = getattr(e, 'prev_state', 'unknown')
            states[state] = states.get(state, 0) + 1
            
        return {
            'count': len(self._events),
            'time_range': (self._events[0].timestamp, self._events[-1].timestamp),
            'cpus': cpus,
            'processes': pids,
            'event_types': event_types,
            'state_distribution': states
        }

    def describe(self) -> str:
        s = self.summary()
        if s['count'] == 0:
            return "No events found."
            
        states_str = ", ".join(f"{k}({v})" for k, v in s['state_distribution'].items())
        return f"""
查询结果摘要
===========
事件数: {s['count']:,}
时间范围: {s['time_range'][0]:.6f} - {s['time_range'][1]:.6f} ({s['time_range'][1] - s['time_range'][0]:.3f}s)
涉及 CPU: {s['cpus']}
涉及进程数: {len(s['processes'])}
状态分布: {states_str}
事件类型: {', '.join(s['event_types'])}
"""

    def filter(self, func: Callable[[Event], bool]) -> 'QueryResult':
        return QueryResult([e for e in self._events if func(e)])

    def by_cpu(self) -> Dict[int, List[Event]]:
        """按 CPU 分组"""
        res = {}
        for e in self._events:
            if e.cpu not in res:
                res[e.cpu] = []
            res[e.cpu].append(e)
        return res

    def by_process(self) -> Dict[int, List[Event]]:
        """按进程 ID 分组"""
        res = {}
        for e in self._events:
            if e.pid not in res:
                res[e.pid] = []
            res[e.pid].append(e)
        return res

    def by_state(self) -> Dict[str, List[Event]]:
        """按 prev_state 分组"""
        res = {}
        for e in self._events:
            state = getattr(e, 'prev_state', 'unknown')
            if state not in res:
                res[state] = []
            res[state].append(e)
        return res

    def timeline(self, bin_size: float = 0.001) -> Dict[str, Any]:
        """生成时间线视图"""
        if not self._events:
            return {'bins': [], 'counts': []}
        
        start = self._events[0].timestamp
        end = self._events[-1].timestamp
        num_bins = int((end - start) / bin_size) + 1
        
        bins = [start + i * bin_size for i in range(num_bins)]
        counts = [0] * num_bins
        events_per_bin = [[] for _ in range(num_bins)]
        
        for e in self._events:
            idx = int((e.timestamp - start) / bin_size)
            if 0 <= idx < num_bins:
                counts[idx] += 1
                events_per_bin[idx].append(e)
                
        return {
            'bins': bins,
            'counts': counts,
            'events_per_bin': events_per_bin
        }

    def to_list(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._events]

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_list(), indent=2)

    def to_csv(self, filepath: str = None) -> str:
        import csv
        import io
        
        output = io.StringIO()
        if self._events:
            writer = csv.DictWriter(output, fieldnames=self._events[0].to_dict().keys())
            writer.writeheader()
            for e in self._events:
                writer.writerow(e.to_dict())
        
        content = output.getvalue()
        if filepath:
            with open(filepath, 'w') as f:
                f.write(content)
        return content

    def to_text(self, format: str = 'table') -> str:
        """导出为文本格式"""
        if not self._events:
            return "No events."
        
        if format == 'raw':
            lines = []
            for e in self._events:
                if getattr(e, "line_no", None) is not None:
                    lines.append(f"{e.line_no}: {e.raw_line.strip()}")
                else:
                    lines.append(e.raw_line.strip())
            return "\n".join(lines)
        
        # Simple list format
        return "\n".join(str(e) for e in self._events)

class QueryBuilder:
    """查询构造器，支持链式调用"""
    def __init__(self, trace_file):
        self.trace_file = trace_file
        self._filters = []
        self._start_ts, self._end_ts = trace_file.get_time_range()
        self._limit = None
        self._order_by = None
        self._group_by = None
        self._ascending = True

    def time_range(self, start: float, end: float) -> 'QueryBuilder':
        self._start_ts = start
        self._end_ts = end
        return self

    def time_slice(self, duration: float, offset: float = 0) -> 'QueryBuilder':
        start, _ = self.trace_file.get_time_range()
        self._start_ts = (start or 0) + offset
        self._end_ts = self._start_ts + duration
        return self

    def around_time(self, timestamp: float, window: float = 0.1) -> 'QueryBuilder':
        self._start_ts = timestamp - window
        self._end_ts = timestamp + window
        return self

    def cpu(self, *cpus: int) -> 'QueryBuilder':
        cpus_set = set(cpus)
        self._filters.append(lambda e: e.cpu in cpus_set)
        return self

    def pid(self, *pids: int) -> 'QueryBuilder':
        pids_set = set(pids)
        self._filters.append(lambda e: e.pid in pids_set)
        return self

    def comm(self, *comms: str, pattern: str = None) -> 'QueryBuilder':
        import re
        if comms:
            comms_set = set(comms)
            self._filters.append(lambda e: e.task in comms_set)
        if pattern:
            prog = re.compile(pattern)
            self._filters.append(lambda e: prog.search(e.task))
        return self

    def process_type(self, *types: str) -> 'QueryBuilder':
        types_set = set(types)
        def filter_type(e):
            if 'idle' in types_set and e.pid == 0: return True
            if 'kernel_thread' in types_set and (e.task.startswith('kworker') or 'softirq' in e.task): return True
            if 'user' in types_set and e.pid != 0 and not (e.task.startswith('kworker') or 'softirq' in e.task): return True
            return False
        self._filters.append(filter_type)
        return self

    def prev_state(self, *states: str) -> 'QueryBuilder':
        states_set = set(states)
        self._filters.append(lambda e: getattr(e, 'prev_state', None) in states_set)
        return self

    def event_type(self, *types: str) -> 'QueryBuilder':
        types_set = set(types)
        self._filters.append(lambda e: e.event_type in types_set)
        return self

    def group_by(self, field: str) -> 'QueryBuilder':
        """设置分组字段"""
        self._group_by = field
        return self

    def order_by(self, field: str, ascending: bool = True) -> 'QueryBuilder':
        self._order_by = field
        self._ascending = ascending
        return self

    def limit(self, n: int) -> 'QueryBuilder':
        self._limit = n
        return self

    def execute(self) -> QueryResult:
        results = []
        for event in self.trace_file.iter_events(self._start_ts, self._end_ts):
            match = True
            for f in self._filters:
                if not f(event):
                    match = False
                    break
            
            if match:
                results.append(event)
                # 如果没有排序，可以直接 limit 优化
                if not self._order_by and self._limit and len(results) >= self._limit:
                    break
        
        if self._order_by:
            results.sort(key=lambda x: getattr(x, self._order_by, 0), reverse=not self._ascending)
            if self._limit:
                results = results[:self._limit]
                    
        return QueryResult(results)

    def count(self) -> int:
        count = 0
        for event in self.trace_file.iter_events(self._start_ts, self._end_ts):
            match = True
            for f in self._filters:
                if not f(event):
                    match = False
                    break
            if match:
                count += 1
        return count

    def first(self, n: int = 1) -> List[Event]:
        self._limit = n
        return self.execute().events

    def to_dataframe(self):
        """转换为 pandas DataFrame（如果已安装 pandas）"""
        try:
            import pandas as pd
            events = self.execute().events
            return pd.DataFrame([e.to_dict() for e in events])
        except ImportError:
            print("Error: pandas is not installed. Please install it to use to_dataframe().")
            return None
