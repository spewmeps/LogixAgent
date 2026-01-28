#!/usr/bin/env python3
"""
ftrace 时间线分析器
生成目标线程的时间线视图，显示调度事件、中断、锁等上下文
"""

import sys
import argparse
import re
from collections import defaultdict
from typing import List, Dict, Optional


class TimelineEvent:
    """时间线事件"""
    def __init__(self, timestamp: float, event_type: str, description: str, 
                 cpu: int = -1, pid: int = -1):
        self.timestamp = timestamp
        self.event_type = event_type
        self.description = description
        self.cpu = cpu
        self.pid = pid


class TimelineAnalyzer:
    """时间线分析器"""
    
    def __init__(self):
        self.events: List[TimelineEvent] = []
        self.target_events: List[TimelineEvent] = []
        
    def parse_line(self, line: str) -> Optional[TimelineEvent]:
        """解析单行日志"""
        # 简化解析
        parts = line.split(':', 3)
        if len(parts) < 4:
            return None
        
        try:
            header = parts[0]
            event_type = parts[2].strip()
            details = parts[3].strip()
            
            # 提取时间戳、CPU、PID
            time_match = re.search(r'\[\d+\]\s+([\d.]+)', header)
            cpu_match = re.search(r'\[(\d+)\]', header)
            pid_match = re.search(r'-(\d+)\s+\[', header)
            
            if not time_match:
                return None
            
            timestamp = float(time_match.group(1))
            cpu = int(cpu_match.group(1)) if cpu_match else -1
            pid = int(pid_match.group(1)) if pid_match else -1
            
            return TimelineEvent(timestamp, event_type, details, cpu, pid)
        
        except (ValueError, IndexError):
            return None
    
    def collect_events(self, filepath: str, target_pid: int = None, 
                       target_comm: str = None, context_ms: float = 100):
        """收集相关事件"""
        
        print(f"正在收集事件...", file=sys.stderr)
        
        # 第一遍：找到目标线程的所有事件
        target_timestamps = []
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                event = self.parse_line(line)
                if not event:
                    continue
                
                # 判断是否是目标事件
                is_target = False
                if target_pid and event.pid == target_pid:
                    is_target = True
                elif target_comm:
                    # 从事件详情中提取进程名
                    if target_comm in event.description:
                        is_target = True
                
                if is_target:
                    target_timestamps.append(event.timestamp)
                    self.target_events.append(event)
        
        if not target_timestamps:
            print(f"警告: 未找到目标线程的事件", file=sys.stderr)
            return
        
        print(f"找到 {len(target_timestamps)} 个目标事件", file=sys.stderr)
        
        # 计算上下文时间窗口
        context_sec = context_ms / 1000.0
        time_windows = []
        for ts in target_timestamps:
            time_windows.append((ts - context_sec, ts + context_sec))
        
        # 第二遍：收集上下文事件
        print(f"正在收集上下文事件（±{context_ms}ms）...", file=sys.stderr)
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                event = self.parse_line(line)
                if not event:
                    continue
                
                # 检查是否在任何时间窗口内
                for start, end in time_windows:
                    if start <= event.timestamp <= end:
                        self.events.append(event)
                        break
        
        # 按时间排序
        self.events.sort(key=lambda e: e.timestamp)
        print(f"共收集 {len(self.events)} 个上下文事件", file=sys.stderr)
    
    def print_timeline(self, show_interrupts: bool = False, 
                       show_locks: bool = False):
        """打印时间线"""
        
        if not self.events:
            print("没有事件可显示")
            return
        
        print("\n" + "=" * 100)
        print("时间线分析")
        print("=" * 100)
        
        base_time = self.events[0].timestamp
        
        print(f"\n基准时间: {base_time:.6f}s")
        print(f"显示选项: 中断={show_interrupts}, 锁={show_locks}")
        print("\n时间线:")
        print("-" * 100)
        
        target_pids = {e.pid for e in self.target_events}
        
        for event in self.events:
            relative_time = (event.timestamp - base_time) * 1000  # 转换为 ms
            
            # 过滤非关键事件
            if not show_interrupts and 'irq' in event.event_type.lower():
                continue
            if not show_locks and 'lock' in event.event_type.lower():
                continue
            
            # 标记目标事件
            marker = ">>>" if event.pid in target_pids else "   "
            
            # 格式化输出
            print(f"{marker} [{relative_time:8.3f}ms] CPU{event.cpu:2d} "
                  f"{event.event_type:20s} {event.description[:70]}")
    
    def analyze_scheduling_path(self):
        """分析调度路径"""
        
        print("\n" + "=" * 100)
        print("调度路径分析")
        print("=" * 100)
        
        # 提取目标线程的状态变化
        sched_events = [e for e in self.target_events 
                        if 'sched' in e.event_type]
        
        if not sched_events:
            print("没有调度相关事件")
            return
        
        print(f"\n找到 {len(sched_events)} 个调度事件\n")
        
        # 分析 wakeup -> switch 延迟
        wakeup_time = None
        
        for event in sched_events:
            if 'wakeup' in event.event_type:
                wakeup_time = event.timestamp
                print(f"[唤醒] {event.timestamp:.6f}s - {event.description[:80]}")
            
            elif 'sched_switch' in event.event_type and wakeup_time:
                # 检查是否切换到目标进程
                if 'next_pid' in event.description:
                    latency = (event.timestamp - wakeup_time) * 1000
                    print(f"[切入] {event.timestamp:.6f}s - {event.description[:80]}")
                    print(f"  >>> 调度延迟: {latency:.3f}ms")
                    
                    if latency > 10:
                        print(f"  ⚠️  警告: 调度延迟超过 10ms!")
                    
                    wakeup_time = None
                else:
                    # 切换到其他进程
                    print(f"[切出] {event.timestamp:.6f}s - {event.description[:80]}")
    
    def generate_svg(self, output_file: str):
        """生成 SVG 时间线图"""
        
        if not self.events:
            print("没有事件可生成图表")
            return
        
        # 简单的 SVG 时间线生成
        width = 1200
        height = max(600, len(self.events) * 5)
        
        base_time = self.events[0].timestamp
        max_time = self.events[-1].timestamp
        time_range = max_time - base_time
        
        svg_lines = [
            f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">',
            '<rect width="100%" height="100%" fill="white"/>',
            f'<text x="10" y="20" font-size="16" font-weight="bold">ftrace 时间线</text>',
            f'<text x="10" y="40" font-size="12">时间范围: {time_range*1000:.3f}ms</text>',
        ]
        
        # 绘制时间线
        y_offset = 60
        target_pids = {e.pid for e in self.target_events}
        
        for i, event in enumerate(self.events):
            relative_time = event.timestamp - base_time
            x = 50 + (relative_time / time_range) * (width - 100)
            y = y_offset + i * 2
            
            # 目标事件用红色，其他用蓝色
            color = "red" if event.pid in target_pids else "blue"
            
            svg_lines.append(
                f'<circle cx="{x}" cy="{y}" r="2" fill="{color}" '
                f'title="{event.event_type}: {event.description[:50]}"/>'
            )
        
        svg_lines.append('</svg>')
        
        with open(output_file, 'w') as f:
            f.write('\n'.join(svg_lines))
        
        print(f"\nSVG 时间线已生成: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='ftrace 时间线分析器',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('logfile', help='ftrace 日志文件')
    parser.add_argument('--target', type=str, metavar='NAME',
                        help='目标线程名称')
    parser.add_argument('--pid', type=int, metavar='PID',
                        help='目标进程 PID')
    parser.add_argument('--context', type=float, metavar='MS', default=100,
                        help='上下文时间范围（毫秒，默认 100ms）')
    parser.add_argument('--show-interrupts', action='store_true',
                        help='显示中断事件')
    parser.add_argument('--show-locks', action='store_true',
                        help='显示锁事件')
    parser.add_argument('--output-svg', type=str, metavar='FILE',
                        help='生成 SVG 时间线图')
    
    args = parser.parse_args()
    
    if not args.target and not args.pid:
        print("错误: 必须指定 --target 或 --pid", file=sys.stderr)
        return 1
    
    # 分析
    analyzer = TimelineAnalyzer()
    analyzer.collect_events(
        args.logfile,
        target_pid=args.pid,
        target_comm=args.target,
        context_ms=args.context
    )
    
    # 输出时间线
    analyzer.print_timeline(
        show_interrupts=args.show_interrupts,
        show_locks=args.show_locks
    )
    
    # 分析调度路径
    analyzer.analyze_scheduling_path()
    
    # 生成 SVG
    if args.output_svg:
        analyzer.generate_svg(args.output_svg)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
