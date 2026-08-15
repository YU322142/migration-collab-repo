# 未打包的历史候选与证据

下列目录类别没有复制进交接包。它们仍留在原位置，等待后续全盘审计；本文件只说明用途和复用禁令。

## 禁止作为转换输入

- `D:\Trans\migration-audit-work\manual-test-*`
- `D:\Trans\migration-audit-work\final-fullstack-smoke-*`
- `D:\Trans\migration-audit-work\world-migration-smoke*`
- `D:\Trans\migration-audit-work\*fullstack-smoke*`
- `D:\Trans\migration-audit-work\client-gate-*`
- `D:\Trans\migration-audit-work\candidate*-artifacts-*`

这些目录曾启动 Java、保存世界、执行玩家登录或被失败门禁写入 attempt marker。目标版本运行时可能已经丢弃无法解码的字段；即使它们“看起来能启动”，也不能反向作为数据转换基线。

## 被后续版本淘汰的 staging / release

- `cutover-staging-final*`
- `cutover-staging-candidate8*`
- `final-mod-bundles-candidate9*` 至 Candidate14-r2
- `final-server-mods-candidate*` / `final-client-mods-candidate*`

其功能由本包的唯一转换结果和 Candidate14-r3 快照取代。旧 READY/manifest/report 可用于历史追溯，但旧世界和旧模组目录不应继续发布。

## 工具缓存、反编译与测试夹具

- `gradle-cache*`, `gradle-home*`, `pip-cache`, `python-packages`, `anvildeps`
- `decompiled`, `*-decompile*`, `*-unpacked*`, `jar-inspect`
- `tmp*`, `temp`, `test-temp`, `*-fixture*`, `pycache-*`, `__pycache__`

这些不是业务数据。交接包保留源码、构建脚本、锁定 JAR 和必要报告，不复制依赖缓存及中间 class 文件。

## 关键失败证据（摘要已入包）

- Candidate8j chute/void_air：Create 6.0.10 客户端区块卸载竞态；由 chute guard 处理，禁止删除 181 个 chute。
- Candidate11/13 TrialSpawner `Not a map`：已由 8,398 条配置转换修复。
- Candidate13 Scarecrow `Slot 1 not in valid range`：由 legacy container compat 修复。
- Candidate14 首次 gate 62 条 stale recipe：客户端已成功入服，门禁主动停止；精确集合首轮可审计自清理，第二轮必须归零。
- Candidate14 人工崩溃：Create carriage `InitialOrientation=down` 的渲染崩溃；本包已修数据并附 runtime guard 源码/构建证据。
- 沉浸画框不显示：`immersive_paintings_cache` 被旧复制白名单遗漏；本包已恢复 87 原图 + 87 缩略图。

## 删除政策

本次打包不删除任何历史目录。后续全盘审计会按 `KEEP / DELETE_AFTER_REVIEW / MANUAL_REVIEW` 分类并给出精确字节数；只有用户审核后才能执行删除。
