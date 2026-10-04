#
# Copyright (C) 2026 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#

# Inherit from those products. Most specific first.
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/aosp_base.mk)

# Inherit some common TWRP stuff.
$(call inherit-product, vendor/twrp/config/common.mk)

# Inherit from TINA device
$(call inherit-product, device/hinova/TINA/device.mk)

PRODUCT_DEVICE := TINA
PRODUCT_NAME := twrp_TINA
PRODUCT_BRAND := Hinova
PRODUCT_MODEL := Hebe-BD00
PRODUCT_MANUFACTURER := PTAC

PRODUCT_GMS_CLIENTID_BASE := android-hinova

PRODUCT_BUILD_PROP_OVERRIDES += \
    TARGET_DEVICE=TS-TINA-Q \
    PRODUCT_NAME=TINA-AN00 \
    PRIVATE_BUILD_DESC="TINA-AN00-user 102.0.1 HUAWEITINA-AN00 166-CHN-LGRP1 release-keys"

BUILD_FINGERPRINT := Hinova/TINA-AN00/TS-TINA-Q:11/HinovaHebe-BD00/102.0.1.166C11:user/release-keys
