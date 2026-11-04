# sheng：KShimC 到 Linux 跑码的补丁实施

范围：菜单确认 → Linux 屏幕控制台。不涉及 SDDM、Denial 或桌面配置。
合并镜像已备份后写入 boot_a，未重启；不宣称闪屏已消失。
用户随后要求再检查时，上一次写入已完成；已立即停止进一步写入并做只读复核。

## 改动

### SM8550 显示时钟

导入 `patches/kernel/0001-sm8550-mdp-clock-parent-enable.patch`，原作者
Philippe Simons。只给 `disp_cc_mdss_mdp_clk_src` 增加
`CLK_OPS_PARENT_ENABLE`，不写其他 SoC 的寄存器，不删除面板复位或缩短时序。

构建脚本：`scripts/build-handoff-kernel.sh`。

- 源：ianchb/sm8550-mainline，`42f3b40c702abbc37c3a04c95af008cd283aeaf3`。
- 源码归档通过镜像获取后，用 Git 索引重算完整源码 tree：
  `8bc4d95a7fa96560aecb76ff7744c6d57a20756b`，与直接从 GitHub 获取的原提交一致。
  没有仅凭镜像 URL/文件名信任源码。
- 原配置：`/boot/config-7.2.6-sm8550-00103-g42f3b40c702a`，SHA256
  `7013c8620f31cf5c8d2a23dc68a717b48e66669776b3f87e0ac0a6c857cd275f`。
- 构建使用本机 Clang/LLD 23.1.4；原内核为 Clang 21.1.8。保留原功能配置，
  自动生成项的差异在 `out/linux-handoff-kernel/config.diff`。
  脚本按审查过的白名单检查差异，拒绝悄悄更改驱动/ABI 相关配置。
- 保留 release `7.2.6-sm8550-00103-g42f3b40c702a` 以使用现有模块路径。
  同源/同配置和时钟内部修改旨在保持模块兼容，但同 release 不是兼容性的充分证明；
  编译器版本变化和真机模块加载仍需验证。
- 只构建 Image，不安装 modules，不改 `/boot`。

### sheng 早期 framebuffer

为 Python packer、`scripts/build.sh` 和 `scripts/make-boot.sh` 增加显式
`--early-console`，普通和诊断 DTB 一同生效。Windows 的 Python 包装器直接转发
此选项，不需要 dtc。

- 仅允许 `xiaomi,sheng`。
- 加入禁用的 `/chosen/framebuffer` 模板及 runtime 所需的 2/2 bus cells、空 ranges。
- 不硬编码 framebuffer 物理地址、尺寸或格式。由已有的
  `dt_simplefb_apply()` 从菜单实际 scanout 填入并启用，保留完整 framebuffer 内存。
- 不改设备 MAC、传感器、显示模式、initrd 入口号或 Android 原厂载荷。
- 已有模板必须唯一、禁用且无 memory-region；不兼容的 chosen bus 布局会拒绝打包，
  不静默覆盖。未传 `--early-console` 时不添加模板。
- 本机原有 `CONFIG_FB_SIMPLE=y`；同版本内核的 msm KMS 使用
  `aperture_remove_all_conflicting_devices()`，具备移除早期 fb 的路径。
- 继续使用已有 runtime，无需为同一份 simplefb 实现再重建菜单。

### 交接安全检查

新增真实 C 代码回放后，合成 Image 的“未知页大小”（按 64 KiB 保护）揭示：
原 initrd 的 4 KiB 首部对齐可能与前一个内核/DTB 共页。本机实际内核是 4 KiB，
这不是声称旧镜像普通 Linux 必然失败；但通用打包器不应输出这种潜在冲突。

现在 initrd 首部改为 64 KiB 对齐，诊断 DTB 继续保留此前修复的 64 KiB 对齐。
打包后检查所有其他条目都不与 initrd 的 64 KiB 页取整保护区间重叠。
没有删除或放宽 runtime 的验证。

## 有意不加入的内容

- Kaanapali 的 no-init-park：未验证 SM8550 的父时钟/GDSC/休眠安全，暂不启用。
- SM8750/Elden 的 block reset 常量及 TB710FU/SM8650 的 PHY fixups：机型不匹配。
- Early-MMU 主优化：本机已存在且 live DT 确认启用，不重复引入。
- 不根据其他机型的灰屏 issue 刷固件，不用 quiet 隐藏问题。

## 验证

- Python 测试 21 项通过，包括：模板 opt-in、板级限制、幂等性、原属性保留、
  非法模板/总线拒绝，以及普通/诊断条目的真实 initrd + simplefb C 代码回放。
