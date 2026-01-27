#!/usr/bin/env python3
"""
ftrace HTML Report Generator
Creates a comprehensive HTML report with analysis and recommendations.
"""

import sys
import argparse
import re
from collections import Counter, defaultdict
from datetime import datetime


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


def analyze_full(lines):
    """Comprehensive analysis of ftrace data."""
    results = {
        'total_lines': len(lines),
        'valid_events': 0,
        'time_range': [float('inf'), 0],
        'events': Counter(),
        'threads': defaultdict(lambda: {'switches': 0, 'wakeups': 0, 'states': Counter()}),
        'cpus': Counter(),
        'blocking': Counter(),
        'migrations': 0
    }
    
    for line in lines:
        parsed = parse_ftrace_line(line)
        if not parsed:
            continue
        
        results['valid_events'] += 1
        results['events'][parsed['event']] += 1
        results['cpus'][parsed['cpu']] += 1
        
        # Update time range
        ts = parsed['timestamp']
        results['time_range'][0] = min(results['time_range'][0], ts)
        results['time_range'][1] = max(results['time_range'][1], ts)
        
        # Analyze by event type
        if parsed['event'] == 'sched_switch':
            next_comm = extract_field(parsed['details'], 'next_comm')
            prev_comm = extract_field(parsed['details'], 'prev_comm')
            prev_state = extract_field(parsed['details'], 'prev_state')
            
            if next_comm:
                results['threads'][next_comm]['switches'] += 1
            
            if prev_comm and prev_state:
                results['threads'][prev_comm]['states'][prev_state] += 1
                if prev_state == 'D':
                    results['blocking'][prev_comm] += 1
        
        elif parsed['event'] == 'sched_waking':
            comm = extract_field(parsed['details'], 'comm')
            if comm:
                results['threads'][comm]['wakeups'] += 1
        
        elif parsed['event'] == 'sched_migrate_task':
            results['migrations'] += 1
    
    return results


def generate_recommendations(results):
    """Generate recommendations based on analysis."""
    recommendations = []
    
    # Check for CPU imbalance
    cpu_counts = list(results['cpus'].values())
    if cpu_counts:
        avg_cpu = sum(cpu_counts) / len(cpu_counts)
        max_cpu = max(cpu_counts)
        if max_cpu > avg_cpu * 2:
            recommendations.append({
                'level': 'warning',
                'title': 'CPU Load Imbalance Detected',
                'description': f'One or more CPUs have >2x average load. Max: {max_cpu:,} vs Avg: {avg_cpu:,.0f}',
                'suggestion': 'Consider CPU pinning or rebalancing workload distribution.'
            })
    
    # Check for high blocking
    if results['blocking']:
        top_blocker, block_count = results['blocking'].most_common(1)[0]
        if block_count > 100:
            recommendations.append({
                'level': 'critical',
                'title': 'High I/O Blocking Detected',
                'description': f'Thread "{top_blocker}" blocked {block_count:,} times (D-state)',
                'suggestion': 'Investigate storage/network performance or lock contention.'
            })
    
    # Check for high migration
    if results['migrations'] > 1000:
        recommendations.append({
            'level': 'warning',
            'title': 'High Task Migration Rate',
            'description': f'{results["migrations"]:,} task migrations detected',
            'suggestion': 'Use CPU affinity (taskset/cgroups) to reduce migrations.'
        })
    
    # Check for specific KVM/QEMU patterns
    kvm_threads = [t for t in results['threads'] if 'KVM' in t or 'qemu' in t]
    if kvm_threads:
        total_switches = sum(results['threads'][t]['switches'] for t in kvm_threads)
        if total_switches > 10000:
            recommendations.append({
                'level': 'info',
                'title': 'High VM Context Switching',
                'description': f'KVM/QEMU threads: {total_switches:,} context switches',
                'suggestion': 'Consider reducing vCPU count or optimizing VM configuration.'
            })
    
    if not recommendations:
        recommendations.append({
            'level': 'success',
            'title': 'No Major Issues Detected',
            'description': 'The trace analysis did not reveal significant performance problems.',
            'suggestion': 'Continue monitoring for changes in behavior.'
        })
    
    return recommendations


