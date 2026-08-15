# Candidate14-r3 OTA 修复性契约（2026-08-12）

这份契约回答一个很具体的问题：第一版暂缓的每一类错误，是否已经有一条可审计、可回滚、不会吞数据的后续修复路线。

结论不是“所有问题都能由 MCModSync 单独热修”。准确结论是：

- 所有已知错误都必须被分类，并绑定到一个版本化交付路线；
- 纯客户端资源/渲染问题可以由 MCModSync 在客户端退出后更新；
- 双端 Java 行为问题必须同时发布服务端和客户端 JAR，并短暂停服；
- 世界、玩家、配方书、进度、地图等持久化数据问题必须由停服后的服务器数据迁移/数据修复处理，MCModSync 本身不能完成；
- 未分类的新错误一律 `NO_GO`，并在启动门禁中阻断。

机器契约：

`outputs/candidate14-ota-repairability-contract-20260812.json`

契约 SHA-256：`99CF24314AA87EEA54C544EB54B7D49192BFD4A7CCAF4C3AED7C2958367A2750`

校验器：

`outputs/tools/validate_candidate14_ota_repairability.py`

测试：

`outputs/tools/test_validate_candidate14_ota_repairability.py`

## 三种修复类别

| 类别 | MCModSync 是否足够 | 是否需要客户端退出 | 是否需要短暂停服 | 是否允许修改世界数据 |
|---|---:|---:|---:|---:|
| `client_only_ota` | 是 | 是 | 否 | 否 |
| `both_side_mod_update` | 否 | 是 | 是 | 仅在明确的迁移契约下 |
| `server_only_data_migration` | 否 | 否 | 是 | 是，但必须快照、sidecar、幂等和回滚 |

## 已知错误覆盖

| 错误 ID | 优先级/状态 | 类别 | 后续路线 |
|---|---|---|---|
| `server.recipebook.unrecognized_ids` | P0，已审阅原生自清理、等待全新两轮门禁 | 服务器/数据迁移 | 第一轮只允许精确锁定的 62 行/41 ID multiset，由服务端原生 load/save 清理；第二轮必须为零。若漂移或重启后仍存在，才启用带 sidecar 的幂等 datafix |
| `server.advancements.unrecognized_ids` | P1，暂缓 | 服务器/数据迁移 | 逐条映射进度，保留未映射项 sidecar |
| `server.map_banner.null_list` | P1，暂缓 | 服务器/数据迁移 | 只规范化受影响地图旗帜字段，保留地图 ID、装饰和 payload |
| `minecraft.netherite_horse_armor.registry_and_gameplay` | P0，保护载体中 | 双端配对升级 | 保持原 registry ID；新完整实现通过两轮账本后替换保护载体；二者禁止共存 |
| `kaleidoscope_cookery.scarecrow.legacy_codec` | P0，Candidate14-r3 已加入兼容 JAR | 双端配对升级 | 客户端/服务端兼容 JAR 成对发布，修复旧列表 codec 越界 |
| `converter.player_attributes.generic_namespace` | P1，转换器已有修复别名 | 服务器/数据迁移 | 只修 7 个已知 `generic.*` 别名，保留数值、修饰符和 UUID；第二次执行必须零变化 |
| `client.yuushya.invalid_models` | P1，暂缓 | 客户端 OTA | 仅发布资源 overlay JAR，修复 5 个模型 JSON；不改用户本地资源包 ZIP |
| `client.yuushya.form2_blockstates` | P1，暂缓 | 客户端 OTA | 为已枚举的 432 个 `form=2` 状态添加合法 fallback/alias |
| `client.yuushya.texture_references` | P1，暂缓 | 客户端 OTA | 只修有证据的纹理引用，包括尾部下划线 typo |
| `client.creaking_heart.active_property` | P1，暂缓 | 客户端 OTA | overlay 合法的 1.21.1 blockstate；保持 `syncResourcePacks=false`，不替换用户 ZIP |
| `client.render.blackout_or_blindness_effect` | P0，观察项 | 客户端 OTA | 依据复现日志/截图发布渲染兼容 JAR 或 overlay；客户端截图、重启和 Render 日志必须通过 |
| `both.connector.nonexistent_locator` | P2，非致命暂缓 | 双端配对升级 | 成对升级/替换 Connector；新 fatal mixin/loader 错误仍是阻断项 |
| `both.optional_mixin_refmap_targets` | P2，非致命暂缓 | 双端配对升级 | 成对修正可选注入；不能用 allowlist 掩盖真正崩溃 |
| `server.mineastr.astrbot_integration` | P1，验收暂缓 | 服务器/数据迁移 | 停服升级 MineAstr 桥接和绑定迁移；账号 UUID、权限和外部绑定写入 sidecar |

