# 当前状态

状态：DEVELOPMENT / NOT_PRODUCTION_GO

目标运行时：Minecraft 1.21.1 + NeoForge 21.1.241。原始输入是
1.21.11 服务端快照；当前最新测试输入为：

- D:\Down\mechanomania-matched-runtime-attempt13-2.zip
- SHA-256 ECCD0C6D28A9444DBBCEB3AAEDBBB882E3EEF82B4DDD2547C729571F21891A92

## 已整理

- 世界转换、三方物品审计、保险柜/储罐对象级 OTA 和回滚工具；
- 保护区地形、POI、实体 CAS 工具；
- 544 高度兼容模组与高度 overlay；
- CEI、TrueUUID、XiyusLogin、Cookery、WorldEdit 等适配源代码；
- JourneyMap 到 Xaero 转换器及验证；
- MineAstr 0.6.27 候选（服务端和客户端配对时使用）；
- MCModSync 资料保留但全局禁用，服务端不安装。

## 当前硬门禁

- 生产世界不能整区块覆盖；冲突对象以当前服务器状态为准。
- 远端公测世界的正式 OTA 必须重新停服取快照并重算 CAS。
- 主世界原版高度/群系保护与 Tectonic 同世界无断崖过渡仍需动态门禁；
  安全 fallback 是主世界原版、Tectonic 仅在独立 frontier。
- 任何动态启动通过只能针对明确标记的 disposable clone，不能自动升级为生产 GO。
