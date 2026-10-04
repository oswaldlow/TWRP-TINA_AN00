# Hi nova 9 Pro (TINA-AN00) TWRP 移植研究记录

> 每次实验/发现都追加在这里。时间为北京时间（UTC+8）。

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

## 2. 华为 recovery 启动链（2026-10-04，来自 ABL 日志，已证实）

进入 recovery 时 ABL 依次加载：

| 顺序 | 分区 | 作用 |
|---|---|---|
| 0 | `recovery` | 提供**内核**；它自带的 ramdisk 实际不起作用 |
| 1 | `recovery_ramdisk` | 主 ramdisk（启动头 v3，kernel_size=0） |
| 2 | `recovery_vendor` | vendor ramdisk，**叠加在 recovery_ramdisk 之上**（同名文件以 vendor 为准） |
| 3 | `vendor_boot` | dtb |
| 4 | `dtbo` | 按 board id 8506 选 overlay |

正常开机同理：`boot`（内核）+ `ramdisk` 分区 + vendor_boot + dtbo。

- AVB：`vbmeta: Public key used to sign data rejected`，但 `AllowVerificationError=1` → orange，继续启动。**AVB 不是阻碍。**
- 第二个 ramdisk 分区（`ramdisk` / `recovery_ramdisk`）**头里的 cmdline 不会传给内核**：系统 `/proc/cmdline` 里没有 `ramdisk.img` 头中的 `slub_min_objects=12` 等参数。生效的是 vendor_boot 的 cmdline（可能再加 `recovery`/`boot` 头的）。
- `fastboot boot` 对任何镜像（包括原厂 recovery.img）都报 `Failed to load/authenticate boot image: Load Error`，**不支持临时启动**。
- 原厂 recovery 以 **SELinux enforcing** 运行；`recovery_ramdisk` 自己不带 sepolicy，策略来自 `recovery_vendor`。
- recovery 模式下华为 BootDetector 关闭（`BootDetector is disabled`），不会因为启动阶段超时被强制重启。

## 3. 日志位置（root）

| 位置 | 内容 |
|---|---|
| `/data/vendor/log/reliability/dumplog/<时间>/xbl_abl`, `last_xbl_abl` | 每次进系统时保存：本次 / 上一次启动的 **ABL 日志**（只保存上一次，不累积）。`cp` 被拒，用 `su -c cat` 读 |
| `/log/recovery/last_kmsg*` | gzip，原厂 recovery 保存的是**它自己这次启动**的内核日志（1MB，尾部为零，不含上一次启动） |
| `/log/recovery/recovery_log` | 原厂 recovery 日志，含部分 cmdline 键值和属性 |
| pstore | 未启用；`/proc/sysrq-trigger` 对 root 也不可访问，`kernel.sysrq=0` |

ABL 的 fastboot oem 命令（从 abl.img 解压出的字符串）：没有读取内核日志的命令（有 `oem himntn`、`oem uart`、`oem get-bootinfo` 等）。

## 4. TWRP 构建

- 设备树：本仓库（twrp-12.1，`device/hinova/TINA`），GitHub Actions 编译（公开仓库，4 核 16G runner，约 36 分钟）。
- 关键构建问题：
  - runner 磁盘：需先删工具缓存等（14G → 58G），runner 没有独立 `/mnt`，`maximize-build-space` 会把根分区占满，不能用。
  - `BOARD_*_PARTITION_LIST` 只接受标准分区名（hw_product、cust 不行）。
  - soong 在 8G 内存的私有 runner 上很慢，公开仓库后正常。
- 产物：`recovery.img`（v3，内核与原厂一致，ramdisk 21.7MB gzip）。
- 华为格式：用原厂 `recovery_ramdisk` 的头页 + TWRP ramdisk，再用 avbtool 加 hash footer（分区大小 37748736）→ `twrp-TINA-recovery_ramdisk.img`。

## 5. 实验记录

