#!/usr/bin/env bash
# Targeted real-platform regression with the production single-Linux layout.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d vendor/kshim/lib/CrDK/.git ]; then
    echo 'Missing pinned CrDK; run scripts/fetch_deps.sh first.' >&2
    exit 1
fi
mkdir -p build
python3 vendor/kshim/ports/crdk/prepare.py \
    --source "$PWD/vendor/kshim/lib/CrDK" --output "$PWD/build/crdk-host"
flags=(-g -O1 -ffunction-sections -fdata-sections -Wl,--gc-sections
       -Wall -Wextra -Werror -Wno-error=unused-function -Wno-error=unused-variable
       -DCR_FREESTANDING=1 -DKSHIM_HOST_TEST=1 -DCONFIG_QCOM_SPMI=1
       -DKSHIM_STANDALONE=1 -DCONFIG_KSHIM_LVGL_BUFFER_BYTES=243712
       -Ivendor/kshim/tests/include -Ivendor/kshim/src/include
       -Ivendor/kshim/lib/libfdt/include -Ibuild/crdk-host/Include
       -Ivendor/kshim/ports/crdk/include
       -DCONFIG_KSHIM_MENU_SESSION_SETTINGS=1 -DCONFIG_KSHIM_MENU_LANGUAGE_SWITCH=1
       -DCONFIG_KSHIM_MENU_ADVANCED_ACTIONS=1 -DCONFIG_KSHIM_MENU_CHINESE=1
       -DCONFIG_KSHIM_QCOM_REBOOT=1 -DCONFIG_KSHIM_MENU_SINGLE_LINUX=1
       -DKSHIM_TEST_SHENG_DIAGNOSTIC_ONLY=1)
gcc "${flags[@]}" vendor/kshim/tests/platform_menu_test.c \
    vendor/kshim/src/core/menu_locale.c vendor/kshim/src/core/boot_settings.c \
    -o build/platform-sheng-diagnostic
build/platform-sheng-diagnostic
