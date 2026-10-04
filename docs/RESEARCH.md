# Hi nova 9 Pro (TINA-AN00) TWRP 移植研究记录

> 每次实验/发现都记录在这里。时间为北京时间（UTC+8），日期 2026-10-04。

## 0. 结论速览（当前状态）

**TWRP 已能使用**：启动到界面、触屏、USB（MTP + adb）、root adb 都正常（实验 14、15）。

能用的分区组合：

| 分区 | 内容 |
|---|---|
| `recovery` | **原厂** recovery.img（提供内核；它的头 cmdline 会传给内核） |
| `recovery_ramdisk` | TWRP 的 ramdisk，其中 `sepolicy` 换成**原厂策略 + `permissive *`**，10 个 `*_contexts` 换成原厂的，加 `/adb_keys` |
| `recovery_vendor` | 原厂 vendor ramdisk，删掉 `init.recovery.huawei.rc`、`init.recovery.lahaina_64.rc`，`sepolicy` 换成同一份 permissive 版 |

三个华为特有的限制（花了 15 个实验才查清）：

1. **TWRP 自己编出来的 sepolicy 一加载，华为内核就整个冻结**（`security_load_policy()` 里），约 10 秒后看门狗复位回 fastboot。在 TWRP 环境里，**任何不是全宽容的策略**都会这样（原厂的也一样）；全宽容的原厂策略没问题。
2. **华为内核不允许 `setenforce 0`**（返回 EINVAL），所以 cmdline 不能带 `androidboot.selinux=permissive`，"宽容"只能靠策略本身。
3. **`recovery_vendor` 叠在 `recovery_ramdisk` 之上**（同名文件以 vendor 为准）。触屏要靠 vendor 里华为 THP 的 `aptouch_daemon`；vendor 里两个华为 recovery 脚本必须删（`critical` 的 `oeminfo_nvm` 和一堆与 TWRP 冲突的服务）。

**手机当前状态**（15:30）：运行的是**调试版** TWRP（CI run 9）+ 上述打包；`reserved2` 里有调试日志（待清零）。下一步：编译正式版（不勾 `debug_kmsg_dump`）→ `build\package_twrp.ps1` 打包 → 刷入 → 清零 `reserved2`。

## 1. 设备基本信息

| 项目 | 值 |
|---|---|
| 型号 | TINA-AN00 / Hebe-BD00，品牌 Hinova，`ro.product.device=TS-TINA-Q`，主板代号 TINA |
| SoC | Qualcomm SM7325（平台 `lahaina`，设备树 `yupik`） |
| 内核 | 5.4.86-perf，Image.gz，非 GKI，驱动内置（recovery 不加载模块） |
| Android / VNDK | 11 / 30，HarmonyOS 12.0.1.166 |
| Board ID | `ro.board.boardid=8506` = 0x213a，对应 dtbo 第 1 项（`ro.boot.dtbo_idx=1`） |
| 动态分区 | super 8145338368 B，单个 `default` 组：system, hw_product, cust, vendor, odm |
| 数据加密 | f2fs，FBE v2 + 元数据加密（wrappedkey_v0） |
| Bootloader | 已解锁（`FB LockState: UNLOCKED`），AVB 状态 orange |
| 背光 | `panel0-backlight`，`max_brightness` = 10000 |
| 温度节点 | `thermal_zone0` = `soc_thermal`，读数 -274000（坏）；`thermal_zone22` = `cpu-0-0-usr`（正常） |
| USB | 只有 configfs（没有 android_usb），控制器 `a600000.dwc3` |
| 触屏 | 华为 THP（Touch Host Processing），需要用户态 `aptouch_daemon` |

## 2. 华为 recovery 启动链（来自 ABL 日志，已证实）

进入 recovery 时 ABL 依次加载：

| 顺序 | 分区 | 作用 |
|---|---|---|
| 0 | `recovery` | 提供**内核**；它自带的 ramdisk 实际不起作用；**头里的 cmdline 会传给内核** |
| 1 | `recovery_ramdisk` | 主 ramdisk（启动头 v3，kernel_size=0）；**头里的 cmdline 不会传给内核** |
| 2 | `recovery_vendor` | vendor ramdisk，**叠加在 recovery_ramdisk 之上**（同名文件以 vendor 为准，实验 13 证实） |
| 3 | `vendor_boot` | dtb |
| 4 | `dtbo` | 按 board id 8506 选 overlay |

