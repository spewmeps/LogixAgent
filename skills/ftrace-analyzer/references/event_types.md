# ftrace 事件类型详解

本文档详细说明 ftrace 中常见事件类型的含义、格式和分析要点。

---

## 调度事件（Scheduler Events）

### sched_switch

**用途**：记录进程/线程的上下文切换

**格式**：
```
prev_comm=task1 prev_pid=123 prev_prio=120 prev_state=S ==>
next_comm=task2 next_pid=456 next_prio=120
```

**字段说明**：
- `prev_comm`: 切出的任务名
- `prev_pid`: 切出的任务 PID
- `prev_prio`: 切出任务的优先级（0-139，数字越小优先级越高）
- `prev_state`: 切出时的状态
  - `R`: Runnable（可运行，被抢占）
  - `S`: Sleeping（睡眠）
  - `D`: Disk sleep（不可中断睡眠，通常等待 I/O）
  - `T`: Stopped（停止）
  - `Z`: Zombie（僵尸）
- `next_comm`: 切入的任务名
- `next_pid`: 切入的任务 PID
- `next_prio`: 切入任务的优先级

**分析要点**：
- `prev_state=R`：表示被抢占，不是主动让出 CPU
- `prev_state=S/D`：表示主动睡眠，等待事件或资源
- 频繁切换表示系统负载高或存在竞争
- 优先级差异说明抢占原因

**示例分析**：
```
prev_comm=myapp prev_pid=1234 prev_prio=120 prev_state=R ==>
next_comm=irq/28-GPU next_pid=234 next_prio=50

解读：myapp 被实时线程 irq/28-GPU 抢占（prev_state=R），
     因为 irq/28-GPU 优先级更高（50 < 120）
```

---

### sched_wakeup / sched_wakeup_new

**用途**：记录任务被唤醒的事件

**格式**：
```
comm=task pid=123 prio=120 target_cpu=0
```

**字段说明**：
- `comm`: 被唤醒的任务名
- `pid`: 被唤醒的任务 PID
- `prio`: 任务优先级
- `target_cpu`: 目标 CPU（任务将在此 CPU 运行）

**分析要点**：
- wakeup → switch 的时间差 = **调度延迟**
- 高频 wakeup 可能表示轮询或忙等待
- `target_cpu` 不同表示发生了 CPU 迁移

**示例分析**：
```
[1234.567000] sched_wakeup: comm=myapp pid=1234 prio=120 target_cpu=0
[1234.587000] sched_switch: ... next_comm=myapp next_pid=1234

调度延迟 = 1234.587000 - 1234.567000 = 20ms
```

---

### sched_migrate_task

**用途**：记录任务在 CPU 间的迁移

**格式**：
```
comm=task pid=123 prio=120 orig_cpu=0 dest_cpu=1
```

**分析要点**：
- 频繁迁移导致缓存失效（cache thrashing）
- 跨 NUMA 节点迁移代价更大
- 迁移可能是负载均衡或 CPU 亲和性变化导致

---

### sched_process_wait / sched_process_exit / sched_process_fork

**用途**：记录进程生命周期事件

**分析要点**：
- 用于理解进程创建/销毁的时间点
- fork 风暴可能导致系统负载增加
- 僵尸进程会导致 exit 后没有 wait

---

## 中断事件（IRQ Events）

### irq_handler_entry / irq_handler_exit

**用途**：记录硬件中断的开始和结束

**格式**：
```
# entry
irq=19 name=eth0

# exit
irq=19 ret=handled
```

**字段说明**：
- `irq`: 中断号
- `name`: 中断源设备名
- `ret`: 返回值
  - `handled`: 成功处理
  - `unhandled`: 未处理
  - `wake_thread`: 唤醒线程化中断

**分析要点**：
- entry → exit 时间差 = 中断处理时长
- 高频中断（> 10000/秒）可能是中断风暴
- 中断期间其他任务无法运行（除更高优先级中断）

**示例分析**：
```
[1234.567000] irq_handler_entry: irq=19 name=eth0
[1234.567030] irq_handler_exit: irq=19 ret=handled

中断处理时长: 30us
如果每秒 10000 次，累计占用 CPU: 30us × 10000 = 300ms
```

