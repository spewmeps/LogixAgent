---
name: ftrace-analyzer
description: >
  专业的 ftrace 日志分析工具，用于诊断 Linux 内核调度、性能、卡顿等问题。
  特别擅长无报错的纯性能问题识别（偏态分析）。
  支持大文件高效处理、时序分析、调度路径还原、因果链构建、正常/异常场景对比。
triggers:
  - ftrace
  - sched
  - latency
  - kernel log
  - 调度
  - 性能
  - 卡顿
  - 延迟
---

# ftrace 日志分析 Skill

## 核心原则

**把 ftrace 当成内核级时序显微镜**，核心不是"抓了什么"，而是**如何把海量事件还原成因果链**。

### 三大基本原则

1. **先有问题，再看日志**：ftrace 用来验证假设，不是用来"扫一眼"
2. **时间因果优先于函数细节**：时间关系 > 调用关系
3. **永远沿调度视角展开**：最终回答三个问题
   - 线程是否 runnable？
   - 线程是否 running？
   - 是谁阻止了它 running？

### 性能问题特殊原则

**⚠️ 重要认知转变**：性能问题 ≠ 异常事件发生，而是**"正常事件以不正常的方式出现"**

**核心方法不是"找错"，而是"找偏态"**：
- 没有 error/warning 也可能有严重性能问题
- 每条事件看起来都合法，但**分布不正常**
- ftrace 是**时间归属证明工具**，不只是错误检测工具

**三种识别视角**：
1. **时间视角**：某些阶段是否比预期更长？延迟模式是什么？
2. **调度视角**：该跑的没跑，跑的不是它（调度资源分配问题）
3. **干扰视角**：谁在"合法地"占用时间？被谁偷走了时间？

**分析模式**：
- **有对照组**：对比正常/异常场景差异（最理想）
- **无对照组**：基于绝对阈值和统计特征判断（常见场景）

## 分析工作流程（五步法）

### Step 1: 锚定异常时间窗

**目标**：确定问题的精确时间范围

```bash
# 快速查看日志时间范围和基本统计
scripts/ftrace_parser.py <日志文件> --summary
```

**输出**：
- 日志起止时间
- 总事件数
- 主要事件类型分布
- CPU 使用情况

### Step 2: 识别受害线程

**目标**：找出体验异常的线程/任务

```bash
# 分析特定线程的状态变化
scripts/sched_analyzer.py <日志文件> --thread <进程名或PID> --window <开始时间>,<结束时间>
```

**关键输出**：
- 线程状态时间线（runnable → running → blocked）
- 调度延迟统计
- 被抢占次数

### Step 3: 还原调度路径

**目标**：理解线程为何不能运行

```bash
# 生成调度事件时间线
scripts/timeline_analyzer.py <日志文件> --target <目标线程> --context 100ms
```

**分析重点**：
- runnable → running 之间的时间（调度延迟）
- 是否被反复抢占或推迟
- 等待资源的时间

### Step 4: 寻找阻断者

**目标**：识别让目标线程无法运行的主体

```bash
# 分析 CPU 占用和干扰源
scripts/causality_chain.py <日志文件> --victim <目标线程> --window <时间窗>
```

**候选阻断者**：
- 高优先级线程
- 中断/软中断
- 长时间运行的内核上下文
- 锁竞争

### Step 5: 构建因果链

**目标**：压缩日志为最短因果链

使用 causality_chain.py 的输出，构建一句话结论：

> **因为 A 在 T1 发生 → 导致 B 在 T2 占用 → 使 C 在 T3 延迟**

## 性能问题专项识别（无报错场景）

**⚠️ 关键认知**：90% 的性能问题没有报错，ftrace 日志看起来"一切正常"

### 性能问题的七步 Checklist

按此顺序逐条检查，任意一条出现明显偏态就是线索：

#### ✅ 1. 时间分布是否异常（第一优先级）

**有对照组场景**：
```bash
# 对比正常和异常场景
scripts/performance_analyzer.py <日志文件> --thread <目标> --baseline <正常日志>
```

