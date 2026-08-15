# To-do（按优先级）

## P0：首发前必须完成

- [ ] 用本交接包中的修正 staging + Candidate14-r3 + `p0-additions` 重新组装全新 server/client；不要复用任何旧 runtime。
- [ ] 服务端和客户端同时安装 Create carriage orientation guard，并核对相同 SHA-256。
- [ ] 运行两轮服务端重启 + 高权限真实玩家入服；重点到列车坐标 `(-99,63,-98)`，观察 carriage/controls/HUD，无 Render thread FATAL。
- [ ] 验证服务端根目录有 `immersive_paintings_cache`，87 幅画均能由空客户端缓存按需下载并显示。
- [ ] 首轮允许并完整记录精确的旧 recipe-book 自清理集合；第二轮必须归零。任何新 ID、格式漂移或其它 ServerRecipeBook ERROR 仍 NO_GO。
- [ ] 对 server/client 日志执行严格 FATAL/ERROR 分类；未知错误 fail-closed。
- [ ] 人工测试完成后生成新的 READY/release-lock、服务端/客户端 manifest 和回滚快照。

## P1：首发后通过版本化服务端迁移或 BOTH-side OTA

- [ ] Netherite horse armor 完整玩法/模型/配方适配；在此之前 Deferred Content Protection 必须阻止丢弃、加工和错误穿戴，但允许安全容器存储。
- [ ] 剩余延迟物品、玩法与贴图适配；每项使用稳定 ID、sidecar/ledger、输入 SHA、幂等 marker、快照与回滚。
- [ ] Create potion fluid 的 108:1 专用换算和小误差政策继续做实机验证；不得把普通 81:1 无条件套到 potion。
- [ ] 修复/审计本地资源包剩余 1.21.11 专属 blockstate/model 差异。
- [ ] 完成 MCModSync 的受控 HTTPS、URL 绑定 Config.jar、完整 v4 manifest、重定向/哈希审计、离线失败策略和两次 Prism 金丝雀；未完成前不要把裸 MCModSync 放进唯一可运行客户端。

## 工程与审计

- [ ] 把新的 P0 JAR 纳入下一版动态 release builder；模组数量是版本快照，不是永久 allowlist/上限。
- [ ] 在新的转换输入到达时，从原始 ZIP 重新跑全量只读预审计；不要从旧候选 runtime 反推源语义。
- [ ] 完成 C/D 盘历史产物审计后，仅保留：原始输入、当前唯一 staging、当前 release、源码/工具、关键报告、人工证据和最终交接包。
- [ ] 删除操作必须等用户审核清单后执行，本交接任务不自动删除任何历史文件。
