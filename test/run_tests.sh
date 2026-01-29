#!/bin/bash

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# 核心脚本目录
CORE_SCRIPTS_DIR="/opt/src/LogixAgent/skills/ftrace-analyzer/scripts"

# 设置 PYTHONPATH 确保可以找到模块
export PYTHONPATH=$PYTHONPATH:$CORE_SCRIPTS_DIR

echo "===================================================="
echo "开始执行 Ftrace Analyzer 综合测试"
echo "测试脚本位置: $SCRIPT_DIR"
echo "核心脚本位置: $CORE_SCRIPTS_DIR"
echo "测试数据源: /opt/src/LogixAgent/logs/ftrace/trace.log (回退: /opt/src/LogixAgent/logs/agent.log)"
echo "===================================================="

# 检查日志文件是否存在
LOG_FILE="/opt/src/LogixAgent/logs/agent.log"
if [ ! -f "$LOG_FILE" ]; then
    echo "警告: $LOG_FILE 不存在，将创建一个空文件进行测试。"
    mkdir -p $(dirname "$LOG_FILE")
    touch "$LOG_FILE"
fi

# 临时修复相对导入问题以进行测试
cd $CORE_SCRIPTS_DIR
sed -i 's/from \.ftrace/from ftrace/g' ftrace_file.py ftrace_analyzer.py ftrace_query.py main.py

# 执行 Python 测试脚本
cd $SCRIPT_DIR
python3 test_ftrace_analyzer.py -v

# 还原相对导入
cd $CORE_SCRIPTS_DIR
sed -i 's/from ftrace/from .ftrace/g' ftrace_file.py ftrace_analyzer.py ftrace_query.py main.py

echo "===================================================="
echo "测试执行完毕"
echo "===================================================="