**无对照组场景**（更常见）：
```bash
# 分析单个日志的统计特征
scripts/sched_analyzer.py <日志文件> --thread <目标>
```

**判断标准（基于绝对阈值）**：
- 平均调度延迟 > 10ms：可疑
- 平均调度延迟 > 20ms：异常
- 最大调度延迟 > 50ms：严重
- P99 延迟 > 30ms：有问题
- 标准差很大：抖动严重

**检查时间分布形态**：
- 是否有明显的长尾？
- 是否有周期性的尖刺？
- 是否持续在高位？

#### ✅ 2. 目标线程是否"该跑却没跑"

```bash
# 分析可运行但未运行的时间
scripts/sched_analyzer.py <日志文件> --thread <目标>
```

**检查指标**（无对照组也能判断）：
- runnable → running 延迟 > 10ms：异常
- runnable 状态占比 > 30%：CPU 资源不足
- 被抢占次数 > 上下文切换次数的 50%：频繁被打断

**关键问题**：
- 何时具备运行条件（runnable）？
- 何时真正开始运行（running）？
- 中间差了多久？（绝对值判断）

#### ✅ 3. CPU 时间归属是否合理

```bash
# 分析目标线程未运行时的 CPU 占用
scripts/timeline_analyzer.py <日志文件> --target <目标> --context 100ms
```

**无对照组判断方法**：
- 查看 runnable 期间，CPU 被谁占用
- 某个任务占用时间 > 10ms：需要关注
- 某个任务占用比例 > 50%：主要阻断者
- 实时线程（优先级 < 100）持续占用：典型问题

**关键判断**：
> 时间不是消失了，而是被别人合法拿走了

**识别时间窃贼的标准**：
- 占用时间长（单次 > 10ms 或累计 > 100ms）
- 占用持续性强（不是偶发）
- 与延迟时间窗口重叠

#### ✅ 4. 运行是否被"切碎"

```bash
# 检查运行片段长度
scripts/sched_analyzer.py <日志文件> --thread <目标>
```

**无对照组判断标准**：
- 平均运行时间片 < 1ms：严重切碎
- 平均运行时间片 < 5ms：被切碎
- 抢占率 > 50%：频繁打断
- 上下文切换频率 > 1000次/秒：异常

**典型性能陷阱**："看起来在跑，实际上没效率"

#### ✅ 5. 是否存在"无关行为膨胀"

```bash
# 查看事件分布
scripts/ftrace_parser.py <日志文件> --summary
```

**无对照组识别方法**：
查看后台任务的活跃度：
- `kworker/*` 事件 > 10000/秒：后台任务过载
- `kswapd` 活跃：内存压力
- `ksoftirqd/*` 频繁运行：软中断过载
- 中断频率 > 50000/秒：可能中断风暴

**判断标准**（绝对值）：
- 后台任务 CPU 占比 > 30%：异常
- 软中断 CPU 占比 > 20%：过载
- 中断处理累计时间 > 可用 CPU 时间的 50%：严重

**性能问题常常是配角戏份太多**

#### ✅ 6. 识别异常的时间段或模式

**无对照组场景的核心方法**：

**a) 时间窗口分析**：
```bash
# 分段分析，找出异常时间段
scripts/sched_analyzer.py <日志文件> --thread <目标> --window <T1>,<T2>
```

**b) 查找异常模式**：
- 周期性延迟：每隔固定时间出现
- 突发延迟：某个时间点突然爆发
- 持续延迟：整个时间窗口都高

**c) 事件聚类分析**：
```bash
# 统计事件时间分布
scripts/ftrace_parser.py <日志文件> --filter-event sched_switch | \
  awk '{print int($3)}' | sort | uniq -c
```

**识别标准**：
- 某些秒的事件数 >> 平均值的 2 倍：异常段
- 延迟集中在某几个时间点：突发问题
- 延迟均匀分布但都很高：系统性问题

