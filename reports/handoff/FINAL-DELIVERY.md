# Minecraft 迁移交付总览

日期：2026-08-13

## 最终交接归档

- 归档：`<HANDOFF_ROOT>.7z`
- 大小：15,372,562,055 bytes
- SHA-256：`28594C4A05AC64D92E8B10D9132FC7CB255DA72B7B483A3D679A806E8F6BB1FA`
- 7z 完整性测试：`PASS / Everything is Ok`
- 归档内：2,440 个目录、20,325 个物理文件、解压总大小 19,837,615,729 bytes
- 逐文件内容清单：20,322 行，聚合 SHA-256 `E180CFE1E912458A8A995D4B685FD1FA1F79FEB96A1B9EA7A5DA1C5EB19B7289`

外部权威验证文件：

- `<HANDOFF_ROOT>.7z.sha256.txt`
- `<HANDOFF_ROOT>.archive-status.json`
- `<HANDOFF_ROOT>.test.log`

包内 `PACKAGE-STATUS.json` 在封存时写为 `PUBLISHED_PENDING_ARCHIVE`；随后完成的外部 `archive-status.json` 才是最终归档验证结论，状态为 `PASS`。

## 交接状态

按用户要求，本轮已停止修复和构建，只交付文件、源码、脚本、报告与 TODO。

整体状态：`HANDOFF_ONLY_NOT_PRODUCTION_GO`。

Candidate14-r3 Attempt 3 自动双轮门禁曾 PASS，但之后人工测试仍发现 Create carriage 渲染崩溃；沉浸画框缓存已恢复到交接 staging。Create carriage 目录里的 JAR 仅是构建证据，状态为 `BUILD_EVIDENCE_ONLY_REQUIRES_FINAL_REBUILD`，不得直接当成正式发布件。

## 容量审计

- 完整机器报告：`<TRANS_ROOT>\migration-storage-audit-20260813.json`
- 审核清单：`<TRANS_ROOT>\migration-storage-review-20260813.json`
- 人读摘要：`<TRANS_ROOT>\migration-storage-review-20260813.md`

结论：不需要保留约 400GB 的历史候选世界。审核后预计可回收：

- D 盘迁移工作区：427,766,797,056 bytes（398.39 GiB）
- C 盘 `outputs\tmp`：6,587,137,384 bytes（6.13 GiB）

本轮没有执行任何删除。删除前必须先由接收方验证最终归档 SHA-256 和 7z 完整性测试，并严格按 JSON 中的精确路径逐项执行，禁止使用父目录或通配符递归删除。
