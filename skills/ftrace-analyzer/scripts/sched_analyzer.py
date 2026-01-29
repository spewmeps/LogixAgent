#!/usr/bin/env python3
"""
ftrace 调度分析器
专注于调度延迟、上下文切换、抢占等调度相关分析
"""

import sys
import argparse
import re
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Optional
import json


class ThreadState:
    """线程状态跟踪"""
    RUNNABLE = 'R'  # 可运行但未运行
    RUNNING = 'RUN'  # 正在运行
    SLEEPING = 'S'  # 睡眠
    UNINTERRUPTIBLE = 'D'  # 不可中断睡眠
    ZOMBIE = 'Z'  # 僵尸
    
    def __init__(self, pid: int, comm: str):
        self.pid = pid
        self.comm = comm
        self.state = None
        self.last_state_time = 0
        self.cpu = -1
        
        # 统计数据
        self.runnable_times = []  # (开始时间, 持续时间)
        self.running_times = []
        self.sleep_times = []
        self.sched_latencies = []  # runnable -> running 的延迟
        self.preemption_count = 0
        self.wakeup_count = 0
        self.context_switches = 0


class SchedAnalyzer:
    """调度分析器"""
    
    def __init__(self):
        self.threads: Dict[int, ThreadState] = {}
        self.cpu_timeline: Dict[int, List] = defaultdict(list)
        self.events = []
        
        # 调度切换事件解析
        # prev_comm=task prev_pid=123 prev_prio=120 prev_state=S ==>
        # next_comm=task next_pid=456 next_prio=120
        self.sched_switch_pattern = re.compile(
            r'prev_comm=(?P<prev_comm>.+?)\s+prev_pid=(?P<prev_pid>\d+)\s+'
            r'prev_prio=(?P<prev_prio>\d+)\s+prev_state=(?P<prev_state>\S+)\s+==>\s+'
            r'next_comm=(?P<next_comm>.+?)\s+next_pid=(?P<next_pid>\d+)\s+'
            r'next_prio=(?P<next_prio>\d+)'
        )
        
        # wakeup 事件解析
        # comm=task pid=123 prio=120 target_cpu=000
        self.sched_wakeup_pattern = re.compile(
            r'comm=(?P<comm>.+?)\s+pid=(?P<pid>\d+)\s+prio=(?P<prio>\d+)'
        )
    
    def get_or_create_thread(self, pid: int, comm: str = '') -> ThreadState:
        """获取或创建线程状态"""
        if pid not in self.threads:
            self.threads[pid] = ThreadState(pid, comm)
        return self.threads[pid]
    
    def parse_sched_switch(self, timestamp: float, cpu: int, details: str):
        """解析调度切换事件"""
        match = self.sched_switch_pattern.search(details)
        if not match:
            return
        
        data = match.groupdict()
        prev_pid = int(data['prev_pid'])
        next_pid = int(data['next_pid'])
        prev_state = data['prev_state']
        
        # 处理切出的线程
        prev_thread = self.get_or_create_thread(prev_pid, data['prev_comm'])
        if prev_thread.state == ThreadState.RUNNING:
            duration = timestamp - prev_thread.last_state_time
            prev_thread.running_times.append((prev_thread.last_state_time, duration))
        
        # 更新状态
        if 'R' in prev_state:
            # 被抢占，仍然 runnable
            prev_thread.state = ThreadState.RUNNABLE
            prev_thread.preemption_count += 1
        elif 'S' in prev_state or 'D' in prev_state:
            # 主动睡眠
            prev_thread.state = ThreadState.SLEEPING
        
        prev_thread.last_state_time = timestamp
        prev_thread.context_switches += 1
        
        # 处理切入的线程
        next_thread = self.get_or_create_thread(next_pid, data['next_comm'])
        
        # 如果之前是 runnable，计算调度延迟
        if next_thread.state == ThreadState.RUNNABLE:
            latency = timestamp - next_thread.last_state_time
            next_thread.sched_latencies.append(latency)
        
        next_thread.state = ThreadState.RUNNING
        next_thread.last_state_time = timestamp
        next_thread.cpu = cpu
        next_thread.context_switches += 1
        
        # 记录 CPU 时间线
        self.cpu_timeline[cpu].append({
            'timestamp': timestamp,
            'prev_pid': prev_pid,
            'prev_comm': data['prev_comm'],
            'next_pid': next_pid,
            'next_comm': data['next_comm']
        })
    
    def parse_sched_wakeup(self, timestamp: float, details: str):
        """解析唤醒事件"""
        match = self.sched_wakeup_pattern.search(details)
        if not match:
            return
        
        data = match.groupdict()
        pid = int(data['pid'])
        
        thread = self.get_or_create_thread(pid, data['comm'])
        thread.state = ThreadState.RUNNABLE
        thread.last_state_time = timestamp
        thread.wakeup_count += 1
    
    def analyze_file(self, filepath: str, filters: Dict = None):
        """分析 ftrace 文件"""
        filters = filters or {}
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                try:
                    # 匹配 ftrace 格式
                    # task-pid [cpu] irqs... timestamp: event_type: details
                    # 示例: swapper/5-0 [005] d.... 7541.834045: sched_switch: ...
                    pattern = re.compile(
                        r'^\s*.*-(?P<pid>\d+)\s+'
                        r'\[(?P<cpu>\d+)\]\s+'
                        r'(?P<irqs>[\w.]{5})\s+'
                        r'(?P<timestamp>[\d.]+):\s+'
                        r'(?P<event_type>\w+):\s+'
                        r'(?P<details>.+)$'
                    )
                    match = pattern.match(line)
                    if not match:
                        continue
                    
                    data = match.groupdict()
                    timestamp = float(data['timestamp'])
                    cpu = int(data['cpu'])
                    event_type = data['event_type']
                    details = data['details']
                    
                    # 应用过滤器
                    if filters.get('cpu') is not None and cpu != filters['cpu']:
                        continue
                    if filters.get('time_range'):
                        start, end = filters['time_range']
                        if not (start <= timestamp <= end):
                            continue
                    
                    # 解析关键事件
                    if event_type == 'sched_switch':
                        self.parse_sched_switch(timestamp, cpu, details)
                    elif event_type in ['sched_wakeup', 'sched_wakeup_new']:
                        self.parse_sched_wakeup(timestamp, details)
                
                except (ValueError, IndexError):
                    continue
    
    def get_thread_report(self, pid: int = None, comm: str = None) -> Dict:
        """生成线程报告"""
        if pid:
            threads = [self.threads.get(pid)]
        elif comm:
            threads = [t for t in self.threads.values() if comm in t.comm]
        else:
            threads = list(self.threads.values())
        
        reports = []
        for thread in threads:
            if not thread:
                continue
            
            # 计算统计数据
            latencies = thread.sched_latencies
            running_times = [d for _, d in thread.running_times]
            
            report = {
                'pid': thread.pid,
                'comm': thread.comm,
                'context_switches': thread.context_switches,
                'preemptions': thread.preemption_count,
                'wakeups': thread.wakeup_count,
                'sched_latency': {
                    'count': len(latencies),
                    'min_ms': min(latencies) * 1000 if latencies else 0,
                    'max_ms': max(latencies) * 1000 if latencies else 0,
                    'avg_ms': (sum(latencies) / len(latencies) * 1000) if latencies else 0,
                },
                'running_time': {
                    'count': len(running_times),
                    'total_ms': sum(running_times) * 1000,
                    'avg_ms': (sum(running_times) / len(running_times) * 1000) if running_times else 0,
                }
            }
            reports.append(report)
        
        return reports
    
    def print_report(self, reports: List[Dict], format_type: str = 'text'):
        """打印报告"""
        if format_type == 'json':
            print(json.dumps(reports, indent=2, ensure_ascii=False))
            return
        
        print("\n" + "=" * 80)
        print("调度分析报告")
        print("=" * 80)
        
        for report in reports:
            print(f"\n进程: {report['comm']} (PID: {report['pid']})")
            print("-" * 80)
            
            print(f"\n基本统计:")
            print(f"  上下文切换次数: {report['context_switches']:,}")
            print(f"  被抢占次数:     {report['preemptions']:,}")
            print(f"  唤醒次数:       {report['wakeups']:,}")
            
            lat = report['sched_latency']
            if lat['count'] > 0:
                print(f"\n调度延迟 (runnable → running):")
                print(f"  样本数:   {lat['count']:,}")
                print(f"  最小值:   {lat['min_ms']:.3f} ms")
                print(f"  最大值:   {lat['max_ms']:.3f} ms")
                print(f"  平均值:   {lat['avg_ms']:.3f} ms")
                
                # 延迟分级警告
                if lat['max_ms'] > 100:
                    print(f"  ⚠️  警告: 存在超过 100ms 的严重调度延迟！")
                elif lat['max_ms'] > 10:
                    print(f"  ⚠️  警告: 存在超过 10ms 的明显调度延迟")
            
            run = report['running_time']
            if run['count'] > 0:
                print(f"\n运行时间统计:")
                print(f"  运行片段数: {run['count']:,}")
                print(f"  总运行时间: {run['total_ms']:.3f} ms")
                print(f"  平均时间片: {run['avg_ms']:.3f} ms")


