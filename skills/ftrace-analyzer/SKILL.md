---
name: ftrace-analyzer
description: Comprehensive ftrace log analysis for Linux kernel tracing, particularly for KVM/QEMU virtual machine scheduling and performance diagnostics. Use when analyzing ftrace text logs to identify scheduling hotspots, context switches, CPU utilization, I/O blocking, and performance bottlenecks in virtualized environments. Handles large trace files (GB scale) with filtering, statistical analysis, time-series visualization, and performance issue diagnosis.
---

# ftrace Analyzer

Analyze Linux ftrace logs to diagnose scheduling issues, performance bottlenecks, and resource contention, with specialized support for KVM/QEMU virtual machine analysis.

## Quick Start

For a typical KVM/QEMU performance analysis:

```bash
# 1. Filter relevant data
grep -E "KVM|qemu" ftrace.txt > kvm_only.txt
grep -E "sched_switch|sched_waking" kvm_only.txt > kvm_sched.txt

# 2. Run analysis script
python3 scripts/ftrace_stats.py kvm_sched.txt

# 3. Generate visualization
python3 scripts/ftrace_visualize.py kvm_sched.txt
```

## Analysis Workflow

### Phase 0: Data Preparation

1. **Verify log format** - Ensure ftrace text format:
   ```
   TASK-PID CPU# TIMESTAMP FUNCTION [EVENT DETAILS]
   ```
   Example:
   ```
   <idle>-0 [086] d... 31686721.679534: sched_switch: prev_comm=swapper/86 prev_pid=0 prev_prio=120 prev_state=S ==> next_comm=CPU 19/KVM next_pid=42321 next_prio=120
   ```

2. **Identify trace events** - Common events:
   - `sched_switch`: Context switches between tasks
   - `sched_waking`: Task wake-up events
   - `sched_migrate_task`: Task migration between CPUs
   - `irq_handler_entry/exit`: Interrupt handling

### Phase 1: Data Filtering

**Objective**: Extract relevant events to reduce data volume

**For KVM/QEMU analysis**:
```bash
# Filter VM-related processes
grep -E "KVM|qemu|vhost" ftrace.txt > vm_only.txt

# Filter scheduling events
grep -E "sched_switch|sched_waking" vm_only.txt > vm_sched.txt

# Clean and extract key fields
awk '{print $2, $3, $5, $NF}' vm_sched.txt > vm_sched_clean.txt
```

**Generic filtering patterns**:
```bash
# Filter by specific PID
grep "next_pid=<PID>" ftrace.txt

# Filter by CPU
grep "\[<CPU#>\]" ftrace.txt

# Filter by time range
awk '$5 >= START_TIME && $5 <= END_TIME' ftrace.txt
```

### Phase 2: Statistical Analysis

Use the provided analysis scripts or manual commands:

**2.1 Thread wake-up frequency**:
```bash
python3 scripts/ftrace_stats.py <file> --wakeup-stats
```
Or manually:
```bash
grep sched_waking <file> | awk -F'comm=' '{print $2}' | awk '{print $1}' | sort | uniq -c | sort -rn | head -20
```

**2.2 Context switch count**:
```bash
python3 scripts/ftrace_stats.py <file> --switch-stats
```
Or manually:
```bash
grep sched_switch <file> | awk -F'next_comm=' '{print $2}' | awk '{print $1}' | sort | uniq -c | sort -rn | head -20
```

**2.3 CPU utilization distribution**:
```bash
python3 scripts/ftrace_stats.py <file> --cpu-stats
```
Or manually:
```bash
awk '{print $3}' <file> | sed 's/\[//g;s/\]//g' | sort | uniq -c | sort -rn
```

### Phase 3: Time Series Analysis

**Objective**: Identify temporal patterns, burst activity, or periodic issues

Use the visualization script:
```bash
python3 scripts/ftrace_visualize.py <file> --window 0.1 --output analysis.png
```

This generates:
- Wake-up event frequency over time
- Context switch rate trends
- CPU utilization heatmap

**Key patterns to look for**:
- **Periodic spikes**: May indicate timer-driven activity
- **Sudden bursts**: Could signal I/O completion or interrupt storms
- **Gradual increases**: Possible resource exhaustion or leak

### Phase 4: Blocking Analysis

**Objective**: Identify I/O wait and resource starvation

