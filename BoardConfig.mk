#
# Copyright (C) 2026 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#
# Hi nova 9 Pro (TINA-AN00 / Hebe-BD00), Qualcomm SM7325 (lahaina / yupik)
# Base: twrpdtgen 3.0.0 output from stock recovery.img, corrected by hand.
#

DEVICE_PATH := device/hinova/TINA

# For building with minimal manifest
ALLOW_MISSING_DEPENDENCIES := true

# Architecture
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-2a-dotprod
TARGET_CPU_ABI := arm64-v8a
TARGET_CPU_ABI2 :=
TARGET_CPU_VARIANT := generic
TARGET_CPU_VARIANT_RUNTIME := kryo385

TARGET_2ND_ARCH := arm
TARGET_2ND_ARCH_VARIANT := armv8-2a
TARGET_2ND_CPU_ABI := armeabi-v7a
TARGET_2ND_CPU_ABI2 := armeabi
TARGET_2ND_CPU_VARIANT := generic
TARGET_2ND_CPU_VARIANT_RUNTIME := kryo385

# APEX
OVERRIDE_TARGET_FLATTEN_APEX := true

# Bootloader
TARGET_BOOTLOADER_BOARD_NAME := lahaina
TARGET_NO_BOOTLOADER := true
TARGET_USES_UEFI := true

# Platform
TARGET_BOARD_PLATFORM := lahaina
QCOM_BOARD_PLATFORMS += lahaina

# Assert (ro.product.device on stock is TS-TINA-Q)
TARGET_OTA_ASSERT_DEVICE := TS-TINA-Q,TINA,TINA-AN00

# Kernel
# Stock recovery.img: boot header v3, page 4096, kernel 5.4.86 (Image.gz),
# no recovery DTB in the image (DTB lives in vendor_boot, dtbo in dtbo).
BOARD_BOOT_HEADER_VERSION := 3
BOARD_KERNEL_PAGESIZE := 4096
BOARD_KERNEL_BASE := 0x00000000
BOARD_KERNEL_IMAGE_NAME := Image.gz
BOARD_KERNEL_CMDLINE := console=ttyMSM0,115200n8 androidboot.hardware=qcom androidboot.console=ttyMSM0 androidboot.memcg=1 lpm_levels.sleep_disabled=1 video=vfb:640x400,bpp=32,memsize=3072000 msm_rtb.filter=0x237 service_locator.enable=1 androidboot.usbcontroller=a600000.dwc3 swiotlb=0 loop.max_part=7 cgroup.memory=nokmem,nosocket pcie_ports=compat loop.max_part=7 iptable_raw.raw_before_defrag=1 ip6table_raw.raw_before_defrag=1 buildvariant=user
BOARD_KERNEL_CMDLINE += androidboot.selinux=permissive
BOARD_MKBOOTIMG_ARGS += --header_version $(BOARD_BOOT_HEADER_VERSION)
BOARD_MKBOOTIMG_ARGS += --pagesize $(BOARD_KERNEL_PAGESIZE)

# Kernel - prebuilt (byte-identical to the kernel inside stock recovery.img)
TARGET_FORCE_PREBUILT_KERNEL := true
TARGET_PREBUILT_KERNEL := $(DEVICE_PATH)/prebuilt/kernel
TARGET_KERNEL_ARCH := arm64
TARGET_KERNEL_HEADER_ARCH := arm64

# Partitions (sizes from the device's GPT / 9008 backup)
BOARD_FLASH_BLOCK_SIZE := 262144
BOARD_BOOTIMAGE_PARTITION_SIZE := 100663296
BOARD_RECOVERYIMAGE_PARTITION_SIZE := 100663296
BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE := 100663296
BOARD_DTBOIMG_PARTITION_SIZE := 25165824
BOARD_HAS_LARGE_FILESYSTEM := true
BOARD_USES_METADATA_PARTITION := true

