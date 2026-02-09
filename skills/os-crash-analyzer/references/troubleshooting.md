# Crash Analysis Troubleshooting

Solutions for common problems when analyzing kernel crashes.

## Environment Issues

### Problem: crash command not found

**Symptoms:**
```bash
-bash: crash: command not found
```

**Solutions:**

1. **Install crash utility:**
   ```bash
   # Red Hat/CentOS/Fedora
   sudo yum install crash
   
   # Debian/Ubuntu
   sudo apt-get install crash
   
   # SUSE
   sudo zypper install crash
   ```

2. **Verify installation:**
   ```bash
   which crash
   crash --version
   ```

---

### Problem: Cannot find vmlinux

**Symptoms:**
```
crash: cannot find vmlinux
```

**Solutions:**

1. **Common vmlinux locations:**
   ```bash
   # Debug symbols package
   /usr/lib/debug/lib/modules/$(uname -r)/vmlinux
   /usr/lib/debug/boot/vmlinux-$(uname -r)
   
   # Direct kernel build
   /usr/src/linux-$(uname -r)/vmlinux
   /boot/vmlinux-$(uname -r)
   ```

2. **Install debug symbols:**
   ```bash
   # Red Hat/CentOS
   sudo debuginfo-install kernel
   
   # Ubuntu/Debian
   sudo apt-get install linux-image-$(uname -r)-dbg
   
   # Fedora
   sudo dnf debuginfo-install kernel
   ```

3. **Find vmlinux for current kernel:**
   ```bash
   find /usr -name "vmlinux*$(uname -r)*" 2>/dev/null
   find /boot -name "vmlinux*" 2>/dev/null
   ```

4. **Extract from compressed file (if present):**
   ```bash
   # Some distributions compress vmlinux
   cd /boot
   sudo gzip -d vmlinux-$(uname -r).gz
   ```

---

### Problem: vmcore file missing or corrupted

**Symptoms:**
```
crash: cannot open vmcore
crash: vmcore is corrupted
```

**Solutions:**

1. **Common vmcore locations:**
   ```bash
   /var/crash/
   /var/crash/vmcore
   /var/crash/*/vmcore  # timestamped directories
   ```

2. **Check kdump configuration:**
   ```bash
   # Verify kdump is enabled
   systemctl status kdump
   
   # Check kdump configuration
   cat /etc/kdump.conf
   ```

3. **Ensure kdump is set up:**
   ```bash
   # Enable kdump
   sudo systemctl enable kdump
   sudo systemctl start kdump
   
   # Verify crashkernel is reserved
   cat /proc/cmdline | grep crashkernel
   ```

4. **Verify vmcore was captured:**
   ```bash
   ls -lh /var/crash/
   ```

5. **If vmcore is compressed:**
   ```bash
   # makedumpfile creates compressed cores
   cd /var/crash/*/
   # crash can read compressed vmcore directly
   crash /usr/lib/debug/lib/modules/*/vmlinux vmcore
   ```

---

## Symbol Resolution Issues

### Problem: No debugging data available

**Symptoms:**
```
crash: no debugging data available
crash: kernel symbols could not be loaded
```

**Root cause:** vmlinux doesn't contain debug symbols

**Solutions:**

1. **Verify vmlinux has symbols:**
   ```bash
   file /usr/lib/debug/lib/modules/$(uname -r)/vmlinux
   # Should show: "not stripped"
   
   nm /usr/lib/debug/lib/modules/$(uname -r)/vmlinux | head
   # Should show symbols
   ```

2. **Install debuginfo packages:**
   ```bash
   # Red Hat family
   sudo yum install kernel-debuginfo-$(uname -r)
   
   # Debian family
   sudo apt-get install linux-image-$(uname -r)-dbgsym
   ```

3. **Enable debuginfo repositories:**
   ```bash
   # CentOS/RHEL
   sudo yum install yum-utils
   sudo yum-config-manager --enable rhel-*-debug-rpms
   
   # Fedora
   sudo dnf config-manager --enable fedora-debuginfo
   ```

---

### Problem: Module symbols not loaded

**Symptoms:**
```
crash> mod
MODULE  NAME       SIZE  OBJECT FILE
<module> <name>   <size>  (no symbols)
```

**Solutions:**

1. **Install kernel module debuginfo:**
   ```bash
   # Red Hat family
   sudo yum install kernel-debuginfo-common-$(uname -m)
   
   # Debian family
   sudo apt-get install linux-modules-$(uname -r)-dbgsym
   ```

2. **Reload module symbols in crash:**
   ```bash
   crash> mod -S
   ```

3. **Manually load module symbols:**
   ```bash
   crash> mod -s <module_name> /path/to/module.ko
   ```

---

### Problem: Version mismatch

**Symptoms:**
```
WARNING: kernel version mismatch
crash: vmlinux and vmcore do not match!
```

**Root cause:** vmlinux from different kernel than vmcore

**Solutions:**

1. **Find matching vmlinux:**
   ```bash
   # Check vmcore kernel version
   strings vmcore | grep "Linux version" | head -1
   
   # Find matching vmlinux
   find /usr/lib/debug -name "vmlinux*" -exec file {} \;
   ```

2. **Use version-specific paths:**
   ```bash
   # Determine exact version from vmcore directory name
   ls /var/crash/
   # Use matching vmlinux
   crash /usr/lib/debug/lib/modules/<version>/vmlinux vmcore
   ```

3. **Keep old kernel debuginfo:**
   ```bash
   # Don't auto-remove old kernels/debuginfo
   # Edit /etc/yum.conf or /etc/dnf/dnf.conf
   installonly_limit=3  # Keep multiple versions
   ```

---

## Analysis Issues

### Problem: Cannot read memory at address

**Symptoms:**
```
crash: cannot access memory at <address>
```