**Check task states in sched_switch**:
- `R`: Running/Runnable
- `S`: Interruptible sleep (waiting for event)
- `D`: Uninterruptible sleep (I/O wait) ⚠️ Critical indicator
- `T`: Stopped
- `Z`: Zombie

**Find I/O-blocked tasks**:
```bash
grep "prev_state=D" <file> | awk -F'prev_comm=' '{print $2}' | awk '{print $1}' | sort | uniq -c | sort -rn
```

**High D-state time indicates**:
- Disk I/O bottleneck
- Network latency
- Virtual device contention (for VMs)
- Lock contention in kernel

### Phase 5: Comprehensive Analysis

**Synthesize findings**:

1. **Top wake-up threads** → Identify scheduling hot spots
2. **CPU distribution** → Detect CPU imbalance or saturation
3. **Blocked threads** → Find I/O or lock bottlenecks
4. **Time series patterns** → Reveal temporal behavior

**Common VM performance issues**:

| Symptom | Likely Cause | Solution |
|---------|-------------|----------|
| Single CPU saturated with KVM switches | Too many vCPUs or host contention | Reduce vCPUs or use CPU pinning |
| High wake-up frequency | I/O intensive workload | Optimize virtual storage/network |
| Many D-state blocks | I/O wait or lock contention | Check host storage performance |
| Periodic spikes | Timer or interrupt storm | Adjust timer coalescing settings |
| Frequent migration events | Poor CPU affinity | Pin vCPUs to physical CPUs |
| High priority inversion | Scheduling policy issues | Adjust real-time priorities |

### Phase 6: Reporting

Generate comprehensive analysis report:
```bash
python3 scripts/ftrace_report.py <file> --output report.html
```

Report includes:
- Executive summary with key metrics
- Per-thread statistics table
- CPU utilization breakdown
- Time series visualizations
- Specific recommendations based on detected patterns

## Advanced Techniques

**Multi-file comparison**:
```bash
python3 scripts/ftrace_compare.py baseline.txt problem.txt --output comparison.html
```
Useful for before/after analysis or A/B testing configurations.

**Custom event filtering**:
```bash
# Focus on specific PID
awk '/<PID>/' ftrace.txt | python3 scripts/ftrace_stats.py -

# Time window extraction
awk '$5 >= 1234567.0 && $5 <= 1234580.0' ftrace.txt > window.txt

# Multiple process pattern
grep -E "process1|process2|process3" ftrace.txt > multi_process.txt
```

**Integration with other tools**:
- Convert trace.dat to text: `trace-cmd report trace.dat > ftrace.txt`
- Filter perf output: `perf script > ftrace.txt`
- Import into KernelShark: May require conversion back to binary format

## Performance Optimization

**For large files (>1GB)**:
1. Filter early to reduce processing time
2. Use grep/awk instead of loading entire file into Python
3. Process in streaming fashion with generators
4. Focus on specific time windows of interest
5. Use parallel processing for multiple files

**Memory considerations**:
- Avoid loading entire file into pandas for files >500MB
- Use iterative processing with chunking
- Generate statistics incrementally
- Clear intermediate results promptly

**Disk I/O optimization**:
- Work on local SSD if possible
- Use tmpfs for intermediate files
- Pipeline operations to avoid intermediate file writes

## Troubleshooting

**Issue**: Script fails with "bad field count"
**Solution**: ftrace format varies by kernel version. Adjust field numbers in awk commands or scripts.

**Issue**: No events found after filtering
**Solution**: Check actual event names with `grep -o '[a-z_]*:' ftrace.txt | sort -u`

**Issue**: Timestamps not monotonic
**Solution**: Multiple CPUs may have unsynchronized clocks. Sort by timestamp first: `sort -k5 -n`

**Issue**: Python scripts fail with import errors
**Solution**: Install dependencies: `pip install pandas matplotlib seaborn numpy --break-system-packages`

**Issue**: Memory error on large files
**Solution**: Use streaming analysis or split file: `split -l 1000000 ftrace.txt chunk_`

## References

See bundled reference files for detailed information:
- `references/ftrace_events.md` - Complete event type reference
- `references/sched_states.md` - Task state meanings and implications
- `references/analysis_patterns.md` - Common analysis patterns and recipes

External resources:
- Linux kernel ftrace documentation: https://www.kernel.org/doc/html/latest/trace/ftrace.html
- KernelShark visualization tool: https://www.kernelshark.org/
- trace-cmd manual: https://man7.org/linux/man-pages/man1/trace-cmd.1.html