| # | 时间 | 刷入 | 结果 | 结论 |
|---|---|---|---|---|
| 1 | 11:05 | TWRP → `recovery` | 进原厂华为 recovery | `recovery` 的 ramdisk 不被使用 |
| 2 | 11:21 | TWRP ramdisk → `recovery_ramdisk`（vendor 原厂） | 黑屏，约 13 秒回 fastboot；之后每次重启都回 fastboot | misc 里的 boot-recovery 请求不清除 → 必须刷回能用的 recovery 并在里面选"重启设备" |
| 3 | 11:46 | 同上 + `recovery_vendor` 去掉 11 个 SELinux 文件 | 同样 13 秒回 fastboot | 不只是 SELinux 文件冲突 |
| 4 | 11:52 | **对照**：原厂 ramdisk（逐字节不变）+ 我们的头/avb footer → `recovery_ramdisk` | 原厂 recovery 正常启动 | **打包方式、分区组合都没问题，问题在 TWRP ramdisk 内容** |
| 5 | 12:00 | TWRP + vendor 再去掉 `init.recovery.huawei.rc`、`init.recovery.lahaina_64.rc` | 同样 13 秒回 fastboot | critical 服务 `oeminfo_nvm`（seclabel 在 TWRP 策略中不存在）不是唯一原因 |
| 6 | 12:25 | 方案 A：TWRP + **空的** `recovery_vendor`（只有 cpio TRAILER，gzip 50 字节） | 14 秒回 fastboot | **彻底排除 vendor 覆盖**：TWRP ramdisk 单独启动也失败，问题在 TWRP ramdisk 本身（或它与内核/ABL 的配合） |
| 7 | 13:23 | **调试版 TWRP**（CI run 8，`debug_kmsg_dump`）+ 空 vendor | 13 秒回 fastboot；reserved2 有标记 0/1/2，**没有 3**，**没有内核日志** | 见下 |

### 实验 7 结果（reserved2）

```
HINOVA-MARK slot=0 tag=first_stage_entry   pid=1 boottime=2.152
HINOVA-MARK slot=1 tag=first_stage_logging pid=1 boottime=2.155
HINOVA-MARK slot=2 tag=selinux_setup_entry pid=1 boottime=2.234
(slot 3 selinux_policy_loaded 没有；offset 0 的 kmsg dump 为空)
```

- 内核正常，TWRP 进入了用户空间，**first stage 完整跑完**。
- **死在 `SetupSelinux()` 里、`SelinuxSetEnforcement()` 之前**。中间依次是：`MountMissingSystemPartitions()` → `SelinuxSetupKernelLogging()` → `ReadPolicy()` → snapuserd → `LoadSelinuxPolicy()`（`security_load_policy`）。
- `MountMissingSystemPartitions()` 在我们的 fstab 下会立即返回（system 挂在 `/system_root`，找不到 `/system` 就 break）。
- **没有 kmsg dump** → init 没走到 `RebootSystem()`。普通的 `LOG(FATAL)` 会走到那里，所以更像是**卡死后被看门狗复位，或内核 panic**。时间上：标记 2 在 2.2 秒，整个周期 13 秒，中间约 9–10 秒，像高通 apps watchdog（日志里有 `hh-watchdog`）。
- 最大嫌疑：`security_load_policy()` 把 TWRP 的策略交给华为内核时出事。两份策略格式相同（policydb v30、MLS、handle_unknown=deny），但 TWRP 的只有 610KB，原厂 1.3MB；内核里有 `hkip`（华为内核完整性保护）。
- 实验 2（原厂 vendor 叠加，原厂 sepolicy 覆盖 TWRP 的）时，加载的其实是原厂策略，失败点可能在别处（例如 critical 的 `oeminfo_nvm`）。**"保留原厂 SELinux 文件、只删华为 rc 脚本"这个组合还没试过。**

### 实验 8（13:29）：调试版 TWRP + 保留原厂 SELinux、只删华为 rc 的 vendor

- 17 秒回 fastboot（之前都是 13 秒）。
- reserved2：标记 0/1/2（2.588 / 2.592 / 2.718 秒），**仍然没有 3**，没有 kmsg dump。
- vendor 叠加后 `/sepolicy` 应为原厂策略，照样卡在同一段 → **不是策略内容的问题**，而是 `SetupSelinux()` 里这几步的执行（`MountMissingSystemPartitions` / `ReadPolicy` / snapuserd / `security_load_policy`）在 TWRP 的 init 下卡住或导致复位。多出的 4 秒可能是原厂策略更大。
- 下一步：更细的标记 + first stage 里起一个后台子进程每 0.3 秒把 kmsg 写到 reserved2 偏移 16MiB（拿到卡死/panic 前最后的内核日志）。

