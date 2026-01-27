import os
import re
import argparse
from datetime import datetime, timedelta, timezone

def parse_ftrace_line(line):
    """
    解析 ftrace 日志行。
    格式示例: <idle>-0 [005] d.... 7541.834045: sched_switch: ...
    """
    # 匹配任务名-PID, CPU号, 标志位, 时间戳, 函数/消息
    pattern = r"^\s*(?P<task>.*?)-(?P<pid>\d+)\s+\[(?P<cpu>\d+)\]\s+(?P<flags>.{5})\s+(?P<timestamp>[\d.]+):\s+(?P<message>.*)$"
    match = re.match(pattern, line)
    if match:
        return match.groupdict()
    return None

def format_as_kernel_log(ftrace_data, base_dt):
    """
    转换为类似 kernel.log 的文本格式:
    TIMESTAMP MESSAGE
    示例: 2026-01-09T10:30:20Z ftrace: [CPU 005] <idle>-0: sched_switch: ...
    """
    timestamp_s = float(ftrace_data['timestamp'])
    # 将 ftrace 相对秒数加到基准时间上
    event_dt = base_dt + timedelta(seconds=timestamp_s)
    
    # 格式化时间为 ISO 8601 格式 (Z 表示 UTC)
    ts_str = event_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    tag = "ftrace"
    
    # 组装消息
    task_info = f"{ftrace_data['task']}-{ftrace_data['pid']}"
    cpu_info = f"[CPU {ftrace_data['cpu']}]"
    
    return f"{ts_str} {tag}: {cpu_info} {task_info}: {ftrace_data['message']}"

def main():
    parser = argparse.ArgumentParser(description="将 ftrace 日志转换为 kernel.log 文本格式")
    parser.add_argument("--input", default="/opt/src/LogixAgent/logs/ftrace/trace.log", help="输入的 ftrace 日志路径")
    parser.add_argument("--output", default="/opt/src/LogixAgent/transform/ftrace_rca.log", help="输出的 RCA Log 路径")
    parser.add_argument("--base_time", default="2026-01-09T10:38:15Z", help="基准 ISO 时间戳")
    
    args = parser.parse_args()

    # 解析基准时间
    base_dt = datetime.fromisoformat(args.base_time.replace('Z', '+00:00'))

    print(f"开始转换: {args.input} -> {args.output}")

    count = 0
    with open(args.input, 'r', encoding='utf-8') as fin, \
         open(args.output, 'w', encoding='utf-8') as fout:
        
        # 写入第一行 window 信息（模仿 kernel.log）
        window_start = args.base_time
        # 假设窗口为 30 分钟
        window_end_dt = base_dt + timedelta(minutes=30)
        window_end = window_end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        fout.write(f"window={window_start}-{window_end} start_utc={window_start} end_utc={window_end} tag=ftrace_transform\n")

        for line in fin:
            if line.startswith('#') or not line.strip():
                continue
            
            if line.startswith('#####') or 'buffer started' in line:
                continue

            ftrace_data = parse_ftrace_line(line)
            if not ftrace_data:
                continue

            log_line = format_as_kernel_log(ftrace_data, base_dt)
            fout.write(log_line + '\n')
            count += 1

    print(f"转换完成，共处理 {count} 条记录。")

if __name__ == "__main__":
    main()
