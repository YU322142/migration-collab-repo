# Minecraft 1.21.11 → NeoForge 1.21.1 迁移交接包

此包用于继续深入处理迁移，不是“所有历史候选副本”的归档。它只保留一份原始输入、一份当前修正后的转换结果、当前发布模组、转换/审计工具源码、关键报告，以及未完成事项。

## 目录

- `01-original/20260811.zip`：用户提供的最新停服原始服务端，永远只读。
- `01-original/resource-pack-original.zip`：用户原始资源包（文件名含中文，包内用 ASCII 文件名保存；SHA 在清单中）。
- `02-latest/converted-staging/`：唯一交接转换结果。它以 Candidate13 frozen staging 为基础，额外应用：
  - `create_tracks.dat` 的四条 `InitialOrientation` 小写→大写修复；
  - 恢复 `immersive_paintings_cache`（87 原图 + 87 缩略图）。
- `02-latest/release-bundle-candidate14-r3/`：Candidate14-r3 的 server/client 模组快照。54 是本版快照，不是永久模组数量上限。
- `02-latest/resource-pack-mc1.21.1-candidate13.zip`：已加 `pack_format=34` 的 1.21.1 派生资源包；原始包不改。
- `02-latest/p0-additions/`：在 Candidate14-r3 之后发现的 P0 兼容件，例如 Create carriage orientation runtime guard。安装时服务端与客户端必须使用同一 JAR 哈希。
- `03-tools-and-source/tools/`：转换、组装、门禁与审计脚本及测试。
- `03-tools-and-source/projects/`：自制兼容模组源码；排除 `build/`、`.gradle/` 和编译缓存。
- `04-reports-and-docs/`：根目录关键 JSON/MD、崩溃证据和最终锁。
- `05-superseded-index/`：未打包的候选世界/运行副本索引。它们仅作历史证据，不应当作转换输入。

## 最重要的边界

1. 不要用任何启动、保存过的 Candidate runtime 作为新转换源。
2. 原始 ZIP 与 `01-original` 永远不写入。
3. `02-latest/converted-staging` 是当前唯一可继续工作的转换结果，但在新的完整运行门禁通过前仍不是生产 GO。
4. 不要删除列车、画框、沉浸画框缓存或未知物品来“消除错误”；优先使用数据转换、稳定 ID、sidecar/ledger 和 BOTH-side 兼容模组。
5. 生产 `server.properties`、端口、白名单和认证配置不得由测试工具覆盖。
6. MCModSync 只负责受控客户端 OTA；服务端 JAR、世界/玩家 NBT、recipe book、advancement 等仍需要短停的服务端版本化迁移。

## 当前已验证修复

- 世界/玩家/实体/方块实体主要 codec 转换和 Candidate13/Candidate14 既有 P0 兼容件。
- Create `InitialOrientation`：真实源 4/4 列车被严格规范化为 `SOUTH/WEST/EAST/NORTH`，blockers=0；21 项 SavedData 单测通过。
- Immersive Paintings：87 个索引、174 个 PNG；索引 SHA-256 `FB0A3F6A32E4E614BD0559B3EC52239F71A2DF9C1FB37BE2741C60E5D062C0C4`，图片树 SHA-256 `E61E30BB3BF856C90FCBFF3F113B9F513DE2E8732EFFD335C957882F7AD0B98F`；迁移/增量/组装/冒烟四条路径已纳入该目录，68 项回归测试通过。
- Waypoint 高权限命令树、Create chute unload race、CC:Tweaked cold-start/stop、Scarecrow legacy container、Deferred Content Protection 等详见报告和模组锁。

## 当前发布状态

Candidate14-r3 Attempt 3 自动双轮门禁为 `PASS`，但随后的用户人工测试又发现 Create carriage orientation 客户端渲染崩溃，并确认沉浸画框图片目录未被旧流水线携带。交接 staging 已恢复原始 `immersive_paintings_cache`；Create carriage 部分只保留源码、失败证据和一个明确标注为 `BUILD_EVIDENCE_ONLY_REQUIRES_FINAL_REBUILD` 的 JAR，它不是发布制品。

按用户最新要求，本任务已停止修复和构建，只完成文件与文档交接。因此本包状态是 `HANDOFF_ONLY_NOT_PRODUCTION_GO`；旧门禁 PASS 不能覆盖后来的人工崩溃证据。

请从 `TODO.md` 开始继续。