def generate_html_report(results, recommendations, output_file):
    """Generate HTML report."""
    duration = results['time_range'][1] - results['time_range'][0]
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>ftrace Analysis Report</title>
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
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 8px;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .metric-value {{
            font-size: 32px;
            font-weight: bold;
            margin: 10px 0;
        }}
        .metric-label {{
            font-size: 14px;
            opacity: 0.9;
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
            font-weight: 600;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .recommendation {{
            margin: 15px 0;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid;
        }}
        .critical {{
            background: #fee;
            border-color: #e74c3c;
        }}
        .warning {{
            background: #fef7e5;
            border-color: #f39c12;
        }}
        .info {{
            background: #e8f4fd;
            border-color: #3498db;
        }}
        .success {{
            background: #e8f8f5;
            border-color: #27ae60;
        }}
        .rec-title {{
            font-weight: bold;
            margin-bottom: 8px;
        }}
        .timestamp {{
            color: #7f8c8d;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 ftrace Analysis Report</h1>
        <p class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <h2>📊 Summary Metrics</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">Total Events</div>
                <div class="metric-value">{results['valid_events']:,}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Duration</div>
                <div class="metric-value">{duration:.2f}s</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Active CPUs</div>
                <div class="metric-value">{len(results['cpus'])}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Unique Threads</div>
                <div class="metric-value">{len(results['threads'])}</div>
            </div>
        </div>
        
        <h2>⚠️ Recommendations</h2>
"""
    
    # Add recommendations
    for rec in recommendations:
        level = rec['level']
        html += f"""
        <div class="recommendation {level}">
            <div class="rec-title">{rec['title']}</div>
            <p><strong>Finding:</strong> {rec['description']}</p>
            <p><strong>Suggestion:</strong> {rec['suggestion']}</p>
        </div>
"""
    
    # Top threads by switches
    html += """
        <h2>📌 Top Threads by Context Switches</h2>
        <table>
            <tr>
                <th>Rank</th>
                <th>Thread Name</th>
                <th>Context Switches</th>
                <th>Wake-ups</th>
                <th>D-state Count</th>
            </tr>
"""
    
    sorted_threads = sorted(results['threads'].items(), 
                          key=lambda x: x[1]['switches'], 
                          reverse=True)[:20]
    
    for idx, (thread, data) in enumerate(sorted_threads, 1):
        d_state = data['states'].get('D', 0)
        html += f"""
            <tr>
                <td>{idx}</td>
                <td>{thread}</td>
                <td>{data['switches']:,}</td>
                <td>{data['wakeups']:,}</td>
                <td>{d_state:,}</td>
            </tr>
"""
    
    html += """
        </table>
        
        <h2>💻 CPU Utilization</h2>
        <table>
            <tr>
                <th>CPU ID</th>
                <th>Event Count</th>
                <th>Percentage</th>
            </tr>
"""
    
    total_cpu_events = sum(results['cpus'].values())
    for cpu, count in sorted(results['cpus'].items(), key=lambda x: int(x[0]))[:32]:
        percentage = (count / total_cpu_events * 100) if total_cpu_events > 0 else 0
        html += f"""
            <tr>
                <td>CPU {cpu}</td>
                <td>{count:,}</td>
                <td>{percentage:.1f}%</td>
            </tr>
"""
    
    html += """
        </table>
        
        <h2>📈 Event Type Distribution</h2>
        <table>
            <tr>
                <th>Event Type</th>
                <th>Count</th>
                <th>Percentage</th>
            </tr>
"""
    
    total_events = sum(results['events'].values())
    for event, count in results['events'].most_common():
        percentage = (count / total_events * 100) if total_events > 0 else 0
        html += f"""
            <tr>
                <td>{event}</td>
                <td>{count:,}</td>
                <td>{percentage:.1f}%</td>
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
    
    print(f"\nHTML report generated: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate comprehensive HTML report from ftrace analysis'
    )
    
    parser.add_argument('input_file', help='Input ftrace log file')
    parser.add_argument('--output', default='ftrace_report.html',
                       help='Output HTML file (default: ftrace_report.html)')
    
    args = parser.parse_args()
    
    # Read input
    try:
        with open(args.input_file, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: File '{args.input_file}' not found", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"\nAnalyzing {len(lines)} lines from ftrace log...")
    
    # Analyze
    results = analyze_full(lines)
    recommendations = generate_recommendations(results)
    
    # Generate report
    generate_html_report(results, recommendations, args.output)
    
    print("\nAnalysis complete!")


if __name__ == '__main__':
    main()
