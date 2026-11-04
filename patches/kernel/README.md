# sheng Linux handoff patch

Baseline: [ianchb/sm8550-mainline](https://github.com/ianchb/sm8550-mainline),
`42f3b40c702abbc37c3a04c95af008cd283aeaf3` (`sheng-7.2.6`).

## Applied

`0001-sm8550-mdp-clock-parent-enable.patch`

- Original author: Philippe Simons; original patch commit header
  `2974d421bb6e5ab6994cd8923180a9c1da7ad035`, 2025-10-08.
- Retrieved from [ArmadaOS Freedom](https://github.com/mydanyi/armadaos-freedom/blob/f4289696afd94a3e64869a0119d228c693a39dbb/packages/kernel/patches/0002-qcom-dispcc-sm8550-Fix-disp_cc_mdss_mdp_clk_src.patch).
- Adds `CLK_OPS_PARENT_ENABLE` to the SM8550 MDP clock. Its stated purpose is
  to fix the same `rcg didn't update its configuration` warning seen on sheng.
- Preserve author/sign-off. Linux driver change under the target file's
  GPL-2.0-only license; not a relicensing of the kShimC runtime.

Build without installing:

```sh
scripts/build-handoff-kernel.sh --source /path/to/pinned-kernel --jobs 4
```

The script checks the source revision, original config SHA256, tracked source
changes, final release and reviewed compiler/config differences. It builds only
Image, leaving the installed kernel, modules and boot partitions untouched.
The source/config remain pinned to avoid inadvertently mixing another kernel
version with the existing initrd/modules. A matching release is not on its own
proof of runtime ABI compatibility; hardware boot testing remains required.

## Deliberately not applied

- Kaanapali `clk_rcg2_shared_no_init_park_ops`: potentially relevant to initial
  artifacts, but not verified on SM8550; keeping a live clock may affect power
  domain safety and suspend. It is not an established sheng fix.
- Elden/SM8750 block-reset constants and TB710FU/SM8650 DSI/PHY register fixups:
  different boards/SoCs, with machine-specific conditions in their source.
- Early-MMU: already present in this runtime; do not apply it a second time.

The sheng simplefb template is provided separately by the packer's explicit
`--early-console` option. The runtime's existing `dt_simplefb_apply()` supplies
actual address/geometry and the no-map reservation; the packer never enables a
hard-coded scanout address. See `docs/upstream-linux-handoff-research-2026-11-04.md`.
