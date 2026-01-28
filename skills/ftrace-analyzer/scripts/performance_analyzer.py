#!/usr/bin/env python3
"""
ftrace 性能问题分析器
专注于无报错场景下的性能偏态识别
核心理念：找的不是"异常"，而是"偏态"
"""

import sys
import argparse
import re
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional
import json
import statistics


class PerformanceMetrics:
    """性能指标收集器"""
    
    def __init__(self):
        # 调度延迟
        self.sched_latencies = []  # (timestamp, latency)
        self.runnable_gaps = []  # runnable 但未运行的时间段
        
        # 时间片统计
        self.running_slices = []  # 每次运行的时长
        self.preemption_count = 0
        
        # CPU 占用归属
        self.cpu_time_by_task = defaultdict(float)
        
        # 事件分布
        self.event_distribution = Counter()
        self.event_timeline = []  # (timestamp, event_type, actor)
        
        # 唤醒统计
        self.wakeup_count = 0
        self.effective_run_ratio = 0  # 有效运行比例
    
    def add_sched_latency(self, timestamp: float, latency: float):
        """添加调度延迟"""
        self.sched_latencies.append((timestamp, latency))
    
    def add_running_slice(self, duration: float, preempted: bool = False):
        """添加运行时间片"""
        self.running_slices.append(duration)
        if preempted:
            self.preemption_count += 1
    
    def add_cpu_time(self, task: str, duration: float):
        """记录 CPU 时间归属"""
        self.cpu_time_by_task[task] += duration
    
    def get_statistics(self) -> Dict:
        """计算统计指标"""
        stats = {}
        
        # 调度延迟统计
        if self.sched_latencies:
            latencies = [l for _, l in self.sched_latencies]
            stats['sched_latency'] = {
                'count': len(latencies),
                'min': min(latencies) * 1000,  # ms
                'max': max(latencies) * 1000,
                'mean': statistics.mean(latencies) * 1000,
                'median': statistics.median(latencies) * 1000,
                'stdev': statistics.stdev(latencies) * 1000 if len(latencies) > 1 else 0,
                'p95': statistics.quantiles(latencies, n=20)[18] * 1000 if len(latencies) > 20 else max(latencies) * 1000,
                'p99': statistics.quantiles(latencies, n=100)[98] * 1000 if len(latencies) > 100 else max(latencies) * 1000,
            }
        
        # 运行时间片统计
        if self.running_slices:
            stats['running_slices'] = {
                'count': len(self.running_slices),
                'mean': statistics.mean(self.running_slices) * 1000,
                'median': statistics.median(self.running_slices) * 1000,
                'min': min(self.running_slices) * 1000,
                'preemption_rate': self.preemption_count / len(self.running_slices) if self.running_slices else 0,
            }
        
        # CPU 时间归属
        if self.cpu_time_by_task:
            total_time = sum(self.cpu_time_by_task.values())
            stats['cpu_time_attribution'] = {
                task: {
                    'time_ms': time * 1000,
                    'percentage': (time / total_time * 100) if total_time > 0 else 0
                }
                for task, time in sorted(self.cpu_time_by_task.items(), 
                                        key=lambda x: x[1], reverse=True)[:10]
            }
        
        # 事件分布
        stats['event_distribution'] = dict(self.event_distribution.most_common(10))
        
        return stats


