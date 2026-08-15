# 测试矩阵

| 范围 | 工具/测试 | 当前证据 |
|---|---|---|
| 仓库安全 | tools/repository/check_repository.py | 必须 PASS |
| 世界 NBT | outputs/tools/test_convert_world_nbt.py | 本地单元测试 |
| 存储 OTA | outputs/tools/test_create_storage_object_ota.py | 对象级 CAS/回滚 |
| 保护区地形 | outputs/tools/test_protected_zone_terrain_ota.py | 13/13 |
| 保护区实体 | outputs/tools/test_protected_zone_entity_ota.py | 13/13 |
| 高度图 | outputs/projects/heightmap-384-to-544-compat-neoforge | 双构建一致 |
| 登录 | XiyusLogin/TrueUUID 测试脚本 | disposable clone only |
| 地图 | outputs/tools/test_convert_journeymap_to_xaero.py | 静态转换验证 |

测试通过不代表生产 GO；每次发布都要绑定具体输入快照和 receipt。
