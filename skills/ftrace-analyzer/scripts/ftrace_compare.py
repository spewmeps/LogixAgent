#!/usr/bin/env python3
"""
ftrace Comparison Tool
Compares two ftrace files (baseline vs problem) to identify differences.
"""

import sys
import argparse
import re
from collections import Counter, defaultdict


def parse_ftrace_line(line):
    """Parse a single ftrace line and extract key information."""
    try:
        parts = line.split()
        if len(parts) < 5:
            return None
        
        task_pid = parts[0]
        cpu = parts[1].strip('[]')
        timestamp = float(parts[3].rstrip(':'))
        event = parts[4].rstrip(':')
        details = ' '.join(parts[5:])
        
        if '-' in task_pid:
            task_name, pid = task_pid.rsplit('-', 1)
            pid = pid.strip('>')
        else:
            task_name, pid = task_pid, '0'
        
        return {
            'task_name': task_name,
            'pid': pid,
            'cpu': cpu,
            'timestamp': timestamp,
            'event': event,
            'details': details
        }
    except (ValueError, IndexError):
        return None


def extract_field(details, field_name):
    """Extract a specific field from event details."""
    pattern = rf'{field_name}=([^\s]+)'
    match = re.search(pattern, details)
    return match.group(1) if match else None


def analyze_file(lines):
    """Analyze a single ftrace file."""
    stats = {
        'total_lines': len(lines),
        'valid_events': 0,
        'duration': 0,
        'events': Counter(),
        'threads_switches': Counter(),
        'threads_wakeups': Counter(),
        'cpus': Counter(),
        'blocking': Counter(),
        'states': defaultdict(Counter),
        'migrations': 0
    }
    
    timestamps = []
    
    for line in lines:
        parsed = parse_ftrace_line(line)
        if not parsed:
            continue
        
        stats['valid_events'] += 1
        stats['events'][parsed['event']] += 1
        stats['cpus'][parsed['cpu']] += 1
        timestamps.append(parsed['timestamp'])
        
        if parsed['event'] == 'sched_switch':
            next_comm = extract_field(parsed['details'], 'next_comm')
            prev_comm = extract_field(parsed['details'], 'prev_comm')
            prev_state = extract_field(parsed['details'], 'prev_state')
            
            if next_comm:
                stats['threads_switches'][next_comm] += 1
            
            if prev_comm and prev_state:
                stats['states'][prev_comm][prev_state] += 1
                if prev_state == 'D':
                    stats['blocking'][prev_comm] += 1
        
        elif parsed['event'] == 'sched_waking':
            comm = extract_field(parsed['details'], 'comm')
            if comm:
                stats['threads_wakeups'][comm] += 1
        
        elif parsed['event'] == 'sched_migrate_task':
            stats['migrations'] += 1
    
    if timestamps:
        stats['duration'] = max(timestamps) - min(timestamps)
    
    return stats


def compare_counters(counter1, counter2, name, top_n=10):
    """Compare two counters and show differences."""
    print(f"\n{'='*70}")
    print(f"{name}")
    print(f"{'='*70}")
    
    # Get all keys from both counters
    all_keys = set(counter1.keys()) | set(counter2.keys())
    
    # Calculate differences
    differences = []
    for key in all_keys:
        val1 = counter1.get(key, 0)
        val2 = counter2.get(key, 0)
        diff = val2 - val1
        pct_change = ((val2 - val1) / val1 * 100) if val1 > 0 else (100 if val2 > 0 else 0)
        
        differences.append((key, val1, val2, diff, pct_change))
    
    # Sort by absolute difference
    differences.sort(key=lambda x: abs(x[3]), reverse=True)
    
    # Print header
    print(f"{'Item':<30} {'Baseline':<12} {'Problem':<12} {'Change':<12} {'% Change':<10}")
    print('-' * 70)
    
    # Print top differences
    for item, val1, val2, diff, pct in differences[:top_n]:
        arrow = "🔺" if diff > 0 else ("🔻" if diff < 0 else "➡️")
        pct_str = f"{pct:+.1f}%" if abs(pct) < 9999 else "NEW" if val1 == 0 else "GONE"
        print(f"{item:<30} {val1:<12,} {val2:<12,} {diff:+12,} {arrow} {pct_str:<10}")


