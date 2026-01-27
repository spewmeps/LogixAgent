# ftrace Analysis Patterns and Recipes

Common analysis patterns and recipes for different performance investigation scenarios.

## Pattern 1: KVM/QEMU VM Performance Analysis

### Scenario
Virtual machine experiencing slow performance or high CPU usage on the host.

### Data Collection
```bash
# On the host
sudo trace-cmd record -e sched:* -e kvm:* -T 30
trace-cmd report > kvm_trace.txt
```

### Analysis Steps

**Step 1: Filter VM-related events**
```bash
grep -E "KVM|qemu|CPU.*KVM" kvm_trace.txt > vm_events.txt
```

**Step 2: Identify most active vCPU threads**
```bash
grep "sched_switch" vm_events.txt | \
  awk -F'next_comm=' '{print $2}' | \
  awk '{print $1}' | \
  sort | uniq -c | sort -rn | head -20
```

**Step 3: Check for vCPU migration**
```bash
grep "sched_migrate_task" vm_events.txt | \
  grep -E "KVM|qemu" | \
  wc -l
```
High count → Poor CPU pinning

**Step 4: Analyze D-state (I/O wait)**
```bash
grep "prev_state=D" vm_events.txt | \
  awk -F'prev_comm=' '{print $2}' | \
  awk '{print $1}' | \
  sort | uniq -c | sort -rn
```

**Step 5: Check VM exits**
```bash
grep "kvm_exit" kvm_trace.txt | \
  awk '{print $NF}' | \
  sort | uniq -c | sort -rn
```

### Expected Findings

**Good**: 
- Low migration count (<100)
- Minimal D-state for vCPU threads
- VM exits mostly for HLT/CPUID

**Bad**:
- High migration (>1000) → Need CPU pinning
- High D-state → Host I/O bottleneck
- Many EPT/MMIO exits → Memory/device issues

---

## Pattern 2: CPU Scheduler Analysis

### Scenario
System feels sluggish, suspecting CPU scheduling issues.

### Quick Health Check
```bash
# Context switch frequency
grep "sched_switch" trace.txt | wc -l

# Calculate per-second rate
total_switches=$(grep "sched_switch" trace.txt | wc -l)
duration=$(awk 'NR==1{first=$5} END{print $5-first}' trace.txt)
echo "scale=2; $total_switches / $duration" | bc
```

**Baseline values**:
- <1000/sec: Low load
- 1000-5000/sec: Moderate load
- >10000/sec: High contention

### Identify CPU Hogs
```bash
python3 scripts/ftrace_stats.py trace.txt --switch-stats | head -30
```

### Check Run Queue Length
```bash
# Count tasks in R state at each sched_switch
awk '/sched_switch/ && /prev_state=R/ {r++} 
     /sched_switch/ && /next_state=R/ {r++}
     {print NR, r}' trace.txt | \
  awk '{sum+=$2; count++} END {print "Avg runnable:", sum/count}'
```

### Detect Priority Inversions
```bash
grep "sched_switch" trace.txt | \
  awk -F'prio=' '{print $2, $4}' | \
  awk '{if($1 > $3) print "Inversion:", $0}' | \
  head -50
```

---

## Pattern 3: Interrupt Storm Detection

### Scenario
System unresponsive, suspecting interrupt issues.

### Quick Check
```bash
# Count interrupt events
grep "irq_handler_entry" trace.txt | wc -l

# Identify top interrupt sources
grep "irq_handler_entry" trace.txt | \
  awk -F'name=' '{print $2}' | \
  awk '{print $1}' | \
  sort | uniq -c | sort -rn | head -20
```

### Interrupt Rate Per Second
```bash
grep "irq_handler_entry" trace.txt | \
  awk '{print int($5)}' | \
  uniq -c | \
  awk '$1 > 10000 {print "Second", NR, ":", $1, "interrupts"}'
```

**Thresholds**:
- <10k/sec: Normal
- 10k-50k/sec: High (check if justified)
- >50k/sec: Likely storm