- 已有 sheng 诊断菜单专项测试通过。
- 上游 memory_overlay_test 默认测试通过。
- 读取本机当前设备树的实际 memory/reservations，对普通/诊断目标 DTB 分别回放
  `dt_memory_capture()` + `dt_memory_apply()`，均返回 0，输入保持不变。
  这仍是主机回放，不是完整 ABL 真机交接。
- 模拟 sheng 的真实 fallback 描述符（0xb8000000、3048×2032、stride 12192、
  XRGB8888）回放后，模板启用、完整扫描缓冲保留、initrd 精确范围和最终 DT 验证均通过。
  物理地址在主机上不被解引用。
- 构建配置差异审计及脚本语法检查通过。

日志：`build/early-console-tests.log`、`build/early-console-menu.log`、
`build/early-console-memory.log`、`build/linux-handoff/build-final.log`、
`build/linux-handoff/package.log`；再次检查的 Python 测试在 `build/handoff-recheck-tests.log`。
首次构建已完成 Image，但执行中的构建脚本被更新后，其尾部记录阶段出现语法错误；
重新执行最终脚本后完整通过，最终 build.exit 和 package.exit 都为 0。
内核构建最终状态看 `build/linux-handoff/build.exit`（0 为成功），
打包/真实交接验证最终状态看 `build/linux-handoff/package.exit`（0 为成功）。

## 产物与测试

`scripts/package-handoff.sh <patched Image>` 在成功构建后生成：

| 镜像 | 内容 |
| --- | --- |
| `out/boot_a_arch_handoff.img` | 新编译的时钟修复内核 + 早期 framebuffer，合并候选 |
| `out/boot_a_arch_handoff_clock_only.img` | 同一新内核，不加 framebuffer 模板 |
| `out/boot_a_arch_handoff_simplefb_only.img` | 原 Linux Image + framebuffer 模板 |

三个镜像都保留 Android、普通 Linux、Linux diagnostics，以及本机原 DTB 的设备地址。
initrd、runtime 与本轮之前的已验证输入相同；新增 `console=tty0` 明确指定屏幕控制台，
不增加正常入口的日志级别。原配置默认 console loglevel 已为 7。

`clock_only` 的命名表示“没有新模板”，不是声称与原二进制仅差一条时钟指令：
原二进制/新二进制还存在编译器差异。严格归因时应再构建同工具链的无补丁基线。
校验和：`out/handoff-SHA256SUMS`；每个镜像旁有打包 JSON 和独立 work 目录。

建议在可恢复条件下先用一次性启动测试，分别记录：

1. 按下确认 → 第一行内核日志（视频计时）。
2. 菜单消失到日志出现之间是亮闪、黑闪还是连续画面。
3. `journalctl -b -k` 中 simplefb、msmdrmfb 及 rcg warning；
   `/proc/device-tree/chosen/` 中是否存在启用的 framebuffer 节点。
4. 普通/诊断入口、Android 回退、蓝牙、模块加载、关屏唤醒与休眠是否正常。

之前可回退的镜像仍为 `out/boot_a_arch_diagnostic_fix2.img`，其原文件未改动。
真实闪屏改善程度须以重启测试为准。

## 部署及用户要求后的只读复核

- 已写入：`out/boot_a_arch_handoff.img`，112,549,888 B。
- SHA256：`76e017bc34270e227685102afe764a145d3d7b78783587ff950bc7e19d99d732`。
- 目标：`/dev/disk/by-partlabel/boot_a`（本次解析为 `/dev/sde14`）。
- 刷前确认实际分区匹配已知 fix2 镜像，然后完整备份至
  `out/backup/boot_a-before-handoff-20261104-235648.img`。
- 完整备份 SHA256：`56ec9ff2cf1911402c525895b9947f64eb75fa7fb2d987210b6f6b473d88911e`。
- 写入后 fsync，读回新镜像逐字节/哈希匹配，分区尾部未变。
- 用户要求“先再次检查一遍再写入”到达时，该次写入已完成；已明确告知，
  没有继续写入，也没有重启。
- 随后的独立只读复核：实际 boot_a 与候选逐字节一致；尾部与刷前备份一致；
  完整备份校验正确；boot_b、dtbo_a、init_boot_a、vendor_boot_a 均与原始备份
  SHA256 一致。21 项测试和两个 Linux 入口的真实 C 交接验证再次通过。
- 安装记录：`out/handoff-install.json`。当前正在运行的仍是重启前的内核。