正常开机同理：`boot`（内核）+ `ramdisk` 分区 + vendor_boot + dtbo。

- AVB：`vbmeta: Public key used to sign data rejected`，但 `AllowVerificationError=1` → orange，继续启动。**AVB 不是阻碍。**
- 第二个 ramdisk 分区头的 cmdline 不生效：系统 `/proc/cmdline` 里没有 `ramdisk.img` 头中的 `slub_min_objects=12` 等参数。
- `recovery` 分区头的 cmdline 生效：实验 10 里 TWRP 镜像头带的 `androidboot.selinux=permissive` 被 init 读到了。
- `fastboot boot` 对任何镜像（包括原厂 recovery.img）都报 `Failed to load/authenticate boot image: Load Error`，**不支持临时启动**。
- 原厂 recovery 以 **SELinux enforcing** 运行；`recovery_ramdisk` 自己不带 sepolicy，策略来自 `recovery_vendor`。
- recovery 模式下华为 BootDetector 关闭（`BootDetector is disabled`）。
- `reboot recovery` 会在 misc 写入 boot-recovery；**只有能正常启动的 recovery 才会清掉它**（原厂 recovery 启动时就清）。recovery 起不来时，之后每次重启都会再进 recovery → 失败 → fastboot，直到刷回能用的 recovery。

## 3. 编译和打包的区别（为什么后期不用重新编译）

- **编译**（GitHub Actions，约 40 分钟）：生成 TWRP 的程序（`twrp`、`init`、`adbd` 等）和写死在程序里的配置（温度路径、亮度、USB 脚本是否包含等）。
- **打包**（本地，几秒）：编译出的 `recovery.img` 里的 ramdisk 是一个 cpio 压缩包。里面的 SELinux 策略、contexts、`.rc` 启动脚本、属性文件、`/adb_keys` 等**普通文件**可以直接解包替换，再压回去，加上华为格式的启动头和 AVB 签名。

最后一次编译是 **run 9（调试版 v3）**，实验 9–15 用的都是它编出的同一个 TWRP 程序，所有改动都是打包层面的：

| 实验 | 改动 | 方式 |
|---|---|---|
| 10 | `sepolicy` → 原厂策略 + `permissive *` | 替换 ramdisk 文件 |
| 11 | `recovery` 分区刷回原厂 recovery.img（去掉 cmdline 里的 permissive） | 换分区 |
| 12 | 10 个 `*_contexts` → 原厂的 | 替换 ramdisk 文件 |
| 13 | `init.recovery.qcom.rc` → 新版（configfs USB 规则） | 替换 ramdisk 文件 |
| 14 | `recovery_vendor` → 原厂去两个脚本 + permissive 策略 | 改另一个分区 |
| 15 | 新增 `/adb_keys` | 新增 ramdisk 文件 |

**必须重新编译的**：`TW_CUSTOM_CPU_TEMP_PATH`、`TW_MAX_BRIGHTNESS`、`TW_EXCLUDE_DEFAULT_USB_INIT`、开机黑屏、去掉调试代码。

