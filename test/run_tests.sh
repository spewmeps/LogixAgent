#!/bin/bash

TEST_DIR="/opt/src/LogixAgent/test"
LOG_FILE="$TEST_DIR/test_results.log"
TRACE_FILE="/opt/src/LogixAgent/logs/ftrace/trace.log"
SCRIPTS_DIR="/opt/src/LogixAgent/skills/ftrace-analyzer/scripts"

echo "========================================================" > "$LOG_FILE"
echo "Starting Ftrace Analysis Scripts Test Suite" >> "$LOG_FILE"
echo "Date: $(date)" >> "$LOG_FILE"
echo "Trace File: $TRACE_FILE" >> "$LOG_FILE"
echo "========================================================" >> "$LOG_FILE"

# Test 1: run_perfetto_analysis.py (Legacy/Simple Runner)
echo "" >> "$LOG_FILE"
echo "--------------------------------------------------------" >> "$LOG_FILE"
echo "[Test 1] Running run_perfetto_analysis.py..." >> "$LOG_FILE"
echo "--------------------------------------------------------" >> "$LOG_FILE"

python3 "$SCRIPTS_DIR/run_perfetto_analysis.py" >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ run_perfetto_analysis.py completed successfully." >> "$LOG_FILE"
else
    echo "❌ run_perfetto_analysis.py failed." >> "$LOG_FILE"
fi

# Test 2: global_analysis.py (Global Analysis Report - File Output)
echo "" >> "$LOG_FILE"
echo "--------------------------------------------------------" >> "$LOG_FILE"
echo "[Test 2] Running global_analysis.py (File Output Mode)..." >> "$LOG_FILE"
echo "--------------------------------------------------------" >> "$LOG_FILE"

REPORT_DIR="$TEST_DIR/reports"
mkdir -p "$REPORT_DIR"
python3 "$SCRIPTS_DIR/global_analysis.py" "$TRACE_FILE" --output_dir "$REPORT_DIR" --jobs 4 --force >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ global_analysis.py completed successfully." >> "$LOG_FILE"
    echo "Report generated at: $REPORT_DIR/report_trace.log.md" >> "$LOG_FILE"
else
    echo "❌ global_analysis.py failed." >> "$LOG_FILE"
fi

# Test 3: query_analysis.py (Ad-hoc Query)
echo "" >> "$LOG_FILE"
echo "--------------------------------------------------------" >> "$LOG_FILE"
echo "[Test 3] Running query_analysis.py (Sched Table Count)..." >> "$LOG_FILE"
echo "Query: SELECT count(*) as sched_count FROM sched" >> "$LOG_FILE"
echo "--------------------------------------------------------" >> "$LOG_FILE"

python3 "$SCRIPTS_DIR/query_analysis.py" "$TRACE_FILE" --query "SELECT count(*) as sched_count FROM sched" --format table >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ query_analysis.py completed successfully." >> "$LOG_FILE"
else
    echo "❌ query_analysis.py failed." >> "$LOG_FILE"
fi

echo "" >> "$LOG_FILE"
echo "========================================================" >> "$LOG_FILE"
echo "Test Suite Completed." >> "$LOG_FILE"
