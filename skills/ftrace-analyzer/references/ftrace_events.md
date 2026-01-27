# ftrace Event Reference

Comprehensive reference for common ftrace event types and their meanings.

## Scheduler Events

### sched_switch
**Description**: Records when a task context switch occurs on a CPU.

**Format**:
```
prev_comm=<name> prev_pid=<pid> prev_prio=<priority> prev_state=<state> ==> next_comm=<name> next_pid=<pid> next_prio=<priority>
```

**Key Fields**:
- `prev_comm`: Name of the task being scheduled out
- `prev_pid`: PID of the task being scheduled out
- `prev_state`: State of the task after being scheduled out
  - `R`: Running/Runnable (will run when CPU available)
  - `S`: Interruptible sleep (waiting for event, can be interrupted)
  - `D`: Uninterruptible sleep (I/O wait, cannot be interrupted) ⚠️
  - `T`: Stopped (by signal or ptrace)
  - `t`: Tracing stop
  - `Z`: Zombie (terminated but not reaped)
  - `X`: Dead (should never see this)
  - `I`: Idle
- `next_comm`: Name of the task being scheduled in
- `next_pid`: PID of the task being scheduled in
- `prev_prio`, `next_prio`: Scheduling priority (0-139, lower is higher priority)

**Analysis Use Cases**:
- Identify frequently context-switched tasks
- Find tasks blocking on I/O (prev_state=D)
- Measure CPU time distribution
- Detect scheduling latency issues

---