#### ✅ 7. 能否压缩成一条因果链

**无对照组也要构建因果链**

模板：
```
在 [时间窗口] 内，
目标线程 X 的调度延迟达到 [具体值]ms（超过正常阈值 [阈值]ms），
期间 CPU 被 Y 占用（持续 [时长]ms，占比 [百分比]%），
Y 的行为特征是 [描述]，
因此判断 Y 是主要阻断者。
```

**示例（无对照）**：
```
在 1234.5-1235.5s 时间窗口内，
myapp 的调度延迟达到 45ms（超过正常阈值 10ms），
期间 CPU 被 irq/28-GPU 占用（持续 180ms，占比 68%），
irq/28-GPU 是实时中断线程（优先级 50），
因此判断 GPU 中断处理是主要阻断者。
```

**如果做不到**：说明还需要更详细的时间线分析

### 无对照场景的判断阈值参考

| 指标 | 正常 | 可疑 | 异常 | 严重 |
|-----|------|------|------|------|
| 平均调度延迟 | < 5ms | 5-10ms | 10-20ms | > 20ms |
| 最大调度延迟 | < 10ms | 10-30ms | 30-50ms | > 50ms |
| P99 延迟 | < 8ms | 8-20ms | 20-30ms | > 30ms |
| 平均运行时间片 | > 10ms | 5-10ms | 1-5ms | < 1ms |
| 抢占率 | < 20% | 20-40% | 40-60% | > 60% |
| 后台任务 CPU 占比 | < 10% | 10-20% | 20-40% | > 40% |
| 中断频率 | < 10k/s | 10-30k/s | 30-50k/s | > 50k/s |

**⚠️ 注意**：这些阈值是经验值，具体场景可能有差异

### 性能问题的五个异常信号

这些信号**不会报错，但一定会在 ftrace 中留下痕迹**：

1. **可运行 → 运行延迟异常**：CPU 忙，但忙的不是你（> 10ms）
2. **运行被频繁切碎**：线程"活着"，但几乎没干成事（时间片 < 5ms）
3. **高频唤醒但低有效运行**：调度效率极低（wakeup > 1000/s）
4. **后台行为时间膨胀**：背景噪声变吵了（后台 CPU > 30%）
5. **时间归属集中**：某个任务持续占用 CPU（单一占比 > 50%）

### 性能问题结论标准

**无对照场景下的合格结论**：

```
在 [时间窗口] 内，X 的调度延迟达到 [具体值]ms（超过正常阈值 [阈值]ms），
期间 CPU 主要被 Y 占用（占比 [百分比]%，持续 [时长]ms），
Y 的特征是 [优先级/类型/行为模式]，
该占用模式 [持续/周期性/突发]，
因此性能问题由 Y 的 [具体行为] 导致。
```

**注意**：
- 必须量化（具体数值）
- 基于绝对阈值判断
- 说明时间归属
- 解释为什么它能阻断

## 脚本工具说明

### ftrace_parser.py - 核心解析器

高效解析大型 ftrace 日志（支持 GB 级文件）

```bash
# 基本用法
scripts/ftrace_parser.py <日志文件> [选项]

# 选项
--summary              # 显示日志概要
--filter-cpu <N>       # 只看特定 CPU
--filter-pid <PID>     # 只看特定进程
--filter-event <类型>  # 只看特定事件类型
--time-range <开始>,<结束>  # 时间范围过滤
--output <输出文件>    # 保存过滤结果
```

**性能优化**：
- 流式处理，不一次性加载到内存
- 支持增量解析
- 自动识别日志格式

### sched_analyzer.py - 调度分析

专注于调度事件的深度分析

```bash
scripts/sched_analyzer.py <日志文件> [选项]

# 关键选项
--thread <名称/PID>     # 分析特定线程
--cpu <N>               # 分析特定 CPU
--latency-threshold <ms> # 延迟阈值
--report-format <text|json|html>  # 输出格式
```

**分析维度**：
- 调度延迟分布
- 上下文切换频率
- 抢占统计
- CPU 亲和性变化

