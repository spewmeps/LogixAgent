---
name: os-crash-analyzer
description: 使用 crash 工具进行全面的 Linux 内核崩溃转储分析，采用深度根本原因分析方法。适用于分析系统崩溃、kernel panic、vmcore 文件或执行事后调试。触发条件包括提及 "crash analysis"、"vmcore"、"kernel panic"、"system crash"、"core dump analysis"，或在排查需要内核调试的操作系统级故障时。强调寻找真正的根本原因，而不仅仅是症状。
---

# OS Crash Analyzer (操作系统崩溃分析器)

基于 **根本原因分析 (RCA)** 框架的 Linux 内核崩溃系统化分析方法论。

## 核心理念：根本原因 vs 症状

**永远不要止步于第一个答案。** 我们的目标是找到真正的**根本原因 (Root Cause)**，而不仅仅是直接原因或症状。

### 分析的 5 个层级

1. **症状 (Symptom)** - 哪里失效了？(例如："kernel panic")
2. **直接原因 (Proximate Cause)** - 是什么触发了它？(例如："空指针解引用")
3. **机制 (Mechanism)** - 它是如何发生的？(例如："访问了未初始化的指针")
4. **潜在原因 (Underlying Cause)** - 为什么这成为可能？(例如："错误处理路径中缺少初始化")
5. **根本原因 (Root Cause)** - 是什么系统性问题导致了这一切？(例如："不完善的错误处理设计模式")

**在得出结论之前，务必推进到第 4-5 层级。**

### 强制性自省问题

在确定你认为的根本原因后，**务必**问自己：

1. ❓ **这真的是根本原因，还是仅仅是一个诱因？**
2. ❓ **我能解释为什么存在这种条件吗？**
3. ❓ **修复这个问题能防止类似问题发生，还是只能解决这一个特例？**
4. ❓ **我有多少证据，又有多少是假设？**
5. ❓ **是否有我尚未检查的其他组件参与其中？**
6. ❓ **更有经验的内核工程师接下来会看什么？**

### 危险信号 (Red Flags) - 当你还没找到根本原因时

⚠️ 你的解释中包含 "莫名其妙" 或 "看起来像"
⚠️ 你无法解释事件的时间线或顺序
⚠️ 多个看似无关的问题指向同一个崩溃
⚠️ 修复方案只是一个变通办法 (workaround)，而不是解决实际问题
⚠️ 你没有用崩溃转储 (crash dump) 中的数据验证你的假设
⚠️ 只有假设发生了某些 "奇怪" 的事情，崩溃才解释得通

**如果出现任何危险信号，你必须继续深挖。**

## 环境检查与配置 (Pre-check & Configuration)

**在执行任何分析之前，必须严格执行以下检查步骤。**

推荐使用封装好的一键检查脚本 `scripts/check_environment.sh`。该脚本会自动验证命令、文件存在性以及版本兼容性。

**执行规则：**
1. **用户自定义执行优先**：如果用户已经明确提供了具体的 `crash` 执行命令（例如完整的命令行），**可以跳过**环境检测和配置步骤，直接按照用户提示的命令执行。
2. **用户参数优先**：如果用户仅提供了路径参数（如 `crash` 路径、`vmlinux` 路径或 `vmcore` 路径），则**必须**使用用户提供的值运行检查脚本。
3. **默认回退**：如果用户未指定任何信息，则使用脚本内置的默认值。
4. **强制阻断**：如果执行检查脚本且返回非 0 退出码，**必须立即停止**后续所有分析步骤，并将错误信息反馈给用户。

**使用方法：**

```bash
# 基本用法（使用默认路径）
./scripts/check_environment.sh

# 指定路径（优先使用用户提供的参数）
./scripts/check_environment.sh \
  --crash-cmd "/custom/path/to/crash" \
  --vmlinux "/custom/path/to/vmlinux" \
  --vmcore "/custom/path/to/vmcore"
```

