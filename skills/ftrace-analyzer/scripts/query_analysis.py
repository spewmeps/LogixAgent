#!/usr/bin/env python3
import os
import sys
import argparse
try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from perfetto.trace_processor import TraceProcessor
except ImportError:
    print("Error: 'perfetto' python module is not installed. Please install it using 'pip install perfetto'.")
    sys.exit(1)

# Default paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TP_BIN = os.path.join(BASE_DIR, 'trace_processor')

def main():
    parser = argparse.ArgumentParser(description="Ad-hoc Ftrace Query Analysis")
    parser.add_argument("trace_file", help="Path to the ftrace/perfetto trace file")
    parser.add_argument("--query", "-q", help="SQL query string to execute")
    parser.add_argument("--query_file", "-f", help="Path to a file containing the SQL query")
    parser.add_argument("--tp_bin", default=DEFAULT_TP_BIN, help="Path to trace_processor binary")
    parser.add_argument("--format", choices=['table', 'csv', 'json'], default='table', help="Output format")
    
    args = parser.parse_args()
    
    # Validation
    if not args.query and not args.query_file:
        print("Error: Must provide either --query or --query_file")
        sys.exit(1)
        
    trace_path = os.path.abspath(args.trace_file)
    if not os.path.exists(trace_path):
        print(f"Error: Trace file not found: {trace_path}")
        sys.exit(1)
        
    # Get SQL
    sql = args.query
    if args.query_file:
        if not os.path.exists(args.query_file):
            print(f"Error: Query file not found: {args.query_file}")
            sys.exit(1)
        with open(args.query_file, 'r') as f:
            sql = f.read()
            
    # Set binary path
    os.environ["PERFETTO_BINARY_PATH"] = args.tp_bin
    
    print(f"Loading trace: {trace_path} ...")
    
    try:
        tp = TraceProcessor(file_path=trace_path)
    except Exception as e:
        print(f"Failed to load trace processor: {e}")
        sys.exit(1)
        
    print("Executing query...")
    try:
        # Use pandas integration for better formatting if available
        # The user environment might not have pandas installed, but standard python perfetto lib usually works well with it
        # Let's try standard query first to be safe, or check imports
        
        # Execute
        stmts = [s.strip() for s in sql.split(';') if s.strip()]
        last_result = None
        
        for stmt in stmts:
            if stmt.upper().startswith('INCLUDE'):
                tp.query(stmt)
            else:
                last_result = tp.query(stmt)
        
        if last_result:
            # Convert to list of dicts for display
            rows = []
            for row in last_result:
                try:
                    # Clean up internal fields
                    d = {k: v for k, v in row.__dict__.items() if not k.startswith('_')}
                    rows.append(d)
                except:
                    rows.append({"result": str(row)})
            
            if not rows:
                print("Query executed successfully but returned no results.")
            else:
                if args.format == 'json':
                    import json
                    print(json.dumps(rows, indent=2, default=str))
                elif args.format == 'csv':
                    if rows:
                        headers = list(rows[0].keys())
                        print(",".join(headers))
                        for r in rows:
                            print(",".join([str(r.get(h, '')) for h in headers]))
                else: # table
                    # Basic table formatting
                    if rows:
                        headers = list(rows[0].keys())
                        # Calculate widths
                        widths = {h: len(h) for h in headers}
                        for r in rows:
                            for h in headers:
                                widths[h] = max(widths[h], len(str(r.get(h, ''))))
                        
                        # Print header
                        header_line = " | ".join([h.ljust(widths[h]) for h in headers])
                        print("-" * len(header_line))
                        print(header_line)
                        print("-" * len(header_line))
                        
                        # Print rows
                        for r in rows:
                            print(" | ".join([str(r.get(h, '')).ljust(widths[h]) for h in headers]))
                        print("-" * len(header_line))
                        print(f"Total rows: {len(rows)}")
                    
    except Exception as e:
        print(f"Query Execution Failed: {e}")
        sys.exit(1)
    finally:
        tp.close()

if __name__ == "__main__":
    main()