### Identify Problematic IRQ
```bash
# Get IRQ numbers causing storms
grep "irq_handler_entry" trace.txt | \
  awk -F'irq=' '{print $2}' | \
  awk '{print $1}' | \
  sort | uniq -c | sort -rn | \
  head -5
```

### Correlate with Performance
```bash
# Find context switches during high interrupt periods
awk '/irq_handler_entry/ {irq[$5]++}
     /sched_switch/ {cs[$5]++}
     END {
       for(t in irq) 
         if(irq[t]>100) 
           print t, "IRQs:", irq[t], "CS:", cs[t]
     }' trace.txt
```

---

## Pattern 4: I/O Bottleneck Investigation

### Scenario
Applications hanging or slow, database queries timing out.

### Identify Blocking Tasks
```bash
python3 scripts/ftrace_stats.py trace.txt --blocking-stats
```

### Calculate D-State Duration
```bash
# Extract D-state periods for a specific task
task_name="mysqld"
awk -v task="$task_name" '
  /sched_switch/ && /prev_comm='"$task_name"'/ && /prev_state=D/ {
    d_start=$5
  }
  /sched_switch/ && /next_comm='"$task_name"'/ && d_start {
    duration=$5 - d_start
    if(duration < 10) {  # Only short periods
      total += duration
      count++
    }
    d_start=0
  }
  END {
    print "Average D-state duration:", total/count, "seconds"
  }
' trace.txt
```

### Check Block I/O Events
```bash
grep "block_rq" trace.txt | \
  awk '{print $5, $7}' | \
  sort -k1 -n | \
  awk '{
    if(prev && $2 ~ /complete/ && $1-prev < 1) {
      sum += ($1-prev)*1000
      count++
    }
    if($2 ~ /issue/) prev=$1
  }
  END {print "Avg I/O latency:", sum/count, "ms"}'
```

---

## Pattern 5: Network Performance Analysis

### Scenario
Network throughput lower than expected.

### Packet Processing Analysis
```bash
# RX processing
grep "netif_receive_skb" trace.txt | \
  awk '{cpu[$3]++} 
  END {for(c in cpu) print c, cpu[c]}' | \
  sort -k2 -rn

# TX processing
grep "net_dev_xmit" trace.txt | \
  awk '{cpu[$3]++}
  END {for(c in cpu) print c, cpu[c]}' | \
  sort -k2 -rn
```

### Check Softirq Processing
```bash
# Network RX softirqs
grep "softirq.*vec=3" trace.txt | wc -l

# Time in NET_RX softirq
awk '/softirq_entry.*vec=3/ {entry=$5}
     /softirq_exit.*vec=3/ && entry {
       duration=$5-entry
       sum+=duration
       count++
       entry=0
     }
     END {print "Avg NET_RX duration:", sum/count*1000, "ms"}' \
  trace.txt
```

### CPU Balance Check
```bash
# Distribution of network processing across CPUs
grep -E "netif_receive|net_dev_xmit" trace.txt | \
  awk '{print $3}' | \
  sed 's/\[//g;s/\]//g' | \
  sort | uniq -c | \
  awk '{print "CPU", $2, ":", $1, "packets"}'
```

---

## Pattern 6: Real-Time Analysis

### Scenario
Real-time application missing deadlines.

### Check Scheduling Latency
```bash
# Time from waking to running
awk '
  /sched_waking/ {
    task=$0
    sub(/.*comm=/, "", task)
    sub(/ .*/, "", task)
    wake_time[task]=$5
  }
  /sched_switch.*next_comm=/ {
    task=$0
    sub(/.*next_comm=/, "", task)
    sub(/ .*/, "", task)
    if(wake_time[task]) {
      latency=($5 - wake_time[task]) * 1000000  # Convert to microseconds
      if(latency < 10000) {  # Ignore unreasonable values
        sum+=latency
        count++
        if(latency > max) max=latency
      }
      delete wake_time[task]
    }
  }
  END {
    print "Avg scheduling latency:", sum/count, "us"
    print "Max scheduling latency:", max, "us"
  }
' trace.txt
```

