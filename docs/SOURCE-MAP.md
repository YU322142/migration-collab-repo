# Source map

详细、机器可读的复制记录在 docs/SOURCE-MAP.json。

源路径使用以下占位符，避免把个人用户目录写入 Git：

- WORKSPACE：当前 Codex 工作区；
- AUDIT_ROOT：<AUDIT_ROOT>；
- HANDOFF_ROOT：<HANDOFF_ROOT>。

复制策略：

- 保留源码、资源、Gradle 配置、测试和可复现补丁；
- 排除 build、.gradle、run、logs、世界、玩家数据和编译产物；
- Gradle wrapper JAR 是唯一允许进入仓库的 JAR；
- source_git_dirty 记录复制时源树是否有未提交改动，不代表本仓库状态。
