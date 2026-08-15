# 外部制品策略

Git 只保存源代码和小型文本证据。以下内容必须留在仓库外：

- 世界、区块、实体、POI、玩家数据和 SavedData；
- NeoForge/Minecraft libraries、客户端实例、模组 JAR；
- 整合包 ZIP/7z、资源包、Xaero/JourneyMap 缓存；
- logs、crash-reports、Gradle build/cache。

外部制品用绝对路径、文件大小、SHA-256 和用途登记在
artifacts/EXTERNAL-ARTIFACTS.md。路径失效时不得自动下载或替换。
