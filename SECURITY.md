# 安全与隐私

本仓库只保存源代码和脱敏证据。禁止提交：

- 密码、BCrypt 哈希、API/RCON/TrueUUID token、私钥；
- 真实玩家名、UUID、IP、玩家数据、OP/白名单；
- server.properties、modsync.properties、运行日志和世界文件。

使用 CHANGE_ME_LOCAL_ONLY 或合成 fixture。需要真实值时，通过未跟踪的
examples/local/ 或环境变量注入，并在提交前运行：

    python tools/repository/check_repository.py

Patreon/sponsor caches are generated identity data. The Armor of the Ages
cache files in `pack/client-config/` and `pack/server-config/` remain empty
templates in Git; do not commit real supporter names or UUIDs.

如果误提交了凭据，先停用/轮换凭据，再从所有本地提交中清理；不要把秘密继续复制到备份或 issue。