def print_summary(stats1, stats2, label1, label2):
    """Print summary comparison."""
    print("\n" + "="*70)
    print(f"COMPARISON SUMMARY: {label1} vs {label2}")
    print("="*70)
    
    metrics = [
        ("Total Events", stats1['valid_events'], stats2['valid_events']),
        ("Duration (sec)", f"{stats1['duration']:.2f}", f"{stats2['duration']:.2f}"),
        ("Unique Threads", len(stats1['threads_switches']), len(stats2['threads_switches'])),
        ("Active CPUs", len(stats1['cpus']), len(stats2['cpus'])),
        ("Total Switches", sum(stats1['threads_switches'].values()), sum(stats2['threads_switches'].values())),
        ("Total Wakeups", sum(stats1['threads_wakeups'].values()), sum(stats2['threads_wakeups'].values())),
        ("D-state Count", sum(stats1['blocking'].values()), sum(stats2['blocking'].values())),
        ("Migrations", stats1['migrations'], stats2['migrations']),
    ]
    
    print(f"\n{'Metric':<25} {label1:<20} {label2:<20} {'Change':<15}")
    print("-" * 70)
    
    for metric, val1, val2 in metrics:
        if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
            diff = val2 - val1
            pct = (diff / val1 * 100) if val1 > 0 else 0
            val1_str = f"{val1:,.0f}" if isinstance(val1, int) else f"{val1}"
            val2_str = f"{val2:,.0f}" if isinstance(val2, int) else f"{val2}"
            change_str = f"{diff:+,.0f} ({pct:+.1f}%)"
        else:
            val1_str = str(val1)
            val2_str = str(val2)
            change_str = "-"
        
        print(f"{metric:<25} {val1_str:<20} {val2_str:<20} {change_str:<15}")