Candidate14-r3 第一次门禁因为尚未有这份窄化规则，把 62 条配方书日志判为 `NO_GO`。随后已经生成不可变的 stale-only sidecar：仅接受该次观测的 62 行、41 个 ID 和精确行形状；新的全新副本第一轮必须完全匹配，服务端正常保存后第二轮必须为零。任何未审阅 ID、不同 logger/消息、multiset 漂移或第二轮残留仍然 `NO_GO`。这不是宽泛忽略日志，也不修改 source/staging。

## 不删数据的硬约束

所有数据修复必须同时满足：

1. 原始世界、玩家文件和第一版 staging 只读保留；修复在快照或新版本副本上执行。
2. 每个持久化对象都有稳定身份：玩家 UUID、实体 UUID、地图 ID、配方/进度 ID、MCA 文件和 slot 等。
3. 每次移除或改写都记录 sidecar：原始路径、原始 payload 摘要、目标路径、规则版本、输入 SHA-256、时间和结果。
4. 同一输入 SHA-256 再执行一次必须报告 `ALREADY_APPLIED` 或零变化，不能产生第二份对象。
5. 任何数量减少、payload hash 改变、registry ID 改名、sidecar 缺失或异常新实例都 `NO_GO`。
6. 失败时保留事务目录、备份和 `RECOVERY_REQUIRED` 标记；不得删除标记后强行继续。

## 版本依赖与发布顺序

- 每个新版本都必须生成新的 `READY.json`、server/client manifest、release-lock 和不可复用的 `catalog-version`。
- 当前 54 个 JAR 只是 Candidate14-r3 快照，不是永久数量上限；后续可以新增、升级或移除模组，但必须从新版本自己的 READY/manifests 动态生成清单。
- 双端修复需要同一 Minecraft/NeoForge 版本、兼容依赖、唯一 mod ID、JAR CRC、SHA-256/MD5 和配对 release-lock。
- 数据迁移必须在停服后执行：先快照，再 dry-run，再提交，再启动；启动后至少完成一次保存和一次重启账本。
- 回滚发布旧业务 JAR 时仍使用新的 `catalog-version`，保留旧目录、旧清单、`.modsync/backups` 和世界快照；不降级 MCModSync 本身。

## MCModSync 1.9.1 的边界

已审计版本：commit `9c1e8b13f5662eb389e73adc94a9a71fcb542bc9`，JAR SHA-256 `2DD2BEC977B8669D0EF6C90FC54A06021DC0998E903B583517052B1B5CDA25AA`。

它能做：

- 客户端 JAR 新增、升级和受控移除；
- MD5/SHA-256 校验；
- 事务式替换、备份和失败回滚；
- 版本化清单，允许后续新增/升级/移除。

它不能单独做：

- 专用服务端 Java JAR 热加载或停服替换；
- 世界、玩家 NBT、配方书、进度、地图等数据迁移；
- 客户端与服务端协议/注册表的双端配对验收；
- 把未签名清单变成可信签名；
- 在本策略下替换用户资源包或修改 `servers.dat`。

此外，MCModSync 代码本身接受 HTTP 和普通重定向，不能单凭客户端代码保证供应链安全。因此正式启用前还必须由发布基础设施执行 HTTPS-only、拒绝跨源重定向、对象先上传/校验、清单最后发布、独立 catalog SHA-256 和 canary。

## 启动阻断规则

出现以下任一标记，启动必须阻断：

`STARTUP_BLOCKED`、`RECOVERY_REQUIRED`、`UNCLASSIFIED_OTA_ERROR`、`MIGRATION_LEDGER_MISMATCH`、`CATALOG_HASH_MISMATCH`、`SIDE_COMPATIBILITY_MISMATCH`。

进程退出码为 0 不能证明启动成功；监控必须读取 `[MCModSync] STARTUP_BLOCKED` 和门禁报告。任何不在本契约或批准 allowlist 中的新错误，都必须先分类、补充修复路线和测试，再生成新 release-lock。

## 只读验收命令

```powershell
C:\Python314\python.exe -B outputs/tools/validate_candidate14_ota_repairability.py
C:\Python314\python.exe -B -m unittest outputs.tools.test_validate_candidate14_ota_repairability -v
```

本次校验器只读取工作区策略和既有证据；没有启动 Java、没有联网、没有绑定端口，也没有修改生产或 staging。
