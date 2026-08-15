# 工作流架构

    权威快照 A
       | 只读审计 / 哈希锁
       v
    隔离 staging B --转换器/适配层--> disposable runtime
       |                                  |
       +--------- reports + receipt <-----+
                         |
                    停服 CAS OTA
                         v
                    生产快照 C

## 层次

1. 输入层：原始 ZIP、停服快照、V 参考世界。只读，不从运行过的目录反推源数据。
2. 转换层：outputs/tools/convert_*.py 和 projects/ports/ 中的适配源码。
3. 验证层：三方 NBT/物品/地形审计、schema 校验、CRC/SHA、负例测试。
4. 发布层：对象级 CAS OTA、preimage/postimage、receipt、rollback。
5. 客户端层：Prism、资源地图、客户端模组只作为外部制品，不进入世界 OTA。

保险柜、储罐、漏斗过滤器等内容使用对象级 CAS；整区块或整 region 覆盖默认禁止。
冲突时保留 C 的当前内容并登记，不静默覆盖。