def generate_html_comparison(stats1, stats2, label1, label2, output_file):
    """Generate HTML comparison report."""
    from datetime import datetime
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>ftrace Comparison Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ecf0f1;
        }}
        th {{
            background: #34495e;
            color: white;
        }}
        .increase {{
            color: #e74c3c;
        }}
        .decrease {{
            color: #27ae60;
        }}
        .neutral {{
            color: #95a5a6;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔬 ftrace Comparison Report</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>Baseline:</strong> {label1} | <strong>Problem:</strong> {label2}</p>
        
        <h2>Summary Metrics</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>{label1}</th>
                <th>{label2}</th>
                <th>Change</th>
            </tr>
"""
    
    # Add summary metrics
    metrics = [
        ("Total Events", stats1['valid_events'], stats2['valid_events']),
        ("Duration", f"{stats1['duration']:.2f}s", f"{stats2['duration']:.2f}s"),
        ("Context Switches", sum(stats1['threads_switches'].values()), sum(stats2['threads_switches'].values())),
        ("Wake-ups", sum(stats1['threads_wakeups'].values()), sum(stats2['threads_wakeups'].values())),
        ("D-state Count", sum(stats1['blocking'].values()), sum(stats2['blocking'].values())),
        ("Migrations", stats1['migrations'], stats2['migrations']),
    ]
    
    for metric, val1, val2 in metrics:
        if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
            diff = val2 - val1
            pct = (diff / val1 * 100) if val1 > 0 else 0
            css_class = "increase" if diff > 0 else ("decrease" if diff < 0 else "neutral")
            change = f'<span class="{css_class}">{diff:+,} ({pct:+.1f}%)</span>'
            val1_str = f"{val1:,}"
            val2_str = f"{val2:,}"
        else:
            val1_str = str(val1)
            val2_str = str(val2)
            change = "-"
        
        html += f"""
            <tr>
                <td>{metric}</td>
                <td>{val1_str}</td>
                <td>{val2_str}</td>
                <td>{change}</td>
            </tr>
"""
    
    html += """
        </table>
        
        <h2>Top Changes in Context Switches</h2>
        <table>
            <tr>
                <th>Thread</th>
                <th>Baseline</th>
                <th>Problem</th>
                <th>Change</th>
            </tr>
"""
    
    # Top switch changes
    all_threads = set(stats1['threads_switches'].keys()) | set(stats2['threads_switches'].keys())
    switch_diffs = []
    for thread in all_threads:
        val1 = stats1['threads_switches'].get(thread, 0)
        val2 = stats2['threads_switches'].get(thread, 0)
        diff = val2 - val1
        switch_diffs.append((thread, val1, val2, diff))
    
    switch_diffs.sort(key=lambda x: abs(x[3]), reverse=True)
    
    for thread, val1, val2, diff in switch_diffs[:15]:
        pct = (diff / val1 * 100) if val1 > 0 else 100
        css_class = "increase" if diff > 0 else ("decrease" if diff < 0 else "neutral")
        html += f"""
            <tr>
                <td>{thread}</td>
                <td>{val1:,}</td>
                <td>{val2:,}</td>
                <td class="{css_class}">{diff:+,} ({pct:+.1f}%)</td>
            </tr>
"""
    
    html += """
        </table>
    </div>
</body>
</html>
"""
    
    with open(output_file, 'w') as f:
        f.write(html)


def main():
    parser = argparse.ArgumentParser(
        description='Compare two ftrace log files',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('baseline', help='Baseline ftrace log file')
    parser.add_argument('problem', help='Problem/comparison ftrace log file')
    parser.add_argument('--output', help='Output HTML comparison report')
    parser.add_argument('--top', type=int, default=15, help='Number of top items to show')
    
    args = parser.parse_args()
    
    # Read files
    print(f"Reading baseline file: {args.baseline}")
    try:
        with open(args.baseline, 'r') as f:
            baseline_lines = f.readlines()
    except (FileNotFoundError, IOError) as e:
        print(f"Error reading baseline file: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Reading problem file: {args.problem}")
    try:
        with open(args.problem, 'r') as f:
            problem_lines = f.readlines()
    except (FileNotFoundError, IOError) as e:
        print(f"Error reading problem file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Analyze both files
    print("\nAnalyzing baseline...")
    baseline_stats = analyze_file(baseline_lines)
    
    print("Analyzing problem file...")
    problem_stats = analyze_file(problem_lines)
    
    # Print comparisons
    print_summary(baseline_stats, problem_stats, "Baseline", "Problem")
    
    compare_counters(baseline_stats['threads_switches'], 
                    problem_stats['threads_switches'],
                    "Context Switches (Top Changes)",
                    args.top)
    
    compare_counters(baseline_stats['threads_wakeups'],
                    problem_stats['threads_wakeups'],
                    "Wake-ups (Top Changes)",
                    args.top)
    
    compare_counters(baseline_stats['blocking'],
                    problem_stats['blocking'],
                    "D-state / Blocking (Top Changes)",
                    args.top)
    
    compare_counters(baseline_stats['cpus'],
                    problem_stats['cpus'],
                    "CPU Utilization (Top Changes)",
                    min(args.top, 20))
    
    # Generate HTML if requested
    if args.output:
        print(f"\nGenerating HTML report: {args.output}")
        generate_html_comparison(baseline_stats, problem_stats, 
                                "Baseline", "Problem", args.output)
        print("HTML report generated successfully!")
    
    print("\n" + "="*70)
    print("Comparison complete!")
    print("="*70 + "\n")


if __name__ == '__main__':
    main()
