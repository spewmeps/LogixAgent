# Perfetto SQL Table Structures

This document describes the schema of tables and views used in `ftrace_sys_sql.md` and `ftrace.sql`.
Descriptions are extracted from `src/trace_processor/tables/` and `src/trace_processor/perfetto_sql/stdlib/`.

## sched
**Description**: This table holds slices with kernel thread scheduling information. These slices are collected when the Linux "ftrace" data source is used with the "sched/switch" and "sched/wakeup*" events enabled. The rows in this table will always have a matching row in the `thread_state` table with `thread_state.state` = 'Running'.

| Column | Type | Description |
| :--- | :--- | :--- |
| id | ID | Unique identifier for the slice. |
| ts | TIMESTAMP | The timestamp at the start of the slice (in nanoseconds). |
| dur | DURATION | The duration of the slice (in nanoseconds). |
| cpu | LONG | The CPU that the slice executed on (meaningful only in single machine traces). |
| utid | JOINID(thread.id) | The thread's unique id in the trace. |
| end_state | STRING | A string representing the scheduling state of the kernel thread at the end of the slice. Characters: R (runnable), S (awaiting wakeup), D (uninterruptible sleep), T (suspended), t (being traced), X (exiting), P (parked), W (waking), I (idle), N (not contributing to load), K (wakeable on fatal signals), Z (zombie). |
| priority | LONG | The kernel priority that the thread ran at. |
| ucpu | LONG | The unique CPU identifier that the slice executed on. |
| ts_end | LONG | Legacy column, should no longer be used. |

## slice
**Description**: Contains slices from userspace which explains what threads were doing during the trace.

| Column | Type | Description |
| :--- | :--- | :--- |
| id | ID | Unique identifier for the slice. |
| ts | TIMESTAMP | The timestamp at the start of the slice (in nanoseconds). |
| dur | DURATION | The duration of the slice (in nanoseconds). |
| track_id | JOINID(track.id) | The id of the track this slice is located on. |
| category | STRING | The "category" of the slice. |
| name | STRING | The name of the slice describing what was happening. |
| depth | LONG | The depth of the slice in the current stack of slices. |
| parent_id | JOINID(slice.id) | The id of the parent (immediate ancestor) slice. |
| arg_set_id | ARGSETID | The id of the argument set associated with this slice. |
| thread_ts | TIMESTAMP | The thread timestamp at the start of the slice (if enabled, in nanoseconds). |
| thread_dur | DURATION | The thread time used by this slice (if enabled, in nanoseconds). |
| thread_instruction_count | LONG | CPU instruction counter at start (if enabled). |
| thread_instruction_delta | LONG | Change in CPU instruction counter (if enabled). |

## thread
**Description**: Contains information of threads seen during the trace.

| Column | Type | Description |
| :--- | :--- | :--- |
| id | ID | The id of the thread. Prefer using `utid` instead. |
| utid | ID | Unique thread id (monotonic). != OS tid. Primary key for threads. |
| tid | LONG | The OS id for this thread (not unique over trace lifetime). |
| name | STRING | The name of the thread. |
| start_ts | TIMESTAMP | The start timestamp of this thread (if known, in nanoseconds). |
| end_ts | TIMESTAMP | The end timestamp of this thread (if known, in nanoseconds). |
| upid | JOINID(process.id) | The process hosting this thread. |
| is_main_thread | BOOL | Boolean indicating if this thread is the main thread in the process. |
| is_idle | BOOL | Boolean indicating if this thread is a kernel idle task. |
| machine_id | LONG | Machine identifier for remote machines. |

## process
**Description**: Contains information of processes seen during the trace.

| Column | Type | Description |
| :--- | :--- | :--- |
| upid | ID | Unique process id (monotonic). != OS pid. Primary key for processes. |
| pid | LONG | The OS id for this process. |
| name | STRING | The name of the process. |
| start_ts | TIMESTAMP | The start timestamp of this process (if known, in nanoseconds). |
| end_ts | TIMESTAMP | The end timestamp of this process (if known, in nanoseconds). |
| parent_upid | JOINID(process.id) | The upid of the process which spawned this process. |
| uid | LONG | The Unix user id of the process. |
| android_appid | LONG | Android appid of this process. |
| android_user_id | LONG | Android user id running the process. |
| cmdline | STRING | /proc/cmdline for this process. |
| arg_set_id | ARGSETID | Extra args for this process. |
| machine_id | LONG | Machine identifier. |

## thread_state
**Description**: This table contains the scheduling state of every thread on the system during the trace.

| Column | Type | Description |
| :--- | :--- | :--- |
| id | ID | Unique identifier. |
| ts | TIMESTAMP | The timestamp at the start of the state interval (in nanoseconds). |
| dur | DURATION | The duration of the state interval (in nanoseconds). |
| utid | JOINID(thread.id) | The thread's unique id. |
| state | STRING | The scheduling state (Running, Runnable, etc.). |
| io_wait | BOOL | Indicates whether this thread was blocked on IO. |
| blocked_function | STRING | The function in the kernel this thread was blocked on. |
| waker_utid | JOINID(thread.id) | The unique thread id of the thread which caused a wakeup. |
| waker_id | JOINID(thread_state.id) | The unique thread state id which caused a wakeup. |
| irq_context | BOOL | Whether the wakeup was from interrupt context or process context. |
| ucpu | LONG | The unique CPU identifier that the thread executed on. |