### 实验 9（14:49）：调试版 v3（实时 kmsg + 细标记）+ 空 vendor —— **卡在 security_load_policy()**

全程无人值守：失败 → 刷 adb 版原厂 recovery → 自动进 recovery → adb 读 reserved2。

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

- **`security_load_policy()` 调用的瞬间整个内核冻结**：连独立的 logger 子进程都不再运行 → 约 10 秒后看门狗复位 → ABL 进 fastboot。不是 init 的普通错误。
- 嫌疑：华为内核对 SELinux 的保护（内核里有 `hkip`；HKIP/HHEE 保护 SELinux 内核数据），或华为内核补丁在 TWRP 策略缺少某些类/权限时卡死。
- **之前"vendor 叠加在 recovery_ramdisk 之上"的假设可能是错的**：这是高通 ABL，按 AOSP v3 规则 vendor ramdisk 在下层，recovery_ramdisk 的同名文件覆盖 vendor 的。那么实验 2、8 实际加载的大概率也是 **TWRP 的策略**，"原厂策略也卡"不成立。
- 实时 kmsg 首次快照（2.216 秒）里 first stage 正常：`First stage mount skipped (recovery mode)`，dt_fstab 解析了 `/patch_hw`、`/preload` 等条目。

实验 10：TWRP v3 ramdisk 里的 `/sepolicy` 换成**原厂策略 + `permissive *`**（magiskpolicy，3641 个类型全部 permissive），验证能否越过加载。

### 实验 10（14:52）结果 —— **策略加载通过；下一处失败：setenforce(false)**

```
slot 7 before_load_policy    2.450
slot 3 selinux_policy_loaded 2.671   ← 原厂策略加载成功
kmsg（RebootSystem 写入，reason=bootloader）：
  init: security_setenforce(false) failed: Invalid argument
  init: InitFatalReboot: signal 6  (SetupSelinux+2228)
```

1. **确认：TWRP 编出来的 sepolicy 会让华为内核在加载时整个冻结；原厂策略加载正常。** 要么 TWRP 用原厂衍生的策略，要么找出 TWRP 策略里触发冻结的部分。
2. **华为内核不允许 setenforce 0**（EINVAL：内核关闭了 SELINUX_DEVELOP 或被锁定）。TWRP（eng，允许 permissive）读到 `androidboot.selinux=permissive` 就去 setenforce(false) → 致命错误。
3. 这个参数来自 **`recovery` 分区里 TWRP 镜像头的 cmdline**（BoardConfig 里加的）→ **`recovery` 分区头的 cmdline 会传给内核**（`recovery_ramdisk` 头的不会）。
4. 必须保持 enforcing；要"宽容"只能靠策略本身（`permissive *`）。

实验 11：`recovery` 分区刷回原厂 recovery.img（内核相同，头里没有 selinux=permissive）+ 实验 10 的 ramdisk。

### 实验 11（14:55）结果 —— **进入 second stage**；下一处失败：PropertyInit

```
slot 3 selinux_policy_loaded 2.432
slot 4 second_stage_entry    2.448   ← 首次进入 second stage
kmsg: SELinux: Context u:object_r:zram_config_prop:s0 is not valid (left unmapped) ...（大量）
      init: Failed to initialize property area → InitFatalReboot (PropertyInit ← SecondStageMain)
```

- 去掉 cmdline 里的 `selinux=permissive` 后 setenforce 问题消失。
- 原厂策略 + TWRP 的 `*_property_contexts` 不匹配（TWRP 引用的属性类型在原厂策略里不存在）→ 属性区初始化失败。
- 注意：**`recovery` 分区现在是原厂 recovery.img**（不再是 TWRP 镜像）。

实验 12：TWRP ramdisk 里的 `*_property_contexts`、`*_file_contexts` 全部换成原厂 recovery_vendor 的（与原厂策略成套）。

### 实验 12（15:00）结果 —— 🎉 **TWRP 第一次启动到界面**

组合：`recovery` = 原厂 recovery.img；`recovery_ramdisk` = TWRP（调试版 v3）+ 原厂 sepolicy（`permissive *`）+ 原厂全部 `*_contexts`；`recovery_vendor` = 空。