class PerformanceAnalyzer:
    """性能偏态分析器"""
    
    def __init__(self):
        self.metrics: Dict[str, PerformanceMetrics] = {}  # 文件名 -> 指标
    
    def analyze_file(self, filepath: str, label: str, target_thread: str = None):
        """分析单个文件"""
        metrics = PerformanceMetrics()
        
        print(f"正在分析 {label}: {filepath}...", file=sys.stderr)
        
        # 线程状态跟踪
        thread_state = {}  # pid -> (state, timestamp)
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            prev_timestamp = 0
            prev_task_on_cpu = {}  # cpu -> (task, timestamp)
            
            for line in f:
                # 简化解析
                parts = line.split(':', 3)
                if len(parts) < 4:
                    continue
                
                try:
                    header = parts[0]
                    event_type = parts[2].strip()
                    details = parts[3].strip()
                    
                    # 提取时间戳、CPU、PID、任务名
                    time_match = re.search(r'\[\d+\]\s+([\d.]+)', header)
                    cpu_match = re.search(r'\[(\d+)\]', header)
                    task_match = re.search(r'^\s*([\w\s/:.()-]+?)-(\d+)', header)
                    
                    if not (time_match and cpu_match):
                        continue
                    
                    timestamp = float(time_match.group(1))
                    cpu = int(cpu_match.group(1))
                    
                    if task_match:
                        task_name = task_match.group(1).strip()
                        pid = int(task_match.group(2))
                    else:
                        continue
                    
                    # 记录事件分布
                    metrics.event_distribution[event_type] += 1
                    metrics.event_timeline.append((timestamp, event_type, task_name))
                    
                    # 处理调度切换
                    if event_type == 'sched_switch':
                        match = re.search(
                            r'prev_comm=(.+?)\s+prev_pid=(\d+)\s+prev_prio=(\d+)\s+prev_state=(\S+)\s+==>\s+'
                            r'next_comm=(.+?)\s+next_pid=(\d+)',
                            details
                        )
                        
                        if match:
                            prev_comm = match.group(1)
                            prev_pid = int(match.group(2))
                            prev_state = match.group(4)
                            next_comm = match.group(5)
                            next_pid = int(match.group(6))
                            
                            # 记录 CPU 时间归属
                            if cpu in prev_task_on_cpu:
                                prev_task, start_time = prev_task_on_cpu[cpu]
                                duration = timestamp - start_time
                                metrics.add_cpu_time(prev_task, duration)
                            
                            prev_task_on_cpu[cpu] = (next_comm, timestamp)
                            
                            # 如果是目标线程
                            is_target = (target_thread and 
                                        (target_thread in prev_comm or target_thread in next_comm))
                            
                            if is_target:
                                # 切出：记录运行时间片
                                if target_thread in prev_comm:
                                    if prev_pid in thread_state:
                                        state, start_time = thread_state[prev_pid]
                                        if state == 'running':
                                            duration = timestamp - start_time
                                            preempted = 'R' in prev_state
                                            metrics.add_running_slice(duration, preempted)
                                    
                                    # 更新状态
                                    new_state = 'runnable' if 'R' in prev_state else 'sleeping'
                                    thread_state[prev_pid] = (new_state, timestamp)
                                
                                # 切入：计算调度延迟
                                if target_thread in next_comm:
                                    if next_pid in thread_state:
                                        state, wakeup_time = thread_state[next_pid]
                                        if state == 'runnable':
                                            latency = timestamp - wakeup_time
                                            metrics.add_sched_latency(timestamp, latency)
                                    
                                    thread_state[next_pid] = ('running', timestamp)
                    
                    # 处理唤醒
                    elif event_type in ['sched_wakeup', 'sched_wakeup_new']:
                        match = re.search(r'comm=(\S+)\s+pid=(\d+)', details)
                        if match:
                            comm = match.group(1)
                            pid = int(match.group(2))
                            
                            if target_thread and target_thread in comm:
                                thread_state[pid] = ('runnable', timestamp)
                                metrics.wakeup_count += 1
                
                except (ValueError, IndexError):
                    continue
        
        self.metrics[label] = metrics
        print(f"完成 {label} 分析", file=sys.stderr)
    
    def detect_anomalies(self, normal_label: str, abnormal_label: str) -> Dict:
        """检测异常模式（偏态）"""
        
        if normal_label not in self.metrics or abnormal_label not in self.metrics:
            print("错误：缺少对照数据", file=sys.stderr)
            return {}
        
        normal = self.metrics[normal_label].get_statistics()
        abnormal = self.metrics[abnormal_label].get_statistics()
        
        anomalies = {}
        
        # 1. 调度延迟偏态检测
        if 'sched_latency' in normal and 'sched_latency' in abnormal:
            n_lat = normal['sched_latency']
            a_lat = abnormal['sched_latency']
            
            anomalies['sched_latency_deviation'] = {
                'mean_increase': a_lat['mean'] - n_lat['mean'],
                'mean_ratio': a_lat['mean'] / n_lat['mean'] if n_lat['mean'] > 0 else 0,
                'max_increase': a_lat['max'] - n_lat['max'],
                'p95_increase': a_lat['p95'] - n_lat['p95'],
                'stdev_increase': a_lat['stdev'] - n_lat['stdev'],
                'verdict': self._classify_deviation(a_lat['mean'] / n_lat['mean'] if n_lat['mean'] > 0 else 0)
            }
        
        # 2. 运行时间片偏态检测
        if 'running_slices' in normal and 'running_slices' in abnormal:
            n_slice = normal['running_slices']
            a_slice = abnormal['running_slices']
            
            anomalies['running_slice_deviation'] = {
                'mean_change': a_slice['mean'] - n_slice['mean'],
                'mean_ratio': a_slice['mean'] / n_slice['mean'] if n_slice['mean'] > 0 else 0,
                'preemption_rate_increase': a_slice['preemption_rate'] - n_slice['preemption_rate'],
                'verdict': '运行被切碎' if a_slice['mean'] < n_slice['mean'] * 0.5 else '正常'
            }
        
        # 3. CPU 时间归属偏态
        if 'cpu_time_attribution' in normal and 'cpu_time_attribution' in abnormal:
            n_attr = normal['cpu_time_attribution']
            a_attr = abnormal['cpu_time_attribution']
            
            # 找出时间占比显著增加的任务
            time_thieves = []
            for task in set(list(n_attr.keys()) + list(a_attr.keys())):
                n_pct = n_attr.get(task, {}).get('percentage', 0)
                a_pct = a_attr.get(task, {}).get('percentage', 0)
                
                if a_pct > n_pct * 2 and a_pct > 10:  # 翻倍且超过 10%
                    time_thieves.append({
                        'task': task,
                        'normal_pct': n_pct,
                        'abnormal_pct': a_pct,
                        'increase': a_pct - n_pct
                    })
            
            anomalies['time_thieves'] = sorted(time_thieves, 
                                              key=lambda x: x['increase'], 
                                              reverse=True)
        
        # 4. 事件分布偏态
        if 'event_distribution' in normal and 'event_distribution' in abnormal:
            n_dist = normal['event_distribution']
            a_dist = abnormal['event_distribution']
            
            # 找出频率显著增加的事件
            event_surge = []
            for event in set(list(n_dist.keys()) + list(a_dist.keys())):
                n_count = n_dist.get(event, 0)
                a_count = a_dist.get(event, 0)
                
                if a_count > n_count * 1.5 and a_count > 100:
                    event_surge.append({
                        'event': event,
                        'normal_count': n_count,
                        'abnormal_count': a_count,
                        'ratio': a_count / n_count if n_count > 0 else float('inf')
                    })
            
            anomalies['event_surge'] = sorted(event_surge,
                                             key=lambda x: x['ratio'],
                                             reverse=True)
        
        return anomalies
    
    def _classify_deviation(self, ratio: float) -> str:
        """分类偏离程度"""
        if ratio < 1.2:
            return '正常范围'
        elif ratio < 2.0:
            return '轻微偏离'
        elif ratio < 5.0:
            return '显著偏离'
        else:
            return '严重偏离'
    
    def print_comparison_report(self, normal_label: str, abnormal_label: str):
        """打印对比分析报告"""
        
        print("\n" + "=" * 100)
        print("性能偏态分析报告")
        print("=" * 100)
        
        anomalies = self.detect_anomalies(normal_label, abnormal_label)
        
        if not anomalies:
            print("\n无法进行对比分析（缺少数据）")
            return
        
        # 1. 调度延迟偏态
        if 'sched_latency_deviation' in anomalies:
            dev = anomalies['sched_latency_deviation']
            print(f"\n### 1. 调度延迟偏态分析")
            print(f"判定: {dev['verdict']}")
            print(f"  平均延迟增加: {dev['mean_increase']:.3f} ms ({dev['mean_ratio']:.2f}x)")
            print(f"  最大延迟增加: {dev['max_increase']:.3f} ms")
            print(f"  P95 延迟增加: {dev['p95_increase']:.3f} ms")
            print(f"  标准差增加: {dev['stdev_increase']:.3f} ms")
            
            if dev['verdict'] in ['显著偏离', '严重偏离']:
                print(f"  ⚠️  异常信号：调度延迟显著增加，CPU 忙但忙的不是目标线程")
        
        # 2. 运行时间片偏态
        if 'running_slice_deviation' in anomalies:
            dev = anomalies['running_slice_deviation']
            print(f"\n### 2. 运行时间片偏态分析")
            print(f"判定: {dev['verdict']}")
            print(f"  平均时间片变化: {dev['mean_change']:.3f} ms ({dev['mean_ratio']:.2f}x)")
            print(f"  抢占率增加: {dev['preemption_rate_increase']:.2%}")
            
            if dev['verdict'] == '运行被切碎':
                print(f"  ⚠️  异常信号：线程"活着"但几乎没干成事")
        
        # 3. 时间窃贼
        if 'time_thieves' in anomalies and anomalies['time_thieves']:
            print(f"\n### 3. CPU 时间窃贼（时间归属偏态）")
            print(f"发现 {len(anomalies['time_thieves'])} 个时间占比显著增加的任务：\n")
            
            for i, thief in enumerate(anomalies['time_thieves'][:5], 1):
                print(f"  {i}. {thief['task']}")
                print(f"     正常场景: {thief['normal_pct']:.2f}%")
                print(f"     异常场景: {thief['abnormal_pct']:.2f}%")
                print(f"     增加: +{thief['increase']:.2f}%")
                print()
            
            print(f"  ⚠️  关键发现：时间不是消失了，而是被这些任务合法拿走了")
        
        # 4. 事件激增
        if 'event_surge' in anomalies and anomalies['event_surge']:
            print(f"\n### 4. 事件激增（后台行为膨胀）")
            print(f"发现 {len(anomalies['event_surge'])} 个频率显著增加的事件：\n")
            
            for i, surge in enumerate(anomalies['event_surge'][:5], 1):
                print(f"  {i}. {surge['event']}")
                print(f"     正常: {surge['normal_count']:,} 次")
                print(f"     异常: {surge['abnormal_count']:,} 次 ({surge['ratio']:.2f}x)")
                print()
            
            if any(s['ratio'] > 3 for s in anomalies['event_surge']):
                print(f"  ⚠️  异常信号：配角戏份太多，背景噪声变吵了")
        
        # 5. 综合结论
        print(f"\n### 5. 综合结论")
        
        has_serious_issue = False
        conclusion_parts = []
        
        if 'sched_latency_deviation' in anomalies:
            dev = anomalies['sched_latency_deviation']
            if dev['verdict'] in ['显著偏离', '严重偏离']:
                has_serious_issue = True
                conclusion_parts.append(
                    f"调度延迟增加 {dev['mean_ratio']:.1f}倍"
                )
        
        if 'time_thieves' in anomalies and anomalies['time_thieves']:
            top_thief = anomalies['time_thieves'][0]
            conclusion_parts.append(
                f"CPU 时间被 {top_thief['task']} 占用（增加 {top_thief['increase']:.1f}%）"
            )
        
        if conclusion_parts:
            print("\n在异常场景中：")
            for part in conclusion_parts:
                print(f"  • {part}")
            
            print("\n这是典型的性能偏态问题：")
            print("  正常事件以不正常的方式出现")
            print("  不是功能错误，而是资源分配失衡")
        
        if not has_serious_issue:
            print("\n未检测到显著的性能偏态，可能需要：")
            print("  • 检查分析的时间窗口是否正确")
            print("  • 确认目标线程名称是否匹配")
            print("  • 验证正常/异常日志是否真的有差异")
    
    def print_single_file_analysis(self, label: str):
        """打印单文件深度分析（无对照组场景）"""
        
        if label not in self.metrics:
            print("错误：未找到分析数据", file=sys.stderr)
            return
        
        stats = self.metrics[label].get_statistics()
        
        print("\n" + "=" * 100)
        print("性能分析报告（单文件模式 - 基于绝对阈值判断）")
        print("=" * 100)
        print("\n⚠️  注意：单文件分析基于经验阈值，如有正常场景日志可进行对比分析获得更准确结论")
        
        # 1. 调度延迟分析
        if 'sched_latency' in stats:
            lat = stats['sched_latency']
            print(f"\n### 1. 调度延迟分析")
            print(f"  样本数: {lat['count']:,}")
            print(f"  平均值: {lat['mean']:.3f} ms")
            print(f"  中位数: {lat['median']:.3f} ms")
            print(f"  最小值: {lat['min']:.3f} ms")
            print(f"  最大值: {lat['max']:.3f} ms")
            print(f"  标准差: {lat['stdev']:.3f} ms")
            print(f"  P95:    {lat['p95']:.3f} ms")
            print(f"  P99:    {lat['p99']:.3f} ms")
            
            # 基于绝对阈值判断
            issues = []
            if lat['mean'] > 20:
                issues.append(f"⚠️  严重：平均延迟 {lat['mean']:.1f}ms > 20ms 阈值")
            elif lat['mean'] > 10:
                issues.append(f"⚠️  异常：平均延迟 {lat['mean']:.1f}ms > 10ms 阈值")
            elif lat['mean'] > 5:
                issues.append(f"⚠️  可疑：平均延迟 {lat['mean']:.1f}ms > 5ms 阈值")
            
            if lat['max'] > 50:
                issues.append(f"⚠️  严重：最大延迟 {lat['max']:.1f}ms > 50ms 阈值")
            elif lat['max'] > 30:
                issues.append(f"⚠️  异常：最大延迟 {lat['max']:.1f}ms > 30ms 阈值")
            
            if lat['p99'] > 30:
                issues.append(f"⚠️  异常：P99 延迟 {lat['p99']:.1f}ms > 30ms 阈值")
            
            if lat['stdev'] > lat['mean']:
                issues.append(f"⚠️  抖动严重：标准差({lat['stdev']:.1f}ms) > 平均值({lat['mean']:.1f}ms)")
            
            if issues:
                print(f"\n  异常信号：")
                for issue in issues:
                    print(f"    {issue}")
                print(f"\n    → CPU 忙，但忙的不是目标线程")
            else:
                print(f"\n  ✓ 调度延迟在正常范围内（< 5ms）")
        
        # 2. 运行时间片分析
        if 'running_slices' in stats:
            slices = stats['running_slices']
            print(f"\n### 2. 运行时间片分析")
            print(f"  运行片段数: {slices['count']:,}")
            print(f"  平均时间片: {slices['mean']:.3f} ms")
            print(f"  中位数: {slices['median']:.3f} ms")
            print(f"  最小值: {slices['min']:.3f} ms")
            print(f"  抢占率: {slices['preemption_rate']:.1%}")
            
            issues = []
            if slices['mean'] < 1:
                issues.append(f"⚠️  严重切碎：平均时间片 {slices['mean']:.2f}ms < 1ms")
            elif slices['mean'] < 5:
                issues.append(f"⚠️  被切碎：平均时间片 {slices['mean']:.2f}ms < 5ms")
            
            if slices['preemption_rate'] > 0.6:
                issues.append(f"⚠️  频繁抢占：抢占率 {slices['preemption_rate']:.1%} > 60%")
            elif slices['preemption_rate'] > 0.4:
                issues.append(f"⚠️  抢占较多：抢占率 {slices['preemption_rate']:.1%} > 40%")
            
            if issues:
                print(f"\n  异常信号：")
                for issue in issues:
                    print(f"    {issue}")
                print(f"\n    → 线程"活着"但几乎没干成事")
            else:
                print(f"\n  ✓ 运行时间片正常（> 5ms）")
        
        # 3. CPU 时间归属分析（时间窃贼）
        if 'cpu_time_attribution' in stats:
            attr = stats['cpu_time_attribution']
            print(f"\n### 3. CPU 时间归属分析（时间窃贼识别）")
            
            # 找出主要占用者
            major_users = [(task, data) for task, data in attr.items() 
                          if data['percentage'] > 10 or data['time_ms'] > 100]
            
            if major_users:
                print(f"\n  主要 CPU 占用者：")
                for i, (task, data) in enumerate(sorted(major_users, 
                                                        key=lambda x: x[1]['percentage'], 
                                                        reverse=True)[:10], 1):
                    print(f"\n    {i}. {task}")
                    print(f"       时间: {data['time_ms']:.1f} ms")
                    print(f"       占比: {data['percentage']:.1f}%")
                    
                    # 判断是否是时间窃贼
                    warnings = []
                    if data['percentage'] > 50:
                        warnings.append("持续占用超过 50% CPU 时间")
                    if data['time_ms'] > 500:
                        warnings.append(f"累计占用 {data['time_ms']:.0f}ms")
                    
                    if warnings:
                        print(f"       ⚠️  疑似时间窃贼：" + "，".join(warnings))
                
                print(f"\n    → 时间不是消失了，而是被这些任务合法拿走了")
            
            # 识别后台任务膨胀
            background_tasks = {}
            for task, data in attr.items():
                if any(keyword in task.lower() for keyword in 
                      ['kworker', 'kswapd', 'ksoftirqd', 'migration']):
                    background_tasks[task] = data
            
            if background_tasks:
                total_bg_pct = sum(data['percentage'] for data in background_tasks.values())
                print(f"\n  后台任务总占比: {total_bg_pct:.1f}%")
                
                if total_bg_pct > 40:
                    print(f"  ⚠️  严重：后台任务占比 > 40%，配角戏份太多")
                elif total_bg_pct > 30:
                    print(f"  ⚠️  异常：后台任务占比 > 30%，背景噪声变吵")
                elif total_bg_pct > 20:
                    print(f"  ⚠️  可疑：后台任务占比 > 20%")
                else:
                    print(f"  ✓ 后台任务占比正常（< 20%）")
        
        # 4. 事件分布分析
        if 'event_distribution' in stats:
            dist = stats['event_distribution']
            print(f"\n### 4. 事件分布分析")
            
            # 查找高频事件
            high_freq_events = [(event, count) for event, count in dist.items() 
                               if count > 10000]
            
            if high_freq_events:
                print(f"\n  高频事件（> 10000次）：")
                for event, count in sorted(high_freq_events, key=lambda x: x[1], reverse=True)[:5]:
                    print(f"    {event}: {count:,} 次")
                    
                    # 判断异常
                    if 'irq' in event.lower() and count > 50000:
                        print(f"      ⚠️  可能中断风暴（> 50k 次）")
                    elif 'softirq' in event.lower() and count > 30000:
                        print(f"      ⚠️  软中断过载（> 30k 次）")
        
        # 5. 综合结论
        print(f"\n### 5. 综合诊断结论")
        
        conclusion_parts = []
        severity = "正常"
        
        if 'sched_latency' in stats:
            lat = stats['sched_latency']
            if lat['mean'] > 20:
                conclusion_parts.append(f"调度延迟严重（平均 {lat['mean']:.1f}ms）")
                severity = "严重"
            elif lat['mean'] > 10:
                conclusion_parts.append(f"调度延迟异常（平均 {lat['mean']:.1f}ms）")
                if severity == "正常":
                    severity = "异常"
        
        if 'running_slices' in stats:
            slices = stats['running_slices']
            if slices['mean'] < 1:
                conclusion_parts.append(f"运行被严重切碎（时间片 {slices['mean']:.2f}ms）")
                severity = "严重"
        
        if 'cpu_time_attribution' in stats:
            attr = stats['cpu_time_attribution']
            # 找出最大占用者
            if attr:
                top_task, top_data = max(attr.items(), key=lambda x: x[1]['percentage'])
                if top_data['percentage'] > 50:
                    conclusion_parts.append(
                        f"CPU 时间被 {top_task} 持续占用（{top_data['percentage']:.1f}%）"
                    )
        
        print(f"\n  总体评估: {severity}")
        
        if conclusion_parts:
            print(f"\n  主要问题：")
            for part in conclusion_parts:
                print(f"    • {part}")
            
            print(f"\n  分析建议：")
            if severity in ["严重", "异常"]:
                print(f"    1. 使用 timeline_analyzer 查看详细时间线")
                print(f"    2. 使用 causality_chain 构建因果链")
                print(f"    3. 重点关注上述时间窃贼的行为模式")
                if 'cpu_time_attribution' in stats and attr:
                    top_task = max(attr.items(), key=lambda x: x[1]['percentage'])[0]
                    print(f"    4. 建议分析 {top_task} 的活动原因")
                print(f"    5. 如有正常场景日志，强烈建议进行对比分析")
        else:
            print(f"\n  未检测到明显的性能问题")
            print(f"\n  可能的情况：")
            print(f"    • 性能确实正常")
            print(f"    • 问题时间窗口不在此日志范围内")
            print(f"    • 需要与正常场景对比才能发现相对性能退化")
            print(f"    • 建议使用 --window 参数指定问题时间窗口重新分析")


