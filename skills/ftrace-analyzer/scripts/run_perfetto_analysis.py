import os
import re
from perfetto.trace_processor import TraceProcessor

TRACE_PATH = '/opt/src/LogixAgent/logs/ftrace/trace.log'
# SQL_FILE = '/opt/src/perfetto/ftrace.sql' # Original path
# Use relative path to the SQL file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_FILE = os.path.join(BASE_DIR, 'perfetto_analysis.sql')

TP_BIN = os.path.join(BASE_DIR, 'trace_processor')

# Set environment variable for custom binary path if supported by the lib
os.environ["PERFETTO_BINARY_PATH"] = TP_BIN

def parse_sql_file(file_path):
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    queries = []
    current_sql = []
    current_desc = "Start"
    
    for line in lines:
        if line.strip().startswith('-- Scenario'):
            # If we have accumulated SQL, save it
            if current_sql:
                full_sql = '\n'.join(current_sql).strip()
                if full_sql:
                    queries.append({'desc': current_desc, 'sql': full_sql})
            
            # Start new block
            current_desc = line.strip()
            current_sql = [line] # Include the scenario line as comment in SQL
        else:
            current_sql.append(line)
            if "Analysis Goal" in line:
                current_desc += " | " + line.strip()
                
    # Add the last block
    if current_sql:
        full_sql = '\n'.join(current_sql).strip()
        if full_sql:
             queries.append({'desc': current_desc, 'sql': full_sql})
            
    return queries

def main():
    print(f"Loading trace: {TRACE_PATH}")
    try:
        # Try using file_path argument if trace argument fails, or vice versa.
        # Based on error "Did you mean 'file_path'?", it likely wants file_path for the trace.
        tp = TraceProcessor(file_path=TRACE_PATH)
    except Exception as e:
        print(f"Failed to load trace processor: {e}")
        # Fallback: try without bin_path if the lib handles it, or check if bin exists
        return

    queries = parse_sql_file(SQL_FILE)
    print(f"Found {len(queries)} scenarios.")

    success_count = 0
    failure_count = 0

    for i, q in enumerate(queries, 1):
        print(f"\n[{i}/30] Executing Scenario: {q['desc']}")
        # print(f"SQL: {q['sql'][:50]}...")
        
        try:
            # We need to execute statements. 
            # Some scenarios have INCLUDE PERFETTO MODULE; followed by SELECT.
            # tp.query() usually expects a single query.
            # We might need to split by ';' if there are multiple statements.
            
            stmts = [s.strip() for s in q['sql'].split(';') if s.strip()]
            
            for stmt in stmts:
                if stmt.upper().startswith('INCLUDE'):
                    # It's a module include, just run it
                    tp.query(stmt)
                else:
                    # It's likely the SELECT
                    try:
                        result = tp.query(stmt)
                        # Iterate to get results without pandas
                        rows = []
                        for row in result:
                            rows.append(row)
                            if len(rows) >= 3:
                                break
                        
                        # Count total (might need to iterate all if we want count)
                        # But for verification, just checking if it runs is enough.
                        # If we want count, we must iterate all.
                        count = len(rows) 
                        # Continue iterating to count rest if needed, but let's just say "at least X" or verify no error.
                        # Actually, let's just print the first few.
                        
                        print(f"Result (first {len(rows)} rows):")
                        for r in rows:
                            print(r)
                            
                    except Exception as e:
                         # If the error is about pandas, handle it. 
                         # But tp.query() itself shouldn't require pandas.
                         # The previous error was specifically calling as_pandas_dataframe().
                         raise e
            
            success_count += 1
            
        except Exception as e:
            print(f"FAILED: {e}")
            failure_count += 1

    print(f"\nExecution Summary: Success={success_count}, Failed={failure_count}")
    tp.close()

if __name__ == "__main__":
    main()
