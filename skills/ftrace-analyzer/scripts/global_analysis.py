#!/usr/bin/env python3
import os
import sys
import argparse
import time
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Any

# Try to import perfetto, if not available, print error
try:
    from perfetto.trace_processor import TraceProcessor
except ImportError:
    print("Error: 'perfetto' python module is not installed. Please install it using 'pip install perfetto'.")
    sys.exit(1)

# Default paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TP_BIN = os.path.join(BASE_DIR, 'trace_processor')
DEFAULT_SQL_FILE = os.path.join(BASE_DIR, 'perfetto_analysis.sql')

def parse_sql_file(file_path: str) -> List[Dict[str, str]]:
    """Parses the SQL file into a list of scenarios."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"SQL file not found: {file_path}")

    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    queries = []
    current_sql = []
    current_desc = "Unknown Scenario"
    
    for line in lines:
        if line.strip().startswith('-- Scenario'):
            if current_sql:
                full_sql = '\n'.join(current_sql).strip()
                if full_sql:
                    queries.append({'desc': current_desc, 'sql': full_sql})
            
            current_desc = line.strip()
            current_sql = [line]
        else:
            current_sql.append(line)
            if "Analysis Goal" in line:
                current_desc += " | " + line.strip()
                
    if current_sql:
        full_sql = '\n'.join(current_sql).strip()
        if full_sql:
             queries.append({'desc': current_desc, 'sql': full_sql})
            
    return queries

def execute_queries_worker(trace_path: str, tp_bin: str, queries: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Worker function to execute a batch of queries on a single TraceProcessor instance."""
    results = []
    
    # Set environment variable for the binary path
    os.environ["PERFETTO_BINARY_PATH"] = tp_bin
    
    try:
        tp = TraceProcessor(file_path=trace_path)
    except Exception as e:
        return [{'desc': q['desc'], 'error': f"Failed to load trace: {str(e)}"} for q in queries]

    for q in queries:
        desc = q['desc']
        sql = q['sql']
        result_data = None
        error_msg = None
        
        try:
            # Handle multiple statements (e.g., INCLUDE MODULE)
            stmts = [s.strip() for s in sql.split(';') if s.strip()]
            query_rows = []
            
            for stmt in stmts:
                if stmt.upper().startswith('INCLUDE'):
                    tp.query(stmt)
                else:
                    # Execute query and fetch results
                    res_iter = tp.query(stmt)
                    # Convert iterator to list of dicts (if possible) or tuples
                    # The python api returns an iterator of specialized row objects
                    # We convert them to simple dicts or lists for serialization
                    
                    # Try to get column names if possible, but the API might just give values
                    # We will store as list of lists for simplicity if dict not available
                    current_rows = []
                    for row in res_iter:
                        # row is usually a confusing object, let's try to convert to dict
                        try:
                            row_dict = row.__dict__
                            # Filter out internal fields if any
                            clean_row = {k: v for k, v in row_dict.items() if not k.startswith('_')}
                            current_rows.append(clean_row)
                        except:
                            current_rows.append(str(row))
                            
                    if current_rows:
                        query_rows = current_rows # Keep the last SELECT result

            result_data = query_rows
            
        except Exception as e:
            error_msg = str(e)
            
        results.append({
            'desc': desc,
            'data': result_data,
            'error': error_msg
        })

    tp.close()
    return results