- 用户看到 TWRP 界面；**触屏不能用、温度显示异常、USB 无设备**。用户误按进了系统，reserved2 里有 TWRP 运行 213 秒的实时 kmsg（标记 0→1→2→5→6→7→3→4 全齐）。
- **USB**：TWRP 把 `sys.usb.config` 设成 `mtp,adb`；TWRP 的 init.rc 只给 configfs 写了 adb/sideload/fastboot 的绑定规则，`init.recovery.usb.rc` 只有旧的 android_usb（本机不存在）→ UDC 从未绑定；adbd 已启动，一直 `usb ffs open: read descriptors`。修：在 `init.recovery.qcom.rc` 补 configfs 的 `mtp,adb` / `mtp` 规则（`mtp.gs0` + `ffs.adb`）。
- **触屏**：华为 THP 方案，需用户态 `aptouch_daemon`（在 recovery_vendor，依赖 `libc_secshared.so`）；vendor 为空所以没有。修：vendor 用"原厂、只删两个华为 rc"的版本（保留 `aptouch_daemon.rc`，`on boot start aptouch`）。
- **温度**：`thermal_zone0` = `soc_thermal`，读数 **-274000**（坏节点），TWRP 默认读它。CPU 应读 `thermal_zone22`（`cpu-0-0-usr`）。修：`TW_CUSTOM_CPU_TEMP_PATH`（需重编译）。

实验 13：同实验 12 + 新的 `init.recovery.qcom.rc`（configfs mtp,adb）+ vendor 用 rcless 版本（带 aptouch）。

### 实验 13（15:10）结果 —— 黑屏，又是 security_load_policy 冻结

- 屏幕全黑、USB 无设备；用户按 电源+音量下 进 fastboot，后台脚本自动刷回 adb 版 recovery 并读日志。
- reserved2：标记到 7（2.609），没有 3；live kmsg 只有 seq=0 → **与实验 7/9 相同的内核冻结**。
- recovery_ramdisk 里的 sepolicy 与实验 12 完全相同（原厂 + permissive *），唯一区别是 vendor 不再为空，而是带着**原厂未打补丁的 sepolicy**。

| 实验 | 最终加载的 sepolicy | 结果 |
|---|---|---|
| 7、9 | TWRP 的 | 冻结 |
| 8、13 | vendor 里原厂未打补丁的 | 冻结 |
| 10、11、12 | 原厂 + permissive *（vendor 为空） | 加载成功 |

- 结论 1：**`recovery_vendor` 确实叠在 `recovery_ramdisk` 之上**（同名文件以 vendor 为准，与 twrpdtgen 文档一致；实验 9 里"顺序相反"的猜测是错的）。
- 结论 2：在 TWRP 环境里加载**任何非全宽容**的策略（TWRP 的或原厂的）都会冻结内核；全宽容的不会。原厂 recovery 用强制策略没事，可能是其环境里没触发拒绝。推测：策略生效瞬间某个华为内核线程（如 THP 触屏驱动开机加载固件）被拒绝，华为内核某路径卡死。待验证。

实验 14：vendor 用 rcless 版本，但其中的 `sepolicy` 也换成原厂 + permissive *。

### 实验 14（15:25）结果 —— 🎉 **TWRP 启动，触屏正常，USB 正常**

- 验证了实验 13 的推断：最终加载的策略是全宽容版后不再冻结。
- **触屏正常**（vendor 里的 `aptouch_daemon` 启动）。
- **USB**：电脑识别 `18D1:4EE2`（configfs `mtp,adb` 规则生效），有 MTP + adb 两个接口。
- adb 显示 **unauthorized**：TWRP 的 prop.default 有 `ro.secure=0`、`ro.debuggable=1`，但没有 `ro.adb.secure`，原厂 vendor 的 default.prop（`ro.adb.secure=1`）叠上来生效，TWRP 没有授权弹框。修：ramdisk 加 `/adb_keys`（实验 15）。
- Windows 里 MTP 接口显示"错误"，待查。
- 温度仍异常（需改 `TW_CUSTOM_CPU_TEMP_PATH` 重编译）。

### 实验 15（15:22）—— adb 可用