---

### softirq_entry / softirq_exit / softirq_raise

**用途**：记录软中断的执行

**格式**：
```
vec=3 action=NET_RX
```

**软中断类型（vec）**：
- 0: HI_SOFTIRQ（高优先级任务）
- 1: TIMER_SOFTIRQ（定时器）
- 2: NET_TX_SOFTIRQ（网络发送）
- 3: NET_RX_SOFTIRQ（网络接收）
- 4: BLOCK_SOFTIRQ（块设备）
- 5: IRQ_POLL_SOFTIRQ（中断轮询）
- 6: TASKLET_SOFTIRQ（小任务）
- 7: SCHED_SOFTIRQ（调度）
- 8: HRTIMER_SOFTIRQ（高精度定时器）
- 9: RCU_SOFTIRQ（RCU）

**分析要点**：
- 软中断在硬件中断上下文或 ksoftirqd 线程中执行
- 单次软中断执行时间过长会触发 ksoftirqd
- NET_RX/NET_TX 高频表示网络负载重

---

## 锁事件（Lock Events）

### lock_acquire / lock_acquired / lock_release

**用途**：记录锁的获取和释放

**格式**：
```
# acquire: 尝试获取锁
lock_acquire: 0xffff8881234abcd0 (&lock->mutex)

# acquired: 成功获取锁
lock_acquired: 0xffff8881234abcd0 (&lock->mutex)

# release: 释放锁
lock_release: 0xffff8881234abcd0 (&lock->mutex)
```

**分析要点**：
- acquire → acquired 的时间差 = **锁等待时间**
- 长时间持锁（acquired → release > 10ms）可疑
- 相同锁地址的多次 acquire 表示锁争用

**需要内核配置**：
```bash
CONFIG_LOCK_STAT=y
CONFIG_PROVE_LOCKING=y
```

---

### lock_contended

**用途**：记录锁竞争事件

**格式**：
```
lock_contended: 0xffff8881234abcd0 (&lock->mutex)
```

**分析要点**：
- 表示多个线程同时竞争同一把锁
- 高频竞争（> 100次/秒）表示热点锁
- 需要优化锁粒度或使用无锁算法

---

## 内存事件（Memory Events）

### mm_page_alloc / mm_page_free

**用途**：记录页面分配和释放

**分析要点**：
- 大量分配可能导致内存碎片
- 分配失败触发内存回收

---

### mm_vmscan_direct_reclaim_begin / mm_vmscan_direct_reclaim_end

**用途**：记录直接内存回收

**格式**：
```
# begin
order=0 gfp_flags=GFP_KERNEL

# end
nr_reclaimed=128
```

**分析要点**：
- 直接回收导致分配线程阻塞（几十到几百 ms）
- `nr_reclaimed` 少表示内存压力大
- 频繁直接回收需要增加内存或优化使用

---

### mm_vmscan_kswapd_wake / mm_vmscan_kswapd_sleep

**用途**：记录后台内存回收守护进程 kswapd 的活动

**分析要点**：
- kswapd 频繁唤醒表示内存压力持续
- kswapd 不睡眠表示内存严重不足

---

## 工作队列事件（Workqueue Events）

### workqueue_execute_start / workqueue_execute_end

**用途**：记录工作队列任务的执行

**格式**：
```
# start
work struct=0xffff888123456789 function=func_name

# end
work struct=0xffff888123456789
```

**分析要点**：
- 工作队列用于延迟执行内核任务
- 长时间执行（> 100ms）的工作可能阻塞其他任务
- 识别周期性任务（如 writeback）

---

## 定时器事件（Timer Events）

### timer_start / timer_expire_entry / timer_expire_exit

**用途**：记录定时器的设置和触发

**格式**：
```
# start
timer=0xffff888123456789 function=func_name expires=1234567890

# expire
timer=0xffff888123456789 function=func_name
```

**分析要点**：
- 定时器用于周期性任务
- 高频定时器（< 10ms 间隔）可能影响性能
- 识别定时器风暴（过多定时器同时触发）

