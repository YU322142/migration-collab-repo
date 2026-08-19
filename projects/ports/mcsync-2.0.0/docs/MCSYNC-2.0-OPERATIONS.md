# MCSync 2.0 操作简表

## 发布者流程

1. 运行 `java -jar MCSync-2.0.0.jar`，在默认打开的“2.0 OTA 发布”页选择已验证客户端的游戏根目录。
2. 在“文件与来源”扫描安全内容目录。发布器只对直接位于 `mods/` 的 Mod JAR 做精确匹配：先批量查询 Modrinth SHA-512，再查询 CurseForge fingerprint；匹配不到才回退为本地托管文件。
   - 只想沿用上一版的中英文描述和必须/推荐设置时，在“Mods”页使用“从 mods-v5.json 导入模组信息”。该操作只重建 Mods 表，不修改其他文件、受管范围、配置 OTA、服务器列表或远端地址。
   - 当前所选客户端的 `mods/` 是权威状态：已经删除的 Mod 不会被旧 JSON 恢复；新加入的 Mod 保留本地扫描默认值；升级后改名的 JAR 仅在 `modId` 唯一时继承旧描述。重复或歧义身份不会猜测匹配。
   - 导入后下载来源会按当前 JAR 重新匹配，旧清单中的哈希、URL 和平台文件 ID 不会直接复用；人工维护的中文描述不会被平台英文覆盖。
3. 资源包、光影、KubeJS、TACZ、女仆模型包和配置等非 Mod 文件始终使用 `publisher-hosted + redistributable`，不会查询模组站，也不展示无意义的分发政策选择。安全扫描会把 `tacz/`、`tlm_custom_pack/` 纳入独立受管范围；Mod JAR 内置的默认包仍不重复同步。
4. 中国镜像只是候选传输端点，必须同时保留官方端点；两者最终都以清单中的大小和 SHA-256 为准。
5. CurseForge 的 API key 只在发布者本机通过 `MCSYNC_CURSEFORGE_API_KEY` 或 JVM system property 提供。发布完成后清单只保存固定文件 URL，不保存 key。
6. 在“配置 OTA”按文件、配置键、旧值前像、目标值、作用端和冲突策略添加统一修复；不必整份覆盖配置。
7. 如需统一服务器入口，在“远端与旧版升级”选择测试客户端的 `servers.dat`。发布器会生成独立 `serverlist.txt`，客户端按所有权台账合并，不删除玩家自行添加的服务器。
8. 在“验证与导出”选择空输出目录并导出。工具生成不可变版本清单、正式 `mods-v5.json`、可再分发文件和本地审计报告。

命令行 `--v5-template` / `--publish-v5` 仍保留，用于 CI 和自动发布；普通发布不再要求人工编写 JSON。旧 v4 模组清单、资源包和服务器列表工具位于主窗口的“1.9.x 兼容工具”页。

## 云端与旧版入口

图形发布器生成 `releases/<releaseSequence>/`、`channel/stable/mods-v5.json`、`legacy/1.9/mods-v4.txt`、`legacy/1.6/mods.txt` 与 `client-modsync.properties`。启用服务器列表同步时还会生成 `server-list/serverlist.txt` 和同级 `servers.dat`，并把对应 URL 写入客户端配置模板。旧版地址不需要填写进项目；发布器只导出需要部署到旧地址的升级材料。

默认发布序号在点击导出时根据当前系统时间刷新，格式为 `yyyyMMddHHmmssSSS`，例如 `20260818153045123`。同一次导出生成的旧 1.9.x v4 网关也使用这个数字作为 `catalog-version`，因此新旧入口共享一个发布顺序。它是防降级排序键，不是展示版本；发布机器的日期和时间必须正确。若要重放已签核项目，可在 GUI 关闭自动刷新并保留原序号。

注意：`legacy/...` 是需要复制到旧版地址的交付材料，不是旧客户端会自动发现的新地址。发布器不记录旧地址，也不要求联网探测旧地址；部署者按自己的旧版地址把对应材料覆盖或发布即可。新的 2.0 稳定入口独立使用 HTTPS 的 `mods-v5.json`。

新版稳定入口使用真实的 `channel/stable/mods-v5.json`。上传顺序为：先上传不可变 `releases/`，再上传可选的 `server-list/`，最后原子替换新版 JSON；如果要支持旧版，再把 `legacy/` 下的升级材料复制到你维护的旧地址。新版客户端不会读取旧版目录。

## 客户端启动流程

- 1.9.x 先通过旧 v2/v4 永久入口升级到 MCSync 2.0。
- 自动下载默认最多并行 128 个文件；实际线程数不会超过待下载文件数。可用 `-Dmcsync.downloadThreads=N` 将并发下调，范围为 1–128。平台识别使用批量 API，不按此线程数轰炸模组站。
- NeoForge 在现有 Minecraft 窗口标题显示检查、下载、校验和“需要重启”；不创建第二个更新窗口。
- 文件、KubeJS、注册表资源或配置发生变化时，MCSync 停止本次启动；隐藏 helper 在 JVM 退出后提交并等待下一次启动。
- 同一发布序号下，文件被玩家改坏会重新修复；清单序号不会降低，清单分叉会阻断。
- `first-install` 文件（例如 `options.txt`）已有时保持玩家版本；世界、地图、区块、实体、POI、gamerule、缓存和凭据永远不进入 OTA。

## 出错处置

- 出现 `RECOVERY_REQUIRED.txt` 时不要手工删除，先保留 `.modsync/transactions/` 和备份，确认回执后再处理。
- 网络失败、镜像哈希错误、配置冲突、路径越界、旧 SHA 不符均是 fail-closed，不会半提交。
- 游戏必须重启才能消费 Mod/JAR/注册表变更；MCSync 不宣称热替换。
