import argparse
import os
import sqlite3
import sys

try:
    from .ftrace_file import TraceFile
except (ImportError, ValueError):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.append(script_dir)
    from ftrace_file import TraceFile


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="build_db",
        description="Build SQLite database for an ftrace log file. "
                    "Example: python3 build_db.py /opt/src/LogixAgent/logs/ftrace/trace.log",
    )
    parser.add_argument("logfile", help="Path to ftrace log file")
    parser.add_argument("--force", action="store_true", help="Rebuild database even if it exists and is up to date")
    args = parser.parse_args()

    log_path = os.path.abspath(args.logfile)
    trace = TraceFile(log_path)
    trace.ensure_sqlite(force=args.force)
    db_path = log_path + ".sqlite"

    count = 0
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM events")
        row = cur.fetchone()
        if row:
            count = row[0]
        conn.close()
    except Exception as e:
        print(f"Failed to read events from {db_path}: {e}", file=sys.stderr)

    print(f"Log file       : {log_path}")
    print(f"SQLite DB      : {db_path}")
    print(f"Events in DB   : {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
