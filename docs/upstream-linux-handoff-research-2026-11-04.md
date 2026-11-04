# KShimC → Linux 早期控制台：公开上游检索

检索时间：2026-11-04（本机时间）。范围仅限菜单确认后到屏幕出现内核日志，不含 SDDM/Denial。
本轮仅检索、下载源码并比较，未修改 runtime、DTB、内核或启动分区。

## 结论

公开代码里有可借鉴的早期 framebuffer 交接、显示时钟接管和 MMU 性能修复；没有找到可直接用于 sheng/SM8550、且经真机证明消除这一下闪屏的现成 PR。
最值得优先验证的是 SM8550 显示时钟补丁及已存在但未由 sheng DTB 启用的 simplefb 交接。面板复位是显示中断的合理机制，但目前不能单凭静态代码确定用户观察到的那一下由它独自造成。

## 1. KShimC 原作者仓库

- 仓库：https://github.com/sunflower2333/kShimC
- `feature/2610` 检索时 HEAD：`82ce6eaa10c36e64cfd3f16799172d854f9a955b`。
- [PR #2: Add TB323FU Canoe key and continuous-splash support](https://github.com/sunflower2333/kShimC/pull/2)：已关闭，未合并。解码活动 CTL/LM 路由、识别真实扫描缓冲，拒绝压缩/重叠/不一致布局。主要解决 ABL → 菜单的缓冲识别，不是 Linux 原生显示驱动无缝接管的保证。PR 自述未重跑该快照的真机验证。
- 搜索返回该仓库 PR #1、#2、#3；#1 为 UI 主题，#3 为 README。未发现专门针对 sheng 菜单 → 内核闪屏的公开 issue/PR。
- 当前 `feature/2610` 文件树没有 `src/dt/simplefb.c`；这部分实现位于 ArmadaOS 下游。

## 2. ArmadaOS / lich-wang：真正的 Linux simplefb 模板

- [已合并 PR #10: TB710FU board/display/GPU](https://github.com/mydanyi/armadaos-freedom/pull/10)：DT overlay 明确加入禁用的 `/chosen/framebuffer@...` 模板，注释说明由 kShimC 填入 ABL scanout 并启用，作为 msm 接管前的控制台。
- [已合并 PR #8: SM8650 支持](https://github.com/mydanyi/armadaos-freedom/pull/8)：作者在 10 月 28 日评论报告真机运行 `23fc939`，生成了地址 `0xd5100000`、3200×2000、stride 12800、a8r8g8b8 的 simple-framebuffer，并进入 Linux。它证明交接机制有真机使用记录，但并未证明所有显示切换都无闪屏。
- [simplefb 实现（固定提交）](https://github.com/mydanyi/armadaos-freedom/blob/f4289696afd94a3e64869a0119d228c693a39dbb/devices/lenovo-tb323fu/boot/kshim-success-source/src/dt/simplefb.c)。与本机 `vendor/kshim/src/dt/simplefb.c` SHA256 完全一致：`4f708e50f8d262c18ac961bec1dc487a061b5dd058f3b527b669f8382680e832`。
- 本机 live DT 无 simple-framebuffer 节点；该函数找不到模板时返回成功但不操作。因此缺的是 sheng 模板/配套接管验证，而不是再引入同一份 C 实现。
- 不能照抄 TB710FU 的 framebuffer 物理地址、分辨率和 PHY 参数；需使用 sheng 的真实资源，并验证内存保留、时钟/电源域及 native DRM takeover。

## 3. 最直接匹配当前日志的 SM8550 时钟补丁

[0002-qcom-dispcc-sm8550-Fix-disp_cc_mdss_mdp_clk_src.patch](https://github.com/mydanyi/armadaos-freedom/blob/f4289696afd94a3e64869a0119d228c693a39dbb/packages/kernel/patches/0002-qcom-dispcc-sm8550-Fix-disp_cc_mdss_mdp_clk_src.patch)

作者 Philippe Simons，补丁头日期 2025-10-08。描述明确说修复 `rcg didn't update its configuration`，将 `disp_cc_mdss_mdp_clk_src` 的 flags 从 `CLK_SET_RATE_PARENT` 改为 `CLK_SET_RATE_PARENT | CLK_OPS_PARENT_ENABLE`。

本机本次启动约 0.268s 出现同名时钟、同样 warning；先前保存的对应内核提交 `42f3b40c702a` 的 `dispcc-sm8550.c` 仍只有 `CLK_SET_RATE_PARENT`。这是同 SoC、同告警的候选补丁，应先固定其余输入做 A/B 测试。消除 warning 不自动等于消除肉眼闪屏，不宣称已修好。

## 4. 另一项直接以开机画面瑕疵命名的修复

[0168-clk-qcom-dispcc-kaanapali-solve-display-artifacts-at.patch](https://github.com/mydanyi/armadaos-freedom/blob/f4289696afd94a3e64869a0119d228c693a39dbb/packages/kernel/patches/0168-clk-qcom-dispcc-kaanapali-solve-display-artifacts-at.patch)

作者 Nazar Kompanets，补丁头日期 2026-08-03，标题 `solve display artifacts at start`。将 MDP clock ops 从 `clk_rcg2_shared_ops` 改为 `clk_rcg2_shared_no_init_park_ops`，避免注册时主动 park 正在使用的显示时钟。

本机对应 `clk-rcg2.c` 已有 no-init-park 实现，当前 SM8550 MDP clock 仍使用 shared ops；告警栈也经过 `clk_rcg2_shared_init`。但该补丁目标为 Kaanapali 而非 SM8550；只能作为下一步受控实验方向，不能直接认定可安全跨机型使用。park 原本用于避免父时钟关闭后 RCG/GDSC 卡死，不能忽略电源管理风险。

## 5. 性能优化：早期 MMU

[已合并 PR #6: enable translation early instead of after resource probing](https://github.com/mydanyi/armadaos-freedom/pull/6)，作者 corebear6010。

PR 自报 TB322FC ENTRY → first menu frame 从 68,816ms 降至 2,580ms；不是菜单确认 → 跑码耗时。PR 同时讨论 HCR_EL2 恢复及缓存属性问题，需区分描述与实际检出的实现，不能仅凭 PR 文案假定所有细节都已进入任一快照。

本机已有 early-MMU，live DT 为 `kshim,mmu-early = [1, 0]`，ENTRY → first menu frame 为 2,252ms。不能再次把这项优化当成本机尚未应用的补丁，也不能用它解释当前确认后的闪屏。

## 6. 其他相关但不能照搬的经验

- [0714 TB710FU controller/PHY state](https://github.com/mydanyi/armadaos-freedom/blob/f4289696afd94a3e64869a0119d228c693a39dbb/packages/kernel/patches/0714-drm-msm-dsi-bootloader-controller-phy-state.patch)：恢复该机 ABL 的 DSI/PHY 参数；避免瞬时 FIFO underflow 触发链路复位而黑屏。严格限定 `lenovo,tb710fu`，不是 sheng 通用修复。
- [0154 Elden reset-live-display](https://github.com/mydanyi/armadaos-freedom/blob/f4289696afd94a3e64869a0119d228c693a39dbb/packages/kernel/patches/0154-clk-qcom-elden-reset-live-display.patch)：为 SM8750/Elden 主动复位仍在工作的显示硬件以恢复正常启动；目标是可靠初始化而非无缝保持画面，不应移植寄存器常量到 sheng。
- [TB321FU issue #7](https://github.com/enij90/armada-tb321fu/issues/7)：早期 framebuffer 能显示，msm 接管后灰屏；最终报告与固件/深刷环境有关，还存在 writeback 等变量。不是 sheng 的短暂闪屏，也不能据此建议刷固件。

## 7. 其他 fork 与搜索限制

- 检索 GitHub `kShimC fork:true` 返回 27 个仓库（含 ArmadaOS 分支及 sheng fork），不是 27 个独立 runtime 实现。
- `Admin0x002/kShimC` 的 feature/2610 与原作者 HEAD 相同。
- Arlong8823、wt-5783、Alrecue 的 sheng master 都是 `51aef95e...`，与本机项目 HEAD 相同。
- alghiffaryfa19 的 sheng fork HEAD 为 `d5279d0`，最新提交为英文翻译/UI及文档改动，没有发现新的早期显示接管补丁。
- 另查看 corebear6010、lich-wang 的分支引用及 onlymykazari 的 TB321FU issue/分支信息；未逐份穷尽所有 fork 的全部历史。
- GitHub 普通 REST API 遇到共享出口 rate limit；使用可用的搜索 API、公开 PR/issue 网页、Git refs/history 和 raw 源码交叉核对。`kShimC flicker`、`kShimC simplefb`、`kShimC 闪屏` 的 issue 搜索没有结果；这不意味着所有公开/未公开讨论中不存在相关问题。

## 建议顺序

1. 先验证 SM8550 的 `CLK_OPS_PARENT_ENABLE` 补丁，记录 warning、菜单确认到首行日志的时长及视频。
2. 再单独加 sheng simplefb 模板，复用已有 runtime 实现，验证 native DRM 接管及内存安全。
3. 如仍有最早期闪屏，再研究 no-init-park 和面板/背光时序；每次只改变一个变量。
4. 不混入桌面启动、UI 主题、其他 SoC 的硬编码寄存器，不以隐藏日志代替修复。