def generate_report(results: List[Dict[str, Any]], output_stream, trace_file: str):
    """Generates a Markdown report from the results."""
    f = output_stream
    f.write(f"# Ftrace Global Analysis Report\n\n")
    f.write(f"**Trace File:** `{trace_file}`\n")
    f.write(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    
    f.write("## Analysis Summary\n")
    success_count = sum(1 for r in results if not r.get('error'))
    f.write(f"- Total Scenarios: {len(results)}\n")
    f.write(f"- Successful: {success_count}\n")
    f.write(f"- Failed: {len(results) - success_count}\n\n")
    
    f.write("## Detailed Results\n\n")
    
    for res in results:
        desc = res['desc']
        data = res.get('data')
        error = res.get('error')
        
        f.write(f"### {desc}\n\n")
        
        if error:
            f.write(f"**Status:** ❌ Error\n")
            f.write(f"```\n{error}\n```\n")
        elif not data:
            f.write(f"**Status:** ⚠️ No Data Found\n")
            f.write("_The query executed successfully but returned no results._\n")
        else:
            f.write(f"**Status:** ✅ Found {len(data)} rows\n")
            
            # Render table for first few rows
            if isinstance(data, list) and len(data) > 0:
                # Check if it's a list of dicts
                if isinstance(data[0], dict):
                    headers = list(data[0].keys())
                    f.write("| " + " | ".join(headers) + " |\n")
                    f.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
                    
                    for row in data[:20]: # Limit to top 20 rows
                        vals = [str(row.get(h, '')) for h in headers]
                        f.write("| " + " | ".join(vals) + " |\n")
                    
                    if len(data) > 20:
                        f.write(f"\n_... {len(data) - 20} more rows hidden ..._\n")
                else:
                    f.write("```\n")
                    for row in data[:20]:
                        f.write(f"{row}\n")
                    f.write("```\n")
        
        f.write("\n---\n")

def main():
    parser = argparse.ArgumentParser(description="Global Ftrace Analysis Overview")
    parser.add_argument("trace_file", help="Path to the ftrace/perfetto trace file")
    parser.add_argument("--sql_file", default=DEFAULT_SQL_FILE, help="Path to the SQL analysis file")
    parser.add_argument("--tp_bin", default=DEFAULT_TP_BIN, help="Path to trace_processor binary")
    parser.add_argument("--output_dir", default=".", help="Directory to save the report")
    parser.add_argument("--jobs", type=int, default=4, help="Number of parallel jobs (default: 4)")
    parser.add_argument("--force", action="store_true", help="Force re-analysis even if report exists")
    parser.add_argument("--stdout", action="store_true", help="Print report to stdout instead of saving to file")
    
    args = parser.parse_args()
    
    trace_path = os.path.abspath(args.trace_file)
    output_dir = os.path.abspath(args.output_dir)
    
    if not os.path.exists(trace_path):
        print(f"Error: Trace file not found: {trace_path}", file=sys.stderr)
        sys.exit(1)
        
    # Determine output filename
    trace_name = os.path.basename(trace_path)
    report_file = os.path.join(output_dir, f"report_{trace_name}.md")
    
    # Check cache (only if not writing to stdout)
    if not args.stdout and os.path.exists(report_file) and not args.force:
        # Check if trace file is newer than report
        trace_mtime = os.path.getmtime(trace_path)
        report_mtime = os.path.getmtime(report_file)
        
        if report_mtime > trace_mtime:
            print(f"Report already exists and is up-to-date: {report_file}", file=sys.stderr)
            print("Skipping analysis. Use --force to override.", file=sys.stderr)
            sys.exit(0)
            
    # Redirect logs to stderr if printing report to stdout
    log_file = sys.stderr if args.stdout else sys.stdout
            
    print(f"Starting Global Analysis for: {trace_path}", file=log_file)
    print(f"Using SQL file: {args.sql_file}", file=log_file)
    
    # Parse queries
    try:
        queries = parse_sql_file(args.sql_file)
        print(f"Loaded {len(queries)} scenarios.", file=log_file)
    except Exception as e:
        print(f"Error parsing SQL file: {e}", file=sys.stderr)
        sys.exit(1)
        
    # Distribute queries to workers
    # To avoid loading the trace too many times, we want each worker to process a chunk of queries.
    # If we have N jobs, we split queries into N chunks.
    
    num_jobs = min(args.jobs, len(queries))
    chunk_size = (len(queries) + num_jobs - 1) // num_jobs
    chunks = [queries[i:i + chunk_size] for i in range(0, len(queries), chunk_size)]
    
    print(f"Processing with {len(chunks)} parallel workers...", file=log_file)
    
    all_results = []
    
    with ProcessPoolExecutor(max_workers=num_jobs) as executor:
        futures = [
            executor.submit(execute_queries_worker, trace_path, args.tp_bin, chunk)
            for chunk in chunks
        ]
        
        for future in as_completed(futures):
            try:
                chunk_results = future.result()
                all_results.extend(chunk_results)
            except Exception as e:
                print(f"Worker failed: {e}", file=sys.stderr)
                
    # Sort results to match original order (optional but nice)
    # We can use the description prefix "Scenario X" to sort if available, or just map back
    # For now, let's just sort by description string
    all_results.sort(key=lambda x: x['desc'])
    
    # Generate Report
    try:
        if args.stdout:
            generate_report(all_results, sys.stdout, trace_path)
        else:
            with open(report_file, 'w') as f:
                generate_report(all_results, f, trace_path)
            print(f"Analysis complete. Report saved to: {report_file}", file=log_file)
    except Exception as e:
        print(f"Failed to generate report: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
