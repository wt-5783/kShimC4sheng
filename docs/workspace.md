# 工作目录、Git 历史与同步范围

## 统一工作目录

本机 KShimC 相关工作统一位于：

```text
/home/alarm/Projects/kShimC4sheng/
```

源码原本已在该目录，因此保留现有项目名，避免破坏已配置的构建路径。
此前单独留在 `/tmp/kshim-upstream-research` 的上游检索缓存已迁入项目内，
不再依赖临时目录。

| 路径 | 内容 | Git 同步 |
| --- | --- | --- |
| `packer/`、`scripts/`、`config/` | 提取、打包、构建及配置修改 | 是 |
| `vendor/kshim/` | 延迟交接、缓存清理、诊断菜单及构建修复源码 | 是；依赖缓存除外 |
| `patches/kernel/` | SM8550 显示时钟补丁及来源 | 是 |
| `tests/` | Python、菜单及真实 C 交接回放 | 是 |
| `prebuilt/` | 更新后的通用 runtime、元数据及原 Windows 工具 | 是 |
| `docs/` | 研究、实施及构建说明 | 是 |
| `out/research/upstream-2026-11-04/` | 从 `/tmp` 迁入的网页、API 结果、上游源码检索克隆 | 否，本地资料 |
| `build/linux-handoff/` | 固定版本 Linux 源码、下载归档、编译日志 | 否，可重建 |
| `out/linux-handoff-kernel/` | 内核编译产物及配置审计 | 否，可重建 |
| `out/backup/` | 刷前完整启动分区及设备备份 | 否，不公开 |
| `out/fix1-payload/`、`out/payload/` | 本机内核、设备 DTB、initrd | 否，不公开 |
| `out/boot_a_arch_handoff*.img` | 合并及对照镜像 | 否，不作为 Git 源码提交 |
| `out/migration-backup/` | 同步前的 `.git` 归档、未提交补丁及旧 runtime | 否，本地恢复资料 |

原诊断报告、安装记录、所有旧镜像继续保留在 `out/`，不删除。
本机的 GitHub 凭据、SSH 私钥和会话记录不属于项目源码，也不迁入或上传。
系统已安装的工具和已写入的设备分区不因本次目录整理而改变。

## Git 历史

原目录是浅克隆，只带 `v0.0.4` 的一个提交；并非原仓库提交被删除。
同步时补全远端历史和原标签，保留原提交 ID、作者、父子关系及已有版本标签。
之前尚未提交的本机修改在原有历史之后追加提交，不重写原提交，不强制推送。

远程配置：

- `origin`：`https://github.com/wt-5783/kShimC4sheng.git`（当前登录用户的 fork，可写）。
- `upstream`：`https://github.com/tc1911/kShimC4sheng.git`（原项目，保留为上游）。
- 本地 `master` 跟踪 `origin/master`。

## 更新内容

详见 [CHANGELOG.md](../CHANGELOG.md) 的未发布条目。
预编译 runtime 与本机此次使用的 `out/runtime.bin` 一致；其 SHA256 和构建信息
记录在 [prebuilt/README.md](../prebuilt/README.md) 和
[prebuilt/sheng-runtime.json](../prebuilt/sheng-runtime.json)。
Linux 候选内核和 boot 镜像留在本机，不将含设备身份信息的 DTB、分区 dump 或
完整构建目录提交到公开仓库。其他设备应使用自己的原厂 boot、DTB 和 initrd 构建。
