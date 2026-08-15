# 协作仓库操作手册

## 新任务

1. 从 artifacts/EXTERNAL-ARTIFACTS.md 选择明确输入，并核对 SHA-256。
2. 新建分支或 worktree；不要直接在 main 上改生产路径。
3. 先运行只读审计，输出 JSON/MD 和校验哈希。
4. 需要写世界时，复制到新的 disposable staging；生产服必须停机并确认。
5. 对每个对象做 preimage CAS；冲突保留当前内容，不能用 region 覆盖绕过。
6. 动态验证只允许使用 disposable clone；完成后留下日志摘要，删除临时运行目录。

## 交接清单

- 输入路径与 SHA-256；
- 变更文件列表；
- 测试命令与结果；
- receipt、postverify、rollback 路径；
- 未解决风险和下一步；
- 是否触碰 world、Java、远端服务器（默认必须是“否”）。

## 本地 Git

    git remote -v
    git status --short
    python tools/repository/refresh_repository_manifest.py
    python tools/repository/check_repository.py
    python tools/repository/stage_manifest_files.py --include-manifest
    python tools/repository/stage_manifest_files.py --verify-only
    git diff --cached --check
    git commit -m "docs: update migration collaboration snapshot"

不要用普通的 `git add .` 代替清单暂存：导入的上游源码含有嵌套
`.gitignore`，普通暂存可能静默漏掉源码或资源。清单暂存只会强制加入
`repository-manifest.json` 中已通过安全检查的文件。

`git remote -v` 应为空。不要把真实账号、服务器地址或 RCON 密码写入提交信息。
