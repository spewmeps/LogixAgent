import sys
import argparse
import json
import os
try:
    # 作为包运行时（python -m skills.ftrace-analyzer.scripts.main）
    from .ftrace_file import TraceFile
    from .ftrace_analyzer import Analyzer
except (ImportError, ValueError):
    # 作为单文件脚本运行时（python scripts/main.py）
    from ftrace_file import TraceFile
    from ftrace_analyzer import Analyzer

def main():
    parser = argparse.ArgumentParser(description='Ftrace Parser & Analyzer Tool')
    parser.add_argument('logfile', help='Path to ftrace log file')
    parser.add_argument('--summary', action='store_true', help='Show text summary')
    parser.add_argument('--info', action='store_true', help='Show JSON metadata')
    parser.add_argument('--analyze-gaps', type=float, metavar='MS', help='Detect time gaps larger than MS')
    parser.add_argument('--classify', action='store_true', help='Classify contexts')
    parser.add_argument('--stats', type=str, metavar='COMM', help='Get scheduling stats for a process name')
    parser.add_argument('--check-pid', type=int, metavar='PID', help='Check specific PID running status')
    parser.add_argument('--query-pid', type=int, metavar='PID', help='Query events for a specific PID')
    parser.add_argument('--query-comm', type=str, metavar='COMM', help='Query events for a specific process name')
    parser.add_argument('--query-cpu', type=int, metavar='CPU', help='Query events for a specific CPU')
    parser.add_argument('--time-range', type=float, nargs=2, metavar=('START', 'END'), help='Limit time range')
    parser.add_argument('--limit', type=int, default=10, help='Limit output rows')
    parser.add_argument('--export-json', type=str, help='Export query results to JSON file')
    parser.add_argument('--export-csv', type=str, help='Export query results to CSV file')

    args = parser.parse_args()
    
    # 确保日志文件路径是绝对路径，增强路径无关性
    log_path = os.path.abspath(args.logfile)
    
    try:
        trace = TraceFile(log_path)
        
        if args.info:
            print(json.dumps(trace.info(), indent=2))

        if args.summary:
            print(trace.summary())
            
        if args.analyze_gaps is not None:
            analyzer = Analyzer(trace)
            print(json.dumps(analyzer.detect_time_anomalies(args.analyze_gaps), indent=2))
            
        if args.classify:
            analyzer = Analyzer(trace)
            print(json.dumps(analyzer.classify_contexts(), indent=2))
            
        if args.stats:
            analyzer = Analyzer(trace)
            print(json.dumps(analyzer.get_process_scheduling_stats(comm=args.stats), indent=2))
            
        if args.check_pid:
            analyzer = Analyzer(trace)
            # 使用 check_process_running，如果提供了时间范围则传入
            tr = tuple(args.time_range) if args.time_range else None
            print(json.dumps(analyzer.check_process_running(pid=args.check_pid, time_range=tr), indent=2))
            
        # 查询处理
        if any([args.query_pid, args.query_comm, args.query_cpu, args.time_range]):
            query = trace.query()
            if args.query_pid: query.pid(args.query_pid)
            if args.query_comm: query.comm(args.query_comm)
            if args.query_cpu is not None: query.cpu(args.query_cpu)
            if args.time_range: query.time_range(*args.time_range)
            
            result = query.limit(args.limit).execute()
            print(result.describe())
            
            if args.export_json:
                with open(args.export_json, 'w') as f:
                    f.write(result.to_json())
                print(f"Exported to {args.export_json}")
            elif args.export_csv:
                result.to_csv(args.export_csv)
                print(f"Exported to {args.export_csv}")
            else:
                for e in result:
                    print(e)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
        
    return 0

if __name__ == '__main__':
    sys.exit(main())