## counter
**Description**: Contains counter events (values that change over time) associated with a track.

| Column | Type | Description |
| :--- | :--- | :--- |
| id | ID | Unique identifier. |
| ts | TIMESTAMP | The timestamp of the counter sample (in nanoseconds). |
| track_id | JOINID(track.id) | The track this counter belongs to. |
| value | DOUBLE | The value of the counter. |
| arg_set_id | ARGSETID | Extra args for this counter sample. |

## counter_track
**Description**: Tracks containing counter-like events. Performance counters and counter tracks. This module provides counter-related tables and views for analyzing performance metrics collected across CPUs, processes, threads, GPUs, and other contexts.

| Column | Type | Description |
| :--- | :--- | :--- |
| id | ID | Unique identifier for this track. |
| name | STRING | Name of the track. |
| parent_id | JOINID(track.id) | The track which is the "parent" of this track. |
| type | STRING | The type of data the track contains (e.g. 'perf_cpu_counter'). |
| unit | STRING | The units of the counter. |
| description | STRING | Description for debugging. |
| source_arg_set_id | ARGSETID | Args about source of this track. |
| machine_id | LONG | Machine identifier. |
| dimension_arg_set_id | ARGSETID | Dimension args (used for grouping). |

## track
**Description**: Tracks are the timeline horizontal bars in the UI. Each track is associated with a specific context (thread, process, cpu, etc.) and contains events.

| Column | Type | Description |
| :--- | :--- | :--- |
| id | ID | Unique identifier. |
| name | STRING | Name of the track. |
| parent_id | JOINID(track.id) | Parent track id. |
| type | STRING | Type of the track. |
| event_type | STRING | Type of events on this track (e.g. 'slice', 'counter'). |
| utid | JOINID(thread.id) | Associated thread utid (if any). |
| upid | JOINID(process.id) | Associated process upid (if any). |
| source_arg_set_id | ARGSETID | Source args. |
| dimension_arg_set_id | ARGSETID | Dimension args (used for grouping). |

## sched_latency_for_running_interval
**Description**: Scheduling latency of running thread states. For each time the thread was running, returns the duration of the runnable state directly before.

| Column | Type | Description |
| :--- | :--- | :--- |
| thread_state_id | JOINID(thread_state.id) | Running state of the thread (joinable with thread_state.id). |
| sched_id | JOINID(sched.id) | Id of a corresponding slice in `sched` table. |
| utid | JOINID(thread.id) | Thread with running state. |
| runnable_latency_id | JOINID(thread_state.id) | Runnable state before thread is "running". |
| latency_dur | DURATION | Scheduling latency of thread state (duration of runnable state, in nanoseconds). |

## linux_hard_irqs
**Description**: All hard IRQs of the trace represented as slices.

| Column | Type | Description |
| :--- | :--- | :--- |
| ts | TIMESTAMP | Starting timestamp of this IRQ (in nanoseconds). |
| dur | DURATION | Duration of this IRQ (in nanoseconds). |
| name | STRING | The name of the IRQ. |
| id | JOINID(slice.id) | The id of the IRQ (joinable with slice.id). |
| parent_id | JOINID(slice.id) | The id of this IRQ's parent IRQ. |

## linux_soft_irqs
**Description**: All soft IRQs of the trace represented as slices.

| Column | Type | Description |
| :--- | :--- | :--- |
| ts | TIMESTAMP | Starting timestamp of this IRQ (in nanoseconds). |
| dur | DURATION | Duration of this IRQ (in nanoseconds). |
| name | STRING | The name of the IRQ. |
| id | JOINID(slice.id) | The id of the IRQ (joinable with slice.id). |

## _slice_flattened
**Description**: Represents slices in a flattened form, removing nesting by projecting every slice to its ancestor.

| Column | Type | Description |
| :--- | :--- | :--- |
| slice_id | JOINID(slice.id) | Id of most active slice. |
| ts | TIMESTAMP | Timestamp when `slice.id` became the most active slice (in nanoseconds). |
| dur | DURATION | Duration of `slice.id` as the most active slice until the next active slice (in nanoseconds). |
| depth | LONG | Depth of `slice.id` in the original stack. |
| name | STRING | Name of `slice.id`. |
| root_id | JOINID(slice.id) | Id of the top most slice of the stack. |
| track_id | JOINID(track.id) | Alias for `slice.track_id`. |
| utid | JOINID(thread.id) | Alias for `thread.utid`. |
| tid | LONG | Alias for `thread.tid`. |
| thread_name | STRING | Alias for `thread.name`. |
| upid | JOINID(process.id) | Alias for `process.upid`. |
| pid | LONG | Alias for `process.pid`. |
| process_name | STRING | Alias for `process.name`. |
