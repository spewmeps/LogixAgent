# ftrace 常见问题模式和案例

本文档整理了实际生产环境中遇到的典型问题模式、诊断方法和解决方案。

---

## 模式 1：实时线程抢占普通进程

### 问题表现

应用线程出现周期性卡顿，卡顿时长 20-100ms。

### ftrace 特征

```
[1234.567890] myapp-1234  [000]  sched_wakeup: comm=myapp pid=1234
[1234.612345] myapp-1234  [000]  sched_switch: myapp -> irq/28-GPU
[1234.657890] myapp-1234  [000]  sched_switch: irq/28-GPU -> myapp

调度延迟: 45.5ms
```

### 诊断命令

```bash
# 1. 找到高延迟时刻
scripts/sched_analyzer.py trace.txt --thread myapp --latency-threshold 20

# 2. 查看延迟期间的 CPU 占用
scripts/timeline_analyzer.py trace.txt --target myapp --context 100ms

# 3. 识别阻断者
scripts/causality_chain.py trace.txt --victim myapp
```

### 根因分析

```
实时线程 irq/28-GPU (优先级 50, FIFO) 在 GPU 中断处理时
持续占用 CPU，myapp (优先级 120, NORMAL) 无法抢占，
导致 45.5ms 调度延迟。
```

### 解决方案

1. **降低实时线程优先级**：
   ```bash
   chrt -f -p 90 $(pgrep "irq/28-GPU")
   ```

2. **将应用提升为实时**（谨慎）：
   ```bash
   chrt -f -p 80 $(pgrep myapp)
   ```

3. **限制中断线程 CPU 时间**：
   ```bash
   echo 50000 > /proc/sys/kernel/sched_rt_runtime_us
   ```

### 预防措施

- 避免在 CPU 密集型设备上使用实时中断线程
- 监控实时线程的 CPU 使用率
- 为关键应用预留独立 CPU（CPU 隔离）

---

## 模式 2：中断风暴

### 问题表现

系统整体响应缓慢，所有进程都有延迟。

### ftrace 特征

```
[1234.567890] <idle>-0     [001]  irq_handler_entry: irq=19 name=eth0
[1234.567920] <idle>-0     [001]  irq_handler_exit: irq=19 ret=handled
[1234.567950] <idle>-0     [001]  irq_handler_entry: irq=19 name=eth0
[1234.567980] <idle>-0     [001]  irq_handler_exit: irq=19 ret=handled
... (重复 1000+ 次/秒)
```

### 诊断命令

```bash
# 统计中断频率
scripts/ftrace_parser.py trace.txt --filter-event irq_handler_entry | \
  awk '{print $NF}' | sort | uniq -c | sort -rn

# 分析中断对特定进程的影响
scripts/timeline_analyzer.py trace.txt --target myapp --show-interrupts
```

### 根因分析

```
网卡 eth0 (IRQ 19) 在 1234.5-1235.5s 时间窗内触发 85000+ 次中断，
平均每秒 85000 次，每次中断处理 30us，累计占用 CPU 时间 2.55s，
超过实际时间窗 1s，导致所有用户进程饥饿。
```

### 解决方案

1. **启用中断合并（Interrupt Coalescing）**：
   ```bash
   ethtool -C eth0 rx-usecs 50 rx-frames 32
   ```

2. **使用 NAPI 轮询模式**：
   ```bash
   ethtool -K eth0 gro on
   ```

3. **中断亲和性绑定**：
   ```bash
   echo 2 > /proc/irq/19/smp_affinity  # 绑定到 CPU 1
   ```

### 预防措施

- 监控 `/proc/interrupts` 中断速率
- 为高频中断设备配置专用 CPU
- 使用硬件卸载（TSO, GSO, GRO）

---

## 模式 3：锁争用

### 问题表现

多线程应用性能下降，吞吐量远低于预期。

### ftrace 特征