- recovery_ramdisk 加 `/adb_keys`（本机 adb 公钥）→ adb 状态 `recovery`，`product:twrp_TINA`，`uid=0 context=u:r:su:s0`，TWRP 3.7.1_12-0。
- `sys.usb.config/state = mtp,adb`；进程里有 `aptouch_daemon`、`adbd`、TWRP 的 MTP（`f_mtp`/`mtp_read`）。Windows MTP 显示错误可能是驱动问题。
- `/data` 能挂载（f2fs），但内容是 FBE 加密的。
- 背光 `max_brightness` = **10000**（之前猜的 2047 不对）；`thermal_zone22`（cpu-0-0-usr）= 39.3°C。

### 固化到设备树（15:30）

- BoardConfig：去掉 `androidboot.selinux=permissive`；`TW_EXCLUDE_DEFAULT_USB_INIT := true`；`TW_CUSTOM_CPU_TEMP_PATH := /sys/class/thermal/thermal_zone22/temp`；去掉 `TW_SCREEN_BLANK_ON_BOOT`；`TW_MAX_BRIGHTNESS := 10000`、默认 4000。
- `recovery/root/init.recovery.qcom.rc`：configfs gadget + `mtp,adb` / `mtp` 规则。
- 本地打包：`build\package_twrp.ps1 -TwrpImage <CI 的 recovery.img>` → `twrp-recovery_ramdisk.img` + `twrp-recovery_vendor.img`（原厂文件和 adb 公钥不进公开仓库）。`recovery` 分区保持原厂 recovery.img。

**目前能用的组合**：`recovery` = 原厂 recovery.img；`recovery_ramdisk` = TWRP + 原厂 sepolicy（permissive *）+ 原厂全部 contexts + 新 `init.recovery.qcom.rc`；`recovery_vendor` = 原厂去掉 `init.recovery.huawei.rc`、`init.recovery.lahaina_64.rc`，sepolicy 换成同一份 permissive 版。

## 7. 原厂 recovery + root adb（14:00 完成，已刷在手机上）

目的：不进系统就能读日志 / dd 分区 / 刷写，后续 GSI 移植也用得上。不用编译，改原厂镜像。

发现：
- 原厂 `recovery_ramdisk` 自带 `/sbin/adbd`，但华为故意关掉了：configfs 下 adb 的触发条件写成 `sys.usb.configfs=0`，`start adbd` 被注释；平时 USB 设为 `mass_storage`（12d1:1037 虚拟光驱）。
- 原厂 `recovery_vendor` 的 `init.recovery.huawei.rc` 里有工厂模式 `sys.usb.config=manufacture,adb`：会 `start adbd` 并把 `ffs.adb` 挂到 gadget（12d1:107d）。
- 原厂 adbd 是 user 编译：**`ro.adb.secure=0` 无效，一定要认证**，recovery 没有授权弹框 → 需要 `/adb_keys`。
- 原厂 recovery 是 SELinux enforcing、策略在 `recovery_vendor` 的 `/sepolicy`；手机上的 su 不是标准 Magisk（`/data/adb/magisk` 为空），`magiskpolicy` 从 `tools\Kitsune...apk` 的 `lib/arm64-v8a/libmagiskpolicy.so` 取出来用。
- 原厂 recovery **启动时会清掉 misc 里的 boot-recovery**，所以在里面 `adb reboot` 直接回系统。

改动（逐条编辑 cpio，其余文件与原厂一致，脚本 `build\make_stock_adb.py` + `build\verify_stock_adb.py`）：

| 镜像 | 改动 |
|---|---|
| `recovery_ramdisk-adb.img` | `prop.default`：`ro.debuggable=1`、`ro.secure=0`、`ro.adb.secure=0`；新增 `system/etc/init/hinova_adb.rc`（`sys.usb.state=mass_storage` 或 `recovery.load_finish=true` 时 `setprop sys.usb.config manufacture,adb`）；新增 `/adb_keys`（本机 `~/.android/adbkey.pub`） |
| `recovery_vendor-adb.img` | `sepolicy` 换成 magiskpolicy 打过补丁的版本：`permissive adbd/shell/su/recovery` |

结果：约 24 秒进 recovery，`adb devices` 显示 `recovery`；`id` = `uid=0(root) context=u:r:su:s0`；能 `dd` 读 `reserved2`；`/log` 已挂载；`adb reboot` 21 秒回系统。

