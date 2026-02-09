# Common Crash Analysis Patterns

Signature patterns for recognizing and diagnosing common kernel failures.

## Panic Types

### NULL Pointer Dereference

**Signature:**
```
BUG: unable to handle kernel NULL pointer dereference at 0000000000000000
IP: [<ffffffff81234567>] function_name+0x12/0x34
```

**Backtrace pattern:**
- Crash in a function attempting to access structure member
- Address near zero (0x0, 0x8, 0x10, etc.)

**Investigation:**
1. `bt` - See which pointer was NULL
2. `dis -l <function>` - See the dereference
3. Look for missed NULL checks in code path

**Common causes:**
- Uninitialized pointer
- Race condition freeing structure
- Failed allocation not checked

---

### General Protection Fault

**Signature:**
```
general protection fault: 0000 [#1] SMP
IP: [<ffffffff81abcdef>] function_name+0x45/0x67
```

**Characteristics:**
- Invalid memory access (bad pointer, corrupted structure)
- Often shows non-canonical address (0x6b6b6b6b, 0x5a5a5a5a patterns)

**Investigation:**
1. Check address in fault - common patterns:
   - `0x6b6b6b6b` - SLAB_POISON (use-after-free)
   - `0x5a5a5a5a` - kmalloc redzone (buffer overflow)
2. `struct <type> <bad_address>` - Try to interpret structure
3. Look for recent memory operations in backtrace

---

### Stack Overflow

**Signature:**
```
stack overflow detected
Double fault
```

**Backtrace pattern:**
- Very deep call stack (100+ frames)
- Recursive function calls
- Large local variables

**Investigation:**
1. `bt` - Count depth
2. Look for repeated function names (recursion)
3. Check for unbounded loops

---

### Out Of Memory (OOM)

**Signature:**
```
Out of memory: Kill process <pid> (<name>) score <X> or sacrifice child
Killed process <pid> (<name>) total-vm:<X>kB, anon-rss:<Y>kB, file-rss:<Z>kB
```

**Log patterns:**
- Multiple OOM killer invocations
- Memory allocation failures
- List of processes with memory scores

**Investigation:**
1. `kmem -i` - Check memory distribution
2. `ps` - Sort by memory usage
3. `vm <pid>` - Examine top consumers
4. `kmem -s` - Check for slab leaks

**Common causes:**
- Memory leak (application or kernel)
- Undersized system for workload
- Memory limit (cgroup) too low

---

### Deadlock

**Signature:**
- System hang
- Multiple processes in D (UN) state
- Watchdog timeout

**Log patterns:**
```
INFO: task <name>:<pid> blocked for more than 120 seconds
```

**Investigation:**
1. `ps | grep UN` - Find stuck processes
2. `foreach bt` - Get all backtraces
3. `bt -l <pid>` - Check locks held
4. Look for circular wait:
   - Process A waiting for lock held by B
   - Process B waiting for lock held by A

**Pattern recognition:**
```bash
# Find ABBA deadlock
foreach bt | grep -A10 "mutex_lock\|down\|spin_lock"
```

---

### Soft Lockup

**Signature:**
```
BUG: soft lockup - CPU#X stuck for Xs!
```

**Characteristics:**
- CPU spinning without yielding
- Interrupts disabled too long
- Infinite loop in kernel

**Investigation:**
1. `bt -a` - Check all CPUs
2. `dis -l <function>` - Examine spinning function
3. Look for:
   - while(1) loops without breaks
   - Tight polling loops
   - Lock held indefinitely

---

### Hard Lockup

**Signature:**
```
NMI watchdog: BUG: hard lockup - CPU#X stuck for Xs!
```

**More severe than soft lockup:**
- CPU not responding to interrupts
- Often hardware issue or critical kernel bug

---

## Memory Corruption Patterns

### Slab Corruption

