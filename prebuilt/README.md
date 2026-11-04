# Prebuilt runtime

`sheng-runtime.bin` is the 4 MiB kShimC runtime for Xiaomi Pad 6S Pro (sheng),
built from this checkout's `vendor/kshim` and `config/sheng_defconfig`.

- updated: 2026-11-04
- size: 4,194,304 B
- SHA256: `f6bd141b9c993d769100511499b586dd39c3a9715db3a6876e5705c0ccd1302f`
- toolchain: GNU AArch64 GCC 16.1.1 (native ARM64 build)
- validation: exactly 4 MiB; no undefined symbols
- features: deferred final MMU/cache shutdown, incoming-DTB cache flush,
  80 ms boot hint, boot timing, and sheng diagnostics menu recognition
- machine-readable metadata: `sheng-runtime.json`

The early framebuffer template is added by the packer's `--early-console`
option; the SM8550 display-clock patch belongs to the separately built Linux
kernel. Neither requires another copy of the same runtime implementation.
The combined kernel/display candidate still needs reboot testing; host tests
are not a guarantee of flicker-free hardware handoff.

You only need to rebuild this file when the runtime or its configuration
changes. Merging another Android boot image or Linux kernel does not require
rebuilding the runtime. Linux and Windows wrappers can reuse this file.
