# XiyusLogin 自动会话配置 OTA（2026-08-15）

## 结论

当前服务端的 `XiyusLogin 1.4-migration4` 已有“同一用户名 + 同一 IP”会话功能，但配置为：

```toml
enableIpSession = false
ipSessionDurationSeconds = 300
```

因此每次重进都会再次要求 `/login`。本 OTA 只把这两个值改为：

```toml
enableIpSession = true
ipSessionDurationSeconds = 86400
```

`86400` 秒（24 小时）是当前模组允许的上限。

## 安全边界

- 不改动 TrueUUID 配置、注册表、玩家密码数据或任何令牌。
- 写入前强制检查 TrueUUID 的三项保护仍为：
  - `knownPremiumDenyOffline = true`
  - `allowOfflineForUnknownOnly = true`
  - `allowOfflineOnTimeout = false`
- 只改 `config/xiyuslogin-common.toml` 中恰好两个键；键缺失或重复时拒绝写入。
- 写入前备份，写后校验 SHA-256；支持按回执进行 CAS 回滚。
- 写入要求服务端已停止，并显式传入 `-ConfirmServerStopped`。

## 重要限制

`XiyusLogin 1.4-migration4` 的 IP 会话仅保存在服务端内存中。部署后：

1. 服务端每次重启后，玩家仍需先手动 `/login` 一次；
2. 之后在 24 小时内、同一用户名且同一 IP 重连，会自动恢复登录；
3. 服务端再次重启或公网 IP 改变后，需要重新输入一次密码。

这能立即解决“短线重连也反复登录”，但还不是完整的“TrueUUID 正版验证成功即自动登录”。完整方案应让 XiyusLogin 订阅 TrueUUID 1.2.1 的公开 `TrueuuidApi.registerLoginCallback`，且只在回调状态 `status.isPremium()` 为真时放行。不能仅凭 `trueuuid-registry.json` 中存在名字就放行，因为“曾经验证过”不等于“本次连接已验证”。

## 部署（远端 Windows 服务端）

先把 `deploy_xiyuslogin_auto_session.ps1` 放到远端任意工具目录。下面的 `D:\MinecraftServer` 替换成远端实际服务端根目录。

只读预检：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy_xiyuslogin_auto_session.ps1 `
  -ServerRoot 'D:\MinecraftServer' `
  -DurationSeconds 86400
```

停止服务端后应用：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy_xiyuslogin_auto_session.ps1 `
  -ServerRoot 'D:\MinecraftServer' `
  -DurationSeconds 86400 `
  -Apply `
  -ConfirmServerStopped
```

重启服务端后做静态校验：

```powershell
powershell -ExecutionPolicy Bypass -File .\verify_xiyuslogin_auto_session.ps1 `
  -ServerRoot 'D:\MinecraftServer' `
  -DurationSeconds 86400
```

完成一次“手动登录 → 退出 → 重进”后检查运行证据：

```powershell
powershell -ExecutionPolicy Bypass -File .\verify_xiyuslogin_auto_session.ps1 `
  -ServerRoot 'D:\MinecraftServer' `
  -DurationSeconds 86400 `
  -CheckLatestLog
```

日志应出现 `Restored IP session for player`。校验脚本只报告是否观察到证据，不输出 IP、密码或令牌。

## 回滚

应用结果会给出 `receiptPath`。停止服务端后执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy_xiyuslogin_auto_session.ps1 `
  -ServerRoot 'D:\MinecraftServer' `
  -RollbackReceipt 'D:\MinecraftServer\ota-backups\xiyuslogin-auto-session-<时间>\receipt.json' `
  -ConfirmServerStopped
```

如果目标配置在应用后被其他人或程序改过，CAS 回滚会拒绝覆盖，避免抹掉协作者的修改。
