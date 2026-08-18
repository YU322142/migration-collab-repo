# MCSync 2.0 操作简表

## 发布者流程

1. 运行 `java -jar MCSync-2.0.0.jar`，在默认打开的“2.0 OTA 发布”页选择已验证客户端的游戏根目录。
2. 在“文件与来源”扫描安全内容目录，为每个文件选择 `publisher-hosted`、`direct`、`modrinth`、`curseforge` 或 `manual`，明确 `redistributable` / `upstream-only` / `manual`，然后人工确认该行。
3. 手工适配的模组放 `publisher-hosted + redistributable`；不允许再分发的模组只能用固定平台版本、固定 fileId/versionId 或人工来源。
4. 中国镜像只是候选传输端点，必须同时保留官方端点；两者最终都以清单中的大小和 SHA-256 为准。
5. CurseForge 的 API key 只在发布者本机通过 `MCSYNC_CURSEFORGE_API_KEY` 或 JVM system property 提供。发布完成后清单只保存固定文件 URL，不保存 key。
6. 在“配置 OTA”按文件、配置键、旧值前像、目标值、作用端和冲突策略添加统一修复；不必整份覆盖配置。
7. 在“验证与导出”选择空输出目录并导出。工具生成 `manifest-v5.json`、可再分发文件和本地审计报告。

命令行 `--v5-template` / `--publish-v5` 仍保留，用于 CI 和自动发布；普通发布不再要求人工编写 JSON。旧 v4 模组清单、资源包和服务器列表工具位于主窗口的“1.9.x 兼容工具”页。

## 云端与旧版入口

图形发布器生成 `releases/<releaseSequence>/`、`channel/stable/mods-v4.txt`、`legacy/1.9/mods-v4.txt`、`legacy/1.6/mods.txt`、`client-modsync.properties` 与 `LEGACY-ENDPOINT-MAP.txt`。

默认发布序号在点击导出时根据当前系统时间刷新，格式为 `yyyyMMddHHmmssSSS`，例如 `20260818153045123`。同一次导出生成的旧 1.9.x v4 网关也使用这个数字作为 `catalog-version`，因此新旧入口共享一个发布顺序。它是防降级排序键，不是展示版本；发布机器的日期和时间必须正确。若要重放已签核项目，可在 GUI 关闭自动刷新并保留原序号。

注意：`legacy/...` 是本地交付布局，不是旧客户端会自动发现的新地址。发布者必须在 GUI 填写当前 1.9.x 与 1.6.x/1.7.x 客户端已经使用的全部旧 URL，然后将生成的网关文件覆盖到这些原 URL，或者在原 URL 配置 HTTP 重定向。历史入口允许保留已经部署的 HTTP 或 HTTPS 地址；新的 2.0 稳定根地址仍强制 HTTPS。只上传到新 `legacy/` URL 无法升级已安装的旧客户端。

稳定 2.0 入口保留 `mods-v4.txt` 文件名，但内容为 schema-v5 JSON。这是为了让 1.9.x 配置引导器允许该 URL；MCSync 2.0 会按内容识别 v5。上传顺序必须是：先上传不可变 `releases/`，再部署旧网关，最后原子切换 `channel/stable/mods-v4.txt`。

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
