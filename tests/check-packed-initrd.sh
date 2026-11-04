#!/usr/bin/env bash
# Usage: bash tests/check-packed-initrd.sh boot.img entry-index expected-status [--early-console]
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
gcc -g -O0 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -Wl,--gc-sections -Ivendor/kshim/src/include -Ivendor/kshim/lib/libfdt/include \
    tests/packed_initrd_check.c vendor/kshim/src/dt/initrd.c vendor/kshim/src/dt/dt.c \
    vendor/kshim/src/dt/simplefb.c \
    vendor/kshim/lib/libfdt/{fdt,fdt_check,fdt_empty_tree,fdt_ro,fdt_rw,fdt_sw,fdt_wip,fdt_addresses,fdt_strerror}.c \
    -o build/packed-initrd-check
build/packed-initrd-check "$@"
