# OS Crash Analyzer 使用示例

## 快速开始

1. **生成快速报告：**
   ```bash
   # 用法: ansible -i "<IP>," all -m script -a "./scripts/quick_report.sh <故障目录路径>" -u root
   ansible -i "<IP>," all -m script -a "/opt/src/LogixAgent/skills/vmcore-analysis/scripts/quick_report.sh /var/crash/202402051200" -u root
   ```

2. **启动手动分析：**
   *注意：Crash 是交互式工具。若需自动化执行特定命令，可使用 Ansible shell 模块配合管道。*
   ```bash
   # 示例：远程执行 crash 命令获取堆栈
   ansible -i "<IP>," all -m shell -a "echo 'bt' | crash /usr/lib/debug/lib/modules/$(uname -r)/vmlinux /var/crash/202402051200/vmcore" -u root
   ```

## 示例工作流

### 场景 1：分析新的崩溃

```bash
# 1. 自动全景扫描
ansible -i "<IP>," all -m script -a "/opt/src/LogixAgent/skills/vmcore-analysis/scripts/quick_report.sh /var/crash/202402051200" -u root

# 2. 查看生成的报告 (假设报告已生成在目标机)
ansible -i "<IP>," all -m command -a "cat /var/crash/202402051200/quick_report.txt" -u root
```

### 场景 2：手动调查 (交互式)

*注意：深度交互式调试建议直接登录服务器。若需通过 Ansible 获取特定信息：*

```bash
# 示例：一次性获取 sys, log, bt 信息
ansible -i "<IP>," all -m shell -a "echo -e 'sys\nlog -t\nbt' | crash /usr/lib/debug/lib/modules/$(uname -r)/vmlinux /var/crash/202402051200/vmcore" -u root
```

### 场景 3：分析特定结构

*需结合 crash 交互环境或编写复杂 Ansible 脚本。*

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
# 分析第一个 crash
ansible -i "<IP>," all -m script -a "/opt/src/LogixAgent/skills/vmcore-analysis/scripts/quick_report.sh /var/crash/crash1" -u root

# 分析第二个 crash
ansible -i "<IP>," all -m script -a "/opt/src/LogixAgent/skills/vmcore-analysis/scripts/quick_report.sh /var/crash/crash2" -u root
```

### 远程崩溃转储分析 (Remote Crash Dump Analysis)

```bash
# 从远程服务器下载目录到控制节点 (使用 fetch 或 synchronize 模块)
ansible -i "<IP>," all -m synchronize -a "mode=pull src=/var/crash/202402051200 dest=/tmp/crash_case" -u root

# 本地分析 (假设控制节点已安装 crash)
./scripts/quick_report.sh /tmp/crash_case/202402051200
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
