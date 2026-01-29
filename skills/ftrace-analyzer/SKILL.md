---
name: ftrace-analyzer
description: 专业的 ftrace 日志分析工具，遵循“时间归属证明”理论，通过三层架构（TraceFile -> QueryBuilder -> Analyzer）实现从宏观总览到微观函数级的深度诊断。特别擅长识别调度抖动、卡顿偏态、中断风暴等无报错性能问题。
---

# ftrace 日志分析 Skill

## 核心哲学：时间归属证明

**ftrace 日志不是“谁调用了谁”，而是一张“CPU 时间账单”。**

### 三大核心认知
1. **性能分析的本质**：时间被谁占走了？（时间因果优先于函数细节）。
2. **偏态识别**：性能问题通常不是异常事件发生，而是“正常事件以不正常的方式出现”（如：原本 10us 的函数跑了 1ms）。
3. **调度视角**：永远通过“线程是否 runnable -> 是否 running -> 谁阻止了它 running”来还原真相。

---

## 分析理论：七层深度模型

在分析任何 ftrace 日志时，应由浅入深套用以下框架：

1. **第一层：识别「时间尺度」与「卡顿级别」**
   - 建立阈值感：<10µs 正常；100µs-1ms 明显卡顿；>1ms 系统级问题。
   - 确定是单点偶发还是周期性/持续性问题。

2. **第二层：按「执行上下文」分区**
   - 将日志拆分为：用户进程、内核线程 (kworker)、硬中断 (irq)、软中断 (softirq)。
   - 明确责任主体：90% 的问题在于 CPU 被非业务上下文占用。

3. **第三层：判断「业务到底在不在跑」**
   - 卡顿期间，业务进程是否在 CPU 上？
   - **不在 CPU** -> 业务在“等”，重点查调度与干扰。
   - **在 CPU** -> 业务在“干”，重点查函数路径与资源竞争。

4. **第四层：调度视角分析（最重要）**
   - **时间断层**：myapp 两次出现之间消失的 500µs 去哪了？
   - **语义解码**：`prev_state=R` (被抢占/时间片用完) vs `prev_state=S` (主动睡眠/等锁/等 IO)。

5. **第五层：中断 / 软中断责任判断**
   - 检查中断是否“过长”或“过密”（中断风暴）。
   - 中断是否把业务时间轴切得过于细碎。

6. **第六层：函数级分析**
   - 只有确认业务在跑且没被抢占时，才分析函数。
   - 关注“哪个函数区间占据了异常长的时间”，关注长尾而非平均值。

7. **第七层：映射回系统资源**
   - ksoftirqd -> 网络/IO；kworker -> 后台任务；无记录 -> CPU 竞争。

---

## 推荐工作流：总览 -> 定位 -> 深入 -> 验证

基于三层架构工具（`TraceFile` -> `QueryBuilder` -> `Analyzer`）的执行步骤：

### Step 1: 总览 (Overview) - 建立全局视野
快速了解日志规模、时间跨度和基本统计特征。
```bash
# 获取日志摘要信息 (时间范围、CPU 数、进程数等)
python3 scripts/main.py trace.log --summary

# 获取更详细的元数据 (JSON 格式)
python3 scripts/main.py trace.log --info
```

### Step 2: 定位 (Locate) - 寻找异常时间窗
通过时间分布和异常检测，缩小关注范围。
```bash
# 1. 检测时间断层 (检测大于 0.1ms 的空白，识别“进程去哪了”)
python3 scripts/main.py trace.log --analyze-gaps 0.1

# 2. 识别执行上下文分区 (统计中断、内核态、用户态占比)
python3 scripts/main.py trace.log --classify
```

### Step 3: 深入 (Deep Dive) - 多维深度分析
针对可疑点，分析上下文切换、进程状态和 CPU 占用。
```bash
# 1. 检查特定 PID 的运行状态与调度延迟
python3 scripts/main.py trace.log --check-pid 1234 --time-range 100.0 101.0

# 2. 统计特定进程名的调度性能 (次数、耗时、时间片)
python3 scripts/main.py trace.log --stats "myapp"

# 3. 灵活查询特定 CPU 在特定时间段的事件详情
python3 scripts/main.py trace.log --query-cpu 0 --time-range 100.0 101.0 --limit 50
```

### Step 4: 验证 (Verify) - 构建因果链与结论
导出数据进行多维对比验证。
```bash
# 导出特定查询结果到 JSON 供进一步分析
python3 scripts/main.py trace.log --query-comm "myapp" --export-json result.json
```

---

## 脚本工具使用指南

