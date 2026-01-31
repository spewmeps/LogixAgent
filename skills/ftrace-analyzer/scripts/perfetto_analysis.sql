-- Scenario 1: CPU利用率分布
-- Analysis Goal: 识别CPU负载不均衡
SELECT
  cpu,
  sum(dur) / 1e9 AS cpu_time_seconds,
  100.0 * sum(dur) / (SELECT sum(dur) FROM sched) AS cpu_usage_percent
FROM sched
GROUP BY cpu
ORDER BY cpu_usage_percent DESC;

-- Scenario 2: 上下文切换频率
-- Analysis Goal: 发现过度调度问题
SELECT
  cpu,
  count(*) AS ctx_switches,
  count(*) * 1e9 / (SELECT max(ts) - min(ts) FROM sched) AS switches_per_sec
FROM sched
GROUP BY cpu;

-- Scenario 3: 进程/线程运行时间片
-- Analysis Goal: 识别抢占和饥饿
SELECT
  t.name,
  avg(s.dur) AS avg_slice_dur,
  max(s.dur) AS max_slice_dur,
  count(*) AS slice_count
FROM sched s
JOIN thread t USING (utid)
GROUP BY utid
ORDER BY avg_slice_dur ASC
LIMIT 20;

-- Scenario 4: 调度延迟(latency)
-- Analysis Goal: 评估实时性能
INCLUDE PERFETTO MODULE sched.latency;
SELECT
  t.name,
  avg(latency_dur) AS avg_latency,
  max(latency_dur) AS max_latency
FROM sched_latency_for_running_interval
JOIN thread t USING (utid)
GROUP BY utid
ORDER BY max_latency DESC
LIMIT 20;

-- Scenario 5: 硬中断频率和时长
-- Analysis Goal: 发现中断风暴
INCLUDE PERFETTO MODULE linux.irqs;
SELECT
  name,
  count(*) AS count,
  sum(dur) AS total_dur,
  avg(dur) AS avg_dur
FROM linux_hard_irqs
GROUP BY name
ORDER BY count DESC;

-- Scenario 6: 软中断(softirq)耗时
-- Analysis Goal: 识别网络/IO瓶颈
INCLUDE PERFETTO MODULE linux.irqs;
SELECT
  name,
  sum(dur) AS total_dur,
  avg(dur) AS avg_dur
FROM linux_soft_irqs
GROUP BY name
ORDER BY total_dur DESC;

-- Scenario 7: 运行态(Running)时长
-- Analysis Goal: 识别CPU密集型任务
SELECT
  t.name,
  p.name AS process_name,
  sum(dur) AS total_running_dur
FROM sched s
JOIN thread t USING (utid)
LEFT JOIN process p USING (upid)
GROUP BY utid
ORDER BY total_running_dur DESC
LIMIT 10;

-- Scenario 8: 睡眠态(Sleep)时长
-- Analysis Goal: 发现IO等待
SELECT
  t.name,
  sum(dur) AS sleep_dur
FROM thread_state ts
JOIN thread t USING (utid)
WHERE state = 'S'
GROUP BY utid
ORDER BY sleep_dur DESC
LIMIT 10;

-- Scenario 9: 不可中断睡眠(D状态)
-- Analysis Goal: 发现IO等待/锁等待
SELECT
  t.name,
  sum(dur) AS d_state_dur
FROM thread_state ts
JOIN thread t USING (utid)
WHERE state = 'D'
GROUP BY utid
ORDER BY d_state_dur DESC
LIMIT 10;

-- Scenario 10: 锁等待时间
-- Analysis Goal: 识别同步瓶颈
-- 假设有锁相关的slice事件
SELECT
  name,
  sum(dur) AS total_wait_dur,
  count(*) AS wait_count
FROM slice
WHERE name GLOB '*lock*' OR name GLOB '*contention*'
GROUP BY name
ORDER BY total_wait_dur DESC;

-- Scenario 11: 缺页中断频率
-- Analysis Goal: 内存压力评估
SELECT
  t.name,
  sum(c.value) AS total_faults
FROM counter c
JOIN counter_track t ON c.track_id = t.id
WHERE t.name LIKE '%page_fault%'
GROUP BY t.name;

-- Scenario 12: 块设备IO延迟
-- Analysis Goal: 存储性能
-- 统计Block IO类型slice的平均耗时
SELECT
  name,
  avg(dur) AS avg_latency,
  max(dur) AS max_latency
FROM slice
WHERE category = 'block_io'
GROUP BY name
ORDER BY avg_latency DESC;

-- Scenario 13: syscall耗时分布
-- Analysis Goal: 发现慢系统调用
SELECT
  name,
  avg(dur) AS avg_dur,
  max(dur) AS max_dur,
  count(*) AS call_count
FROM slice
WHERE category = 'syscall'
GROUP BY name
ORDER BY avg_dur DESC
LIMIT 20;

-- Scenario 14: 热点函数耗时
-- Analysis Goal: 性能瓶颈
INCLUDE PERFETTO MODULE slices.flat_slices;
SELECT
  name,
  sum(dur) AS self_time
FROM _slice_flattened
GROUP BY name
ORDER BY self_time DESC
LIMIT 20;

-- Scenario 15: 中断分布不均
-- Analysis Goal: CPU亲和性问题
SELECT
  t.name AS track_name,
  count(*) AS irq_count
