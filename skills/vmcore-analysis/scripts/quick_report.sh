#!/bin/bash
# quick_report.sh - Generate initial crash assessment report
# Usage: ./quick_report.sh <path_to_crash_directory> [output_report_path]

set -e

# 1. Check arguments
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "Usage: $0 <path_to_crash_directory> [output_report_path]"
    echo "Example: $0 /home/crash/ixgbe_core"
    echo "Example: $0 /home/crash/ixgbe_core /tmp/my_report.txt"
    echo "The directory must contain 'vmcore' and 'vmlinux' files."
    exit 1
fi

TARGET_DIR="$1"
OUTPUT_REPORT_PATH="$2"

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
# Generate report in the target directory or use provided path
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

if [ -n "$OUTPUT_REPORT_PATH" ]; then
    # Use provided path, ensure directory exists
    REPORT_DIR=$(dirname "$OUTPUT_REPORT_PATH")
    if [ ! -d "$REPORT_DIR" ]; then
        echo "Creating report directory: $REPORT_DIR"
        mkdir -p "$REPORT_DIR"
    fi
    # If path is relative, make it absolute or handle it carefully. 
    # For simplicity, we'll assume the user provides a valid path relative to current PWD or absolute.
    # To be safe when we change directory later, let's resolve it to absolute path if possible, 
    # or keep it as is if we don't change directory or change back.
    # Since we use 'pushd', we should resolve absolute path for REPORT_FILE if it's not absolute.
    if [[ "$OUTPUT_REPORT_PATH" != /* ]]; then
        OUTPUT_REPORT_PATH="$(pwd)/$OUTPUT_REPORT_PATH"
    fi
    REPORT_FILE="$OUTPUT_REPORT_PATH"
else
    REPORT_FILE="${TARGET_DIR}/quick_report_${TIMESTAMP}.txt"
    # Resolve absolute path for consistency
    if [[ "$REPORT_FILE" != /* ]]; then
        REPORT_FILE="$(cd "$TARGET_DIR" && pwd)/quick_report_${TIMESTAMP}.txt"
    fi
fi

echo "Analyzing crash dump in: $TARGET_DIR"
echo "Generating report to: $REPORT_FILE"

# 4. Create temporary crash script with analysis commands
CRASH_SCRIPT=$(mktemp)
cat > "$CRASH_SCRIPT" << 'CRASH_EOF'
!echo "================================================================================"
!echo ">>> Command: sys"
!echo ">>> Description: 系统概览 (System Overview) - 显示系统基本信息，如内核版本、Panic信息等"
!echo "================================================================================"
sys

!echo ""
!echo "================================================================================"
!echo ">>> Command: bt -a"
!echo ">>> Description: 所有活跃任务堆栈 (Backtrace of active tasks) - 查看所有CPU上正在运行的任务"
!echo "================================================================================"
bt -a

!echo ""
!echo "================================================================================"
!echo ">>> Command: log | tail -100"
!echo ">>> Description: 内核日志 (Kernel Log) - 查看 dmesg 缓冲区的最后 100 行"
!echo "================================================================================"
log | tail -100

!echo ""
!echo "================================================================================"
!echo ">>> Command: bt"
!echo ">>> Description: 崩溃堆栈 (Crash Backtrace) - 触发 Panic 的当前进程堆栈"
!echo "================================================================================"
bt

!echo ""
!echo "================================================================================"
!echo ">>> Command: ps | grep UN"
!echo ">>> Description: D状态进程 (Uninterruptible Tasks) - 查找处于不可中断睡眠状态的进程"
!echo "================================================================================"
ps | grep UN

!echo ""
!echo "================================================================================"
!echo ">>> Command: kmem -i"
!echo ">>> Description: 内存概览 (Memory Info) - 查看整体内存使用情况"
!echo "================================================================================"
kmem -i

!echo ""
!echo "================================================================================"
!echo ">>> Command: kmem -s | sort -k 2 -n -r | head -20"
!echo ">>> Description: Slab 内存排行 (Slab Usage Top 20) - 按对象数量排序的 Slab 缓存使用情况"
!echo "================================================================================"
kmem -s | sort -k 2 -n -r | head -20

!echo ""
!echo "================================================================================"
!echo ">>> Command: foreach UN bt"
!echo ">>> Description: D状态进程堆栈 (Backtrace of UN tasks) - 检查死锁嫌疑进程的调用栈"
!echo "================================================================================"
foreach UN bt

!echo ""
!echo "================================================================================"
!echo ">>> Command: foreach UN files"
!echo ">>> Description: D状态进程持有文件 (Files held by UN tasks) - 检查是否阻塞在IO/锁"
!echo "================================================================================"
foreach UN files

!echo ""
!echo "================================================================================"
!echo ">>> Command: foreach UN task -R state,flags,comm,pid"
!echo ">>> Description: D状态进程关键字段 (Task Struct Details) - 查看进程状态位和标志"
!echo "================================================================================"
foreach UN task -R state,flags,comm,pid

!echo ""
!echo "================================================================================"
!echo ">>> Command: irq"
!echo ">>> Description: 中断统计 (IRQ Stats) - 查看中断计数"
!echo "================================================================================"
irq

!echo ""
!echo "================================================================================"
!echo ">>> Command: timer"
!echo ">>> Description: 定时器 (Timers) - 查看挂起的定时器"
!echo "================================================================================"
timer

!echo ""
!echo "================================================================================"
!echo ">>> Command: files"
!echo ">>> Description: 打开文件 (Open Files) - 当前上下文打开的文件句柄"
!echo "================================================================================"
files

!echo ""
!echo "================================================================================"
!echo ">>> Command: mount"
!echo ">>> Description: 挂载信息 (Mount Points) - 文件系统挂载情况"
!echo "================================================================================"
mount

!echo ""
!echo "================================================================================"
!echo ">>> Command: dev"
!echo ">>> Description: 设备信息 (Device Info) - 块设备和字符设备信息"
!echo "================================================================================"
dev

!echo ""
!echo "================================================================================"
!echo ">>> Command: mod"
!echo ">>> Description: 内核模块 (Kernel Modules) - 已加载的模块列表"
!echo "================================================================================"
mod

!echo ""
!echo "================================================================================"
!echo ">>> Command: log | grep -iE 'hardware|error|pci|mce|warn'"
!echo ">>> Description: 错误日志搜索 (Error Log Search) - 搜索包含硬件错误关键字的日志"
!echo "================================================================================"
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
