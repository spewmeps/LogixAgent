#!/usr/bin/env python3
"""
ftrace 因果链分析器
自动识别和构建事件间的因果关系
"""

import sys
import argparse
import re
from collections import defaultdict, deque
from typing import List, Dict, Tuple, Optional


class CausalEvent:
    """因果事件"""
    def __init__(self, timestamp: float, event_type: str, actor: str, 
                 action: str, target: str = None):
        self.timestamp = timestamp
        self.event_type = event_type
        self.actor = actor  # 执行者（进程/CPU/中断）
        self.action = action  # 动作
        self.target = target  # 目标（可选）
        self.causality_score = 0.0  # 与受害者的因果相关性
    
    def __repr__(self):
        return (f"[{self.timestamp:.6f}] {self.actor} {self.action} "
                f"{self.target or ''}")


class CausalityAnalyzer:
    """因果关系分析器"""
    
    def __init__(self):
        self.events: List[CausalEvent] = []
        self.victim_events: List[CausalEvent] = []
        self.blocking_events: List[CausalEvent] = []
    
    def parse_event(self, line: str) -> Optional[CausalEvent]:
        """解析事件并提取因果信息"""
        parts = line.split(':', 3)
        if len(parts) < 4:
            return None
        
        try:
            header = parts[0]
            event_type = parts[2].strip()
            details = parts[3].strip()
            
            time_match = re.search(r'\[\d+\]\s+([\d.]+)', header)
            if not time_match:
                return None
            
            timestamp = float(time_match.group(1))
            
            # 提取执行者
            actor_match = re.search(r'^\s*([\w\s/:.()-]+?)-\d+', header)
            actor = actor_match.group(1).strip() if actor_match else "unknown"
            
            # 根据事件类型提取动作和目标
            action = event_type
            target = None
            
            if event_type == 'sched_switch':
                # prev -> next
                prev_match = re.search(r'prev_comm=(\S+)', details)
                next_match = re.search(r'next_comm=(\S+)', details)
                if prev_match and next_match:
                    action = f"切换: {prev_match.group(1)} -> {next_match.group(1)}"
                    target = next_match.group(1)
            
            elif 'wakeup' in event_type:
                # 唤醒目标进程
                comm_match = re.search(r'comm=(\S+)', details)
                if comm_match:
                    target = comm_match.group(1)
                    action = f"唤醒 {target}"
            
            elif 'irq' in event_type or 'softirq' in event_type:
                # 中断处理
                action = f"中断: {event_type}"
            
            return CausalEvent(timestamp, event_type, actor, action, target)
        
        except (ValueError, IndexError):
            return None
    
    def collect_events(self, filepath: str, victim_pid: int = None,
                       victim_comm: str = None, time_window: Tuple[float, float] = None):
        """收集事件并识别受害者"""
        
        print(f"正在收集事件...", file=sys.stderr)
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                event = self.parse_event(line)
                if not event:
                    continue
                
                # 应用时间窗口过滤
                if time_window:
                    start, end = time_window
                    if not (start <= event.timestamp <= end):
                        continue
                
                self.events.append(event)
                
                # 识别受害者事件
                is_victim = False
                if victim_pid:
                    # 通过 PID 匹配（需要从原始行提取）
                    pid_match = re.search(r'-(\d+)\s+\[', line)
                    if pid_match and int(pid_match.group(1)) == victim_pid:
                        is_victim = True
                
                if victim_comm and victim_comm in event.actor:
                    is_victim = True
                
                if victim_comm and event.target and victim_comm in event.target:
                    is_victim = True
                
                if is_victim:
                    self.victim_events.append(event)
        
        print(f"收集到 {len(self.events)} 个事件，"
              f"其中 {len(self.victim_events)} 个与受害者相关", file=sys.stderr)
    
    def analyze_causality(self):
        """分析因果关系"""
        
        if not self.victim_events:
            print("警告: 未找到受害者事件", file=sys.stderr)
            return
        
        print(f"\n正在分析因果关系...", file=sys.stderr)
        
        # 对每个受害者事件，找出可能的阻断者
        for victim_event in self.victim_events:
            victim_time = victim_event.timestamp
            
            # 查找受害者事件前的相关事件（时间窗口：前 100ms）
            window_start = victim_time - 0.1  # 100ms
            
            for event in self.events:
                if window_start <= event.timestamp < victim_time:
                    # 计算时间相关性（越接近，相关性越高）
                    time_diff = victim_time - event.timestamp
                    proximity_score = 1.0 / (time_diff + 0.001)  # 避免除零
                    
                    # 计算事件类型相关性
                    type_score = 0.0
                    if 'sched' in event.event_type:
                        type_score = 1.0  # 调度事件高度相关
                    elif 'irq' in event.event_type or 'softirq' in event.event_type:
                        type_score = 0.8  # 中断事件较相关
                    elif 'lock' in event.event_type:
                        type_score = 0.9  # 锁事件高度相关
                    else:
                        type_score = 0.3  # 其他事件低相关
                    
                    # 综合因果评分
                    event.causality_score = proximity_score * type_score
        
        # 找出高因果相关的阻断事件
        self.blocking_events = [
            e for e in self.events 
            if e.causality_score > 0.5 and e not in self.victim_events
        ]
        
        # 按因果分数排序
        self.blocking_events.sort(key=lambda e: e.causality_score, reverse=True)
        
        print(f"识别出 {len(self.blocking_events)} 个潜在阻断事件", file=sys.stderr)
    
    def build_causal_chain(self, max_length: int = 5) -> List[List[CausalEvent]]:
        """构建因果链"""
        
        chains = []
        
        for victim_event in self.victim_events[:10]:  # 限制分析前 10 个受害者事件
            chain = [victim_event]
            victim_time = victim_event.timestamp
            
            # 回溯寻找因果链
            current_time = victim_time
            
            for _ in range(max_length - 1):
                # 找最接近且高相关的前驱事件
                candidates = [
                    e for e in self.blocking_events
                    if e.timestamp < current_time
                    and current_time - e.timestamp < 0.1  # 100ms 窗口
                ]
                
                if not candidates:
                    break
                
                # 选择相关性最高的
                best = max(candidates, key=lambda e: e.causality_score)
                chain.insert(0, best)
                current_time = best.timestamp
            
            if len(chain) > 1:  # 只保留有意义的链
                chains.append(chain)
        
        return chains
    
    def print_analysis(self):
        """打印分析结果"""
        
        print("\n" + "=" * 100)
        print("因果链分析报告")
        print("=" * 100)
        
        # 1. 受害者概览
        print(f"\n### 受害者事件概览")
        print(f"共识别 {len(self.victim_events)} 个受害者事件\n")
        
        for event in self.victim_events[:5]:  # 显示前 5 个
            print(f"  [{event.timestamp:.6f}] {event.actor}: {event.action}")
        
        if len(self.victim_events) > 5:
            print(f"  ... 还有 {len(self.victim_events) - 5} 个事件")
        
        # 2. 主要阻断者
        print(f"\n### 主要阻断者 (Top 10)")
        print(f"{'时间':<15} {'因果分':<10} {'执行者':<20} {'动作':<40}")
        print("-" * 100)
        
        for event in self.blocking_events[:10]:
            print(f"{event.timestamp:<15.6f} {event.causality_score:<10.2f} "
                  f"{event.actor:<20} {event.action:<40}")
        
        # 3. 因果链
        chains = self.build_causal_chain()
        
        if chains:
            print(f"\n### 因果链分析")
            print(f"识别出 {len(chains)} 条因果链\n")
            
            for i, chain in enumerate(chains[:5], 1):  # 显示前 5 条
                print(f"因果链 #{i}:")
                
                for j, event in enumerate(chain):
                    prefix = "  └─>" if j == len(chain) - 1 else "  ├─>"
                    marker = " [受害者]" if event in self.victim_events else ""
                    
                    time_ms = event.timestamp * 1000
                    print(f"{prefix} [{time_ms:10.3f}ms] {event.actor}: "
                          f"{event.action}{marker}")
                
                # 计算总延迟
                if len(chain) > 1:
                    total_delay = (chain[-1].timestamp - chain[0].timestamp) * 1000
                    print(f"       总延迟: {total_delay:.3f}ms\n")
        
        # 4. 结论
        print(f"\n### 分析结论")
        
        if self.blocking_events:
            top_blocker = self.blocking_events[0]
            print(f"\n最可能的阻断者:")
            print(f"  执行者: {top_blocker.actor}")
            print(f"  动作: {top_blocker.action}")
            print(f"  时间: {top_blocker.timestamp:.6f}s")
            print(f"  因果相关性: {top_blocker.causality_score:.2f}")
            
            # 统计阻断者类型
            blocker_types = defaultdict(int)
            for event in self.blocking_events[:20]:
                if 'irq' in event.event_type or 'softirq' in event.event_type:
                    blocker_types['中断'] += 1
                elif 'sched' in event.event_type:
                    blocker_types['调度'] += 1
                elif 'lock' in event.event_type:
                    blocker_types['锁'] += 1
                else:
                    blocker_types['其他'] += 1
            
            print(f"\n阻断类型分布:")
            for btype, count in sorted(blocker_types.items(), 
                                       key=lambda x: x[1], reverse=True):
                print(f"  {btype}: {count} 次")


def main():
    parser = argparse.ArgumentParser(
        description='ftrace 因果链分析器',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('logfile', help='ftrace 日志文件')
    parser.add_argument('--victim', type=str, metavar='NAME', required=True,
                        help='受害者线程名称')
    parser.add_argument('--window', type=str, metavar='START,END',
                        help='分析时间窗口（秒）')
    parser.add_argument('--min-correlation', type=float, metavar='SCORE',
                        default=0.5, help='最小相关性阈值（默认 0.5）')
    parser.add_argument('--max-chain-length', type=int, metavar='N',
                        default=5, help='最大因果链长度（默认 5）')
    
    args = parser.parse_args()
    
    # 解析时间窗口
    time_window = None
    if args.window:
        try:
            start, end = map(float, args.window.split(','))
            time_window = (start, end)
        except ValueError:
            print("错误: 时间窗口格式应为 '开始,结束'", file=sys.stderr)
            return 1
    
    # 分析
    analyzer = CausalityAnalyzer()
    analyzer.collect_events(
        args.logfile,
        victim_comm=args.victim,
        time_window=time_window
    )
    
    analyzer.analyze_causality()
    analyzer.print_analysis()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
