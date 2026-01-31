# Ftrace Analysis Tool (Skill Script)

这是一个专为探索式分析设计的高性能 Ftrace 日志解析与分析工具，支持 PB 级规模日志的流式处理。

## 核心设计理念

本工具遵循 **“总览 -> 定位 -> 深入 -> 验证”** 的实际分析工作流：

1.  **先总览**：快速了解日志基本情况（时间范围、文件规模、涉及任务）。
2.  **再定位**：根据初步观察，利用灵活的过滤条件缩小关注范围。
3.  **深入查**：针对异常点（如卡顿、调度延迟）进行多维度深度分析。
4.  **来回看**：在不同视角（CPU、进程、时间线）间快速切换，验证根因假设。

---

## 核心特性

-   **高性能流式处理**：基于索引和按需加载机制，处理 GB 级日志无需全部载入内存。
-   **三层架构设计**：
    -   `TraceFile`: 负责文件元信息、索引管理和高效读取。
    -   `QueryBuilder`: 提供链式调用的灵活过滤、排序和分页。
    -   `Analyzer`: 封装高层专家分析模式（时间异常检测、上下文分类、调度统计）。
-   **分析状态保持**：支持多次调用不重复解析，适合“对话式”交互分析。

---

## 快速开始：四步分析法

### 1. 先总览 (Overview First)
快速获取日志的宏观画像。
```bash
# 获取文本摘要 (时间范围、CPU 数、进程数等)
python3 main.py /path/to/trace.log --summary

# 获取详细的元数据 (JSON 格式)
python3 main.py /path/to/trace.log --info
```

### 2. 再定位 (Locate Scope)
通过过滤条件定位到感兴趣的片段。
```bash
# 查询特定 PID 在特定时间段的事件
python3 main.py /path/to/trace.log \
    --query-pid 3711 \
    --time-range 7541.0 7542.0
```

### 3. 深入查 (Drill Down)
利用高层分析接口识别异常。
```bash
# 检测大于 1ms 的时间断层 (发现"进程去哪了")
python3 main.py /path/to/trace.log --analyze-gaps 1.0

# 统计执行上下文分区 (识别中断、软中断、内核态占比)
python3 main.py /path/to/trace.log --classify
```

### 4. 来回看 (Verify Hypothesis)
导出数据进行多维对比验证。
```bash
# 获取特定进程的调度统计
python3 main.py /path/to/trace.log --stats "kube-apiserver"

# 导出特定查询结果到 CSV 供外部工具进一步分析
python3 main.py /path/to/trace.log \
    --query-event sched_switch --export-csv switches.csv
```

---

## Python API 用法

```python
from ftrace_file import TraceFile
from ftrace_analyzer import Analyzer

# 1. 总览
trace = TraceFile("/path/to/trace.log")
print(trace.summary())

# 2. 定位与查询
results = trace.query()\
               .cpu(0)\
               .time_range(7541.0, 7542.0)\
               .execute()
print(results.describe())

# 3. 深入分析
analyzer = Analyzer(trace)
anomalies = analyzer.detect_time_anomalies(threshold_us=1000)

# 4. 验证与导出
df = trace.query().pid(1234).to_dataframe()
```
