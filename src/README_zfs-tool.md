# src/ — 源码目录

> 完整项目说明见仓库根目录的 [README.md](../README.md)。

| 文件 | 角色 |
|---|---|
| `zfs-tool.py` | 主工具单文件发行版（v6.2，ZFS 运维管理工具箱）。`_ZT_EMBED_B64` 为**空**——不含 fnOS 模块，见下方说明 |
| `zfs-tool.sh` | 早期 bash 版（行为基准，保留） |
| `_zt_build_single.py` | 构建脚本：把自备的 `zt_fnos.py`（+解锁模板）压成 gzip+base64 注入单文件 |
| `_zt_audit_payload.py` | payload 审计（开发版与注入版差异比对） |
| `_zt_audit_single_load.py` | 单文件加载链路实测（解包 payload → 调 `main(["-v"])`） |

> ⚠️ 本仓**不含** fnOS 扩展模块 `zt_fnos.py`（它是飞牛论坛网友 **mspilot86** 两个 bash 脚本的移植版，原帖未声明许可协议，未随本仓分发）。
> 缺少该模块时，fnOS 相关子命令会 fail-safe 退出，**不影响 ZFS 本体功能**。