```
[1234.567890] thread-1  [000]  lock_acquire: &lock->mutex
[1234.567900] thread-1  [000]  lock_acquired: &lock->mutex
[1234.588900] thread-1  [000]  lock_release: &lock->mutex

[1234.568000] thread-2  [001]  lock_acquire: &lock->mutex
[1234.588910] thread-2  [001]  lock_acquired: &lock->mutex  ← 等待 20ms
[1234.589000] thread-2  [001]  lock_release: &lock->mutex
```

### 诊断命令

```bash
# 启用锁跟踪（需要重新抓取）
echo 1 > /sys/kernel/debug/tracing/events/lock/enable

# 分析锁等待
scripts/ftrace_parser.py trace.txt --filter-event lock_contended | wc -l
scripts/timeline_analyzer.py trace.txt --target thread-2 --show-locks
```

### 根因分析

```
线程 thread-1 持有 mutex 锁 21ms（正常应 < 1ms），
导致 thread-2 等待 20.91ms。分析 thread-1 持锁期间的行为，
发现其在持锁时执行了阻塞 I/O 操作。
```

### 解决方案

1. **缩小临界区**：
   ```c
   // 错误：持锁时做 I/O
   mutex_lock(&lock);
   read_data_from_disk();  // ❌
   process(data);
   mutex_unlock(&lock);
   
   // 正确：先读数据，再持锁
   data = read_data_from_disk();
   mutex_lock(&lock);
   process(data);  // ✅
   mutex_unlock(&lock);
   ```

2. **使用读写锁**：
   ```c
   // 如果大部分是读操作
   rwlock_t lock;
   read_lock(&lock);    // 允许并发读
   read_unlock(&lock);
   ```

3. **无锁算法**：
   ```c
   // 使用原子操作替代锁
   atomic_inc(&counter);
   ```

### 预防措施

- 持锁时避免阻塞操作（I/O、sleep、大计算）
- 使用细粒度锁代替粗粒度锁
- 监控锁争用次数和等待时间

---

## 模式 4：优先级反转

### 问题表现

高优先级任务被低优先级任务阻塞。

### ftrace 特征

```
[1234.567000] low-prio-123  [000]  lock_acquire: &shared_lock
[1234.567100] low-prio-123  [000]  lock_acquired: &shared_lock
[1234.568000] high-prio-456 [000]  sched_wakeup: comm=high-prio pid=456
[1234.568100] high-prio-456 [000]  lock_acquire: &shared_lock
[1234.587000] low-prio-123  [000]  lock_release: &shared_lock
[1234.587100] high-prio-456 [000]  lock_acquired: &shared_lock  ← 等待 19ms
```

### 诊断命令

```bash
# 查看优先级和锁等待
scripts/sched_analyzer.py trace.txt --thread high-prio
scripts/timeline_analyzer.py trace.txt --target high-prio --show-locks
```

### 根因分析

```
低优先级线程 low-prio (优先级 120) 持有锁，
高优先级线程 high-prio (优先级 80) 需要该锁但无法获取，
期间中等优先级线程抢占 low-prio，导致优先级反转，
high-prio 被低优先级线程间接阻塞 19ms。
```

### 解决方案

1. **使用优先级继承协议**：
   ```c
   pthread_mutexattr_t attr;
   pthread_mutexattr_init(&attr);
   pthread_mutexattr_setprotocol(&attr, PTHREAD_PRIO_INHERIT);
   pthread_mutex_init(&lock, &attr);
   ```

2. **避免不同优先级线程共享锁**：
   - 重新设计数据结构
   - 使用消息队列通信

3. **优先级天花板协议**：
   ```c
   pthread_mutexattr_setprotocol(&attr, PTHREAD_PRIO_PROTECT);
   pthread_mutexattr_setprioceiling(&attr, 80);
   ```

### 预防措施

- 实时系统必须使用优先级继承
- 避免多个优先级层次共享资源
- 定期审计锁的使用

---