工具（`Desktop\Hi Nova\build\`，不在仓库里）：

| 脚本 | 作用 |
|---|---|
| `package_twrp.ps1` | CI 的 recovery.img → 可刷的 `twrp-recovery_ramdisk.img` + `twrp-recovery_vendor.img` |
| `make_twrp_variant.py` | TWRP 镜像 → recovery_ramdisk，`路径=文件` 替换、`+路径=文件` 新增 |
| `make_vendor_variant.py` | 原厂 recovery_vendor，`-drop 路径` 删除、`路径=文件` 替换 |
| `make_stock_adb.py` / `verify_stock_adb.py` | 原厂 recovery + root adb（第 7 节） |
| `run_experiment.ps1` | 一次无人值守实验：清 reserved2 → 刷入 → 启动 → 判断 → 失败自动恢复 → 读日志 |
| `recover_and_read.ps1` | 等手机进 fastboot → 刷回 adb 版原厂 recovery → 读 reserved2 |
| `read_reserved2.ps1` / `parse_reserved2.py` | 读取并解析 reserved2 里的调试痕迹 |

原厂文件（策略、contexts、vendor ramdisk）和本机 adb 公钥只在本地，**不进公开仓库**。

## 4. TWRP 构建

- 设备树：本仓库（twrp-12.1，`device/hinova/TINA`），GitHub Actions 编译（公开仓库，4 核 16G runner，约 40 分钟）。
- 构建踩过的坑：
  - runner 磁盘：先删工具缓存等（14G → 58G）；runner 没有独立 `/mnt`，`maximize-build-space` 会把根分区占满，不能用。
  - `BOARD_*_PARTITION_LIST` 只接受标准分区名（hw_product、cust 不行）。
  - soong 在 8G 内存的私有 runner 上很慢，仓库公开后正常。
- 产物：`recovery.img`（v3，内核与原厂一致，ramdisk 约 21.7MB gzip）。

固化到设备树的修改（15:30）：

- BoardConfig：去掉 `androidboot.selinux=permissive`；`TW_EXCLUDE_DEFAULT_USB_INIT := true`；`TW_CUSTOM_CPU_TEMP_PATH := /sys/class/thermal/thermal_zone22/temp`；去掉 `TW_SCREEN_BLANK_ON_BOOT`；`TW_MAX_BRIGHTNESS := 10000`、默认 4000。
- `recovery/root/init.recovery.qcom.rc`：configfs gadget + `mtp,adb` / `mtp` 规则（TWRP 的 init.rc 只给 configfs 写了 adb/sideload/fastboot 规则）。

## 5. 实验记录

| # | 时间 | 刷入 | 结果 | 结论 |
|---|---|---|---|---|
| 1 | 11:05 | TWRP → `recovery` | 进原厂华为 recovery | `recovery` 的 ramdisk 不被使用 |
| 2 | 11:21 | TWRP ramdisk → `recovery_ramdisk`（vendor 原厂） | 黑屏，约 13 秒回 fastboot；之后每次重启都回 fastboot | misc 里的 boot-recovery 不清除 → 刷回能用的 recovery 并"重启设备" |
| 3 | 11:46 | 同上 + vendor 去掉 11 个 SELinux 文件 | 13 秒回 fastboot | （事后看：vendor 在上层，这次加载的是 TWRP 策略） |
| 4 | 11:52 | **对照**：原厂 ramdisk（逐字节不变）+ 我们的头 / AVB footer | 原厂 recovery 正常启动 | **打包方式没问题，问题在 TWRP ramdisk 内容** |
| 5 | 12:00 | TWRP + vendor 再去掉两个华为 rc | 13 秒回 fastboot | critical 服务不是唯一原因 |
| 6 | 12:25 | TWRP + **空** vendor（只有 cpio TRAILER） | 14 秒回 fastboot | TWRP ramdisk 单独启动也失败 |
| 7 | 13:23 | 调试版（run 8）+ 空 vendor | 标记 0/1/2，没有 3，没有 kmsg | 死在 `SetupSelinux()` 里 |
| 8 | 13:29 | 调试版 + vendor 保留原厂 SELinux、删 rc | 17 秒；标记到 2 | 原厂未打补丁的策略（vendor 在上层）也卡 |
| 9 | 14:49 | 调试版 v3（run 9，细标记 + 实时 kmsg）+ 空 vendor | 停在标记 7（`before_load_policy`）；实时 kmsg 停在 2.216 秒 | **`security_load_policy()` 时整个内核冻结** |
| 10 | 14:52 | v3 + `sepolicy` 换原厂 + `permissive *` | 标记 3 出现；`security_setenforce(false) failed: Invalid argument` | **原厂全宽容策略能加载；内核不许 setenforce 0** |
| 11 | 14:55 | 同上 + `recovery` 刷回原厂 recovery.img | 进入 second stage（标记 4）；`Failed to initialize property area` | contexts 与策略不配套 |
| 12 | 15:00 | 同上 + 原厂全部 `*_contexts` | 🎉 **TWRP 界面出现**；触屏、USB 不可用，温度 -274°C | 启动链全通 |
| 13 | 15:10 | 同上 + 新 USB rc + vendor（删 rc，保留原厂未打补丁策略） | 黑屏；停在标记 7 | **vendor 在上层**；非全宽容策略又冻结 |
| 14 | 15:18 | vendor 的 `sepolicy` 也换成 permissive 版 | 🎉 **触屏、USB 正常**；adb unauthorized | 方案成立 |
| 15 | 15:22 | ramdisk 加 `/adb_keys` | **root adb 可用** | TWRP 3.7.1_12-0 |

### 实验 7：第一次拿到调试痕迹

```
HINOVA-MARK slot=0 tag=first_stage_entry   pid=1 boottime=2.152
HINOVA-MARK slot=1 tag=first_stage_logging pid=1 boottime=2.155
HINOVA-MARK slot=2 tag=selinux_setup_entry pid=1 boottime=2.234
(slot 3 selinux_policy_loaded 没有；offset 0 的 kmsg dump 为空)
```

- 内核正常，TWRP 进入了用户空间，first stage 完整跑完；死在 `SetupSelinux()` 里、`SelinuxSetEnforcement()` 之前。
- 没有 kmsg dump → init 没走到 `RebootSystem()`。普通的 `LOG(FATAL)` 会走到那里，所以更像卡死后被看门狗复位（标记 2 在 2.2 秒，周期 13 秒，中间约 9–10 秒，日志里有 `hh-watchdog`）。
- `MountMissingSystemPartitions()` 在我们的 fstab 下会立即返回（system 挂在 `/system_root`）。

### 实验 9：精确到 security_load_policy()

```
slot 0 first_stage_entry     2.197
slot 1 first_stage_logging   2.200
slot 2 selinux_setup_entry   2.285
slot 5 after_mount_missing   2.289
slot 6 policy_read           2.290
slot 7 before_load_policy    2.291
slot 3 (policy loaded)       —— 没有
live kmsg: 只有 seq=0 @2.216，下一次（约 2.52）没写出来
```

- 调用 `security_load_policy()` 的瞬间**整个内核冻结**：连独立的 logger 子进程都不再运行 → 看门狗复位 → ABL 进 fastboot。
- 两份策略格式相同（policydb v30、MLS、handle_unknown=deny），TWRP 的 610KB、原厂 1.3MB；内核里有 `hkip`（华为内核完整性保护）。
- 实时 kmsg 首次快照里 first stage 正常：`First stage mount skipped (recovery mode)`，dt_fstab 解析了 `/patch_hw`、`/preload` 等条目。

### 实验 10：策略加载通过，setenforce 失败

```
slot 7 before_load_policy    2.450
slot 3 selinux_policy_loaded 2.671   ← 原厂全宽容策略加载成功
kmsg（RebootSystem 写入，reason=bootloader）：
  init: security_setenforce(false) failed: Invalid argument
  init: InitFatalReboot: signal 6  (SetupSelinux+2228)