def main():
    parser = argparse.ArgumentParser(
        description='ftrace 性能偏态分析器 - 专注于无报错性能问题',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
核心理念：
  性能问题 ≠ 异常事件发生
  而是"正常事件以不正常的方式出现"
  
  ftrace 是时间归属证明工具，不只是错误检测工具
  
示例用法：

  # 对比正常和异常场景
  %(prog)s --normal normal.txt --abnormal problem.txt --thread myapp

  # 分析单个文件的基本指标
  %(prog)s --file trace.txt --thread myapp --show-stats
        '''
    )
    
    parser.add_argument('--normal', type=str, metavar='FILE',
                        help='正常场景的 ftrace 日志')
    parser.add_argument('--abnormal', type=str, metavar='FILE',
                        help='异常场景的 ftrace 日志')
    parser.add_argument('--file', type=str, metavar='FILE',
                        help='单个日志文件（用于基本统计）')
    parser.add_argument('--thread', type=str, required=True,
                        help='目标线程名称')
    parser.add_argument('--show-stats', action='store_true',
                        help='显示基本统计信息')
    parser.add_argument('--output-json', type=str, metavar='FILE',
                        help='输出 JSON 格式结果')
    
    args = parser.parse_args()
    
    analyzer = PerformanceAnalyzer()
    
    # 对比分析模式
    if args.normal and args.abnormal:
        analyzer.analyze_file(args.normal, 'normal', args.thread)
        analyzer.analyze_file(args.abnormal, 'abnormal', args.thread)
        analyzer.print_comparison_report('normal', 'abnormal')
    
    # 单文件分析模式
    elif args.file:
        analyzer.analyze_file(args.file, 'single', args.thread)
        if args.show_stats:
            # JSON 格式输出
            stats = analyzer.metrics['single'].get_statistics()
            print(json.dumps(stats, indent=2, ensure_ascii=False))
        else:
            # 默认深度分析报告
            analyzer.print_single_file_analysis('single')
    
    else:
        parser.print_help()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
