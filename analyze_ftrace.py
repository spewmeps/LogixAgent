#!/usr/bin/env python3
"""
ftrace 日志分析脚本
用于分析 sched_switch 事件并统计各种指标
"""

import re
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

def parse_sched_switch(line: str) -> Dict[str, str]:
    """解析 sched_switch 事件行"""
    result = {}
    
    # 提取 prev_comm
    prev_match = re.search(r'prev_comm=([^\s]+)', line)
    if prev_match:
        result['prev_comm'] = prev_match.group(1)
    
    # 提取 prev_pid
    prev_pid_match = re.search(r'prev_pid=(\d+)', line)
    if prev_pid_match:
        result['prev_pid'] = prev_pid_match.group(1)
    
    # 提取 prev_state
    prev_state_match = re.search(r'prev_state=([A-Z])', line)
    if prev_state_match:
        result['prev_state'] = prev_state_match.group(1)
    
    # 提取 next_comm
    next_match = re.search(r'next_comm=([^\s]+)', line)
    if next_match:
        result['next_comm'] = next_match.group(1)
    
    # 提取 next_pid
    next_pid_match = re.search(r'next_pid=(\d+)', line)
    if next_pid_match:
        result['next_pid'] = next_pid_match.group(1)
    
    # 提取 CPU
    cpu_match = re.search(r'\[(\d+)\]', line)
    if cpu_match:
        result['cpu'] = cpu_match.group(1)
    
    # 提取时间戳
    timestamp_match = re.search(r'\s(\d+\.\d+):\s', line)
    if timestamp_match:
        result['timestamp'] = float(timestamp_match.group(1))
    
    return result