**只有脚本显示 `✅ Environment check passed!`，才能进入 [分析工作流](#分析工作流)。**

## 分析工作流

### 第一阶段：初步评估 (必须执行)

按顺序执行这些命令以建立基线信息：

```
crash> sys              # 系统信息：内核版本、panic 原因、运行时间
crash> log              # 内核日志 (关注最后 100 行)
crash> bt               # 崩溃任务的回溯 (Backtrace)
```

**需要提取的信息：**
- Panic 消息和触发器
- 内核版本和架构
- 启动时长 (Uptime)
- 失败函数的调用栈

### 第二阶段：上下文发现

基于初步评估，继续收集上下文：

```
crash> ps               # 所有进程 - 查找 UN (不可中断) 或 RU (运行中) 状态
crash> bt -a            # 所有 CPU 回溯 - 检查挂起的 CPU
crash> foreach bt       # 所有进程回溯 - 识别模式
```

**决策点：** 审查回溯以对问题进行分类：
- 内存相关 → 转至阶段 3A
- 锁/死锁 → 转至阶段 3B
- 中断/定时器 → 转至阶段 3C
- 文件系统/IO → 转至阶段 3D
- 驱动/硬件相关 → 转至阶段 3E
- 未知 → 执行所有阶段 3 的部分

### 第三阶段 A：内存分析

```
crash> kmem -i          # 内存使用摘要
crash> kmem -s          # Slab 分配器状态 (寻找非零计数)
crash> vm               # 虚拟内存信息
crash> free             # 可用内存
```

**寻找：** 内存耗尽、Slab 泄漏、OOM (内存溢出) 条件

### 第三阶段 B：锁分析

```
crash> bt -l            # 带有锁信息的回溯
crash> waitq            # 等待队列检查
crash> ps -l            # 带有锁状态的进程
```

**寻找：** 循环等待条件、持有的锁、ABBA 死锁

### 第三阶段 C：中断/定时器分析

```
crash> irq              # 中断统计
crash> timer            # 定时器队列
crash> bt -a            # 验证所有 CPU 的卡死状态
```

**寻找：** 定时器风暴、中断洪水、挂起的 CPU 上下文

### 第三阶段 D：文件系统/IO 分析

```
crash> files            # 打开的文件描述符
crash> mount            # 挂载的文件系统
crash> dev              # 设备信息
```

**寻找：** 陈旧的文件句柄、挂载问题、设备错误

### 第三阶段 E：驱动与硬件分析

```
crash> mod              # 加载的内核模块 (检查 Tainted 标记)
crash> log | grep -iE "hardware|error|pci|mce|warn"  # 硬件与驱动日志
crash> dev              # 设备中断与 I/O 统计
crash> sym <address>    # 确认崩溃地址属于哪个模块
```

**寻找：** 非树外驱动 (Out-of-tree modules)、Tainted 内核、MCE (Machine Check Exception)、PCIe 总线错误、特定的驱动函数调用。

### 第四阶段：深度钻取 (Deep Dive)

一旦确定了问题区域，检查特定的数据结构：

```
crash> struct task_struct <address>        # 任务结构体
crash> dis -l <function_name>              # 带行号反汇编函数
crash> rd <address> <count>                # 读取内存
crash> px <address>                        # 打印地址处的十六进制
```

使用 `scripts/analyze_struct.py` 进行自动化结构体分析。

### 第五阶段：根本原因分析与验证

**关键：不要跳过此阶段。这是区分症状与根本原因的关键。**

#### 步骤 5.0：证据链构建

**可信 RCA 的基础是一条完整的证据链。**

从崩溃点反向构建到根本原因的证据链：

```
证据链模板：

[观察到的现象] ← [直接证据]
    ↓
[直接原因] ← [技术证据]
    ↓
[技术机制] ← [代码/数据证据]
    ↓
[设计缺陷] ← [架构/流程证据]
    ↓
[根本原因] ← [系统性证据]
```

**示例 - 完整的证据链：**

```
[现象] 系统panic
├─ 证据: crash> sys 显示 "BUG: unable to handle kernel NULL pointer"
│
[直接原因] NULL指针解引用在do_work()
├─ 证据: crash> bt 显示
│   #0 panic
│   #1 oops_end
│   #2 no_context  
│   #3 __bad_area_nosemaphore
│   #4 do_work+0x23/0x45 ← 崩溃点
│   #5 process_request+0x67/0x89
│
[技术机制] struct request.ptr未初始化
├─ 证据: crash> struct request ffff880012345678
│   {
│     state = REQ_ERROR (0x2)
│     ptr = 0x0           ← NULL!
│     timestamp = 1234567890
│   }
├─ 证据: crash> dis -l do_work
│   120: mov 0x8(%rdi),%rax    ← 读取request.ptr
│   123: mov (%rax),%ebx       ← 解引用NULL，崩溃！
│
[设计缺陷] error_path缺少初始化
├─ 证据: crash> dis -l process_request  
│   456: test %eax,%eax
│   457: je error_path
│   ...
│   error_path:
│   460: mov $0x2,0x0(%rbx)    ← 设置state=REQ_ERROR
│   464: ret                   ← 直接返回，未初始化ptr!
│
[根本原因] 无错误处理规范，代码审查未覆盖
├─ 证据: git log process_request.c
│   commit abc123 - "Add error handling" (无code review记录)
├─ 证据: 项目无error path checklist
├─ 证据: 无静态分析工具检测未初始化成员
```

**每一个环节都必须有来自 crash dump 或代码的确凿证据。**

**可视化 - 带有证据的调用链：**

```
完整调用链可视化（从触发到崩溃）：

用户操作
    ↓
network_receive()           ← 网络包到达
    ↓ 
driver_interrupt()          ← 中断处理
    ↓
process_request()           ← 处理请求
    ├─ [正常路径]
    │   ↓
    │   allocate_buffer()   
    │   ↓
    │   ptr = buffer        ← ptr被正确初始化
    │   ↓
    │   do_work()           ← 安全执行
    │
    └─ [错误路径] ⚠️ BUG在这里
        ↓
        validation_failed   
        ↓
        state = REQ_ERROR   ← 只设置了状态
        ↓
        return              ← 未初始化ptr! ❌
        ↓
do_work()                   ← 仍被调用
    ↓
access ptr (NULL)           ← 崩溃！💥

证据支持：
✓ bt显示这个调用顺序
✓ struct显示state=ERROR但ptr=NULL
✓ dis显示error_path缺少初始化
✓ log显示validation error发生在崩溃前30ms
```

#### 步骤 5.1：构建时间线

重构导致崩溃的事件过程：

```
crash> log | grep -B50 "panic"             # Panic 之前的事件
crash> bt -t                                # 带时间戳的回溯
crash> ps -l                                # 任务当时在做什么
```

**需要回答的问题：**
- 系统崩溃时正在做什么？
- 最近有什么变更 (新负载、配置、代码)？
- 这是第一次发生还是反复发生？
- 哪些进程是活跃的？

#### 步骤 5.2：验证你的假设

**永远不要假设 —— 始终用数据验证。**

如果你认为是内存泄漏：
```
crash> kmem -s <suspected_cache>           # 验证增长
crash> kmem -s <cache> | grep "ALLOCATED"  # 检查分配计数
crash> foreach vm | grep -A5 <process>     # 验证进程内存
```

如果你认为是死锁：
```
crash> bt -l <pid1>                        # P1 持有什么锁？
crash> bt -l <pid2>                        # P2 持有什么锁？
# 验证：P1 持有 L1，想要 L2；P2 持有 L2，想要 L1
```

如果你认为是竞态条件：
```
crash> bt -a                               # 所有 CPU - 它们当时在做什么？
crash> struct <shared_data> <addr>         # 共享数据的状态
# 寻找：部分更新的状态、不一致的数据
```

#### 步骤 5.3：5 Whys 分析

应用 "5个为什么" 技术：

**示例：**
1. **为什么会崩溃？** → 函数 X 中空指针解引用
2. **为什么指针是空的？** → 结构体成员未初始化
3. **为什么没有初始化？** → 分配函数返回了 NULL
4. **为什么分配失败？** → 系统内存耗尽
5. **为什么系统内存耗尽？** → 驱动程序 Y 内存泄漏
   
   → **根本原因：驱动程序 Y 内存泄漏**

**轮到你了 —— 对你的崩溃应用 5 Whys：**
```
1. 为什么会崩溃？ → _________________
2. 为什么会发生这种情况？ → _________________
3. 为什么存在这种条件？ → _________________
4. 为什么被允许发生？ → _________________
5. 为什么设计中可能出现这种情况？ → _________________
```

#### 步骤 5.4：基于证据的验证

**检查清单 —— 你能用 crash dump 数据证明它吗？**

□ 我能展示导致崩溃的确切内存状态
□ 我能追踪导致此处的函数调用序列
□ 我能识别具体的数据结构损坏
□ 我能解释**为什么**系统处于这种状态
□ 我能指出造成该条件的代码路径
□ 我明白是什么阻碍了错误更早被捕获

**如果你勾选少于 4 项，你需要更多分析。**

#### 步骤 5.5：替代假设

**挑战自己：** 还有什么**其他原因**能解释这个崩溃？

列出至少 2 个替代解释：
1. 替代假设 #1: _________________
2. 替代假设 #2: _________________

然后用 crash dump 证据**反驳**每一个：
- 假设 #1 被反驳，因为：_________________
- 假设 #2 被反驳，因为：_________________

**只有那样**你才能对你的根本原因充满信心。

#### 步骤 5.6：影响分析

**理解范围：**

□ 这是一次性损坏还是系统性问题？
□ 这会影响其他配置类似的系统吗？
□ 是否有其他代码路径存在相同的漏洞？
□ 如果再次发生，爆炸半径 (影响范围) 有多大？

深度钻取问题示例：
```
crash> mod                                 # 这是一个内核模块吗？
crash> mod -s <module>                     # 检查模块版本
crash> grep <function> <source>            # 审查代码中类似的模式
```

#### 步骤 5.7：根本原因陈述

编写一份完整的根本原因陈述，包含**技术版本和通俗语言版本**：

**技术版本模板：**
```
ROOT CAUSE: [具体技术问题]

MECHANISM: [问题如何表现]

EVIDENCE CHAIN:
1. [观察] → [来自 crash dump 的证据]
2. [直接原因] → [来自 bt/log 的证据]
3. [技术机制] → [来自 struct/dis 的证据]
4. [设计缺陷] → [来自 code/git 的证据]
5. [系统性问题] → [来自 process/standards 的证据]

CALL CHAIN (with evidence):
[Function A] → [证据]
    ↓
[Function B] → [证据]
    ↓
[Crash point] → [证据]

SYSTEMIC ISSUE: [为什么这成为可能]

SCOPE: [一次性或反复出现，局部或广泛]
```

**通俗语言版本模板 (面向非技术受众)：**
```
=== 通俗解释版 ===

问题是什么？
[用日常语言描述症状，如"系统突然关机"而非"kernel panic"]

为什么会发生？
[用类比解释，如："就像你去餐厅点菜，服务员记下了你的订单状态（'等待中'），
但忘记记下你的桌号。当厨房做好菜要送过来时，因为找不到桌号，系统就崩溃了。"]

具体是怎么出错的？
[分步骤，用生活化语言]
1. 第一步发生了什么：[简单描述 + 证据]
2. 第二步哪里出错：[简单描述 + 证据]  
3. 最后导致：[结果]

证据在哪里？
[指出关键证据，解释为什么这些证据支持你的结论]
• 证据1：[在crash dump的XX位置看到YY] - 这说明[ZZ]
• 证据2：[在代码的XX位置看到YY] - 这证明[ZZ]
• 证据3：[在日志的XX位置看到YY] - 这表明[ZZ]

真正的根本原因是什么？
[系统性问题的通俗解释]
"不是某个具体的代码错误，而是我们的[流程/规范/工具]缺少了[XX]，
导致这类错误可能发生而没被发现。"

打个比方：
[用生活化的类比]
"这就像一个工厂，某个工位的工人忘记做质检步骤，但因为没有检查清单，
也没有下一道工序来复查，所以次品就这样流出去了。"

修复方案：
• 立即修复：[解决这一个问题]
• 长远方案：[防止这类问题] - 就像给工厂建立质检流程
```

**完整示例：**

**技术版本 (Technical Version):**
```
ROOT CAUSE: xyz_driver error path leaks allocated buffers
(根本原因：xyz_driver 错误路径泄漏已分配的缓冲区)

MECHANISM: Driver allocates buffer in interrupt context, processes packet,
but on validation errors returns without freeing buffer. Under 30% packet 
loss rate, leak accumulates 30K buffers/sec, exhausting memory in 48 hours.
(机制：驱动在中断上下文分配缓冲区，处理数据包，但在验证错误时未释放缓冲区即返回。在 30% 丢包率下，每秒泄漏 3万个缓冲区，48小时内耗尽内存。)

EVIDENCE CHAIN:
1. [System panic with OOM] → sys shows "Out of memory: Kill process"
2. [Memory exhaustion] → kmem -i shows 15.9GB/16GB used, 100MB free
3. [Slab leak] → kmem -s shows xyz_buffer_cache: 100M objects, 4.2GB
4. [Allocation source] → foreach bt shows allocations in xyz_driver_receive
5. [Missing free] → dis -l xyz_driver_receive shows error_cleanup returns without kmem_cache_free
6. [High error rate] → log shows 30% packet validation failures
7. [Timeline] → dmesg shows leak started 48h ago, correlates with driver load
8. [No detection] → Project has no leak detection in CI, no slab monitoring

CALL CHAIN (with evidence):
network_interrupt
    ↓ [证据: bt -a shows CPU0 in IRQ context]
xyz_driver_receive+0x12
    ↓ [证据: dis -l shows kmem_cache_alloc call at offset 0x12]
kmem_cache_alloc
    ↓ [证据: struct xyz_buffer shows allocated object]
validate_packet
    ↓ [证据: returns -EINVAL, shown in log]
error_cleanup+0x45
    ↓ [证据: dis -l shows direct ret, no free call]
ret (LEAK!) ← [证据: buffer never freed, ref in kmem -s]

SYSTEMIC ISSUE: Driver error paths lack resource cleanup discipline; 
no automated leak detection; no production monitoring for slab growth
(系统性问题：驱动错误路径缺乏资源清理纪律；无自动化泄漏检测；生产环境无 Slab 增长监控)

SCOPE: All systems running xyz_driver v2.3.1-2.3.5 under packet loss >10%
```

**通俗语言版本 (Plain Language Version):**
```
=== 通俗解释版 ===

问题是什么？
系统在运行48小时后内存耗尽并崩溃重启。

为什么会发生？
打个比方：网络驱动就像一个快递站，每收到一个包裹，就要准备一个箱子
来装它。正常情况下，包裹处理完了，箱子会回收。但是当包裹损坏（数据
验证失败）时，程序员写的代码忘记了回收箱子这一步，直接就结束了。

在30%的包裹都损坏的环境下（网络质量差），每秒要泄漏30,000个箱子。
48小时后，所有箱子（内存）都用光了，系统就崩了。

具体是怎么出错的？
1. 网络包到达，驱动分配一块内存（"箱子"）来处理
   [证据：crash dump显示xyz_driver_receive函数分配了内存]
   
2. 驱动检查包的数据，发现是坏包（30%都是坏的）
   [证据：日志显示30% packet validation failures]
   
3. 驱动设置错误状态，准备返回
   [证据：代码反汇编显示设置了错误码]
   
4. ❌ BUG在这里：驱动直接返回了，忘记释放之前分配的内存！
   [证据：代码显示error_cleanup路径没有调用free函数]
   
5. 这样的泄漏每秒发生30,000次，48小时累积了1亿个泄漏对象
   [证据：kmem -s显示xyz_buffer_cache有100M个对象，占用4.2GB]
   
6. 最终内存耗尽，系统崩溃
   [证据：sys显示OOM killer被触发]

证据在哪里？
我们有完整的证据链证明这个判断：

• 证据1：崩溃现场的内存统计 - 显示几乎所有内存都被xyz_buffer占用
  [在crash dump中用 'kmem -s' 命令看到的]
  
• 证据2：驱动代码的反汇编 - 证明error路径确实没有free调用
  [用 'dis -l xyz_driver_receive' 命令看到的汇编代码]
  
• 证据3：系统日志 - 显示30%的包验证失败
  [用 'log' 命令看到的内核日志]
  
• 证据4：时间线 - 从驱动加载到崩溃正好48小时
  [日志时间戳显示的]

真正的根本原因是什么？
表面上看是"代码少写了一行free"，但真正的根因是：

我们的开发流程缺少对错误处理路径的系统性检查。具体来说：
- 没有要求错误路径必须有资源清理checklist
- 没有自动化工具检测内存泄漏
- 生产环境没有监控内存使用异常

所以这类错误能够：
1. 被写进代码
2. 通过代码审查
3. 通过测试（因为测试场景没有高错误率）
4. 部署到生产环境
5. 运行48小时才暴露

打个比方：
就像一家餐厅，正常流程是：接单→做菜→上菜→收盘子。但当客人临时
取消订单时（错误场景），服务员只记得取消厨房的菜，忘记收回已经
摆好的盘子。

如果偶尔有人取消，问题不大。但如果30%的客人都取消（高错误率），
一天下来盘子全用光，餐厅就没法营业了（系统崩溃）。

真正的问题不是某个服务员忘记收盘子，而是餐厅没有"异常情况处理
流程"，也没有"盘子库存监控"，导致这类错误可以发生并持续。

修复方案：
• 立即修复：在error_cleanup代码路径添加kmem_cache_free调用
  [就像提醒那个服务员要记得收盘子]
  
• 长远方案：
  1. 建立错误路径资源清理checklist（所有驱动必须遵守）
  2. 在CI中添加内存泄漏检测工具
  3. 在生产环境添加slab监控告警
  [就像给餐厅建立"异常处理SOP"和"库存监控系统"]
  
这样不仅修复了这一个bug，还能防止将来出现类似的内存泄漏问题。
```

**分析中的使用：**

始终提供**两个**版本：
- 技术版本给工程团队 (详细、精确)
- 通俗语言版本给管理层/利益相关者 (易懂、可执行)

两个版本必须基于**同一条**证据链 —— 只是解释方式不同。

#### 步骤 5.8：最终验证问题

**在宣布找到根本原因之前，回答所有问题：**

✅ **你能向初级工程师解释清楚并让他完全理解吗？**
✅ **你的解释能涵盖 crash dump 中的所有观察结果吗？**
✅ **你是否确定了事情出错的第一个点？**
✅ **你的根本原因是否具体到足以指导修复？**
✅ **提议的修复能否防止此类错误，而不仅仅是这个实例？**
✅ **你是否检查了代码库中其他地方是否存在此模式？**

**如果有任何回答是 NO，你必须继续分析。**

## 快速分析模式

为了快速诊断，使用这些命令组合：

**模式 1：Panic 分析**
```
sys → log | tail -100 → bt → dis -l <crash_function>
```

**模式 2：OOM (内存溢出) 调查**
```
sys → kmem -i → ps (sort by memory) → kmem -s | grep -v " 0 "
```

**模式 3：死锁检测**
```
ps | grep " UN " → foreach bt | grep -A5 "UN" → bt -l
```

**模式 4：任务挂起 (Hung Task)**
```
ps → bt <pid> → bt -l → waitq
```

## 辅助脚本

### scripts/evidence_chain.sh ⭐
**交互式证据链构建器** - 引导你从症状到根本原因构建完整、可验证的证据链。生成包含技术和通俗语言解释的综合报告。

**何时使用：** 在阶段 5 之前或期间，以确保每个主张都有确凿证据。

**输出：** 完整的证据链报告，包含可视化和通俗语言翻译。

### scripts/rca_wizard.sh ⭐
自动化 RCA 会话，包含结构化的 5 Whys、证据收集、验证清单。生成带时间戳的 RCA 报告。

### scripts/crash_wrapper.sh
使用配置好的路径进行自动化 crash 会话，将输出保存到带时间戳的日志中。

### scripts/quick_report.sh
一条命令生成初步评估报告 (sys, log, bt, ps, kmem -i)。

### scripts/analyze_struct.py
从 crash 输出中解析并美化打印内核数据结构。

## 详细参考资料

深入的命令文档和高级技术：

- `references/crash_commands.md` - 完整的 crash 命令参考
- `references/analysis_patterns.md` - 常见的故障模式和特征
- `references/troubleshooting.md` - 环境问题和符号解析
- `references/root_cause_analysis.md` - **关键：深度 RCA 方法论和案例研究**

**何时阅读：**
- `crash_commands.md` - 当你需要特定 crash 命令的语法时
- `analysis_patterns.md` - 当识别故障特征 (NULL 解引用, OOM, 死锁) 时
- `troubleshooting.md` - 当 crash 工具本身出现问题时
- `root_cause_analysis.md` - **当从阶段 4 进入阶段 5 时务必阅读**

## 最佳实践

1. **始终从阶段 1 开始** - 基线信息指导后续分析
2. **永远不要跳过阶段 5** - 症状不是根本原因
3. **保存输出** - 重定向到文件以便稍后比较：`log > /tmp/kernlog.txt`
4. **应用 5 Whys** - 坚持问 "为什么" 直到找到系统性问题
5. **用证据验证** - 每个主张都必须有 crash dump 数据的支持
6. **考虑替代方案** - 生成并反驳替代假设
7. **质疑你的结论** - 使用阶段 5 中的反思问题
8. **上下文很重要** - 负载类型影响解释
9. **符号验证** - 不匹配的符号会产生垃圾输出
10. **渐进式聚焦** - 从宽泛开始，根据发现缩小范围

## 分析思维模式

**优秀的分析师认为：** "崩溃发生是因为 X"

**卓越的分析师认为：** "崩溃发生是因为 X，X 发生是因为 Y，Y 成为可能因为 Z，这反映了我们在错误处理设计模式上的系统性问题。"

**始终向深处挖掘，直到找到系统性问题。**