**Signature:**
```
slab error in <function>: cache `<cache_name>'
Freepointer corrupt
```

**Investigation:**
1. `kmem -s <cache_name>` - Examine slab cache
2. Look for use-after-free in backtrace
3. Check for buffer overflows

---

### Page Table Corruption

**Signature:**
```
BUG: Bad page map
BUG: Bad page state
```

**Indicates:**
- Kernel page table corrupted
- Hardware memory error possible

**Investigation:**
1. `kmem -p` - Check page info
2. Review recent memory operations
3. Consider hardware diagnostics

---

## Driver Issues

### Device Timeout

**Signature:**
```
<driver>: timeout waiting for <operation>
```

**Common in:**
- Storage drivers (SCSI, SATA, NVMe)
- Network drivers

**Investigation:**
1. `dev` - Check device state
2. `irq` - Verify interrupt delivery
3. Look for hardware errors in log

---

### DMA Errors

**Signature:**
```
DMA: Out of SW-IOMMU space
DMAR: DRHD: handling fault status
```

**Investigation:**
1. Check hardware health
2. Review driver initialization
3. Verify IOMMU configuration

---

## File System Issues

### Filesystem Corruption Detected

**Signature:**
```
EXT4-fs error: <details>
XFS: Internal error <details>
```

**Investigation:**
1. `mount` - Check filesystem status
2. `files` - Look for problematic file operations
3. Review recent disk operations

---

### VFS Deadlock

**Signature:**
- Processes stuck in D state
- Backtrace shows VFS functions

**Common patterns:**
```
do_sys_open
vfs_read
vfs_write
```

**Investigation:**
1. Check filesystem mount options
2. Review NFS/network filesystem issues
3. Look for lock ordering violations

---

## Network Issues

### RCU Stall

**Signature:**
```
INFO: rcu_sched self-detected stall on CPU
```

**Characteristics:**
- CPU hasn't completed RCU grace period
- Often network stack related

**Investigation:**
1. `bt -a` - Check CPU activity
2. Look for network driver in backtrace
3. Check for excessive packet processing

---

### Network Stack Overflow

**Signature:**
```
net_ratelimit: <X> callbacks suppressed
```

**Indicates:**
- Excessive network activity
- Possible attack or misconfiguration

---

## Workload-Specific Patterns

### Database Server Crashes

**Common signatures:**
- High memory pressure (OOM)
- Many processes in D state (IO wait)
- Filesystem deadlocks

**Investigation focus:**
- `kmem -i` - Memory
- `files` - Open descriptors
- `bt -a` - IO operations

---

### Web Server Crashes

**Common signatures:**
- Socket exhaustion
- Thread/process limit reached
- Network driver issues

**Investigation focus:**
- `ps` - Process count
- Network stack traces
- Memory allocation failures

---

### Container/Virtualization Issues

**Common signatures:**
- Cgroup OOM
- Namespace-related panics
- Virtio driver timeouts

**Investigation focus:**
- Cgroup memory limits
- Virtual device states
- Host-guest interaction

---

## Quick Pattern Matching

Use these greps on log output to quickly identify issues:

```bash
# Panic indicators
log | grep -i "panic\|oops\|bug:\|kernel bug"

# Memory issues
log | grep -i "out of memory\|oom\|allocation fail"

# Deadlock indicators
log | grep -i "blocked for\|hung task\|deadlock"

# Hardware errors
log | grep -i "hardware error\|mce\|machine check"

# Driver issues
log | grep -i "timeout\|firmware\|driver.*fail"

# Filesystem problems
log | grep -i "ext4-fs\|xfs\|io error"
```

---

## Pattern Analysis Workflow

For any crash, follow this pattern recognition workflow:

1. **Classify the panic type** (NULL deref, GPF, OOM, etc.)
2. **Identify the subsystem** (MM, FS, NET, drivers)
3. **Look for known signatures** (patterns listed above)
4. **Apply subsystem-specific investigation** (relevant commands)
5. **Check for hardware issues** (if software causes unclear)

## Common False Leads

Be aware of these misleading patterns:

1. **Panic in panic handler:** Secondary crash while handling first panic
   - Look earlier in backtrace for original crash
   
2. **Generic allocation failure:** May be symptom, not cause
   - Find where memory was exhausted
   
3. **Timeout messages:** Often consequence of deadlock elsewhere
   - Find what blocked the operation

4. **Workqueue stuck:** Usually waiting for something else
   - Find what the workqueue is waiting for