def main():
    parser = argparse.ArgumentParser(
        description='ftrace 调度分析器',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('logfile', help='ftrace 日志文件')
    parser.add_argument('--thread', type=str, metavar='NAME',
                        help='分析特定线程（按名称匹配）')
    parser.add_argument('--pid', type=int, metavar='PID',
                        help='分析特定进程 PID')
    parser.add_argument('--cpu', type=int, metavar='N',
                        help='只分析特定 CPU')
    parser.add_argument('--window', type=str, metavar='START,END',
                        help='时间窗口（秒）')
    parser.add_argument('--latency-threshold', type=float, metavar='MS',
                        help='只报告超过阈值的延迟（毫秒）')
    parser.add_argument('--report-format', choices=['text', 'json'], 
                        default='text', help='报告格式')
    parser.add_argument('--summary', action='store_true',
                        help='显示所有线程的概要')
    
    args = parser.parse_args()
    
    # 构建过滤器
    filters = {}
    if args.cpu is not None:
        filters['cpu'] = args.cpu
    if args.window:
        try:
            start, end = map(float, args.window.split(','))
            filters['time_range'] = (start, end)
        except ValueError:
            print("错误: 时间窗口格式应为 '开始,结束'", file=sys.stderr)
            return 1
    
    # 分析
    analyzer = SchedAnalyzer()
    print(f"正在分析 {args.logfile}...", file=sys.stderr)
    analyzer.analyze_file(args.logfile, filters)
    
    # 生成报告
    reports = analyzer.get_thread_report(
        pid=args.pid,
        comm=args.thread
    )
    
    # 应用延迟阈值过滤
    if args.latency_threshold:
        threshold_ms = args.latency_threshold
        reports = [r for r in reports 
                   if r['sched_latency']['max_ms'] >= threshold_ms]
    
    # 输出报告
    if not reports:
        print("没有找到匹配的线程或数据", file=sys.stderr)
        return 1
    
    analyzer.print_report(reports, args.report_format)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
