# OS Crash Analyzer Usage Examples

## Quick Start

1. **Configure your environment:**
   ```bash
   ./scripts/crash_config.sh set \
     --vmlinux /usr/lib/debug/lib/modules/$(uname -r)/vmlinux \
     --vmcore /var/crash/vmcore
   ```

2. **Verify configuration:**
   ```bash
   ./scripts/crash_config.sh test
   ```

3. **Generate quick report:**
   ```bash
   ./scripts/quick_report.sh
   ```

## Example Workflows

### Scenario 1: Analyze a new crash

```bash
# 1. Set paths
./scripts/crash_config.sh set \
  --vmlinux /usr/lib/debug/vmlinux-5.10.0 \
  --vmcore /var/crash/202402051200/vmcore

# 2. Run automated analysis
./scripts/crash_wrapper.sh

# 3. Review the log
less ~/crash_logs/crash_session_*.log
```

### Scenario 2: Manual investigation

```bash
# Launch crash with saved config
./scripts/crash_config.sh run

# Inside crash:
crash> sys
crash> log | tail -100
crash> bt
crash> kmem -i
```

### Scenario 3: Analyze specific structures

```bash
# Inside crash, get task_struct address
crash> ps
  PID    PPID  CPU       TASK        ST  %MEM     VSZ    RSS  COMM
  1234   1     2   ffff8800345fb040  RU   1.2  123456  45678  myapp

# Save to file
crash> struct task_struct ffff8800345fb040 > /tmp/task.txt
crash> exit

# Analyze with script
./scripts/analyze_struct.py /tmp/task.txt --type task
```

## Configuration Examples

### Multiple crash dumps

```bash
# Save configurations for different crashes
export VMLINUX=/usr/lib/debug/vmlinux-5.10.0
export VMCORE_CRASH1=/var/crash/crash1/vmcore
export VMCORE_CRASH2=/var/crash/crash2/vmcore

# Analyze first crash
./scripts/crash_config.sh set --vmlinux $VMLINUX --vmcore $VMCORE_CRASH1
./scripts/quick_report.sh

# Analyze second crash
./scripts/crash_config.sh set --vmlinux $VMLINUX --vmcore $VMCORE_CRASH2
./scripts/quick_report.sh
```

### Remote crash dump analysis

```bash
# Copy vmcore from remote server
scp server:/var/crash/vmcore /tmp/remote_vmcore

# Analyze
./scripts/crash_config.sh set \
  --vmlinux /usr/lib/debug/vmlinux-5.10.0 \
  --vmcore /tmp/remote_vmcore
  
./scripts/quick_report.sh
```

## Tips

1. **Save crash outputs:** Always redirect output to files for later review
   ```bash
   crash> log > /tmp/kernlog.txt
   crash> foreach bt > /tmp/all_backtraces.txt
   ```

2. **Use grep for patterns:** Filter large outputs
   ```bash
   crash> log | grep -i "error\|panic\|oops"
   ```

3. **Compare crashes:** If you have multiple vmcores, compare outputs
   ```bash
   diff crash1_report.txt crash2_report.txt
   ```

4. **Automate common checks:** Create your own wrapper scripts
   ```bash
   #!/bin/bash
   # my_analysis.sh
   crash vmlinux vmcore << EOF
   sys
   log | tail -100
   bt
   kmem -i
   ps | grep UN
   exit
   EOF
   ```