## 模式 5：CPU 迁移抖动

### 问题表现

性能波动大，缓存未命中率高。

### ftrace 特征

```
[1234.567000] myapp-1234  [000]  sched_migrate_task: comm=myapp pid=1234 dest_cpu=1
[1234.567100] myapp-1234  [001]  sched_switch: prev=idle next=myapp
[1234.567500] myapp-1234  [001]  sched_migrate_task: comm=myapp pid=1234 dest_cpu=0
[1234.567600] myapp-1234  [000]  sched_switch: prev=idle next=myapp
... (频繁迁移)
```

### 诊断命令

```bash
# 统计迁移次数
scripts/ftrace_parser.py trace.txt --filter-event sched_migrate_task | \
  grep "comm=myapp" | wc -l

# 分析迁移模式
scripts/timeline_analyzer.py trace.txt --target myapp
```

### 根因分析

```
线程 myapp 在 1s 内被迁移 237 次，平均 4.2ms 迁移一次。
每次迁移导致 L1/L2 缓存失效，缓存未命中惩罚累计 ~3ms/次，
总计约 711ms 浪费在缓存重建上。
```

### 解决方案

1. **设置 CPU 亲和性**：
   ```bash
   taskset -cp 0,1 $(pgrep myapp)  # 限制在 CPU 0,1
   ```

2. **调整调度策略**：
   ```bash
   # 增加 CPU 亲和性权重
   echo 1 > /proc/sys/kernel/sched_migration_cost_ns
   ```

3. **使用 cgroup cpuset**：
   ```bash
   mkdir /sys/fs/cgroup/cpuset/myapp
   echo "0-1" > /sys/fs/cgroup/cpuset/myapp/cpuset.cpus
   echo $(pgrep myapp) > /sys/fs/cgroup/cpuset/myapp/tasks
   ```

### 预防措施

- 为 CPU 密集型应用固定 CPU
- 使用 NUMA 节点亲和性
- 监控缓存未命中率

---

## 模式 6：软中断过载

### 问题表现

网络延迟高，但 CPU 使用率不高。

### ftrace 特征

```
[1234.567000] ksoftirqd/0-3    [000]  softirq_entry: vec=3 action=NET_RX
[1234.568000] ksoftirqd/0-3    [000]  softirq_exit: vec=3 action=NET_RX
[1234.568100] ksoftirqd/0-3    [000]  softirq_entry: vec=3 action=NET_RX
... (连续执行)
```

### 诊断命令

```bash
# 统计软中断类型和频率
scripts/ftrace_parser.py trace.txt --filter-event softirq_entry | \
  awk -F'action=' '{print $2}' | sort | uniq -c

# 分析软中断对应用的影响
scripts/causality_chain.py trace.txt --victim myapp
```

### 根因分析

```
NET_RX 软中断在 1s 内执行 15000 次，每次 ~60us，
累计占用 CPU 时间 900ms，导致 ksoftirqd 线程持续运行，
抢占普通应用。软中断处理时间超过单次时间片限制，
被推迟到 ksoftirqd 线程执行，增加延迟。
```

### 解决方案

1. **调整软中断预算**：
   ```bash
   echo 1000 > /proc/sys/net/core/netdev_budget
   ```

2. **启用 RPS（Receive Packet Steering）**：
   ```bash
   echo f > /sys/class/net/eth0/queues/rx-0/rps_cpus
   ```

3. **使用多队列网卡**：
   ```bash
   ethtool -L eth0 combined 4  # 4 个队列
   ```

### 预防措施

- 监控 `/proc/softirqs` 统计
- 使用硬件卸载减少软中断
- 为网络密集型应用预留 CPU

---

## 模式 7：周期性任务干扰

### 问题表现

应用出现规律性抖动，周期 1-10 秒。

### ftrace 特征