---

## 信号事件（Signal Events）

### signal_generate / signal_deliver

**用途**：记录信号的生成和传递

**格式**：
```
# generate
sig=15 errno=0 code=0 comm=sender pid=123

# deliver
sig=15 errno=0 code=0 sa_handler=0xffffffff comm=receiver pid=456
```

**分析要点**：
- 频繁信号可能导致任务频繁唤醒
- SIGKILL (9) / SIGTERM (15) 表示进程终止
- 信号处理可能引入延迟

---

## 网络事件（Network Events）

### net_dev_queue / net_dev_xmit

**用途**：记录网络数据包的队列和发送

**分析要点**：
- queue → xmit 延迟表示网络栈处理延迟
- 大量 queue 但少量 xmit 表示发送拥塞

---

### napi_poll

**用途**：记录 NAPI 轮询事件

**分析要点**：
- NAPI 用于高效处理网络数据包
- 频繁轮询但处理少量数据包表示低效

---

## 块设备事件（Block Events）

### block_rq_insert / block_rq_issue / block_rq_complete

**用途**：记录块设备 I/O 请求的生命周期

**分析要点**：
- insert → issue: 请求在队列中等待时间
- issue → complete: 实际 I/O 时间
- 长延迟（> 100ms）表示存储性能问题

---

## RCU 事件（RCU Events）

### rcu_utilization / rcu_grace_period

**用途**：记录 RCU（Read-Copy-Update）同步机制

**分析要点**：
- RCU 用于内核数据结构的无锁读
- Grace period 过长可能影响性能

---

## 电源管理事件（Power Management Events）

### cpu_idle / cpu_frequency

**用途**：记录 CPU 空闲状态和频率变化

**分析要点**：
- 频繁进出空闲状态表示负载波动
- 频率变化可能影响性能（CPU 频率调节）

---

## 事件过滤策略

### 关键事件优先级

**高优先级（必看）**：
1. `sched_switch` - 调度核心
2. `sched_wakeup` - 唤醒和延迟
3. `irq_handler_entry/exit` - 中断影响

**中优先级（重要）**：
4. `softirq_entry/exit` - 软中断负载
5. `lock_acquire/release` - 锁竞争
6. `sched_migrate_task` - CPU 迁移

**低优先级（按需）**：
7. 内存事件 - 内存压力分析
8. 网络事件 - 网络性能分析
9. 块设备事件 - I/O 性能分析

### 过滤技巧

```bash
# 只看调度相关
scripts/ftrace_parser.py trace.txt --filter-event sched_switch

# 只看特定 CPU
scripts/ftrace_parser.py trace.txt --filter-cpu 0

# 组合过滤
scripts/ftrace_parser.py trace.txt \
  --filter-cpu 0 \
  --time-range 1234.5,1235.5 \
  --filter-pid 1234
```

---

## 常用事件组合

### 诊断调度延迟
```
sched_wakeup
sched_switch
sched_migrate_task
```

### 诊断中断影响
```
irq_handler_entry
irq_handler_exit
softirq_entry
softirq_exit
```

### 诊断锁竞争
```
lock_acquire
lock_acquired
lock_release
lock_contended
```

### 诊断内存压力
```
mm_page_alloc
mm_vmscan_direct_reclaim_begin
mm_vmscan_direct_reclaim_end
mm_vmscan_kswapd_wake
```

---

## 事件时间戳精度

ftrace 时间戳通常精度为：
- **微秒级（us）**：1234567.123456
- 前面是秒数（自启动），后面 6 位小数是微秒

**注意**：
- 时间戳是单调递增的
- 不同 CPU 的时间戳可能有轻微偏差（< 1us）
- 使用 `local` clock 时，不同 CPU 之间可能不同步

---

## 参考资源

- 内核文档：`Documentation/trace/ftrace.txt`
- 事件格式：`/sys/kernel/debug/tracing/events/*/format`
- 可用事件：`/sys/kernel/debug/tracing/available_events`

**查看事件格式命令**：
```bash
cat /sys/kernel/debug/tracing/events/sched/sched_switch/format
```
