#!/bin/bash
# quick_report.sh - Generate initial crash assessment report
# Usage: ./quick_report.sh <path_to_crash_directory>

set -e

# 1. Check arguments
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <path_to_crash_directory>"
    echo "Example: $0 /home/crash/ixgbe_core"
    echo "The directory must contain 'vmcore' and 'vmlinux' files."
    exit 1
fi

TARGET_DIR="$1"

# 2. Verify directory and files
if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: Directory '$TARGET_DIR' not found."
    exit 1
fi

# Check for vmcore and vmlinux
VMCORE_PATH="${TARGET_DIR}/vmcore"
VMLINUX_PATH="${TARGET_DIR}/vmlinux"

if [ ! -f "$VMCORE_PATH" ]; then
    echo "Error: 'vmcore' file not found in '$TARGET_DIR'."
    echo "Expected path: $VMCORE_PATH"
    exit 1
fi

if [ ! -f "$VMLINUX_PATH" ]; then
    echo "Error: 'vmlinux' file not found in '$TARGET_DIR'."
    echo "Expected path: $VMLINUX_PATH"
    exit 1
fi

# Check for crash command
if ! command -v crash &> /dev/null; then
    echo "Error: 'crash' command not found. Please install it first."
    exit 1
fi

# 3. Prepare report file
# Generate report in the target directory
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="${TARGET_DIR}/quick_report_${TIMESTAMP}.txt"

echo "Analyzing crash dump in: $TARGET_DIR"
echo "Generating report to: $REPORT_FILE"

# 4. Create temporary crash script with analysis commands
CRASH_SCRIPT=$(mktemp)
cat > "$CRASH_SCRIPT" << 'CRASH_EOF'
# Phase 1: Initial Assessment
sys
bt -a
log | tail -100
bt

# Phase 2: Context
ps | grep UN
bt -a

# Phase 3A: Memory Analysis
kmem -i
kmem -s | sort -k 2 -n -r | head -20

# Phase 3B: Deadlock Analysis (Check for stuck tasks)
foreach UN bt

# Phase 3C: Interrupt/Timer Analysis
irq
timer

# Phase 3D: Filesystem/IO Analysis
files
mount
dev

# Phase 3E: Driver/Hardware Analysis
mod
log | grep -iE "hardware|error|pci|mce|warn"

# Exit crash
exit
CRASH_EOF

# 5. Execute analysis
# Change to target directory to use relative paths as requested
pushd "$TARGET_DIR" > /dev/null

{
    cat << EOF
================================================================================
                        CRASH ANALYSIS REPORT
================================================================================
Generated: $(date)
Target Directory: $TARGET_DIR
Kernel: ./vmlinux
Core:   vmcore

================================================================================
                        ANALYSIS OUTPUT
================================================================================
EOF

    # Execute crash command with input redirection
    # Using ./vmlinux and vmcore as specified
    crash ./vmlinux vmcore < "$CRASH_SCRIPT" 2>&1

    cat << EOF

================================================================================
                        ANALYSIS RECOMMENDATIONS
================================================================================
Based on the initial assessment, consider:

1. Review the panic message in the 'sys' output
2. Check the last 100 log lines for errors/warnings
3. Examine the crashing task's backtrace (bt output)
4. Look for processes in UN (uninterruptible) state
5. Check memory statistics for OOM conditions

Next Steps (refer to SKILL.md):
- Memory Issue: Phase 3A (kmem -s)
- Deadlock: Phase 3B (bt <pid> -> struct mutex)
- Interrupts: Phase 3C (irq, timer)
- IO/FS: Phase 3D (files, mount)

================================================================================
EOF

} > "$REPORT_FILE"

popd > /dev/null

# 6. Cleanup and Summary
rm -f "$CRASH_SCRIPT"

echo "Report generated successfully: $REPORT_FILE"
echo ""
echo "--- Quick Summary (Panic/Oops) ---"
grep -A2 "PANIC\|Oops\|BUG:" "$REPORT_FILE" | head -20 || echo "  No obvious panic messages found in summary."
echo "----------------------------------"
