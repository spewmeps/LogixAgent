# Linux Task States Reference

Comprehensive guide to Linux task states as seen in ftrace `sched_switch` events.

## Task State Codes

### R - Running or Runnable
**Full Name**: TASK_RUNNING

**Meaning**: The task is either:
1. Currently executing on a CPU
2. Ready to run and waiting in the run queue

**Characteristics**:
- The task wants CPU time
- No external event is being waited for
- Will run as soon as scheduler selects it

**Analysis Implications**:
- High R-state time → CPU-bound workload
- Many tasks in R-state → CPU contention
- Context switches from R → R indicate CPU sharing/preemption

**When to Investigate**:
- Too many R-state tasks compared to available CPUs
- Single task monopolizing CPU (check priorities)

---

### S - Interruptible Sleep
**Full Name**: TASK_INTERRUPTIBLE

**Meaning**: The task is sleeping, waiting for an event, and can be interrupted by signals.

**Common Reasons**:
- Waiting for user input
- Waiting for network data
- Waiting for timer expiry
- Waiting on locks with timeout
- Sleeping between work items

**Characteristics**:
- Can be woken by signals (SIGTERM, SIGKILL, etc.)
- Voluntarily gave up CPU
- Normal and expected state for idle tasks

**Analysis Implications**:
- Normal state for most tasks most of the time
- Frequent S → R transitions indicate event-driven workload
- Long S periods indicate idle or waiting tasks

**When to Investigate**:
- Task should be working but is in S-state
- Unexpected wake-up patterns
- Abnormally short or long sleep periods

---

### D - Uninterruptible Sleep
**Full Name**: TASK_UNINTERRUPTIBLE

**Meaning**: The task is sleeping and CANNOT be interrupted by signals.

**Common Reasons**:
- Waiting for disk I/O completion
- Waiting for network I/O (sometimes)
- Waiting for device driver operations
- Holding critical kernel locks
- NFS operations (notorious)

**Characteristics**:
- Cannot be killed (even with SIGKILL)
- Usually brief (milliseconds to seconds)
- If prolonged, indicates stuck I/O or deadlock

**⚠️ Critical Performance Indicator**:
- High D-state time = I/O bottleneck
- Many tasks in D-state = system under I/O stress
- Stuck in D-state = serious problem (hung task)

**Analysis Implications**:
```
D-state count → I/O operations frequency
D-state duration → I/O latency
Many D-state tasks → I/O subsystem saturation
```

**When to Investigate**:
- Any task stuck in D-state for >120 seconds (hung_task_timeout)
- Frequent D-state transitions (check storage performance)
- Multiple VMs in D-state (host I/O bottleneck)

**Common Culprits**:
- Slow disk/SSD
- Network file systems (NFS, CIFS)
- RAID rebuilds
- Failing hardware
- Kernel deadlocks

---

### T - Stopped
**Full Name**: TASK_STOPPED

**Meaning**: Task execution stopped by:
- SIGSTOP signal
- SIGTSTP signal (Ctrl+Z)
- SIGTTIN or SIGTTOU signals

**Characteristics**:
- Task can be resumed with SIGCONT
- Used by job control (shell background jobs)
- Debugger breakpoints

**Analysis Implications**:
- Usually not relevant for performance analysis
- May appear in debugging scenarios

---

### t - Tracing Stop
**Full Name**: TASK_TRACED

**Meaning**: Task is stopped by a tracer (ptrace).

**Common Scenarios**:
- GDB debugging session
- strace/ltrace attached
- System call tracing

**Characteristics**:
- Controlled by another process (the tracer)
- Can only be resumed by tracer

**Analysis Implications**:
- Expected when debugging
- Should not appear in production unless debugging

---

### Z - Zombie
**Full Name**: EXIT_ZOMBIE

**Meaning**: Task has terminated but parent hasn't yet read its exit status.

**Characteristics**:
- All resources freed except task_struct
- Waiting for parent to call wait() or waitpid()
- Cannot be killed (already dead)
- Takes minimal resources

**Analysis Implications**:
- Normal to see briefly during process termination
- Many zombies → parent not reaping children properly
- Long-lived zombies → parent process bug

