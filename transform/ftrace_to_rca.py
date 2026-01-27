import os
import re
import argparse
import time
from datetime import datetime, timedelta

# 预编译正则表达式以提高性能
FTRACE_PATTERN = re.compile(
    r"^\s*(?P<task>.*?)-(?P<pid>\d+)\s+\[(?P<cpu>\d+)\]\s+(?P<flags>\S{4,5})\s+(?P<timestamp>[\d.]+):\s+(?P<message>.*)$"
)

def main():
    parser = argparse.ArgumentParser(description="将 ftrace 日志转换为 kernel.log 文本格式 (高性能版)")
    parser.add_argument("--input", default="/opt/src/LogixAgent/logs/ftrace/trace.log", help="输入的 ftrace 日志路径")
    parser.add_argument("--output", default="/opt/src/LogixAgent/transform/ftrace_rca.log", help="输出的 RCA Log 路径")
    parser.add_argument("--base_time", default="2026-01-09T10:38:15Z", help="基准 ISO 时间戳")
    
    args = parser.parse_args()

    # 解析基准时间
    base_dt = datetime.fromisoformat(args.base_time.replace('Z', '+00:00'))

    if not os.path.exists(args.input):
        print(f"错误: 输入文件不存在: {args.input}")
        return

    file_size = os.path.getsize(args.input)
    print(f"开始转换: {args.input} ({file_size / 1024 / 1024:.2f} MB) -> {args.output}")

    count = 0
    start_time = time.time()
    
    # 写入第一行 window 信息
    window_start = args.base_time
    window_end_dt = base_dt + timedelta(minutes=30)
    window_end = window_end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 使用较大的缓冲区 (8MB) 提高 I/O 性能
    with open(args.input, 'r', encoding='utf-8', buffering=8*1024*1024) as fin, \
         open(args.output, 'w', encoding='utf-8', buffering=8*1024*1024) as fout:
        
        fout.write(f"window={window_start}-{window_end} start_utc={window_start} end_utc={window_end} tag=ftrace_transform\n")

        # 为了极致性能，将循环内的逻辑尽量展平，减少函数调用
        for line in fin:
            # 快速过滤非数据行
            if not line or line[0] == '#' or line[0] == '\n':
                continue
            
            # 进一步过滤不常见的特殊行
            if line[0] == ' ' and ('buffer started' in line or line.startswith('     ')):
                continue

            match = FTRACE_PATTERN.match(line)
            if not match:
                continue

            data = match.groupdict()
            
            # 时间转换优化：避免在循环中重复创建 timedelta 对象（可选，但这里 timestamp_s 是变的）
            timestamp_s = float(data['timestamp'])
            event_dt = base_dt + timedelta(seconds=timestamp_s)
            ts_str = event_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            # 组装输出行
            fout.write(f"{ts_str} ftrace: [CPU {data['cpu']}] {data['task']}-{data['pid']}: {data['message']}\n")
            
            count += 1
            # 每 100,000 行打印一次进度
            if count % 100000 == 0:
                elapsed = time.time() - start_time
                speed = count / elapsed if elapsed > 0 else 0
                print(f"已处理 {count} 条记录... 当前速度: {speed:.0f} 条/秒")

    end_time = time.time()
    duration = end_time - start_time
    print(f"转换完成！")
    print(f"总处理记录: {count}")
    print(f"总耗时: {duration:.2f} 秒")
    if duration > 0:
        print(f"平均速度: {count / duration:.0f} 条/秒")

if __name__ == "__main__":
    main()
