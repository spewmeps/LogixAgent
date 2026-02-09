# Crash Command Reference

Complete reference for crash utility commands used in kernel analysis.

## Core Analysis Commands

### sys
**Purpose:** Display system information and panic details

**Usage:** `sys`

**Output includes:**
- Kernel version and release
- Machine architecture
- Panic string (if available)
- System uptime
- Crash time
- Number of CPUs

**When to use:** Always run first to establish baseline

---

### log
**Purpose:** Display kernel ring buffer (dmesg output)

**Usage:** 
- `log` - Full log
- `log | tail -100` - Last 100 lines (recommended)
- `log | grep ERROR` - Filter for errors

**Look for:**
- Panic messages
- Oops reports
- Hardware errors
- Driver failures
- Memory corruption warnings

**When to use:** First command after sys

---

### bt (backtrace)
**Purpose:** Display call stack of current/specified task

**Usage:**
- `bt` - Current task backtrace
- `bt <pid>` - Specific process backtrace
- `bt -a` - All CPU backtraces
- `bt -l` - Include locks held
- `bt -t` - Include timestamps
- `bt -f` - Full symbol information

**Interpretation:**
- Top of stack shows where crash occurred
- Follow call chain downward
- Look for known problematic functions

**When to use:** Essential for understanding crash context

---

### ps
**Purpose:** Display process status

**Usage:**
- `ps` - All processes
- `ps -l` - Include lock information
- `ps -u` - User/kernel times
- `ps -p` - Per-CPU breakdown

**Key states:**
- `RU` - Running
- `IN` - Interruptible sleep
- `UN` - Uninterruptible sleep (often stuck)
- `ST` - Stopped
- `ZO` - Zombie
- `DE` - Dead

**When to use:** Finding stuck or problematic processes

---

## Memory Analysis Commands

### kmem
**Purpose:** Kernel memory analysis

**Common usages:**
- `kmem -i` - Memory usage summary (start here)
- `kmem -s` - Slab allocator statistics
- `kmem -s <cache>` - Specific cache detail
- `kmem -p` - Memory pages info
- `kmem -v` - Virtual memory context

**Interpreting kmem -i:**
- Total memory vs used
- Slab usage percentage
- Page cache size
- Free memory at crash time

**Finding leaks:**
```bash
kmem -s | grep -v "  0  "  # Non-empty caches
kmem -s | sort -k6 -n -r   # Sort by total size
```

**When to use:** Any memory-related issue

---

### vm
**Purpose:** Virtual memory information for processes

**Usage:**
- `vm` - Current task VM info
- `vm <pid>` - Specific process VM
- `vm -p` - Physical address mapping
- `vm -m` - Memory map details

**When to use:** Process memory issues, segfaults

---

### free
**Purpose:** Display memory availability

**Usage:** `free`

**Shows:** Total, used, free memory in system view

---

## Lock and Wait Analysis

### waitq
**Purpose:** Display wait queue information

**Usage:**
- `waitq <address>` - Specific wait queue
- Typically used after seeing tasks in UN state

**When to use:** Deadlock investigation

---

## Interrupt and Timer Commands

### irq
**Purpose:** Display interrupt statistics

**Usage:** `irq`

**Shows:**
- IRQ number
- Count
- Handler function
- Device name

**Look for:** Unusually high counts indicating storms

---

### timer
**Purpose:** Display kernel timer information

**Usage:** `timer`

**Shows active timers and their handlers

**When to use:** Timer-related hangs or watchdog triggers

---

## File System Commands

### files
**Purpose:** Display open file descriptors

**Usage:**
- `files` - Current task files
- `files <pid>` - Specific process files

**When to use:** File descriptor leaks, filesystem issues

---

### mount
**Purpose:** Display mounted filesystems

**Usage:** `mount`

**Shows:** Mount points, filesystem types, devices

---

### dev
**Purpose:** Display device information

**Usage:** `dev`

---

## Structure Inspection

### struct
**Purpose:** Display kernel structure contents

**Usage:**
- `struct <type> <address>`
- `struct task_struct <address>`
- `struct file <address>`

**Tips:**
- Get addresses from other commands (ps, bt, etc.)
- Use with | grep to filter fields

**Example:**
```bash
struct task_struct ffff8800345fb040
struct file ffff88003456cd00
```

---

### union
**Purpose:** Display union contents

**Usage:** Same as struct but for union types

---

## Disassembly Commands

### dis
**Purpose:** Disassemble functions or addresses

**Usage:**
- `dis <function_name>` - Disassemble function
- `dis -l <function_name>` - Include source lines
- `dis <address>` - Disassemble at address
- `dis -r <address>` - Reverse disassemble

**When to use:** Understanding exact crash point

**Example:**
```bash
dis -l panic
dis -l 0xffffffff81234567
```

---

## Memory Reading Commands

### rd (read)
**Purpose:** Read memory contents

**Usage:**
- `rd <address>` - Read one word
- `rd <address> <count>` - Read multiple
- `rd -8 <address>` - Read 8-byte words
- `rd -4 <address>` - Read 4-byte words

---

### px (print hex)
**Purpose:** Print memory in hex format

**Usage:** `px <address> <count>`

**Better formatted than rd for raw memory dumps**

---

## Advanced Commands

### foreach
**Purpose:** Execute command for each element

**Usage:**
- `foreach bt` - Backtrace all processes
- `foreach files` - Files for all processes
- `foreach vm` - VM info for all processes

**Powerful for:**
- Finding patterns across processes
- Identifying widespread issues

**Example:**
```bash
foreach bt | grep -B2 "UN"  # Find stuck processes
```

---

### mod
**Purpose:** Kernel module information

**Usage:**
- `mod` - List all modules
- `mod -S` - Reload symbols for modules

**When to use:** Module-related crashes

---

### alias
**Purpose:** Create command shortcuts

**Usage:**
- `alias <name> <command>`
- `alias ll log | tail -100`

**Tip:** Create aliases for frequently used command chains

---

## Command Combinations

### Quick Panic Analysis
```bash
sys
log | tail -100
bt
```

### Memory Leak Hunt
```bash
kmem -i
kmem -s | grep -v "  0  " | sort -k6 -n -r | head -20
```

### Deadlock Investigation
```bash
ps | grep UN
foreach bt | grep -A5 "UN"
bt -l <pid>
```

### Complete System State
```bash
sys
ps
bt -a
kmem -i
free
mount
```

## Tips and Tricks

1. **Piping:** Most commands support piping to grep, less, head, tail
   ```bash
   log | grep -i error
   ps | grep UN
   ```

2. **Output redirection:** Save command output
   ```bash
   log > /tmp/kernlog.txt
   foreach bt > /tmp/all_backtraces.txt
   ```

3. **Repeat commands:** Use `!` for command history
   ```bash
   !sys    # Repeat last sys command
   !ps     # Repeat last ps command
   ```

4. **Tab completion:** Crash supports tab completion for commands and symbols

5. **Help system:**
   ```bash
   help <command>     # Command-specific help
   help sys
   help bt
   ```

## Common Pitfalls

1. **Symbol mismatch:** If output looks garbled, check vmlinux matches vmcore
2. **Module symbols:** Use `mod -S` to reload module symbols if needed
3. **Address validity:** Not all addresses in memory dumps are valid - crash will warn
4. **Output buffer:** Very large outputs may be truncated - use output redirection
