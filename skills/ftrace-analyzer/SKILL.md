---
name: ftrace-analyzer
description: 专业的 ftrace 日志分析工具，遵循“时间归属证明”理论，通过三层架构（TraceFile -> QueryBuilder -> Analyzer）实现从宏观总览到微观函数级的深度诊断。特别擅长识别调度抖动、卡顿偏态、中断风暴等无报错性能问题。
---

# ftrace 日志分析 Skill

## 使用范围与安全边界

- 本 Skill 仅对**离线 ftrace 日志文件**进行读取和分析。
- 不会，也不应该在当前运行环境执行任何系统命令（如 `ssh`、`perf`、`trace-cmd` 等）。
- 日志所属主机与当前运行环境无关，请在目标主机上完成采集后，仅将日志文件交给本 Skill 做离线分析。

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

> 重要说明：以下命令只对 `trace.log` 等 ftrace 日志文件做离线解析，不会在当前运行环境执行任何系统命令。

| 类别 | 参数 | 功能描述 | 示例 |
| :--- | :--- | :--- | :--- |
| **基础信息** | `--summary` | 显示日志文本摘要（起止时间、CPU/进程数等） | `python3 scripts/main.py trace.log --summary` |
| | `--info` | 以 JSON 格式输出详细的元数据和统计信息 | `python3 scripts/main.py trace.log --info` |
| **核心分析** | `--analyze-gaps MS` | 检测大于 MS 毫秒的时间断层，识别 CPU 空白期 | `python3 scripts/main.py trace.log --analyze-gaps 0.1` |
| | `--analyze-qos` | 检测可能由 CPU QoS 导致的规律性时延（5-10ms） | `python3 scripts/main.py trace.log --analyze-qos` |
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

在输出分析结论时，**最重要的目标是给出问题出处**，方便你回到原始日志中做二次验证，而不是给出解决方案或验证方案。

推荐使用精简的两段式结构：

### 1. 问题描述 (What)
用 1～2 句话描述你在日志中观察到的现象，避免展开解决思路。
- **示例**：CPU 0 在 100.5s 附近存在一段约 45ms 的调度延迟，期间 `myapp` 长时间未在 CPU 上运行。

### 2. 证据出处 (Where)
列出关键日志片段，**必须包含日志文件名和行号 / 行号区间**，能够直接定位到原始日志位置，支持你自行复现和验证。
- **基础格式**：`[文件名:行号] 时间戳 事件内容 -> 关键字段值`
- **示例**：
- [trace.log:1245] `100.501234: sched_switch: prev_comm=myapp prev_pid=1234 prev_prio=120 prev_state=R ==> next_comm=ksoftirqd/0 next_pid=10` -> `myapp` 被抢占。
- [trace.log:1246-1300] 期间 CPU 0 持续运行 `ksoftirqd/0`，直到 `100.546789` 才切回 `myapp`。

如需补充统计类信息（例如聚合统计结果、百分位数等），同样需要给出可以复现该统计的命令或查询条件，但**不在结论中写解决方案或验证步骤**。

---

## 故障检测与识别指南

### 1. CPU QoS 导致的规律性时延
**现象特征**：
- **时延集中**：调度延迟高度集中在 5~10ms 之间（通常吻合 CPU QoS 默认粒度）。
- **规律性**：延迟出现具有明显的周期性或在时间轴上分布均匀。
- **CPU 空闲**：延迟期间 CPU 往往处于空闲状态（无软/硬中断或高优先级任务抢占），表现为 ftrace 上的大段空白间隙。

**分析逻辑**：
1. **非随机波动**：延迟不是随机出现的，而是被某种机制“整齐”地切分。
2. **QoS 基线吻合**：5~10ms 的延迟时长与内核 CPU QoS (Bandwidth Control) 的默认检测周期高度一致。
3. **空闲却不调度**：任务 Runnable 但 CPU 空闲且不调度，强烈暗示是配额（Quota）耗尽导致的 Throttling。

**检测命令**：
```bash
# 自动检测是否存在 QoS 导致的规律性时延
python3 scripts/main.py trace.log --analyze-qos
```

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

一个合格的 ftrace 分析结论，**至少要让使用者能根据“出处”在原始日志中复现你的观察**。建议遵循以下要点：

1. **明确定位**  
   - 每条结论都应包含至少一个带行号的引用，例如：`[trace.log:1234]` 或 `[trace.log:1200-1210]`。

2. **适度概括**  
   - 用简短自然语言说明“这里发生了什么”，避免在结论中写“应该怎么修”“如何验证”等方案类内容。

3. **可复现性**  
   - 如结论依赖聚合统计或过滤查询，给出对应的查询条件或命令（例如使用 `main.py` 的参数组合），方便在相同日志上重复得到同样的结果。

4. **不包含解决方案与验证方案**  
   - 结论仅承担“指出问题在哪里、表现是什么”的职责；解决思路、优化建议、验证计划可以由人类在拿到这些出处信息后再行撰写。

---

## 注意事项
1. **仅针对离线日志分析**：本 Skill 只读取并分析你提供的 ftrace 日志，不会在当前环境执行任何系统命令；请在目标主机上完成采集后再上传日志。
2. **优先使用 CLI 工具进行探索分析**：通过 `main.py` 提供的命令行接口可以快速获取统计数据和过滤结果，无需编写代码。
3. **复杂自动化场景可调用 API**：对于需要高度定制的复杂分析逻辑，可以使用 `TraceFile` 和 `Analyzer` 提供的 Python 类库进行二次开发。
4. **关注长尾**：1% 的 10ms 卡顿比 99% 的 10us 正常运行更具诊断价值。
5. **保持怀疑**：日志可能因缓冲区溢出而丢失，结论需具备可证伪性。
6. **分析完整性**：对文件的分析内容必须是完整的，不能仅仅针对局部内容分析，要确保全部都分析过，避免遗漏关键线索。
