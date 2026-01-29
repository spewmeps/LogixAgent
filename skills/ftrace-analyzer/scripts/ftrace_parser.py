#!/usr/bin/env python3
"""
ftrace 日志核心解析器
支持大文件流式处理，避免内存溢出
"""

import sys
import re
import argparse
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional
import json

class FtraceEvent:
    """ftrace 事件数据结构"""
    def __init__(self, timestamp: float, cpu: int, task: str, pid: int, 
                 event_type: str, details: str):
        self.timestamp = timestamp
        self.cpu = cpu
        self.task = task
        self.pid = pid
        self.event_type = event_type
        self.details = details
    
    def __repr__(self):
        return (f"[{self.timestamp:.6f}] CPU{self.cpu} {self.task}-{self.pid} "
                f"{self.event_type}: {self.details}")


class FtraceParser:
    """高效的 ftrace 日志解析器"""
    
    # ftrace 典型格式：
    # task-pid [cpu] irqs-off... timestamp: event_type: details
    # 示例: kworker/0:1H-234   [000] d.... 12345.678901: sched_switch: prev_comm=...
    PATTERN = re.compile(
        r'^\s*(?P<task>[\w\s/:.()-]+?)-(?P<pid>\d+)\s+'
        r'\[(?P<cpu>\d+)\]\s+'
        r'(?P<irqs>[\w.]{5})\s+'
        r'(?P<timestamp>[\d.]+):\s+'
        r'(?P<event_type>\w+):\s+'
        r'(?P<details>.+)$'
    )
    
    def __init__(self):
        self.stats = {
            'total_events': 0,
            'event_types': Counter(),
            'cpus': set(),
            'pids': set(),
            'time_range': [float('inf'), 0],
            'parse_errors': 0
        }
    
    def parse_line(self, line: str) -> Optional[FtraceEvent]:
        """解析单行 ftrace 日志"""
        match = self.PATTERN.match(line)
        if not match:
            self.stats['parse_errors'] += 1
            return None
        
        data = match.groupdict()
        timestamp = float(data['timestamp'])
        cpu = int(data['cpu'])
        pid = int(data['pid'])
        
        # 更新统计信息
        self.stats['total_events'] += 1
        self.stats['event_types'][data['event_type']] += 1
        self.stats['cpus'].add(cpu)
        self.stats['pids'].add(pid)
        self.stats['time_range'][0] = min(self.stats['time_range'][0], timestamp)
        self.stats['time_range'][1] = max(self.stats['time_range'][1], timestamp)
        
        return FtraceEvent(
            timestamp=timestamp,
            cpu=cpu,
            task=data['task'].strip(),
            pid=pid,
            event_type=data['event_type'],
            details=data['details']
        )
    
    def parse_file_streaming(self, filepath: str, filters: Dict = None):
        """流式解析文件（不一次性加载到内存）"""
        filters = filters or {}
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                event = self.parse_line(line)
                if not event:
                    continue
                
                # 应用过滤器
                if filters.get('cpu') is not None and event.cpu != filters['cpu']:
                    continue
                if filters.get('pid') is not None and event.pid != filters['pid']:
                    continue
                if filters.get('event_type') and event.event_type != filters['event_type']:
                    continue
                if filters.get('time_range'):
                    start, end = filters['time_range']
                    if not (start <= event.timestamp <= end):
                        continue
                
                yield event
    
    def print_summary(self):
        """打印日志概要"""
        print("\n" + "=" * 70)
        print("ftrace 日志分析摘要")
        print("=" * 70)
        
        if self.stats['time_range'][0] != float('inf'):
            duration = self.stats['time_range'][1] - self.stats['time_range'][0]
            print(f"\n时间范围:")
            print(f"  起始: {self.stats['time_range'][0]:.6f}s")
            print(f"  结束: {self.stats['time_range'][1]:.6f}s")
            print(f"  持续: {duration:.6f}s ({duration * 1000:.2f}ms)")
        
        print(f"\n基本统计:")
        print(f"  总事件数: {self.stats['total_events']:,}")
        print(f"  CPU 数量: {len(self.stats['cpus'])}")
        print(f"  进程数量: {len(self.stats['pids'])}")
        print(f"  解析错误: {self.stats['parse_errors']}")
        
        print(f"\n事件类型分布 (Top 10):")
        for event_type, count in self.stats['event_types'].most_common(10):
            percentage = (count / self.stats['total_events']) * 100
            print(f"  {event_type:25s}: {count:8,} ({percentage:5.2f}%)")
        
        if self.stats['cpus']:
            print(f"\nCPU 使用:")
            for cpu in sorted(self.stats['cpus']):
                print(f"  CPU {cpu}")
        
        print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='ftrace 日志解析器 - 高效处理大文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 查看日志概要
  %(prog)s trace.txt --summary
  
  # 过滤特定 CPU
  %(prog)s trace.txt --filter-cpu 0 --output cpu0.txt
  
  # 过滤特定进程
  %(prog)s trace.txt --filter-pid 1234 --output process.txt
  
  # 时间范围过滤
  %(prog)s trace.txt --time-range 1000.5,1005.5 --output window.txt
  
  # 只看调度事件
  %(prog)s trace.txt --filter-event sched_switch --output sched.txt
        '''
    )
    
    parser.add_argument('logfile', help='ftrace 日志文件路径')
    parser.add_argument('--summary', action='store_true', 
                        help='只显示概要统计，不输出事件')
    parser.add_argument('--filter-cpu', type=int, metavar='N',
                        help='只处理指定 CPU 的事件')
    parser.add_argument('--filter-pid', type=int, metavar='PID',
                        help='只处理指定进程的事件')
    parser.add_argument('--filter-event', type=str, metavar='TYPE',
                        help='只处理指定类型的事件')
    parser.add_argument('--time-range', type=str, metavar='START,END',
                        help='时间范围过滤 (秒)')
    parser.add_argument('--output', '-o', type=str, metavar='FILE',
                        help='输出到文件而不是标准输出')
    parser.add_argument('--format', choices=['text', 'json'], default='text',
                        help='输出格式 (默认: text)')
    
    args = parser.parse_args()
    
    # 构建过滤器
    filters = {}
    if args.filter_cpu is not None:
        filters['cpu'] = args.filter_cpu
    if args.filter_pid is not None:
        filters['pid'] = args.filter_pid
    if args.filter_event:
        filters['event_type'] = args.filter_event
    if args.time_range:
        try:
            start, end = map(float, args.time_range.split(','))
            filters['time_range'] = (start, end)
        except ValueError:
            print(f"错误: 时间范围格式错误，应为 '开始,结束'", file=sys.stderr)
            return 1
    
    # 解析日志
    ftrace = FtraceParser()
    
    # 如果只需要概要，快速扫描
    if args.summary:
        for _ in ftrace.parse_file_streaming(args.logfile, filters):
            pass  # 只统计，不输出
        ftrace.print_summary()
        return 0
    
    # 输出过滤后的事件
    output_file = open(args.output, 'w') if args.output else sys.stdout
    
    try:
        event_count = 0
        for event in ftrace.parse_file_streaming(args.logfile, filters):
            if args.format == 'json':
                output_file.write(json.dumps({
                    'timestamp': event.timestamp,
                    'cpu': event.cpu,
                    'task': event.task,
                    'pid': event.pid,
                    'event_type': event.event_type,
                    'details': event.details
                }) + '\n')
            else:
                output_file.write(str(event) + '\n')
            event_count += 1
        
        # 输出统计到 stderr（以便管道操作时不干扰主输出）
        print(f"\n处理完成: 匹配 {event_count:,} 个事件", file=sys.stderr)
        if filters:
            print(f"应用的过滤器: {filters}", file=sys.stderr)
        
    finally:
        if args.output:
            output_file.close()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