### timeline_analyzer.py - 时间线分析

生成可视化的事件时间线

```bash
scripts/timeline_analyzer.py <日志文件> [选项]

--target <线程>          # 目标线程
--context <时间范围>     # 显示前后多少时间的上下文
--show-interrupts       # 显示中断事件
--show-locks            # 显示锁事件
--output-svg <文件>     # 生成 SVG 图表
```

### causality_chain.py - 因果链构建

自动识别事件间的因果关系

```bash
scripts/causality_chain.py <日志文件> --victim <目标线程> [选项]

--window <时间窗>        # 分析时间窗口
--min-correlation <阈值> # 最小相关性阈值
--max-chain-length <N>   # 最大因果链长度
--output-graph <文件>    # 输出因果图
```

## 典型问题分析模式

### 卡顿/延迟问题

**模型**：runnable 但长期未 running

**分析命令**：
```bash
# 1. 找到延迟最大的时间段
scripts/sched_analyzer.py log.txt --thread <目标> --latency-threshold 10ms

# 2. 查看该时间段内的 CPU 占用
scripts/timeline_analyzer.py log.txt --target <目标> --context 50ms

# 3. 识别阻断者
scripts/causality_chain.py log.txt --victim <目标> --window <问题时间窗>
```

### 抖动/不稳定

**模型**：高频 wakeup + 快速 sleep

**分析命令**：
```bash
# 统计 wakeup/sleep 频率
scripts/ftrace_parser.py log.txt --filter-pid <PID> | \
  grep -E 'sched_wakeup|sched_switch.*\[S\]' | wc -l
```

### 性能退化

**模型**：单次不慢，但累计耗时异常

**需要对照分析**：
```bash
# 对比正常和异常日志的事件密度
scripts/sched_analyzer.py normal.txt --summary > normal_stats.txt
scripts/sched_analyzer.py abnormal.txt --summary > abnormal_stats.txt
diff normal_stats.txt abnormal_stats.txt
```

## 性能优化建议

### 处理大文件

```bash
# 1. 先过滤再分析（减少数据量）
scripts/ftrace_parser.py huge_log.txt \
  --filter-cpu 0 \
  --time-range 1000.0,2000.0 \
  --output filtered.txt

# 2. 对过滤后的小文件进行详细分析
scripts/sched_analyzer.py filtered.txt --thread myapp
```

### 避免中间文件

```bash
# 使用管道直接传递数据
scripts/ftrace_parser.py log.txt --filter-event sched_switch | \
  scripts/sched_analyzer.py --stdin --report-format json
```

### 并行处理（多 CPU 日志）

```bash
# 分别分析每个 CPU，然后合并结果
for cpu in 0 1 2 3; do
  scripts/sched_analyzer.py log.txt --cpu $cpu --output cpu${cpu}_analysis.json &
done
wait
```

## 输出结论的标准格式

一个合格的分析报告必须包含：

1. **异常表现**（可量化）
   - 示例："线程 X 的平均调度延迟从 2ms 增加到 50ms"

2. **直接原因**（谁挡了路）
   - 示例："CPU 0 被高优先级线程 Y 持续占用"

3. **机制解释**（为什么它能挡路）
   - 示例："线程 Y 优先级为 99（实时），而 X 为 120（普通）"

4. **排他性**（为什么不是别的原因）
   - 示例："中断延迟正常，锁竞争不显著，排除其他因素"

## 参考文档

- `references/methodology.md` - 完整的分析方法论
- `references/performance_methodology.md` - **无报错性能问题专项方法论**（重要）
- `references/common_patterns.md` - 常见问题模式和案例
- `references/event_types.md` - ftrace 事件类型详解

## 注意事项

1. **只分析日志**：本 skill 不支持远程登录或实时抓取
2. **必须有对照**：对比正常和异常场景的差异
3. **量化结论**：避免主观描述，用数据说话
4. **保持怀疑**：日志可能不完整，结论需要可证伪性