### sched_waking
**Description**: Records when a task is being woken up (before it's actually scheduled).

**Format**:
```
comm=<name> pid=<pid> prio=<priority> target_cpu=<cpu>
```

**Key Fields**:
- `comm`: Name of the task being woken
- `pid`: PID of the task
- `target_cpu`: CPU where the task will be scheduled

**Analysis Use Cases**:
- Identify tasks that are frequently woken up
- Detect interrupt storm patterns
- Find I/O completion patterns
- Measure wake-up latency

---

### sched_wakeup
**Description**: Similar to sched_waking but fired after the task is actually placed on the run queue.

**Format**: Same as sched_waking

**Difference from sched_waking**: 
- `sched_waking`: Intent to wake up (before placement on run queue)
- `sched_wakeup`: Task actually placed on run queue

---

### sched_migrate_task
**Description**: Records when a task migrates from one CPU to another.

**Format**:
```
comm=<name> pid=<pid> prio=<priority> orig_cpu=<cpu> dest_cpu=<cpu>
```

**Key Fields**:
- `orig_cpu`: Source CPU
- `dest_cpu`: Destination CPU

**Analysis Use Cases**:
- Measure task migration frequency
- Identify poor CPU affinity
- Detect load balancing issues
- Find cache thrashing problems

**High migration rates indicate**:
- Poor CPU pinning
- Aggressive load balancing
- Potential cache line bouncing
- NUMA issues

---

### sched_process_fork
**Description**: Records when a new process is forked.

**Format**:
```
comm=<parent_name> pid=<parent_pid> child_comm=<child_name> child_pid=<child_pid>
```

**Analysis Use Cases**:
- Track process creation
- Identify fork bombs
- Measure process creation rate

---

### sched_process_exit
**Description**: Records when a process exits.

**Format**:
```
comm=<name> pid=<pid> prio=<priority>
```

**Analysis Use Cases**:
- Track process lifecycle
- Detect rapid process churn
- Correlate with performance issues

---

## Interrupt Events

### irq_handler_entry
**Description**: Fired when an interrupt handler starts.

**Format**:
```
irq=<number> name=<handler_name>
```

**Analysis Use Cases**:
- Identify interrupt frequency
- Detect interrupt storms
- Measure interrupt handling time (with irq_handler_exit)

---

### irq_handler_exit
**Description**: Fired when an interrupt handler completes.

**Format**:
```
irq=<number> ret=<return_value>
```

**Analysis Use Cases**:
- Calculate interrupt handler duration
- Identify slow interrupt handlers

---

### softirq_entry
**Description**: Fired when a soft IRQ handler starts.

**Format**:
```
vec=<vector_number>
```

**Vector Numbers**:
- 0: HI_SOFTIRQ (high priority tasklet)
- 1: TIMER_SOFTIRQ (timer)
- 2: NET_TX_SOFTIRQ (network transmit)
- 3: NET_RX_SOFTIRQ (network receive)
- 4: BLOCK_SOFTIRQ (block I/O)
- 5: IRQ_POLL_SOFTIRQ (IRQ polling)
- 6: TASKLET_SOFTIRQ (normal tasklet)
- 7: SCHED_SOFTIRQ (scheduler)
- 8: HRTIMER_SOFTIRQ (high-resolution timer)
- 9: RCU_SOFTIRQ (RCU callbacks)

---

### softirq_exit
**Description**: Fired when a soft IRQ handler completes.

---

## Power Management Events

### cpu_idle
**Description**: CPU enters idle state.

**Format**:
```
state=<state> cpu_id=<cpu>
```

**Analysis Use Cases**:
- Measure CPU idle time
- Identify power management issues
- Detect C-state transitions

---

### cpu_frequency
**Description**: CPU frequency change.

**Format**:
```
state=<frequency> cpu_id=<cpu>
```

---

## KVM/Virtualization Events

### kvm_entry
**Description**: VM entry (guest execution starts).

---

### kvm_exit
**Description**: VM exit (return to host).

**Format**:
```
reason=<exit_reason> guest_rip=<address>
```

**Common Exit Reasons**:
- 0: Exception/NMI
- 10: CPUID
- 12: HLT
- 28: Control register access
- 30: I/O instruction
- 32: WRMSR
- 48: EPT violation (memory)

**Analysis Use Cases**:
- Measure VM exit frequency
- Identify performance-critical exits
- Detect excessive I/O emulation

---

### kvm_inj_virq
**Description**: Virtual interrupt injection to guest.

---

### kvm_page_fault
**Description**: Guest page fault.

**Format**:
```
address=<fault_address> error_code=<code>
```

---

## Block I/O Events

### block_rq_insert
**Description**: Request inserted into block layer queue.

---

### block_rq_issue
**Description**: Request issued to device.

---

### block_rq_complete
**Description**: Request completed by device.

**Analysis Use Cases**:
- Measure I/O latency (issue to complete)
- Identify I/O bottlenecks
- Track queue depth

---

## Network Events

### net_dev_xmit
**Description**: Network packet transmission.

---

### netif_receive_skb
**Description**: Network packet reception.

---

## Common Analysis Patterns

### Finding CPU Hogs
Look for tasks with high `sched_switch` count and low `prev_state=S` ratio.

### Identifying I/O Bottlenecks
Count `prev_state=D` in `sched_switch` events.

### Detecting Interrupt Storms
High frequency of `irq_handler_entry` events, especially for the same IRQ number.

### Measuring VM Performance
Analyze `kvm_exit` frequency and reasons. High exit rates indicate overhead.

### Finding Wake-up Latency
Time difference between `sched_waking` and corresponding `sched_switch` with matching PID.

---

## Event Filtering Patterns

```bash
# Only scheduling events
grep -E "sched_switch|sched_waking" trace.txt

# Only interrupts
grep -E "irq_handler_entry|irq_handler_exit" trace.txt

# KVM events only
grep "kvm_" trace.txt

# Specific CPU
grep "\[CPU_NUM\]" trace.txt

# Time range (adjust field number based on format)
awk '$5 >= START && $5 <= END' trace.txt
```

---

## References

- Linux kernel documentation: Documentation/trace/ftrace.txt
- Kernel event definitions: include/trace/events/
- Scheduler: include/trace/events/sched.h
