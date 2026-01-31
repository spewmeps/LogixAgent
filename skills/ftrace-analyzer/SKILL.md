---
name: ftrace-analyzer
description: 专业的 ftrace 日志分析工具，遵循“时间归属证明”理论，通过 Perfetto SQL 引擎实现从宏观总览到微观函数级的深度诊断。特别擅长识别调度抖动、卡顿偏态、中断风暴等无报错性能问题。
---

# ftrace 日志分析 Skill

## 使用范围与安全边界

- 本 Skill 仅对**离线 ftrace/perfetto 日志文件**进行读取和分析。
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

在分析任何 ftrace 日志时，应由浅入深套用以下框架（详见 [ftrace_analysis_metrics.md](file:///opt/src/LogixAgent/skills/ftrace-analyzer/references/ftrace_analysis_metrics.md)）：

1. **第一层：识别「时间尺度」与「卡顿级别」**
   - 建立阈值感：<10µs 正常；100µs-1ms 明显卡顿；>1ms 系统级问题。
2. **第二层：按「执行上下文」分区**
   - 将日志拆分为：用户进程、内核线程 (kworker)、硬中断 (irq)、软中断 (softirq)。
3. **第三层：判断「业务到底在不在跑」**
   - **不在 CPU** -> 业务在“等”，重点查调度与干扰。
   - **在 CPU** -> 业务在“干”，重点查函数路径与资源竞争。
4. **第四层：调度视角分析（最重要）**
   - **时间断层**：myapp 两次出现之间消失的 500µs 去哪了？
   - **语义解码**：`prev_state=R` (被抢占/时间片用完) vs `prev_state=S` (主动睡眠/等锁/等 IO)。
5. **第五层：中断 / 软中断责任判断**
   - 检查中断是否“过长”或“过密”（中断风暴）。
6. **第六层：函数级分析**
   - 关注“哪个函数区间占据了异常长的时间”，关注长尾而非平均值。
7. **第七层：映射回系统资源**
   - ksoftirqd -> 网络/IO；kworker -> 后台任务；无记录 -> CPU 竞争。

---

## 标准分析工作流规范：总览 -> 钻取 -> 验证

必须严格遵循基于新一代 Perfetto SQL 分析架构的执行步骤：

### Step 1: 全局体检 (Global Check) - 建立全局视野
使用 `global_analysis.py` 运行预置的 30+ 个分析场景，快速识别系统瓶颈。

```bash
# 生成全景分析报告 (Markdown 格式直接输出)
python3 scripts/global_analysis.py <trace_file> --stdout

# 或者保存到文件
python3 scripts/global_analysis.py <trace_file> --output_dir ./reports
```

**关注点**：
- 查看报告中的 `❌ Error` 和 `⚠️ No Data Found` 部分。
- 重点关注 "Top CPU Users", "Long Scheduling Latency", "Interrupt Storms" 等章节。

### Step 2: 深度钻取 (Deep Dive) - 交互式查询
针对 Step 1 发现的可疑点，使用 `query_analysis.py` 进行灵活的 SQL 查询。

> **💡 强烈建议**：在编写自定义 SQL 前，请务必先参考 [perfetto_analysis.sql](file:///opt/src/LogixAgent/skills/ftrace-analyzer/scripts/perfetto_analysis.sql)。
> 该文件中预置了 30+ 个经过验证的高频分析场景（如 CPU 利用率、调度延迟、锁竞争、中断风暴等），直接复用这些 SQL 往往能事半功倍，避免重复造轮子或编写错误的查询语句。

以下是几个精选的高频查询示例（更多场景请直接查看上述 SQL 文件）：

#### 1. 基础查询：Top CPU 消耗进程
快速定位谁吃掉了 CPU：
```bash
python3 scripts/query_analysis.py <trace_file> --query "SELECT p.name, sum(s.dur)/1e9 as cpu_sec FROM sched s JOIN thread t USING(utid) JOIN process p USING(upid) GROUP BY p.name ORDER BY cpu_sec DESC LIMIT 10"
```

#### 2. 进阶查询：调度延迟 (Scheduling Latency)
查询线程进入 Runnable 状态后，实际等待 CPU 调度的时间（反映系统繁忙程度或优先级反转）：
```bash
python3 scripts/query_analysis.py <trace_file> --query "SELECT t.name, max(dur) as max_lat, avg(dur) as avg_lat FROM thread_state ts JOIN thread t USING(utid) WHERE state='R' GROUP BY utid ORDER BY max_lat DESC LIMIT 10"
```

#### 3. 异常分析：查找超长耗时切片
查找耗时超过 10ms 的函数或事件：
```bash
python3 scripts/query_analysis.py <trace_file> --query "SELECT name, dur/1e6 as dur_ms, ts FROM slice WHERE dur > 10000000 ORDER BY dur DESC LIMIT 10"
```

#### 4. 关系分析：唤醒链追踪 (Waker -> Wakee)
查看谁在频繁唤醒关键线程（排查频繁上下文切换）：
```bash
python3 scripts/query_analysis.py <trace_file> --query "SELECT waker.name as waker, wakee.name as wakee, count(*) as cnt FROM thread_state ts JOIN thread waker ON ts.waker_utid = waker.utid JOIN thread wakee ON ts.utid = wakee.utid WHERE ts.state = 'R' GROUP BY waker, wakee ORDER BY cnt DESC LIMIT 10"
```

**执行自定义 SQL 文件**：
对于复杂的 SQL（包含 `INCLUDE PERFETTO MODULE` 等），建议保存为文件执行：
```bash
python3 scripts/query_analysis.py <trace_file> --query_file my_custom_query.sql
```

**辅助资源**：
- 表结构查询：[perfetto_sql_schema.md](file:///opt/src/LogixAgent/skills/ftrace-analyzer/references/perfetto_sql_schema.md)
- 分析指标定义：[ftrace_analysis_metrics.md](file:///opt/src/LogixAgent/skills/ftrace-analyzer/references/ftrace_analysis_metrics.md)

### Step 3: 归纳总结 (Summarize) - 输出问题详述
不要只列出数据，必须结合 Step 1 的宏观指标和 Step 2 的微观证据，对发现的问题进行详细的总结和陈述。

最终输出应包含：
1. **现象复盘**：结合全局分析报告，描述系统在何时出现了何种异常（如 CPU 飙升、卡顿）。
2. **根因定位**：引用深度钻取的 SQL 数据，指明导致异常的具体进程、函数或资源竞争。
3. **数据支撑**：将关键的查询结果（表格或 CSV）直接嵌入报告或作为附件，确保证据确凿。

建议将关键证据导出并附在总结中：
```bash
# 导出关键证据数据作为报告附件
python3 scripts/query_analysis.py <trace_file> --query "SELECT ..." --format csv > evidence.csv
```

---

## 脚本工具使用指南

### 1. 全局分析器: [global_analysis.py](file:///opt/src/LogixAgent/skills/ftrace-analyzer/scripts/global_analysis.py)

自动执行 [perfetto_analysis.sql](file:///opt/src/LogixAgent/skills/ftrace-analyzer/scripts/perfetto_analysis.sql) 中的所有场景，生成综合报告。

| 参数 | 功能描述 | 示例 |
| :--- | :--- | :--- |
| `trace_file` | **(必选)** Trace 文件路径 | `<trace_file>` |
| `--stdout` | 将报告输出到终端 (stdout) | `--stdout` |
| `--jobs N` | 并行任务数 (默认 4) | `--jobs 8` |
| `--output_dir DIR` | 报告保存目录 | `--output_dir ./out` |
| `--force` | 强制重新分析 (忽略缓存) | `--force` |

### 2. 交互式查询器: [query_analysis.py](file:///opt/src/LogixAgent/skills/ftrace-analyzer/scripts/query_analysis.py)

执行 Ad-hoc SQL 查询，支持多种输出格式。

| 参数 | 功能描述 | 示例 |
| :--- | :--- | :--- |
| `trace_file` | **(必选)** Trace 文件路径 | `<trace_file>` |
| `--query "SQL"` | 直接传入 SQL 语句 | `--query "SELECT count(*) FROM slice"` |
| `--query_file FILE` | 从文件读取 SQL | `--query_file analysis.sql` |
| `--format FMT` | 输出格式 (table, csv, json) | `--format csv` |

---

## 参考文档 (References)

- **核心指标体系**：[ftrace_analysis_metrics.md](file:///opt/src/LogixAgent/skills/ftrace-analyzer/references/ftrace_analysis_metrics.md)  
  详细定义了 CPU 调度、内存管理、I/O 等维度的关键指标、分析目的及异常特征。

- **Perfetto SQL 表结构**：[perfetto_sql_schema.md](file:///opt/src/LogixAgent/skills/ftrace-analyzer/references/perfetto_sql_schema.md)  
  包含 `sched`, `slice`, `thread`, `process` 等核心表的字段说明，是编写自定义 SQL 的必备字典。

---

## 结论输出标准格式

在输出分析结论时，**最重要的目标是给出问题出处**。

推荐使用精简的两段式结构：

### 1. 问题描述 (What)
用 1～2 句话描述观察到的现象。
- **示例**：CPU 0 在 100.5s 附近存在一段约 45ms 的调度延迟，期间 `myapp` 长时间处于 Runnable 状态但未被调度。

### 2. 证据出处 (Where)
列出关键日志片段或 SQL 查询结果，**必须包含可以复现的命令或位置**。
- **日志引用**：`[trace.log:1245] timestamp ...`
- **SQL 复现**：
  ```sql
  SELECT ts, dur, name FROM slice WHERE name = 'myapp' AND dur > 1000000
  ```
- **统计数据**：
  > 运行 `python3 scripts/query_analysis.py <trace_file> --query "..."` 可复现以下数据：
  > - Max Latency: 45ms
  > - Avg Latency: 2ms

---

## 注意事项
1. **完整性检查**：对文件的分析内容必须是完整的，不能仅仅针对局部内容分析，要确保全部都分析过，避免遗漏关键线索。
2. **环境隔离**：本 Skill 及其脚本完全离线运行，不依赖宿主机的系统工具。
3. **性能优化**：`global_analysis.py` 默认已启用并行模式加速分析；对于超大 Trace 文件，可根据机器配置通过 `--jobs` 参数进一步调整并发度。
