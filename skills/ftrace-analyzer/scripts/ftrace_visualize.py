#!/usr/bin/env python3
"""
ftrace 可视化工具
创建 ftrace 调度事件的时间序列可视化图表。
"""

import sys
import argparse
import re
from collections import defaultdict
import numpy as np

# Check for required libraries
try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
except ImportError:
    print("Error: matplotlib is required. Install with: pip install matplotlib --break-system-packages", file=sys.stderr)
    sys.exit(1)


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


def analyze_time_series(lines, window_size=0.1):
    """Analyze events over time with binning."""
    timestamps = []
    events = []
    cpus = []
    
    for line in lines:
        parsed = parse_ftrace_line(line)
        if not parsed:
            continue
        
        timestamps.append(parsed['timestamp'])
        events.append(parsed['event'])
        cpus.append(int(parsed['cpu']))
    
    if not timestamps:
        return None, None, None, None
    
    # Convert to numpy arrays
    timestamps = np.array(timestamps)
    events = np.array(events)
    cpus = np.array(cpus)
    
    # Normalize timestamps to start from 0
    timestamps = timestamps - timestamps.min()
    
    # Create time bins
    max_time = timestamps.max()
    num_bins = int(max_time / window_size) + 1
    time_bins = np.arange(0, max_time + window_size, window_size)
    
    # Bin the data
    event_counts = defaultdict(lambda: np.zeros(num_bins))
    cpu_activity = defaultdict(lambda: np.zeros(num_bins))
    
    for i, ts in enumerate(timestamps):
        bin_idx = int(ts / window_size)
        if bin_idx < num_bins:
            event_counts[events[i]][bin_idx] += 1
            cpu_activity[cpus[i]][bin_idx] += 1
    
    return time_bins, event_counts, cpu_activity, max_time


def create_visualizations(time_bins, event_counts, cpu_activity, max_time, output_file):
    """Create comprehensive visualization plots."""
    # Create figure with subplots
    fig, axes = plt.subplots(3, 1, figsize=(14, 10))
    fig.suptitle('ftrace Scheduling Analysis', fontsize=16, fontweight='bold')
    
    # Plot 1: Event counts over time
    ax1 = axes[0]
    for event_type, counts in event_counts.items():
        if event_type in ['sched_switch', 'sched_waking', 'sched_migrate_task']:
            ax1.plot(time_bins[:-1], counts, label=event_type, linewidth=1.5)
    
    ax1.set_xlabel('Time (seconds)')
    ax1.set_ylabel('Event Count per Window')
    ax1.set_title('Scheduling Events Over Time')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Wake-up events (zoomed)
    ax2 = axes[1]
    if 'sched_waking' in event_counts:
        waking_counts = event_counts['sched_waking']
        ax2.fill_between(time_bins[:-1], waking_counts, alpha=0.5, color='orange')
        ax2.plot(time_bins[:-1], waking_counts, color='darkorange', linewidth=1)
        
        # Calculate and show moving average
        window = 10
        if len(waking_counts) >= window:
            moving_avg = np.convolve(waking_counts, np.ones(window)/window, mode='valid')
            ax2.plot(time_bins[:len(moving_avg)], moving_avg, 
                    color='red', linewidth=2, label=f'{window}-window moving average')
    
    ax2.set_xlabel('Time (seconds)')
    ax2.set_ylabel('Wake-up Count')
    ax2.set_title('Thread Wake-up Events (sched_waking)')
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: CPU utilization heatmap
    ax3 = axes[2]
    
    # Prepare data for heatmap
    cpu_ids = sorted(cpu_activity.keys())[:32]  # Limit to first 32 CPUs for visibility
    if cpu_ids:
        heatmap_data = np.array([cpu_activity[cpu] for cpu in cpu_ids])
        
        im = ax3.imshow(heatmap_data, aspect='auto', cmap='hot', 
                       extent=[0, max_time, len(cpu_ids)-0.5, -0.5],
                       interpolation='nearest')
        
        ax3.set_xlabel('Time (seconds)')
        ax3.set_ylabel('CPU ID')
        ax3.set_title('CPU Activity Heatmap')
        ax3.set_yticks(range(len(cpu_ids)))
        ax3.set_yticklabels([f'CPU{cpu}' for cpu in cpu_ids])
        
        # Add colorbar
        cbar = plt.colorbar(im, ax=ax3)
        cbar.set_label('Event Count', rotation=270, labelpad=20)
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\nVisualization saved to: {output_file}")
    
    # Print summary statistics
    print("\n" + "="*60)
    print("Summary Statistics")
    print("="*60)
    print(f"Total duration: {max_time:.2f} seconds")
    print(f"Time bins: {len(time_bins)-1}")
    
    total_events = sum(sum(counts) for counts in event_counts.values())
    print(f"Total events: {int(total_events)}")
    
    print("\nEvent breakdown:")
    for event_type, counts in sorted(event_counts.items()):
        total = int(sum(counts))
        avg = np.mean(counts)
        max_val = np.max(counts)
        print(f"  {event_type:<25} Total: {total:>8,}  Avg/bin: {avg:>6.1f}  Max/bin: {int(max_val):>6,}")
    
    print("\nCPU activity:")
    cpu_totals = {cpu: int(sum(counts)) for cpu, counts in cpu_activity.items()}
    top_cpus = sorted(cpu_totals.items(), key=lambda x: x[1], reverse=True)[:10]
    for cpu, count in top_cpus:
        print(f"  CPU {cpu:>3}: {count:>8,} events")
    
    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Visualize ftrace scheduling events over time',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python3 ftrace_visualize.py trace.txt
  python3 ftrace_visualize.py trace.txt --window 0.05 --output custom.png
  cat filtered.txt | python3 ftrace_visualize.py - --window 0.2
        '''
    )
    
    parser.add_argument('input_file', help='Input ftrace log file (use - for stdin)')
    parser.add_argument('--window', type=float, default=0.1, 
                       help='Time window size in seconds (default: 0.1)')
    parser.add_argument('--output', default='ftrace_analysis.png',
                       help='Output image file (default: ftrace_analysis.png)')
    
    args = parser.parse_args()
    
    # Read input
    if args.input_file == '-':
        lines = sys.stdin.readlines()
    else:
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
    print(f"Time window size: {args.window} seconds")
    
    # Analyze
    time_bins, event_counts, cpu_activity, max_time = analyze_time_series(lines, args.window)
    
    if time_bins is None:
        print("Error: No valid trace events found in input", file=sys.stderr)
        sys.exit(1)
    
    # Create visualizations
    create_visualizations(time_bins, event_counts, cpu_activity, max_time, args.output)


if __name__ == '__main__':
    main()
