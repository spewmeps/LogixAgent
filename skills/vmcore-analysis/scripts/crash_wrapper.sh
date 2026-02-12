#!/bin/bash
# crash_wrapper.sh - Automated crash session with logging

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="${HOME}/crash_logs"
LOG_FILE="${LOG_DIR}/crash_session_${TIMESTAMP}.log"

# Load configuration
CONFIG_FILE="${HOME}/.crash_analyzer.conf"
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
else
    echo "Error: No configuration file found at $CONFIG_FILE"
    echo "Run crash_config.sh set first"
    exit 1
fi

# Create log directory
mkdir -p "$LOG_DIR"

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Starting crash analysis session...${NC}"
echo "Logging to: $LOG_FILE"
echo ""

# Create crash command script
CRASH_SCRIPT=$(mktemp)
cat > "$CRASH_SCRIPT" << 'CRASH_EOF'
# Automated initial analysis
sys
log | tail -100
bt
ps
kmem -i
exit
CRASH_EOF

# Run crash and capture output
{
    echo "==================================="
    echo "Crash Analysis Session"
    echo "Timestamp: $(date)"
    echo "==================================="
    echo ""
    echo "Configuration:"
    echo "  VMLINUX: $VMLINUX_PATH"
    echo "  VMCORE:  $VMCORE_PATH"
    echo "  CRASH:   $CRASH_CMD"
    echo ""
    echo "==================================="
    echo ""
    
    # Prepare execution environment
    TARGET_DIR=$(dirname "$VMCORE_PATH")
    VMCORE_FILE=$(basename "$VMCORE_PATH")
    VMLINUX_DIR=$(dirname "$VMLINUX_PATH")
    VMLINUX_FILE=$(basename "$VMLINUX_PATH")

    # If vmlinux is in the same directory, use relative path
    if [ "$VMLINUX_DIR" == "$TARGET_DIR" ]; then
        FINAL_VMLINUX="./$VMLINUX_FILE"
    else
        FINAL_VMLINUX="$VMLINUX_PATH"
    fi
    FINAL_VMCORE="./$VMCORE_FILE"

    echo "Working Directory: $TARGET_DIR"
    echo "Command: $CRASH_CMD $FINAL_VMLINUX $FINAL_VMCORE"
    
    cd "$TARGET_DIR" || exit 1
    "$CRASH_CMD" "$FINAL_VMLINUX" "$FINAL_VMCORE" < "$CRASH_SCRIPT" 2>&1
    
} | tee "$LOG_FILE"

# Cleanup
rm -f "$CRASH_SCRIPT"

echo ""
echo -e "${GREEN}Session log saved to: $LOG_FILE${NC}"
echo -e "${YELLOW}Review the log file for detailed analysis${NC}"

# Generate summary
echo ""
echo "Quick Summary:"
grep -E "PANIC:|Oops|BUG:|WARNING:" "$LOG_FILE" || echo "  No panic/oops messages found"