**When to Investigate**:
- Growing zombie count
- Zombies persisting for extended periods
- Parent process not calling wait()

---

### X - Dead
**Full Name**: EXIT_DEAD

**Meaning**: Task is being removed from the system.

**Characteristics**:
- Final state before task_struct is freed
- Should be very brief
- Rarely seen in traces

**Analysis Implications**:
- Seeing this frequently may indicate rapid process churn
- Should transition quickly to complete removal

---

### I - Idle
**Full Name**: TASK_IDLE (recent kernels)

**Meaning**: Similar to D-state but doesn't contribute to load average.

**Usage**:
- Kernel worker threads waiting for work
- I/O operations that shouldn't affect load
- Introduced to prevent artificial load average inflation

**Characteristics**:
- Like D-state but doesn't count as "load"
- Used for kernel threads that wait frequently

---

## State Transition Patterns

### Normal Patterns

#### CPU-Bound Task
```
R → R → R → R → S (preempted or yields)
```

#### I/O-Bound Task
```
R → D (I/O wait) → R (I/O complete) → S (idle)
```

#### Interactive Task
```
S → R (event) → R (process) → S (wait for input)
```

#### Timer-Driven Task
```
S → R (timer) → R (work) → S (sleep) → ...
```

### Abnormal Patterns

#### Stuck in D-State
```
R → D → D → D → D → ... (hung task)
```
**Problem**: I/O not completing, possible hardware failure or deadlock

#### Rapid Context Switching
```
R → R → R → R → R (different tasks)
```
**Problem**: CPU contention, too many runnable tasks

#### Zombie Accumulation
```
R → Z → Z → Z → ...
```
**Problem**: Parent not reaping children

---

## Analysis Queries

### Find Tasks Blocking on I/O
```bash
grep "prev_state=D" ftrace.txt | \
  awk -F'prev_comm=' '{print $2}' | \
  awk '{print $1}' | \
  sort | uniq -c | sort -rn
```

### Count State Transitions Per Task
```bash
grep sched_switch ftrace.txt | \
  awk -F'prev_comm=|prev_state=' '{print $2, $3}' | \
  awk '{print $1, $2}' | \
  sort | uniq -c
```

### Find Long-Running D-State
```bash
# Requires timestamps - look for same PID staying in D-state
awk '/prev_state=D/ {print $5, $0}' ftrace.txt | \
  sort -k1 -n
```

---

## Performance Implications by State

| State | CPU Usage | I/O Wait | Impact on Load Avg |
|-------|-----------|----------|-------------------|
| R     | High      | No       | Yes               |
| S     | None      | No       | No                |
| D     | None      | Yes      | Yes               |
| T     | None      | No       | No                |
| Z     | None      | No       | No                |
| I     | None      | Maybe    | No                |

**Load Average Formula (simplified)**:
```
Load = (R-state tasks) + (D-state tasks) + (I-state tasks on old kernels)
```

---

## Best Practices

1. **R-state**: Normal for CPU-bound workloads, but monitor for contention
2. **S-state**: Expected for idle tasks, check wake-up frequency
3. **D-state**: Minimize duration and frequency, critical performance metric
4. **Z-state**: Should be transient, investigate if accumulating
5. **T-state**: Usually intentional (debugging), ignore in production traces

---

## Troubleshooting Checklist

### High D-State Count
- [ ] Check disk I/O with `iostat -x 1`
- [ ] Check network I/O if using network storage
- [ ] Examine dmesg for hardware errors
- [ ] Review storage array/RAID status
- [ ] Check NFS mount points (if applicable)

### High R-State Count
- [ ] Verify CPU count vs workload
- [ ] Check for CPU-bound processes
- [ ] Review process priorities
- [ ] Consider CPU affinity/pinning
- [ ] Investigate real-time scheduling

### Zombie Accumulation
- [ ] Identify parent process
- [ ] Check parent process for bugs
- [ ] Verify proper signal handling
- [ ] Review process lifecycle management

---

## References

- Linux kernel: include/linux/sched.h
- Process states: fs/proc/array.c (proc_pid_status)
- Scheduler: kernel/sched/core.c
