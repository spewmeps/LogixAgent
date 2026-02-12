# OS Crash Analyzer 使用示例

## 快速开始

1. **生成快速报告：**
   ```bash
   # 用法: ./scripts/quick_report.sh <故障目录路径>
   ./scripts/quick_report.sh /var/crash/202402051200
   ```

2. **启动手动分析：**
   ```bash
   cd /var/crash/202402051200
   crash ./vmlinux vmcore
   ```

## 示例工作流

### 场景 1：分析新的崩溃

```bash
# 1. 自动全景扫描
./scripts/quick_report.sh /var/crash/202402051200

# 2. 查看生成的报告
less /var/crash/202402051200/quick_report.txt
```

### 场景 2：手动调查

```bash
# 进入目录并启动 crash
cd /var/crash/202402051200
crash ./vmlinux vmcore

# 在 crash 内部：
crash> sys
crash> log | tail -100
crash> bt
crash> kmem -i
```

### 场景 3：分析特定结构

```bash
# 在 crash 内部，获取 task_struct 地址
crash> ps
  PID    PPID  CPU       TASK        ST  %MEM     VSZ    RSS  COMM
  1234   1     2   ffff8800345fb040  RU   1.2  123456  45678  myapp

# 保存到文件
crash> struct task_struct ffff8800345fb040 > /tmp/task.txt
crash> exit


```

## 高级用法示例

### 多个崩溃转储 (Multiple Crash Dumps)

```bash
# 定义变量
export VMLINUX=/usr/lib/debug/vmlinux-5.10.0

# 分析第一个 crash
./scripts/quick_report.sh /var/crash/crash1

# 分析第二个 crash
./scripts/quick_report.sh /var/crash/crash2
```

### 远程崩溃转储分析 (Remote Crash Dump Analysis)

```bash
# 从远程服务器复制目录
scp -r server:/var/crash/202402051200 /tmp/crash_case

# 分析
./scripts/quick_report.sh /tmp/crash_case
```

## 技巧 (Tips)

1. **保存 crash 输出：** 始终将输出重定向到文件以供稍后查看
   ```bash
   crash> log > /tmp/kernlog.txt
   crash> foreach bt > /tmp/all_backtraces.txt
   ```

2. **使用 grep 过滤模式：** 过滤大量输出
   ```bash
   crash> log | grep -i "error\|panic\|oops"
   ```

3. **比较 crashes：** 如果有多个 vmcore，比较输出
   ```bash
   diff crash1_report.txt crash2_report.txt
   ```

4. **自动化常用检查：** 创建自己的包装脚本
   ```bash
   #!/bin/bash
   # my_analysis.sh
   crash vmlinux vmcore << EOF
   sys
   log | tail -100
   bt
   kmem -i
   ps | grep UN
   exit
   EOF
   ```
