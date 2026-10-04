#
# Copyright (C) 2026 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#

LOCAL_PATH := device/hinova/TINA

# API levels
PRODUCT_SHIPPING_API_LEVEL := 30

# Dynamic partitions
PRODUCT_USE_DYNAMIC_PARTITIONS := true

# fastbootd
PRODUCT_PACKAGES += \
    android.hardware.fastboot@1.0-impl-mock \
    fastbootd

# Soong namespaces
PRODUCT_SOONG_NAMESPACES += \
    $(LOCAL_PATH)

# Recovery props
PRODUCT_PROPERTY_OVERRIDES += \
    ro.product.device=TS-TINA-Q \
    ro.build.product=TINA \
    ro.boot.boot_devices=soc/1d84000.ufshc