**Causes:**
- Invalid pointer
- Memory corruption
- Virtual address not mapped

**Solutions:**

1. **Verify address validity:**
   ```bash
   crash> vm  # Check valid address ranges
   ```

2. **Try physical address:**
   ```bash
   crash> rd -p <physical_address>
   ```

3. **Check if address was valid:**
   ```bash
   crash> kmem -v | grep <address>
   ```

---

### Problem: Crash hangs or very slow

**Symptoms:**
- Crash utility hangs
- Commands take very long

**Solutions:**

1. **Increase memory for analysis:**
   ```bash
   # crash needs RAM approximately 2x vmcore size
   # If insufficient, use swap
   sudo fallocate -l 8G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```

2. **Use compressed vmcore:**
   ```bash
   # makedumpfile can compress while preserving needed data
   makedumpfile -c -d 31 /proc/vmcore /var/crash/vmcore
   ```

3. **Disable auto-loading:**
   ```bash
   # Start crash without immediately loading all symbols
   crash --minimal vmlinux vmcore
   ```

---

### Problem: Incomplete backtrace

**Symptoms:**
```
crash> bt
#0 [address]
#?? [address]
```

**Causes:**
- Stack corruption
- Missing frame pointers
- Optimized code

**Solutions:**

1. **Try alternative backtrace methods:**
   ```bash
   crash> bt -f  # Full symbols
   crash> bt -t  # Include timestamps
   crash> bt -o  # Old format
   ```

2. **Manual stack walk:**
   ```bash
   crash> rd <stack_address> 100
   # Look for function addresses
   ```

3. **Check for stack overflow:**
   ```bash
   crash> bt  # If very deep, likely overflow
   ```

---

## Data Collection Issues

### Problem: kdump not capturing vmcore

**Symptoms:**
- System crashes but no vmcore in /var/crash
- kdump service appears running but captures nothing

**Solutions:**

1. **Verify crashkernel memory reserved:**
   ```bash
   cat /proc/cmdline | grep crashkernel
   # Should show: crashkernel=auto or crashkernel=256M
   
   dmesg | grep -i crash
   # Should show reserved memory
   ```

2. **Add crashkernel to boot parameters:**
   ```bash
   # Edit /etc/default/grub
   GRUB_CMDLINE_LINUX="... crashkernel=256M"
   
   # Regenerate grub config
   sudo grub2-mkconfig -o /boot/grub2/grub.cfg
   # OR for EFI systems
   sudo grub2-mkconfig -o /boot/efi/EFI/redhat/grub.cfg
   
   # Reboot
   sudo reboot
   ```

3. **Test kdump:**
   ```bash
   echo 1 > /proc/sys/kernel/sysrq
   echo c > /proc/sysrq-trigger  # WARNING: Will crash system!
   ```

4. **Check kdump logs:**
   ```bash
   journalctl -u kdump
   cat /var/log/kdump.log
   ```

---

### Problem: Not enough space for vmcore

**Symptoms:**
```
kdump: saving vmcore failed: No space left on device
```

**Solutions:**

1. **Check available space:**
   ```bash
   df -h /var/crash
   ```

2. **Configure makedumpfile for compression:**
   ```bash
   # Edit /etc/kdump.conf
   core_collector makedumpfile -l --message-level 1 -d 31 -c
   
   # Restart kdump
   sudo systemctl restart kdump
   ```

3. **Change vmcore destination:**
   ```bash
   # Edit /etc/kdump.conf
   path /mnt/largefs/crash
   
   # Restart kdump
   sudo systemctl restart kdump
   ```

4. **Network dump (dump to remote server):**
   ```bash
   # Edit /etc/kdump.conf
   nfs server.example.com:/export/crash
   
   # Restart kdump
   sudo systemctl restart kdump
   ```

---

## Performance Optimization

### Analyze large vmcore files efficiently

1. **Use selective page filtering:**
   ```bash
   makedumpfile -d 31 vmcore vmcore.filtered
   # Filters out:
   # - Cache pages
   # - Free pages
   # - User data
   ```

2. **Extract only needed data:**
   ```bash
   crash --minimal vmlinux vmcore
   crash> log > kernlog.txt
   crash> bt > backtrace.txt
   crash> ps > processes.txt
   crash> exit
   ```

3. **Pre-filter before transfer:**
   ```bash
   makedumpfile -c --message-level 1 -d 31 \
     /proc/vmcore /var/crash/vmcore.compressed
   ```

---

## Best Practices for Crash Analysis Environment

1. **Setup dedicated analysis system:**
   - Separate from production
   - Sufficient RAM (2x largest expected vmcore)
   - Fast storage for vmcore files

2. **Maintain symbol repositories:**
   ```bash
   # Keep debuginfo packages for all deployed kernel versions
   mkdir -p /usr/local/kernel-debuginfo
   # Download and store all versions
   ```

3. **Automate collection:**
   ```bash
   # Script to collect initial analysis
   #!/bin/bash
   crash --minimal vmlinux vmcore << EOF > initial_report.txt
   sys
   log | tail -200
   bt
   ps
   kmem -i
   exit
   EOF
   ```

4. **Document environment:**
   - Kernel version
   - Hardware configuration
   - Workload characteristics
   - Reproduction steps (if known)

---

## Getting Help

When stuck, gather this information for support:

1. **Crash environment:**
   ```bash
   crash --version
   file vmlinux
   file vmcore
   ```

2. **Basic analysis output:**
   ```bash
   crash> sys
   crash> log | tail -100
   crash> bt
   ```

3. **System information:**
   - Distribution and version
   - Kernel version
   - Hardware platform
   - Workload description

4. **Exact error messages:**
   - Screenshot or copy full error text
   - Include context (command that caused error)
