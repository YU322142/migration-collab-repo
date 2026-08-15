# Candidate14-r3 已知错误族 OTA 覆盖矩阵

这份矩阵是主契约的补充，专门覆盖审计文档中出现过的非致命警告、已修复资源问题和供应链门禁。它避免把“警告”遗漏在“只修 P0”的第一版范围之外。

文件：`outputs/candidate14-ota-error-family-coverage-20260812.json`

## 如何理解“可 OTA 处理”

这里的 OTA 是版本化发布流程，不等于 MCModSync 能在不停服时修改一切：

- 客户端资源、字体、模型、声音和渲染兼容层：客户端退出后由 MCModSync 更新；
- 双端 Java/注册表/协议兼容：服务端短暂停机，客户端退出后同步配对 JAR；
- 世界、玩家、配方书、进度、地图、数据包和配置迁移：停服后由服务器版本/数据修复执行，配合快照、sidecar 和幂等标记；
- 外部网络或认证依赖：可以有版本化配置/模组路线，但不能承诺只靠 MCModSync 消除外部故障。

因此矩阵中每一条都有 `route_class`、`mcmodsync_alone`、`external_dependency`、`requires_client_exit`、`requires_server_short_shutdown` 和 `startup_blocker`。

## 覆盖内容

当前矩阵收录 15 个错误族：

- 客户端资源/渲染：缺失声音、动画帧、重复字体码点、shader uniform/sampler、版本检查超时；
- 双端/服务端运行：Content Backport creative-tab fallback、ConfigTracker 生命周期警告、语音聊天离线加密、Connector locator、可选 Mixin、停服时 tick 症状、Kaleidoscope stale GLM、Create optional DataMap；
- 服务器数据/资源修复：旧 datapack ID、Bukkit pack format、Moon transfer permission；
- OTA 供应链：HTTPS、Config.jar、v4 清单、哈希/重定向、回滚与 canary。

主契约中的 14 个重点错误仍然保留逐对象稳定 ID、ledger/sidecar、依赖版本、幂等和回滚要求；本矩阵对资源/警告类提供族级兜底。任何新日志模式不属于这两个文件时，都必须先补充分类，门禁保持 `NO_GO`。

## 明确不属于独立错误的事项

`syncResourcePacks=false`、`syncServerList=false` 是防呆策略，不是待修故障；用户本地资源包和服务器列表不能被 OTA 覆盖。入服后断线是测试观察结果，必须追溯到真正的底层错误，不得用“断线”作为宽泛 allowlist。

## 供应链边界

MCModSync 1.9.1 只负责客户端文件事务、哈希校验和备份回滚。它不能热替换服务端 Java、执行世界 NBT 迁移或把未签名清单变成可信签名。正式上线仍需要：

1. 受控 HTTPS origin；
2. 对象先上传、逐个外部 GET/长度/SHA-256/MD5 验证；
3. `mods-v4.txt` 最后发布；
4. 独立 catalog SHA-256（未来可再加签名）；
5. Prism 首次退出更新、第二次启动入服、渲染和重启 canary；
6. 失败时 `STARTUP_BLOCKED`/`RECOVERY_REQUIRED` 阻断并保留旧 catalog/备份。

这保证后续每次新增、升级或移除模组都能走同一条可回滚、可审计的 OTA 路径，而不会把当前 54 个 JAR 数量误当永久上限。