脚本路径：[main.py](file:///opt/src/LogixAgent/skills/ftrace-analyzer/scripts/main.py)

| 类别 | 参数 | 功能描述 | 示例 |
| :--- | :--- | :--- | :--- |
| **基础信息** | `--summary` | 显示日志文本摘要（起止时间、CPU/进程数等） | `python3 scripts/main.py trace.log --summary` |
| | `--info` | 以 JSON 格式输出详细的元数据和统计信息 | `python3 scripts/main.py trace.log --info` |
| **核心分析** | `--analyze-gaps MS` | 检测大于 MS 毫秒的时间断层，识别 CPU 空白期 | `python3 scripts/main.py trace.log --analyze-gaps 0.1` |
| | `--classify` | 统计执行上下文分区占比（用户、内核、中断、软中断） | `python3 scripts/main.py trace.log --classify` |
| | `--stats COMM` | 获取特定进程名的调度性能统计（次数、耗时、时间片） | `python3 scripts/main.py trace.log --stats "myapp"` |
| | `--check-pid PID` | 检查特定 PID 的运行状态、调度延迟及平均时间片 | `python3 scripts/main.py trace.log --check-pid 1234` |
| **灵活查询** | `--query-pid PID` | 按进程 ID 过滤事件 | `python3 scripts/main.py trace.log --query-pid 1234` |
| | `--query-comm COMM` | 按进程名称过滤事件 | `python3 scripts/main.py trace.log --query-comm "myapp"` |
| | `--query-cpu CPU` | 按 CPU 核心过滤事件 | `python3 scripts/main.py trace.log --query-cpu 0` |
| | `--time-range S E` | 限定分析的时间范围（开始 结束，单位：秒） | `python3 scripts/main.py trace.log --time-range 100.0 101.0` |
| | `--limit N` | 限制查询输出的行数（默认 10） | `python3 scripts/main.py trace.log --query-pid 1 --limit 50` |
| **数据导出** | `--export-json FILE` | 将查询结果导出为 JSON 文件 | `python3 scripts/main.py trace.log --query-cpu 0 --export-json cpu0.json` |
| | `--export-csv FILE` | 将查询结果导出为 CSV 文件 | `python3 scripts/main.py trace.log --query-pid 123 --export-csv pid123.csv` |

---

## 输出格式规范

在输出分析结论时，必须严格遵守以下三段式结构，确保结论可追溯、可验证：

### 1. 定位根因 (Root Cause)
直接给出结论性的判断。
- **示例**：CPU 0 在 100.5s 附近发生严重调度延迟，导致 `myapp` 进程卡顿 45ms。

### 2. 理论依据 (Methodology)
解释为何得出此结论，对应“七层分析模型”中的哪一层或哪种信号。
- **示例**：基于“第四层：调度视角分析”，观察到 `myapp` 处于 `runnable` 状态但长时间未切入 `running`，且 `prev_state=R` 表明其被抢占。

### 3. 证据 (Evidence)
提供日志中的具体数据支撑，**必须包含行号**。
- **格式**：`[文件名:行号] 时间戳 事件内容 -> 关键字段值`
- **示例**：
  - [trace.log:1245] `100.501234: sched_switch: prev_comm=myapp prev_pid=1234 prev_prio=120 prev_state=R ==> next_comm=ksoftirqd/0 next_pid=10` -> `myapp` 被抢占。
  - [trace.log:1246-1300] 期间 CPU 0 持续运行 `ksoftirqd/0`，直到 `100.546789` 才切回 `myapp`。
  - 统计数据支持：`python3 scripts/main.py trace.log --check-pid 1234` 输出显示 `avg_timeslice_ms: 0.8` (运行被严重切碎)。

---

## 典型异常信号清单

| 信号 | 含义 | 判据 (经验值) |
| :--- | :--- | :--- |
| **时间断层** | 进程消失，CPU 忙于他事 | gap > 100µs |
| **调度延迟** | Runnable 到 Running 间隔过长 | delay > 1ms |
| **调度抖动** | 频繁唤醒立即睡眠 (Wakeup Storm) | 切换频率 > 1000/s |
| **运行切碎** | 单次运行时间片过短 | timeslice < 500µs |
| **中断侵占** | 中断/软中断持续占用 CPU | 占比 > 20% 或单次 > 500µs |

---

## 结论输出标准格式

一个专业的 ftrace 分析结论必须包含：
1. **异常表现**：量化受害者的指标（如：调度延迟从 10us 飙升至 2ms）。
2. **时间归属**：说明这段时间 CPU 在干什么（如：被 ksoftirqd 占用 80%）。
3. **直接原因**：指明阻断者及其行为（如：中断风暴导致 CPU 被切碎）。
4. **机制解释**：为什么阻断者能影响受害者（如：RT 线程抢占了普通线程）。

---

## 注意事项
1. **优先使用 CLI 工具进行探索分析**：通过 `main.py` 提供的命令行接口可以快速获取统计数据和过滤结果，无需编写代码。
2. **复杂自动化场景可调用 API**：对于需要高度定制的复杂分析逻辑，可以使用 `TraceFile` 和 `Analyzer` 提供的 Python 类库进行二次开发。
3. **关注长尾**：1% 的 10ms 卡顿比 99% 的 10us 正常运行更具诊断价值。
4. **保持怀疑**：日志可能因缓冲区溢出而丢失，结论需具备可证伪性。
