# 已知问题与限制

- 同主世界高度过渡：544 高度 overlay 可静态验证，但 Tectonic 与原版 noise
  在同一 overworld 的无断崖自然过渡仍是 BLOCKED。
- 保护区：最新 C 的 29,305 个目标 chunk 可用槽位级 OTA；远端继续变化后必须
  重新生成锁和 preimage。
- 存储迁移：保险柜、储罐、黄铜漏斗缺少时不可用整区块覆盖；冲突以 C 为准。
- MineAstr：服务端 active TOML 必须 enabled=true，客户端/服务端版本应统一；
  CHANGE_ME_LOCAL_ONLY 只可出现在本地模板。
- MCModSync：目前全局不使用，避免降级或错误覆盖模组。
- 女仆换模型：C6C 的 dedicated-server 平衡开关默认禁止，这是原包设计，不应
  被普通兼容修复悄悄改变。
- Xaero：地图缓存按服务器身份分目录；测试 loopback 与正式地址不是同一节点。
