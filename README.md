# Minecraft 1.21.11 -> NeoForge 1.21.1 migration collaboration repository

这是一个本地 Git 协作仓库，不连接 GitHub，也不是可直接启动的发布包。
这里保存可复现的转换脚本、适配模组源代码、OTA 工具、测试和决策文档；
运行中的服务器、客户端、世界存档和构建产物留在仓库外。

当前状态：DEVELOPMENT / NOT_PRODUCTION_GO

## 快速开始

    git clone <本机共享路径> migration-collab-repo
    cd migration-collab-repo
    python -m pip install -r requirements-test.txt
    python tools/repository/check_repository.py
    python tools/repository/stage_manifest_files.py --verify-only

修改文件并准备提交时，再按 `docs/REPOSITORY-OPERATIONS.md` 的顺序刷新清单、
安全检查和白名单暂存。

协作者先阅读：

1. docs/STATUS.md
2. docs/ARCHITECTURE.md
3. docs/MODULE-CATALOG.md
4. docs/MODULE-INTERNAL-REFACTOR-MAP.md
5. docs/MODULE-FILE-INDEX.md
6. docs/SCRIPT-DOMAIN-CATALOG.md
7. docs/REPOSITORY-OPERATIONS.md
8. docs/ARTIFACT-POLICY.md
9. docs/KNOWN-ISSUES.md

## 目录

- outputs/tools/：世界转换、三方审计、对象级 OTA、门禁和测试脚本。
- outputs/projects/：当前工作区的小型 NeoForge/诊断工程。
- projects/ports/：较大的模组移植和兼容层源代码。
- projects/patches/：最小补丁及其验证脚本。
- pack/：脱敏后的客户端/服务端配置与 KubeJS 模板。
- docs/：架构、状态、流程、测试矩阵和风险记录。
- reports/：可审计的小型报告；大报告和世界快照只保留外部索引。
- artifacts/：外部制品路径、大小、SHA-256 和用途索引，不含 JAR/ZIP/世界本体。

## 明确边界

- 不把 .mca、NBT、玩家数据、Prism 实例、日志、JAR、ZIP、构建缓存或认证配置提交到 Git。
- MCModSync 目前全局禁用；仓库中的 catalog 仅作格式研究，服务端绝不安装。
- 任何生产 OTA 都必须在停服快照上执行，先 dry-run，再 CAS apply，并留下 receipt 与 rollback。
- 保护区 (10192,-1574) 的核心半径 1000、冻结半径 1536 以及 544 高度过渡规则见 docs/。

外部大制品请查阅 artifacts/EXTERNAL-ARTIFACTS.md。
