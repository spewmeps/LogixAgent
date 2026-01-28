# ftrace 事件参考

常用 ftrace 事件类型及其含义的全面参考。

## 调度器事件 (Scheduler Events)

### sched_switch
**描述**：记录 CPU 上发生任务上下文切换的时刻。

**格式**：
```
prev_comm=<名称> prev_pid=<PID> prev_prio=<优先级> prev_state=<状态> ==> next_comm=<名称> next_pid=<PID> next_prio=<优先级>
```

**关键字段**：
- `prev_comm`: 被切出任务的名称
- `prev_pid`: 被切出任务的 PID
- `prev_state`: 切出后任务的状态
  - `R`: 正在运行/可运行（CPU 空闲时即可运行）
  - `S`: 可中断睡眠（等待事件，可被信号中断）
  - `D`: 不可中断睡眠（等待 I/O，不可被中断） ⚠️
  - `T`: 已停止（被信号或 ptrace 停止）
  - `t`: 追踪停止
  - `Z`: 僵尸进程（已终止但未被回收）
  - `X`: 死亡（理论上不应看到）
  - `I`: 空闲
- `next_comm`: 被切入任务的名称
- `next_pid`: 被切入任务的 PID
- `prev_prio`, `next_prio`: 调度优先级（0-139，数值越小优先级越高）

**分析用例**：
- 识别上下文切换频繁的任务
- 查找因 I/O 阻塞的任务 (prev_state=D)
- 衡量 CPU 时间分布
- 检测调度延迟问题

---

### sched_waking
**描述**：记录任务正在被唤醒的时刻（在实际被调度运行之前）。

**格式**：
```
comm=<名称> pid=<PID> prio=<优先级> target_cpu=<CPU>
```

**关键字段**：
- `comm`: 被唤醒任务的名称
- `pid`: 任务 PID
- `target_cpu`: 任务将被调度运行的 CPU 核心

**分析用例**：
- 识别频繁被唤醒的任务
- 检测中断风暴模式
- 查找 I/O 完成模式
- 衡量唤醒延迟

---

### sched_wakeup
**描述**：与 `sched_waking` 类似，但在任务实际被放入运行队列后触发。

**格式**：与 `sched_waking` 相同

**与 sched_waking 的区别**：
- `sched_waking`: 唤醒意图（在放入运行队列之前）
- `sched_wakeup`: 任务已实际放入运行队列

---

### sched_migrate_task
**描述**：记录任务从一个 CPU 核心迁移到另一个核心的时刻。

**格式**：
```
comm=<名称> pid=<PID> prio=<优先级> orig_cpu=<源CPU> dest_cpu=<目标CPU>
```

**关键字段**：
- `orig_cpu`: 源 CPU
- `dest_cpu`: 目标 CPU

**分析用例**：
- 衡量任务迁移频率
- 识别 CPU 亲和性不佳的情况
- 检测负载均衡问题
- 查找缓存抖动 (Cache Thrashing) 问题

**高迁移率通常表示**：
- CPU 绑定 (CPU Pinning) 不足
- 过度的负载均衡
- 潜在的缓存行冲突 (Cache Line Bouncing)
- NUMA 相关问题

---

### sched_process_fork
**描述**：记录新进程被 fork 出来的时刻。

**格式**：
```
comm=<父进程名> pid=<父PID> child_comm=<子进程名> child_pid=<子PID>
```
