# TWRP device tree — Hi nova 9 Pro (TINA-AN00 / Hebe-BD00)

| | |
|---|---|
| SoC | Qualcomm SM7325 (`lahaina` platform, `yupik` DT) |
| Kernel | 5.4.86 prebuilt, byte-identical to stock `recovery.img` |
| Boot header | v3, page 4096; DTB from `vendor_boot`, overlay from `dtbo` (idx 1) |
| Dynamic partitions | `super` 8145338368 B: system, hw_product, cust, vendor, odm |
| Data | f2fs, FBE v2 + metadata encryption (wrappedkey_v0) |
| Android | 11 (VNDK 30) |

Generated with twrpdtgen 3.0.0 from stock `recovery.img`, then corrected:
device name/brand, super layout from LP metadata, fstab from the real
first-stage fstab (the stock recovery.fstab is a QCOM template), bootdevice symlink.

## Build with GitHub Actions

Actions → **Build TWRP (TINA)** → Run workflow. When it finishes, `recovery.img`
is in the run's Artifacts.

## Build locally (twrp-12.1, Linux, ~80–100 GB disk, 16 GB+ RAM)

```bash
repo init --depth=1 -u https://github.com/minimal-manifest-twrp/platform_manifest_twrp_aosp.git -b twrp-12.1
repo sync -j$(nproc) --force-sync --no-clone-bundle --no-tags
git clone https://github.com/oswaldlow/TWRP-TINA_AN00 device/hinova/TINA
. build/envsetup.sh
lunch twrp_TINA-eng
mka recoveryimage
# output: out/target/product/TINA/recovery.img
```

## Installing (Huawei split recovery)

The `recovery.img` from the build is **not flashed as is**. In recovery mode the
Huawei bootloader loads three partitions:

| Partition | Content |
|---|---|
| `recovery` | kernel; its header cmdline reaches the kernel → keep the **stock** `recovery.img` |
| `recovery_ramdisk` | main ramdisk → the TWRP ramdisk (boot header v3, kernel_size 0) |
| `recovery_vendor` | overlaid **on top of** `recovery_ramdisk` |

Two Huawei-specific constraints (details in [docs/RESEARCH.md](docs/RESEARCH.md)):

- TWRP's own compiled sepolicy **freezes the Huawei kernel** when loaded, and so does any
  policy that is not fully permissive in the TWRP environment. The kernel also rejects
  `setenforce 0`. Working setup: the **stock** recovery policy with every type made
  permissive (`magiskpolicy 'permissive *'`), plus the matching stock `*_contexts`.
- Touch needs Huawei's THP daemon `aptouch_daemon` from the stock `recovery_vendor`; the
  two Huawei recovery init scripts in it must be removed (a `critical` oeminfo_nvm service
  and services that clash with TWRP).

The packaging uses stock Huawei files from the device's own backup, so it is done
locally and those files are not in this repo:

- `recovery_ramdisk` = TWRP ramdisk + stock policy (permissive) + stock contexts + `/adb_keys`
- `recovery_vendor` = stock vendor ramdisk − `init.recovery.huawei.rc` − `init.recovery.lahaina_64.rc`,
  sepolicy replaced by the same permissive policy
- both keep the stock v3 header page and get an AVB hash footer

Leave `vbmeta`, `recovery_vbmeta`, `boot`, `vendor_boot` and `dtbo` alone.
Requires an unlocked bootloader (fastboot reports `FB LockState: UNLOCKED`).

## Status

Works: boots to the TWRP UI, touch, USB (MTP + adb over configfs), root adb.

TODO:
- Decryption of `/data` (FBE v2 + metadata encryption, wrappedkey_v0).
- MTP shows a driver error on Windows (TWRP's MTP process runs).
- Find which part of TWRP's policy freezes the kernel (to use a TWRP-built policy).
