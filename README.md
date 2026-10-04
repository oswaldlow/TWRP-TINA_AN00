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

## Test first, then flash

- Back up the stock `recovery` partition (already in `images\recovery.img`).
- Flash only the `recovery` partition. Leave `vbmeta`, `recovery_vbmeta`, `boot`,
  `vendor_boot` and `dtbo` alone.
- Requires an unlocked bootloader (fastboot reports `FB LockState: UNLOCKED`).

## TODO / unverified

- Decryption: disabled. It needs Huawei keymaster / gatekeeper / qseecomd blobs from vendor.
- Touch: the Huawei TP driver may need firmware from `/vendor/firmware` or `/odm`.
- `TW_MAX_BRIGHTNESS`: guessed. Read `max_brightness` on the device and fix it.
- How the Huawei bootloader picks `recovery` vs `recovery_ramdisk` + `recovery_vendor`
  for recovery boot has not been confirmed.
