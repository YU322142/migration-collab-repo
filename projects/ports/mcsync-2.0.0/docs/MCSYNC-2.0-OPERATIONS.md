# MCSync 2.0 操作简表

## 发布者流程

1. 用 `java -jar MCSync-2.0.0.jar --v5-template project.json` 生成项目模板。
2. 为每个文件选择 `publisher-hosted`、`direct`、`modrinth`、`curseforge` 或 `manual`，并明确 `redistributable` / `upstream-only` / `manual`。
3. 手工适配的模组放 `publisher-hosted + redistributable`；不允许再分发的模组只能用固定平台版本、固定 fileId/versionId 或人工来源。
4. 中国镜像只是候选传输端点，必须同时保留官方端点；两者最终都以清单中的大小和 SHA-256 为准。
5. CurseForge 的 API key 只在发布者本机通过 `MCSYNC_CURSEFORGE_API_KEY` 或 JVM system property 提供。发布完成后清单只保存固定文件 URL，不保存 key。
6. 用 `--publish-v5 <游戏根目录> <project.json> <空输出目录>` 物化发布目录。输出目录必须为空，生成 `manifest-v5.json` 和本地报告。

## 客户端启动流程

- 1.9.x 先通过旧 v2/v4 永久入口升级到 MCSync 2.0。
- NeoForge 在现有 Minecraft 窗口标题显示检查、下载、校验和“需要重启”；不创建第二个更新窗口。
- 文件、KubeJS、注册表资源或配置发生变化时，MCSync 停止本次启动；隐藏 helper 在 JVM 退出后提交并等待下一次启动。
- 同一发布序号下，文件被玩家改坏会重新修复；清单序号不会降低，清单分叉会阻断。
- `first-install` 文件（例如 `options.txt`）已有时保持玩家版本；世界、地图、区块、实体、POI、gamerule、缓存和凭据永远不进入 OTA。

## 出错处置

- 出现 `RECOVERY_REQUIRED.txt` 时不要手工删除，先保留 `.modsync/transactions/` 和备份，确认回执后再处理。
- 网络失败、镜像哈希错误、配置冲突、路径越界、旧 SHA 不符均是 fail-closed，不会半提交。
- 游戏必须重启才能消费 Mod/JAR/注册表变更；MCSync 不宣称热替换。
