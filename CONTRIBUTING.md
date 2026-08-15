# 协作约定

## 分支与提交

- 本仓库是本地 Git；不要添加 GitHub 或公网 remote。
- main 只接收经过测试的源代码和文档。
- 每个修复使用独立分支或 worktree，提交信息包含范围和验证结果。
- 不提交运行时目录；把外部输入写进 artifacts/EXTERNAL-ARTIFACTS.md。

## 修改前

1. 阅读 docs/STATUS.md 和相关 runbook。
2. 确认输入快照路径与 SHA-256。
3. 为 destructive/OTA 工作建立 detached staging。
4. 先运行 dry-run/preflight；失败时保持 fail-closed。

## 修改后

    python tools/repository/check_repository.py
    python tools/repository/refresh_repository_manifest.py
    git diff --check
    git status --short

把测试命令、输入哈希、输出 receipt 和已知限制写入提交说明或对应报告。