两套都保留：原厂未改的在 `images\recovery_ramdisk.img` / `recovery_vendor.img`，adb 版在 `build\stock_adb\`。**手机上当前刷的是 adb 版。**

新的调试循环：刷测试镜像 → 失败掉回 fastboot → 刷 adb 版 recovery_ramdisk/vendor → 自动进 recovery → adb 读 reserved2 → `adb reboot` 回系统。全程不用碰手机。

### 操作注意

- 清零 reserved2 的标记区要 `conv=notrunc`（toybox dd 带 seek 时会截断，块设备上报 Permission denied）：
  `dd if=/dev/zero of=/dev/block/by-name/reserved2 bs=4096 seek=25600 count=16 conv=notrunc`
- 手机每次重启后 adb 经常掉（offline / 列表为空）：重启 adb server；不行就解锁屏幕看授权框、重新插线。

每次失败后的恢复：刷回原厂 `recovery_ramdisk`/`recovery_vendor` → 重启 → 原厂 recovery 里点"重启设备"。

### 已排除

- AVB 验签（解锁后放行）
- 打包格式 / 头 / footer（对照实验 #4 通过）
- 华为 BootDetector（recovery 下关闭）
- SELinux 分离策略（TWRP 无 `plat_sepolicy.cil`，原厂 vendor 无 `vendor/etc/selinux`）
- TWRP init 依赖缺失（`/system/bin/init` 动态链接，33 个依赖库全部在 ramdisk 内）
- 只是 recovery_vendor 的 SELinux 文件或华为 rc 脚本（#3、#5 已去除仍失败）
- recovery_vendor 覆盖整体（#6 vendor 为空仍失败）

### 时序推断

从 `fastboot reboot recovery` 到重新出现 fastboot 约 13 秒；原厂 recovery 23 秒出现。ABL 到内核约 4.1 秒，因此内核大概率已启动，TWRP 在用户空间早期（first stage / selinux_setup / 早期服务）失败，init 走 "reboot,bootloader"。

## 6. 下一步：调试版 TWRP

`.github/patches/hinova_kmsg_dump.py`（workflow 开关 `debug_kmsg_dump`）往 **`reserved2`** 分区（112MB，原厂全零，ABL 从不读取）留痕迹：

| 偏移 | 内容 |
|---|---|
| 0 | 整个内核日志，在 `RebootSystem()` 开头写入（致命错误、critical 服务、普通重启都会经过） |
| 100MiB + 0K | 标记 0：`FirstStageMain()` 入口（/sys 未挂载，用固定设备号 259:20） |
| 100MiB + 4K | 标记 1：first stage 日志就绪 |
| 100MiB + 8K | 标记 2：`SetupSelinux()` 入口 |
| 100MiB + 12K | 标记 3：策略已加载、`SelinuxSetEnforcement()` 之前 |
| 100MiB + 16K | 标记 4：`SecondStageMain()` 入口 |

判读：一个标记都没有 → 没进用户空间（内核/ramdisk 问题）；停在某个标记 → 死在下一阶段。

失败后回系统读取：

```sh
su -c 'dd if=/dev/block/by-name/reserved2 bs=1M count=4' > kmsg.bin
su -c 'dd if=/dev/block/by-name/reserved2 bs=4096 skip=25600 count=8' > marks.bin
```

补丁已在服务器上对 TWRP android-12.1 的真实源码验证：5 个文件全部打上，辅助代码 `-Wall -Wextra -Werror` 编译通过。

并行的方案 A：`recovery_vendor` 刷成只有 cpio 结束标记的空 ramdisk，彻底排除 vendor 覆盖。

实验后把 `reserved2` 清零（原厂就是全零）。

- 日志写在 UFS 上并 `fsync`，**重启/关机都保留**；读取只需正常进系统用 root `dd`，**不需要 9008**。
- 这台电脑没有 9008 驱动（需关闭驱动签名），9008 只在虚拟机里可用；整个调试流程只用 fastboot + adb。
- 12:20 实测：`reserved2` = `/dev/block/sda36`，112197632 B，uevent 含 `PARTNAME=reserved2`、`MAJOR=259`、`MINOR=20`，整个分区 0 个非零字节。
- 如果失败后 `reserved2` 仍全零：说明 TWRP 没走到 init 的 `RebootSystem()`（例如内核 panic 或更早失败），同样能缩小范围。

候选空分区（备份中全零、ABL 不读）：reserved1–5、logdump、mdcompress、spunvm。**不要用** kpatch / patch（ABL 会读）、rrecord（ABL 有引用）。