def analyze_ftrace_log(file_path: str):
    """分析 ftrace 日志文件"""
    
    print(f"正在分析 ftrace 日志文件: {file_path}")
    print("=" * 80)
    
    # 初始化计数器
    next_comm_counter = Counter()
    prev_comm_counter = Counter()
    cpu_counter = Counter()
    prev_state_counter = Counter()
    d_state_processes = Counter()
    virtualization_processes = Counter()
    
    total_events = 0
    virtualization_keywords = ['kvm', 'qemu', 'vhost']
    
    try:
        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if 'sched_switch:' in line:
                    total_events += 1
                    
                    # 解析事件
                    event = parse_sched_switch(line)
                    
                    if not event:
                        continue
                    
                    # 统计 next_comm
                    if 'next_comm' in event:
                        next_comm_counter[event['next_comm']] += 1
                    
                    # 统计 prev_comm
                    if 'prev_comm' in event:
                        prev_comm_counter[event['prev_comm']] += 1
                    
                    # 统计 CPU
                    if 'cpu' in event:
                        cpu_counter[event['cpu']] += 1
                    
                    # 统计 prev_state
                    if 'prev_state' in event:
                        prev_state_counter[event['prev_state']] += 1
                        
                        # 检查 D 状态（不可中断睡眠）
                        if event['prev_state'] == 'D' and 'prev_comm' in event:
                            d_state_processes[event['prev_comm']] += 1
                    
                    # 检查虚拟化相关进程
                    if 'prev_comm' in event:
                        for keyword in virtualization_keywords:
                            if keyword in event['prev_comm'].lower():
                                virtualization_processes[event['prev_comm']] += 1
                    
                    if 'next_comm' in event:
                        for keyword in virtualization_keywords:
                            if keyword in event['next_comm'].lower():
                                virtualization_processes[event['next_comm']] += 1
                    
                    # 显示进度
                    if total_events % 10000 == 0:
                        print(f"已处理 {total_events} 个调度事件...")
    
    except FileNotFoundError:
        print(f"错误: 文件 {file_path} 不存在")
        return
    except Exception as e:
        print(f"读取文件时出错: {e}")
        return
    
    print(f"\n分析完成！总共处理了 {total_events} 个 sched_switch 事件")
    print("=" * 80)
    
    # 1. 统计 next_comm 频率
    print("\n1. sched_switch 事件中 next_comm（下一个要运行的进程）的出现频率:")
    print("-" * 60)
    print(f"{'进程名':<30} {'出现次数':<10} {'百分比':<10}")
    print("-" * 60)
    
    total_next = sum(next_comm_counter.values())
    for process, count in next_comm_counter.most_common(20):
        percentage = (count / total_next) * 100
        print(f"{process:<30} {count:<10} {percentage:.2f}%")
    
    # 2. 统计 prev_comm 频率
    print("\n\n2. sched_switch 事件中 prev_comm（上一个运行的进程）的出现频率:")
    print("-" * 60)
    print(f"{'进程名':<30} {'出现次数':<10} {'百分比':<10}")
    print("-" * 60)
    
    total_prev = sum(prev_comm_counter.values())
    for process, count in prev_comm_counter.most_common(20):
        percentage = (count / total_prev) * 100
        print(f"{process:<30} {count:<10} {percentage:.2f}%")
    
    # 3. 检查虚拟化相关进程
    print("\n\n3. 虚拟化相关进程统计:")
    print("-" * 60)
    if virtualization_processes:
        print(f"{'虚拟化进程':<30} {'出现次数':<10}")
        print("-" * 60)
        for process, count in virtualization_processes.most_common():
            print(f"{process:<30} {count:<10}")
    else:
        print("未发现 KVM、qemu、vhost 等虚拟化相关进程")
    
    # 4. 统计每个 CPU 上的调度事件数量
    print("\n\n4. 每个 CPU 上的调度事件数量统计:")
    print("-" * 60)
    print(f"{'CPU编号':<10} {'事件数量':<10} {'百分比':<10} {'繁忙程度':<15}")
    print("-" * 60)
    
    total_cpu_events = sum(cpu_counter.values())
    if total_cpu_events > 0:
        # 找出最繁忙的 CPU
        busiest_cpu = cpu_counter.most_common(1)[0][0] if cpu_counter else "N/A"
        
        for cpu in sorted(cpu_counter.keys(), key=lambda x: int(x)):
            count = cpu_counter[cpu]
            percentage = (count / total_cpu_events) * 100
            # 简单评估繁忙程度
            if percentage > 20:
                busy_level = "非常繁忙"
            elif percentage > 15:
                busy_level = "繁忙"
            elif percentage > 10:
                busy_level = "中等"
            else:
                busy_level = "较空闲"
            
            print(f"{cpu:<10} {count:<10} {percentage:.2f}% {busy_level:<15}")
        
        print(f"\n最繁忙的 CPU: CPU {busiest_cpu}，处理了 {cpu_counter[busiest_cpu]} 个事件")
        print(f"占总事件数的 {(cpu_counter[busiest_cpu]/total_cpu_events)*100:.2f}%")
    
    # 5. 检查 D 状态（不可中断睡眠）进程
    print("\n\n5. 处于 D 状态（不可中断睡眠）的进程统计:")
    print("-" * 60)
    if d_state_processes:
        print(f"{'进程名':<30} {'D状态次数':<10}")
        print("-" * 60)
        for process, count in d_state_processes.most_common():
            print(f"{process:<30} {count:<10}")
        
        total_d_state = sum(d_state_processes.values())
        d_state_percentage = (total_d_state / total_events) * 100
        print(f"\n总共有 {total_d_state} 次进程处于 D 状态")
        print(f"占所有调度事件的 {d_state_percentage:.2f}%")
        
        if d_state_percentage > 5:
            print("⚠️  警告: D 状态事件比例较高，可能存在 I/O 阻塞问题")
        elif d_state_percentage > 1:
            print("ℹ️  注意: 存在一定数量的 D 状态事件，建议关注 I/O 性能")
        else:
            print("✓ D 状态事件比例正常")
    else:
        print("未发现进程处于 D 状态（不可中断睡眠）")
    
    # 6. 进程状态统计
    print("\n\n6. 进程状态分布统计:")
    print("-" * 60)
    print(f"{'状态':<10} {'出现次数':<10} {'百分比':<10} {'说明':<30}")
    print("-" * 60)
    
    state_descriptions = {
        'R': '运行/可运行',
        'S': '可中断睡眠',
        'D': '不可中断睡眠(I/O等待)',
        'T': '停止',
        'Z': '僵尸',
        'I': '空闲',
        'X': '退出'
    }
    
    total_states = sum(prev_state_counter.values())
    for state, count in prev_state_counter.most_common():
        percentage = (count / total_states) * 100
        description = state_descriptions.get(state, '未知状态')
        print(f"{state:<10} {count:<10} {percentage:.2f}% {description:<30}")
    
    print("\n" + "=" * 80)
    print("分析报告总结:")
    print("=" * 80)
    
    # 总结最活跃的进程
    if next_comm_counter:
        most_active = next_comm_counter.most_common(1)[0]
        print(f"最活跃的进程: {most_active[0]} (出现 {most_active[1]} 次)")
    
    # 总结最繁忙的 CPU
    if cpu_counter:
        busiest = cpu_counter.most_common(1)[0]
        print(f"最繁忙的 CPU: CPU {busiest[0]} (处理 {busiest[1]} 个事件)")
    
    # 虚拟化进程总结
    if virtualization_processes:
        print(f"发现虚拟化相关进程: {', '.join(virtualization_processes.keys())}")
    else:
        print("未发现虚拟化相关进程")
    
    # D 状态总结
    if d_state_processes:
        print(f"发现 {len(d_state_processes)} 个进程处于 D 状态")
    else:
        print("未发现进程处于 D 状态")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python analyze_ftrace.py <ftrace_log_file>")
        sys.exit(1)
    
    analyze_ftrace_log(sys.argv[1])