BOARD_SYSTEMIMAGE_PARTITION_TYPE := ext4
BOARD_USERDATAIMAGE_FILE_SYSTEM_TYPE := f2fs
BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_ODMIMAGE_FILE_SYSTEM_TYPE := ext4
TARGET_COPY_OUT_VENDOR := vendor
TARGET_COPY_OUT_ODM := odm

# Dynamic partitions (from stock super LP metadata: single "default" group,
# block device size 8145338368)
BOARD_SUPER_PARTITION_SIZE := 8145338368
BOARD_SUPER_PARTITION_GROUPS := hinova_dynamic_partitions
BOARD_HINOVA_DYNAMIC_PARTITIONS_PARTITION_LIST := system hw_product cust vendor odm
BOARD_HINOVA_DYNAMIC_PARTITIONS_SIZE := 8141144064

# Recovery
TARGET_RECOVERY_PIXEL_FORMAT := RGBX_8888
TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/recovery/root/system/etc/recovery.fstab
TARGET_USERIMAGES_USE_EXT4 := true
TARGET_USERIMAGES_USE_F2FS := true
BOARD_SUPPRESS_SECURE_ERASE := true
RECOVERY_SDCARD_ON_DATA := true
TARGET_RECOVERY_QCOM_RTC_FIX := true

# Verified Boot
# Recovery is signed with the AVB test key; the bootloader must be unlocked.
# Do NOT flash a modified vbmeta/recovery_vbmeta for this.
BOARD_AVB_ENABLE := true
BOARD_AVB_RECOVERY_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_RECOVERY_ALGORITHM := SHA256_RSA4096
BOARD_AVB_RECOVERY_ROLLBACK_INDEX := 1
BOARD_AVB_RECOVERY_ROLLBACK_INDEX_LOCATION := 1

# Security patch level / version (keep keymaster from rejecting on rollback)
PLATFORM_SECURITY_PATCH := 2099-12-31
VENDOR_SECURITY_PATCH := 2099-12-31
PLATFORM_VERSION := 99.87.36
PLATFORM_VERSION_LAST_STABLE := $(PLATFORM_VERSION)

# SELinux
SELINUX_IGNORE_NEVERALLOWS := true

# Crypto
# Stock /data is FBE v2 (aes-256-xts, inlinecrypt, wrappedkey_v0) with
# metadata encryption. Decryption needs Huawei's keymaster/gatekeeper/qseecomd
# blobs from vendor -- not included yet, so it is disabled for the first build.
# TW_INCLUDE_CRYPTO := true
# TW_INCLUDE_CRYPTO_FBE := true
# TW_INCLUDE_FBE_METADATA_DECRYPT := true
# BOARD_USES_QCOM_FBE_DECRYPTION := true

# TWRP Configuration
TW_THEME := portrait_hdpi
TW_EXTRA_LANGUAGES := true
TW_DEFAULT_LANGUAGE := zh_CN
TW_SCREEN_BLANK_ON_BOOT := true
TW_INPUT_BLACKLIST := "hbtp_vm"
TW_USE_TOOLBOX := true
TW_INCLUDE_REPACKTOOLS := true
TW_INCLUDE_RESETPROP := true
TW_INCLUDE_LPTOOLS := true
TW_INCLUDE_LPDUMP := true
TW_INCLUDE_NTFS_3G := true
TW_HAS_EDL_MODE := true
TW_FRAMERATE := 60
TW_EXCLUDE_APEX := true
TW_BACKUP_EXCLUSIONS := /data/fonts
TARGET_USES_MKE2FS := true
TW_NO_EXFAT_FUSE := true

# Brightness (stock recovery writes panel0-backlight; max level not yet verified on device)
TW_BRIGHTNESS_PATH := "/sys/class/backlight/panel0-backlight/brightness"
TW_MAX_BRIGHTNESS := 2047
TW_DEFAULT_BRIGHTNESS := 1200

# Debug
TWRP_INCLUDE_LOGCAT := true
TARGET_USES_LOGD := true