### Identify Preemption
```bash
# Tasks preempted from running
grep "sched_switch" trace.txt | \
  grep "prev_state=R" | \
  awk -F'prev_comm=' '{print $2}' | \
  awk '{print $1}' | \
  sort | uniq -c | sort -rn | \
  head -20
```

---

## Pattern 7: Lock Contention Analysis

### Scenario
Multi-threaded application not scaling with cores.

### Mutex Wait Times
```bash
# Requires mutex_lock tracepoints
grep "mutex_lock" trace.txt | \
  awk '{print $1, $5}' | \
  sort -k1 | \
  awk '{
    if(prev_task==$1) {
      wait=$2-prev_time
      if(wait>0.001) print prev_task, "waited", wait*1000, "ms"
    }
    prev_task=$1
    prev_time=$2
  }'
```

### Spinlock Hot Spots
```bash
# Tasks frequently in D state (potential lock wait)
grep "prev_state=D" trace.txt | \
  awk -F'prev_comm=' '{print $2}' | \
  awk '{print $1}' | \
  sort | uniq -c | sort -rn | \
  awk '$1>100 {print "High D-state:", $2, "count:", $1}'
```

---

## Pattern 8: Time-Series Trending

### Scenario
Need to identify when problem started.

### Event Rate Over Time
```bash
python3 scripts/ftrace_visualize.py trace.txt --window 1.0
```

### Find Anomalies
```bash
# Calculate moving average and find spikes
awk '/sched_switch/ {
  bucket=int($5)
  count[bucket]++
}
END {
  for(i=0; i<=length(count); i++) {
    sum=0
    for(j=i-5; j<=i+5; j++) {
      if(count[j]) sum+=count[j]
    }
    avg=sum/11
    if(count[i] > avg*2) {
      print "Spike at second", i, ":", count[i], "(avg:", int(avg), ")"
    }
  }
}' trace.txt
```

---

## Pattern 9: Comparative Analysis

### Scenario
Need to compare "good" vs "bad" traces.

### Before/After Comparison
```bash
python3 scripts/ftrace_compare.py baseline.txt problem.txt
```

### Manual Diff Analysis
```bash
# Compare top CPU consumers
for file in baseline.txt problem.txt; do
  echo "=== $file ==="
  grep "sched_switch" $file | \
    awk -F'next_comm=' '{print $2}' | \
    awk '{print $1}' | \
    sort | uniq -c | sort -rn | head -10
done
```

---

## Quick Reference Commands

```bash
# Top 20 context-switched tasks
python3 scripts/ftrace_stats.py trace.txt --switch-stats | head -25

# Top 20 woken tasks  
python3 scripts/ftrace_stats.py trace.txt --wakeup-stats | head -25

# CPU distribution
python3 scripts/ftrace_stats.py trace.txt --cpu-stats

# Full analysis with visualization
python3 scripts/ftrace_stats.py trace.txt --all
python3 scripts/ftrace_visualize.py trace.txt
python3 scripts/ftrace_report.py trace.txt

# Quick one-liners
grep "sched_switch" trace.txt | wc -l                    # Total switches
grep "prev_state=D" trace.txt | wc -l                    # Total D-state
grep "sched_migrate_task" trace.txt | wc -l              # Total migrations
grep "kvm_exit" trace.txt | awk '{print $NF}' | sort | uniq -c  # VM exit reasons
```

---

## Troubleshooting Tips

1. **Large files**: Use grep/awk to filter before Python analysis
2. **Field alignment**: Adjust awk field numbers based on kernel version
3. **Time windows**: Focus on problematic time periods only
4. **Sampling**: For very large traces, use `head -n 100000` to test scripts
5. **Correlation**: Cross-reference with system metrics (vmstat, iostat, sar)
