# Repository validation snapshot — 2026-08-15

Python test dependencies are pinned in `requirements-test.txt`; install them
inside a local virtual environment, and do not commit that environment or its
download cache.

在发布为本地 Git 仓库前完成：

| 范围 | 结果 |
|---|---|
| repository safety scan | PASS |
| create storage object OTA | 9/9 PASS |
| protected terrain OTA | 13/13 PASS |
| protected entity OTA | 13 tests PASS；6 个需要外部 bundle 的集成用例按设计跳过 |
| 544-height overlay validator | 10/10 PASS |
| JourneyMap to Xaero | 13/13 PASS |
| world NBT converter | 112 tests PASS；1 个未提交私有 trial-spawner fixture 按设计跳过 |

world NBT 测试需要外部 Python nbt 包。本机验证使用：

    PYTHONPATH=D:\Trans\migration-audit-work\poi-nbtdeps

地图转换测试使用 Codex bundled Python（包含 NumPy/Pillow）。这些依赖不复制进 Git。

安全处理：

- 已移除真实玩家名、UUID 和个人工作区绝对路径；
- 已排除 XiyusLogin 玩家数据库、OP/白名单、server.properties 和凭据；
- JAR 仅允许 Gradle wrapper；
- MCModSync 资料标记为 disabled，不进入 active runtime。