```

- TWRP（eng，允许 permissive）读到 `androidboot.selinux=permissive`（来自 `recovery` 分区 TWRP 镜像头）就去 setenforce(false) → 华为内核拒绝 → 致命错误。

### 实验 11：进入 second stage，属性区失败

```
slot 4 second_stage_entry    2.448
kmsg: SELinux: Context u:object_r:zram_config_prop:s0 is not valid (left unmapped) ...（大量）
      init: Failed to initialize property area → InitFatalReboot (PropertyInit ← SecondStageMain)
```

- 原厂策略 + TWRP 的 `*_property_contexts` 不配套（TWRP 引用的属性类型在原厂策略里不存在）。

### 实验 12：第一次进入 TWRP 界面

- 用户看到 TWRP 界面；reserved2 里有 TWRP 运行 213 秒的实时 kmsg（标记 0→1→2→5→6→7→3→4 全齐）。
- **USB**：TWRP 设 `sys.usb.config=mtp,adb`，但 configfs 下没有 `mtp,adb` 的规则，`init.recovery.usb.rc` 只有旧的 android_usb → UDC 从未绑定；adbd 一直 `usb ffs open: read descriptors`。
- **触屏**：vendor 为空，没有 `aptouch_daemon`（依赖 `libc_secshared.so`）。
- **温度**：TWRP 默认读 `thermal_zone0`（`soc_thermal`，-274000）。

### 实验 13：黑屏 → 证实 vendor 在上层

| 实验 | 最终加载的 sepolicy | 结果 |
|---|---|---|
| 7、9 | TWRP 的 | 冻结 |
| 8、13 | vendor 里原厂未打补丁的 | 冻结 |
| 10、11、12 | 原厂 + permissive *（vendor 为空） | 加载成功 |

- ramdisk 里的策略与实验 12 完全相同，唯一区别是 vendor 带着原厂未打补丁的 `sepolicy` → vendor 在上层。
- 推测冻结机制：策略生效瞬间某个华为内核线程（如开机加载固件的 THP 触屏驱动）被拒绝，华为内核某条路径卡死。**未证实**。

### 实验 14、15：可用

- 触屏正常（`aptouch_daemon` 运行）；USB 识别为 `18D1:4EE2`（MTP + adb）。
- adb unauthorized：TWRP 的 prop.default 没有 `ro.adb.secure`，原厂 vendor 的 default.prop（`ro.adb.secure=1`）叠上来生效；加 `/adb_keys` 解决。
- adb：`product:twrp_TINA`，`uid=0 context=u:r:su:s0`，TWRP 3.7.1_12-0；`/data` 能挂载但内容是 FBE 加密的。
- Windows 上 MTP 接口显示"错误"（TWRP 的 MTP 进程 `f_mtp`/`mtp_read` 在运行），待查。

### 已排除

- AVB 验签（解锁后放行）
- 打包格式 / 头 / footer（对照实验 4）
- 华为 BootDetector（recovery 下关闭）
- SELinux 分离策略（TWRP 无 `plat_sepolicy.cil`，原厂 vendor 无 `vendor/etc/selinux`）
- TWRP init 依赖缺失（`/system/bin/init` 动态链接，33 个依赖库全部在 ramdisk 内）
- 策略格式（policydb 版本、MLS、handle_unknown 都与原厂相同）

## 6. 调试版 TWRP（reserved2 痕迹）

`.github/patches/hinova_kmsg_dump.py`（workflow 开关 `debug_kmsg_dump`）修改 TWRP 的 init，往 **`reserved2`** 分区留痕迹。`reserved2` = `/dev/block/sda36`（259:20），112MB，原厂全零，ABL 从不读取。

| 偏移 | 内容 |
|---|---|
| 0 | 整个内核日志，在 `RebootSystem()` 开头写入（致命错误、critical 服务、普通重启都会经过） |
| 16 MiB | 实时内核日志：first stage 里 fork 的子进程每 0.3 秒重写一次，持续约 3 分钟 |
| 100MiB + slot×4K | 阶段标记：0 `FirstStageMain` 入口（/sys 未挂载，用固定 259:20）、1 first stage 日志就绪、2 `SetupSelinux` 入口、5 `MountMissingSystemPartitions` 之后、6 `ReadPolicy` 之后、7 `security_load_policy` 之前、3 策略已加载、4 `SecondStageMain` 入口 |

- 日志写在 UFS 上并 `fsync`，重启/关机都保留；在系统里用 su 或在 adb 版原厂 recovery 里直接 `dd` 读取，**不需要 9008**。
- 判读：一个标记都没有 → 没进用户空间；停在某个标记 → 死在下一阶段；实时 kmsg 停止更新 → 内核冻结。
- 补丁在服务器上对 TWRP android-12.1 真实源码验证过（5 个文件全部打上，辅助代码 `-Wall -Wextra -Werror` 通过）。
- 候选空分区（备份中全零、ABL 不读）：reserved1–5、logdump、mdcompress、spunvm。**不要用** kpatch / patch（ABL 会读）、rrecord（ABL 有引用）。
- **实验结束后要把 `reserved2` 清零**（原厂就是全零）。

## 7. 原厂 recovery + root adb（已完成，两套都保留）

目的：不进系统就能读日志 / dd 分区 / 刷写，后续 GSI 移植也用得上。不用编译，改原厂镜像。

发现：
- 原厂 `recovery_ramdisk` 自带 `/sbin/adbd`，但华为故意关掉了：configfs 下 adb 的触发条件写成 `sys.usb.configfs=0`，`start adbd` 被注释；平时 USB 设为 `mass_storage`（12d1:1037 虚拟光驱）。
- 原厂 `recovery_vendor` 的 `init.recovery.huawei.rc` 里有工厂模式 `sys.usb.config=manufacture,adb`：会 `start adbd` 并把 `ffs.adb` 挂到 gadget（12d1:107d）。
- 原厂 adbd 是 user 编译：**`ro.adb.secure=0` 无效，一定要认证**，recovery 没有授权弹框 → 需要 `/adb_keys`。
- 手机上的 su 不是标准 Magisk（`/data/adb/magisk` 为空），`magiskpolicy` 从 `tools\Kitsune...apk` 的 `lib/arm64-v8a/libmagiskpolicy.so` 取出来用（`permissive *` 也支持）。
- 原厂 recovery 启动时清掉 misc 里的 boot-recovery，所以在里面 `adb reboot` 直接回系统。

| 镜像 | 改动 |
|---|---|
| `recovery_ramdisk-adb.img` | `prop.default`：`ro.debuggable=1`、`ro.secure=0`、`ro.adb.secure=0`；新增 `system/etc/init/hinova_adb.rc`（`sys.usb.state=mass_storage` 或 `recovery.load_finish=true` 时 `setprop sys.usb.config manufacture,adb`）；新增 `/adb_keys` |
| `recovery_vendor-adb.img` | `sepolicy` 用 magiskpolicy 打补丁：`permissive adbd/shell/su/recovery` |

结果：约 24 秒进 recovery，adb 状态 `recovery`，`uid=0(root) context=u:r:su:s0`，能 `dd` 读分区，`/log` 已挂载，`adb reboot` 21 秒回系统。

原厂未改版在 `images\recovery_ramdisk.img` / `recovery_vendor.img`，adb 版在 `build\stock_adb\`。

调试循环：刷测试镜像 → 失败掉回 fastboot → 刷 adb 版原厂 recovery → 自动进 recovery → adb 读 reserved2 → `adb reboot` 回系统。

## 8. 日志位置（root）

| 位置 | 内容 |
|---|---|
| `/data/vendor/log/reliability/dumplog/<时间>/xbl_abl`, `last_xbl_abl` | 每次进系统时保存：本次 / 上一次启动的 **ABL 日志**（只保存上一次，不累积）。`cp` 被拒，用 `su -c cat` 读 |
| `/log/recovery/last_kmsg*` | gzip，原厂 recovery 保存的是**它自己这次启动**的内核日志（1MB，尾部为零，不含上一次启动） |
| `/log/recovery/recovery_log` | 原厂 recovery 日志，含部分 cmdline 键值和属性 |
| pstore | 未启用；`/proc/sysrq-trigger` 对 root 也不可访问，`kernel.sysrq=0` |

ABL 的 fastboot oem 命令（从 abl.img 解压出的字符串）：没有读取内核日志的命令（有 `oem himntn`、`oem uart`、`oem get-bootinfo` 等）。

## 9. 待办

- **`/data` 解密**：FBE v2 + 元数据加密（wrappedkey_v0），需要华为 keymaster / gatekeeper / qseecomd 等。
- **Windows MTP 驱动错误**。
- **找出 TWRP 策略里让内核冻结的部分**，以后才能用 TWRP 自己编的策略。
- **"重启到 EDL"选项**：TWRP 本身支持，但默认隐藏；是设备树里 `TW_HAS_EDL_MODE := true`（我加的）让它显示。会执行 `reboot edl`，华为 bootloader 是否认这个重启原因**未验证**；这台电脑没有 9008 驱动，进了 9008 只能长按电源键强制重启或接到有驱动的虚拟机。暂时别点。
- 正式版刷入后清零 `reserved2`。

## 10. 操作注意

- 清零 reserved2 的标记区要 `conv=notrunc`（toybox dd 带 seek 时会截断，块设备上报 Permission denied）；在同一条 `su -c` 里连续两个 dd 也会被拒，要分开执行：
  `dd if=/dev/zero of=/dev/block/by-name/reserved2 bs=1048576 count=24 conv=notrunc`
  `dd if=/dev/zero of=/dev/block/by-name/reserved2 bs=4096 seek=25600 count=16 conv=notrunc`
- 手机每次重启后 adb 经常掉（offline / 列表为空）：重启 adb server；不行就解锁屏幕看授权框、重新插线。
- 这台电脑没有 9008 驱动（需关闭驱动签名），9008 只在虚拟机里可用；调试流程只用 fastboot + adb。
- TWRP 黑屏或卡住时：长按 电源 + 音量下 进 fastboot。