FROM slice s
JOIN track t ON s.track_id = t.id
WHERE t.type = 'cpu_irq'
GROUP BY t.name
ORDER BY irq_count DESC;

-- Scenario 16: 僵尸进程/异常退出
-- Analysis Goal: 系统稳定性
SELECT
  t.name,
  count(*) AS zombie_count
FROM thread_state ts
JOIN thread t USING (utid)
WHERE state = 'Z' OR state = 'X'
GROUP BY t.name
ORDER BY zombie_count DESC;

-- Scenario 17: 内存回收(reclaim)活动
-- Analysis Goal: 内存不足
SELECT
  name,
  sum(dur) AS total_dur,
  count(*) AS count
FROM slice
WHERE name GLOB '*kswapd*' OR name GLOB '*reclaim*'
GROUP BY name
ORDER BY total_dur DESC;

-- Scenario 18: IO操作频率
-- Analysis Goal: 识别IO热点
SELECT
  name,
  count(*) AS io_count
FROM slice
WHERE category = 'block_io'
GROUP BY name
ORDER BY io_count DESC;

-- Scenario 19: QoS限流/调度延迟规律分析
-- Analysis Goal: 识别Cgroup/QoS限流导致的规律性延迟
INCLUDE PERFETTO MODULE sched.latency;
SELECT
  t.name AS thread_name,
  count(*) AS latency_count_total,
  SUM(CASE WHEN latency_dur BETWEEN 5000000 AND 10000000 THEN 1 ELSE 0 END) AS count_5ms_10ms,
  SUM(CASE WHEN latency_dur > 10000000 THEN 1 ELSE 0 END) AS count_over_10ms,
  MAX(latency_dur) AS max_latency,
  AVG(latency_dur) AS avg_latency
FROM sched_latency_for_running_interval
JOIN thread t USING (utid)
WHERE latency_dur > 5000000
GROUP BY t.name
ORDER BY count_5ms_10ms DESC
LIMIT 20;

-- Scenario 20: 唤醒源统计
-- Analysis Goal: 分析唤醒关系，定位谁在唤醒关键线程
SELECT
  waker.name AS waker_thread,
  wakee.name AS wakee_thread,
  count(*) AS wake_count
FROM thread_state ts
JOIN thread waker ON ts.waker_utid = waker.utid
JOIN thread wakee ON ts.utid = wakee.utid
WHERE ts.state = 'R'
GROUP BY waker.name, wakee.name
ORDER BY wake_count DESC
LIMIT 20;

-- Scenario 21: Futex/锁竞争
-- Analysis Goal: 识别用户态锁竞争(通过syscall)
SELECT
  name,
  count(*) AS count,
  avg(dur) AS avg_dur
FROM slice
WHERE name LIKE 'sys_futex%'
GROUP BY name
ORDER BY count DESC;

-- Scenario 22: 长时D状态(疑似死锁)
-- Analysis Goal: 发现超过5秒的不可中断睡眠
SELECT
  t.name,
  ts.state,
  ts.dur,
  ts.ts
FROM thread_state ts
JOIN thread t USING (utid)
WHERE ts.state = 'D' AND ts.dur > 5000000000
ORDER BY ts.dur DESC
LIMIT 20;

-- Scenario 23: 内存分配耗时
-- Analysis Goal: 评估内核内存分配延迟
SELECT
  name,
  count(*) AS count,
  avg(dur) AS avg_dur,
  max(dur) AS max_dur
FROM slice
WHERE name GLOB '*alloc*'
  AND (category GLOB '*kmem*' OR category GLOB '*mm*')
GROUP BY name
ORDER BY avg_dur DESC;

-- Scenario 24: Trace时间范围概览
-- Analysis Goal: 确认Trace时长和基本规模
SELECT
  (max(ts) - min(ts)) / 1e9 AS duration_sec,
  count(*) AS sched_events
FROM sched;

-- Scenario 25: Slice事件分类统计
-- Analysis Goal: 了解系统活动分布
SELECT
  category,
  count(*) AS count
FROM slice
GROUP BY category
ORDER BY count DESC;

-- Scenario 26: 调用栈深度分析
-- Analysis Goal: 评估函数调用复杂度(需相关Trace)
SELECT
  depth,
  count(*) AS count
FROM slice
GROUP BY depth
ORDER BY depth DESC;

-- Scenario 27: Top耗时事件(单次)
-- Analysis Goal: 发现极端的长耗时操作
SELECT
  name,
  dur,
  ts
FROM slice
ORDER BY dur DESC
LIMIT 20;

-- Scenario 28: 进程级CPU消耗排名
-- Analysis Goal: 宏观评估各进程负载
SELECT
  p.name AS process_name,
  sum(s.dur) / 1e9 AS cpu_time_sec
FROM sched s
JOIN thread t USING (utid)
LEFT JOIN process p USING (upid)
GROUP BY p.name
ORDER BY cpu_time_sec DESC
LIMIT 20;

-- Scenario 29: 活跃线程统计
-- Analysis Goal: 评估系统并发规模
SELECT
  count(distinct utid) AS active_threads_count
FROM sched;

-- Scenario 30: 调度时间轴不连续检测
-- Analysis Goal: 发现Trace数据丢失或溢出
SELECT
  ts,
  ts - lag(ts) OVER (ORDER BY ts) AS gap
FROM sched
ORDER BY gap DESC
LIMIT 10;