```
[1234.000000] kworker/0:1  [000]  sched_switch: prev=myapp next=kworker
[1235.000000] kworker/0:1  [000]  sched_switch: prev=myapp next=kworker
[1236.000000] kworker/0:1  [000]  sched_switch: prev=myapp next=kworker
... (周期性出现)
```

### 诊断命令

```bash
# 查找周期性事件
scripts/ftrace_parser.py trace.txt --filter-cpu 0 | \
  grep kworker | awk '{print $3}' | \
  awk '{print int($1)}' | uniq -c

# 分析干扰模式
scripts/timeline_analyzer.py trace.txt --target myapp --context 1000ms
```

### 根因分析

```
内核工作队列 kworker/0:1 每秒执行一次定时任务（如同步脏页），
每次执行 ~15ms，抢占 myapp。该任务由定时器触发，周期固定。
```

### 解决方案

1. **调整定时器周期**：
   ```bash
   # 减少脏页回写频率
   echo 3000 > /proc/sys/vm/dirty_writeback_centisecs
   ```

2. **绑定工作队列到其他 CPU**：
   ```bash
   # 创建自定义工作队列并绑定
   echo 2 > /sys/devices/virtual/workqueue/writeback/cpumask
   ```

3. **应用 CPU 隔离**：
   ```bash
   # 启动参数
   isolcpus=0,1 nohz_full=0,1
   ```

### 预防措施

- 识别所有周期性内核任务
- 将周期性任务迁移到独立 CPU
- 监控 CPU 使用模式

---

## 模式 8：内存回收延迟

### 问题表现

应用偶尔卡顿几百毫秒，无明显规律。

### ftrace 特征

```
[1234.567000] myapp-1234  [000]  mm_vmscan_direct_reclaim_begin
[1234.867000] myapp-1234  [000]  mm_vmscan_direct_reclaim_end: reclaimed=1024
```

### 诊断命令

```bash
# 启用内存回收跟踪
echo 1 > /sys/kernel/debug/tracing/events/vmscan/enable

# 分析回收延迟
scripts/ftrace_parser.py trace.txt --filter-event mm_vmscan_direct_reclaim
```

### 根因分析

```
应用在内存分配时触发直接内存回收，耗时 300ms。
回收期间应用被阻塞，无法继续执行。系统可用内存不足，
kswapd 后台回收速度跟不上分配速度。
```

### 解决方案

1. **增加内存**（最直接）

2. **调整 vm 参数**：
   ```bash
   echo 10 > /proc/sys/vm/swappiness        # 减少 swap
   echo 1 > /proc/sys/vm/overcommit_memory  # 限制过度分配
   ```

3. **使用内存预留**：
   ```bash
   echo 524288 > /proc/sys/vm/min_free_kbytes  # 预留 512MB
   ```

4. **应用层优化**：
   - 使用内存池
   - 预分配内存
   - 主动释放不用的内存

### 预防措施

- 监控可用内存和 kswapd 活动
- 设置内存告警阈值
- 定期审计内存使用

---

## 快速诊断流程总结

```
┌─────────────────────┐
│ 问题表现            │
│ (卡顿/抖动/性能下降)│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 抓取 ftrace 日志    │
│ (异常时间窗)        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 识别受害线程        │
│ sched_analyzer.py   │
└──────────┬──────────┘
           │
           ▼
    ┌──────┴──────┐
    │ 调度延迟？  │
    └──┬──────┬───┘
       │ Yes  │ No
       ▼      ▼
  ┌────────┐ ┌─────────┐
  │ 找阻断 │ │ 查锁/IO │
  │ 者     │ │         │
  └────┬───┘ └────┬────┘
       │          │
       ▼          ▼
  ┌─────────────────┐
  │ 构建因果链      │
  │ causality_chain │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ 验证假设        │
  │ (对照分析)      │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ 输出结论        │
  │ (量化 + 机制)   │
  └─────────────────┘
```

记住：**每个问题都有其独特的时间指纹，在 ftrace 中寻找这个指纹！**
