---
name: ftrace-analyzer
description: 全面的 Linux 内核 ftrace 日志分析工具，特别适用于 KVM/QEMU 虚拟机调度和性能诊断。在分析 ftrace 文本日志以识别虚拟化环境中的调度热点、上下文切换、CPU 利用率、I/O 阻塞和性能瓶颈时使用。支持通过过滤、统计分析、时间序列可视化和性能问题诊断来处理大规模（GB 级）追踪文件。
---

# ftrace 分析器

分析 Linux ftrace 日志，以诊断调度问题、性能瓶颈和资源竞争，并提供对 KVM/QEMU 虚拟机分析的专门支持。

## 快速入门

典型的 KVM/QEMU 性能分析流程：

```bash
# 1. 过滤相关数据
grep -E "KVM|qemu" ftrace.txt > kvm_only.txt
grep -E "sched_switch|sched_waking" kvm_only.txt > kvm_sched.txt

# 2. 运行分析脚本
python3 scripts/ftrace_stats.py kvm_sched.txt

# 3. 生成可视化图表
python3 scripts/ftrace_visualize.py kvm_sched.txt
```

## 分析流程

### 阶段 0：数据准备

1. **验证日志格式** - 确保为 ftrace 文本格式：
   ```
   TASK-PID CPU# TIMESTAMP FUNCTION [EVENT DETAILS]
   ```
   示例：
   ```
   <idle>-0 [086] d... 31686721.679534: sched_switch: prev_comm=swapper/86 prev_pid=0 prev_prio=120 prev_state=S ==> next_comm=CPU 19/KVM next_pid=42321 next_prio=120
   ```

2. **识别追踪事件** - 常用事件：
   - `sched_switch`: 任务之间的上下文切换
   - `sched_waking`: 任务唤醒事件
   - `sched_migrate_task`: 任务在 CPU 之间的迁移
   - `irq_handler_entry/exit`: 中断处理过程

### 阶段 1：数据过滤

**目标**：提取相关事件以减少数据量

**针对 KVM/QEMU 分析**：
```bash
# 过滤虚拟机相关进程
grep -E "KVM|qemu|vhost" ftrace.txt > vm_only.txt

# 过滤调度相关事件
grep -E "sched_switch|sched_waking" vm_only.txt > vm_sched.txt

# 清洗并提取关键字段
awk '{print $2, $3, $5, $NF}' vm_sched.txt > vm_sched_clean.txt
```

**通用过滤模式**：
```bash
# 按特定 PID 过滤
grep "next_pid=<PID>" ftrace.txt

# 按 CPU 过滤
grep "\[<CPU#>\]" ftrace.txt

# 按时间范围过滤
awk '$5 >= START_TIME && $5 <= END_TIME' ftrace.txt
```

### 阶段 2：统计分析

使用提供的分析脚本或手动命令：

**2.1 线程唤醒频率**：
```bash
python3 scripts/ftrace_stats.py <file> --wakeup-stats
```
或手动执行：
```bash
grep sched_waking <file> | awk -F'comm=' '{print $2}' | awk '{print $1}' | sort | uniq -c | sort -rn | head -20
```

**2.2 上下文切换计数**：
```bash
python3 scripts/ftrace_stats.py <file> --switch-stats
```
或手动执行：
```bash
grep sched_switch <file> | awk -F'next_comm=' '{print $2}' | awk '{print $1}' | sort | uniq -c | sort -rn | head -20
```

**2.3 CPU 利用率分布**：
```bash
python3 scripts/ftrace_stats.py <file> --cpu-stats
```
或手动执行：
```bash
# 此处省略具体手动命令
```
