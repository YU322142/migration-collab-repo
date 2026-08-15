# P0 制品状态说明

## Create carriage orientation

- 源码：`outputs/projects/create-carriage-orientation-guard-neoforge/`
- 已有 D 盘构建证据：`D:\Trans\migration-audit-work\handoff-create-carriage-orientation-guard-20260812\build1-create-carriage-orientation-guard.jar`
- 已知构建证据 SHA-256：`C38D9E569D4F2FB84A2DC570CF170D610ADEDFAFAAEFE655E9198157A0BE82B0`
- 当前状态：`BUILD_EVIDENCE_ONLY_REQUIRES_FINAL_REBUILD`。按用户要求，本交接任务不再继续修复或构建；后续人员自行处理。
- 原因：本轮离线重建第一次选用了错误 Gradle 工作目录；第二次在线插件解析未在当前会话产出终态 JAR。交接者必须在 D 盘可联网 Gradle 环境中执行两次 `clean check jar`，逐字节比较 SHA，再把结果加入下一版动态 release-lock。
- 该兼容件是 BOTH-side；服务端和客户端必须安装相同 SHA。它只对非法/垂直 carriage orientation 做只读水平回退，不改世界 NBT。

## Immersive Paintings

- 已完成严格源审计：87 索引、174 PNG、原图/缩略图全部存在且 PNG 有效。
- 缓存必须与 `world/data/immersive_paintings.dat` 同级部署在服务端游戏根目录；不要把玩家私图作为 MCModSync 客户端 OTA 内容。
- 客户端缓存可以为空，由服务端按需发送。

## 交接原则

任何“待重建/待重锁”的制品都只放在 `p0-additions` 或源码区，不修改 Candidate14-r3 的 READY、manifest、生产配置或原始输入。

Candidate14-r3 Attempt 3 的自动双轮门禁报告是 PASS，但之后人工测试出现了新的 Create carriage 渲染崩溃。交接结论以较新的人工失败为准：`HANDOFF_ONLY_NOT_PRODUCTION_GO`。
