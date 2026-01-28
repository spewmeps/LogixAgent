# ftrace 分析模式与方法

针对不同性能调查场景的常用分析模式和方法。

## 模式 1：KVM/QEMU 虚拟机性能分析

### 场景
虚拟机在宿主机上表现出性能缓慢或 CPU 占用率过高。

### 数据收集
```bash
# 在宿主机上执行
sudo trace-cmd record -e sched:* -e kvm:* -T 30
trace-cmd report > kvm_trace.txt
```

### 分析步骤

**第 1 步：过滤虚拟机相关事件**
```bash
grep -E "KVM|qemu|CPU.*KVM" kvm_trace.txt > vm_events.txt
```

**第 2 步：识别最活跃的 vCPU 线程**
```bash
grep "sched_switch" vm_events.txt | \
  awk -F'next_comm=' '{print $2}' | \
  awk '{print $1}' | \
  sort | uniq -c | sort -rn | head -20
```

**第 3 步：检查 vCPU 迁移情况**
```bash
grep "sched_migrate_task" vm_events.txt | \
  grep -E "KVM|qemu" | \
  wc -l
```
计数较高 → 说明 CPU 绑定 (CPU Pinning) 不足。

**第 4 步：分析 D 状态 (I/O 等待)**
```bash
grep "prev_state=D" vm_events.txt | \
  awk -F'prev_comm=' '{print $2}' | \
  awk '{print $1}' | \
  sort | uniq -c | sort -rn
```

**第 5 步：检查虚拟机退出 (VM Exits)**
```bash
grep "kvm_exit" kvm_trace.txt | \
  awk '{print $NF}' | \
  sort | uniq -c | sort -rn
```

### 预期结果

**良好状态**：
- 迁移计数低 (<100)
- vCPU 线程的 D 状态极少
- 虚拟机退出主要原因是 HLT 或 CPUID

**糟糕状态**：
- 迁移计数高 (>1000) → 需要进行 CPU 绑定
- D 状态占比高 → 宿主机存在 I/O 瓶颈
- 大量 EPT/MMIO 退出 → 内存或设备相关问题

---

## 模式 2：CPU 调度器分析

### 场景
系统感觉卡顿，怀疑是 CPU 调度问题。

### 快速健康检查
```bash
# 上下文切换频率
grep "sched_switch" trace.txt | wc -l

# 计算每秒切换率
total_switches=$(grep "sched_switch" trace.txt | wc -l)
duration=$(awk 'NR==1{first=$5} END{print $5-first}' trace.txt)
echo "scale=2; $total_switches / $duration" | bc
```

**基准参考值**：
- <1000/秒：低负载
- 1000-5000/秒：中等负载
- >10000/秒：高资源竞争

### 识别 CPU 占用大户
```bash
python3 scripts/ftrace_stats.py trace.txt --switch-stats | head -30
```

### 检查运行队列长度
```bash
# 统计每次 sched_switch 时处于 R 状态的任务
# (此处为示例逻辑，实际需复杂脚本解析)
```
