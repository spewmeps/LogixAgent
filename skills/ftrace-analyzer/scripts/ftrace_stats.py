#!/usr/bin/env python3
"""
ftrace Statistics Analyzer
Analyzes ftrace logs for scheduling statistics, wake-up patterns, and CPU utilization.
"""

import sys
import argparse
from collections import Counter, defaultdict
import re


def parse_ftrace_line(line):
    """Parse a single ftrace line and extract key information."""
    # Example: <idle>-0 [086] d... 31686721.679534: sched_switch: prev_comm=swapper/86 ...
    try:
        parts = line.split()
        if len(parts) < 5:
            return None
        
        task_pid = parts[0]  # e.g., <idle>-0 or task_name-1234
        cpu = parts[1].strip('[]')  # e.g., [086] -> 086
        timestamp = float(parts[3].rstrip(':'))
        event = parts[4].rstrip(':')
        details = ' '.join(parts[5:])
        
        # Extract task name and PID
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
            'details': details,
            'raw': line
        }
    except (ValueError, IndexError):
        return None


def extract_field(details, field_name):
    """Extract a specific field from event details."""
    pattern = rf'{field_name}=([^\s]+)'
    match = re.search(pattern, details)
    return match.group(1) if match else None


def analyze_wakeups(lines):
    """Analyze sched_waking events to find frequently woken threads."""
    wakeup_counter = Counter()
    
    for line in lines:
        parsed = parse_ftrace_line(line)
        if not parsed or parsed['event'] != 'sched_waking':
            continue
        
        # Extract woken process name
        comm = extract_field(parsed['details'], 'comm')
        if comm:
            wakeup_counter[comm] += 1
    
    return wakeup_counter


def analyze_switches(lines):
    """Analyze sched_switch events to find frequently scheduled threads."""
    switch_counter = Counter()
    state_counter = defaultdict(Counter)
    
    for line in lines:
        parsed = parse_ftrace_line(line)
        if not parsed or parsed['event'] != 'sched_switch':
            continue
        
        # Extract next process (the one being scheduled)
        next_comm = extract_field(parsed['details'], 'next_comm')
        prev_state = extract_field(parsed['details'], 'prev_state')
        prev_comm = extract_field(parsed['details'], 'prev_comm')
        
        if next_comm:
            switch_counter[next_comm] += 1
        
        if prev_comm and prev_state:
            state_counter[prev_comm][prev_state] += 1
    
    return switch_counter, state_counter


def analyze_cpus(lines):
    """Analyze CPU utilization distribution."""
    cpu_counter = Counter()
    cpu_events = defaultdict(list)
    
    for line in lines:
        parsed = parse_ftrace_line(line)
        if not parsed:
            continue
        
        cpu = parsed['cpu']
        cpu_counter[cpu] += 1
        cpu_events[cpu].append(parsed['event'])
    
    return cpu_counter, cpu_events


def analyze_blocking(lines):
    """Analyze blocking patterns (D state - uninterruptible sleep)."""
    blocking_counter = Counter()
    
    for line in lines:
        parsed = parse_ftrace_line(line)
        if not parsed or parsed['event'] != 'sched_switch':
            continue
        
        prev_state = extract_field(parsed['details'], 'prev_state')
        prev_comm = extract_field(parsed['details'], 'prev_comm')
        
        if prev_state == 'D' and prev_comm:
            blocking_counter[prev_comm] += 1
    
    return blocking_counter


def print_top_stats(counter, title, top_n=20):
    """Print top N entries from a counter."""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(f"{'Rank':<6} {'Count':<10} {'Name':<40}")
    print('-' * 60)
    
    for idx, (name, count) in enumerate(counter.most_common(top_n), 1):
        print(f"{idx:<6} {count:<10} {name:<40}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze ftrace logs for scheduling statistics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python3 ftrace_stats.py trace.txt --wakeup-stats
  python3 ftrace_stats.py trace.txt --all
  python3 ftrace_stats.py trace.txt --cpu-stats --top 10
        '''
    )
    
    parser.add_argument('input_file', help='Input ftrace log file (use - for stdin)')
    parser.add_argument('--wakeup-stats', action='store_true', help='Show wake-up statistics')
    parser.add_argument('--switch-stats', action='store_true', help='Show context switch statistics')
    parser.add_argument('--cpu-stats', action='store_true', help='Show CPU utilization statistics')
    parser.add_argument('--blocking-stats', action='store_true', help='Show blocking (D-state) statistics')
    parser.add_argument('--all', action='store_true', help='Show all statistics')
    parser.add_argument('--top', type=int, default=20, help='Number of top entries to show (default: 20)')
    
    args = parser.parse_args()
    
    # If no specific stats requested, show all
    if not any([args.wakeup_stats, args.switch_stats, args.cpu_stats, args.blocking_stats]):
        args.all = True
    
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
    
    # Run analyses
    if args.all or args.wakeup_stats:
        wakeup_counter = analyze_wakeups(lines)
        print_top_stats(wakeup_counter, "Top Woken Threads (sched_waking events)", args.top)
    
    if args.all or args.switch_stats:
        switch_counter, state_counter = analyze_switches(lines)
        print_top_stats(switch_counter, "Top Scheduled Threads (sched_switch events)", args.top)
        
        # Print state distribution for top threads
        print(f"\n{'='*60}")
        print("State Distribution for Top Threads")
        print(f"{'='*60}")
        for thread, _ in switch_counter.most_common(10):
            if thread in state_counter:
                states = state_counter[thread]
                state_str = ', '.join([f"{s}:{c}" for s, c in states.most_common()])
                print(f"{thread:<40} {state_str}")
    
    if args.all or args.cpu_stats:
        cpu_counter, cpu_events = analyze_cpus(lines)
        print_top_stats(cpu_counter, "CPU Utilization (event count per CPU)", top_n=min(args.top, len(cpu_counter)))
    
    if args.all or args.blocking_stats:
        blocking_counter = analyze_blocking(lines)
        if blocking_counter:
            print_top_stats(blocking_counter, "Top Blocking Threads (D-state)", args.top)
        else:
            print("\nNo blocking events (D-state) found in trace.")
    
    print("\n" + "="*60)
    print("Analysis complete.")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
