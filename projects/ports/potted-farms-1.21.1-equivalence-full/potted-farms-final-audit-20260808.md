# Potted Farms 1.21.11 -> NeoForge 1.21.1 最终等价审计

审计日期：2026-08-08  
范围：只读审计 `D:\Trans\20260807`；构建和运行测试仅位于 `D:\Trans\migration-audit-work`。未修改或部署生产目录。

## 结论

- **技术迁移 GO（有依赖条件）**：使用候选 3，并同时部署已锁定的 `backport-1.5.jar`。
- **候选 1/2 均不应发布**：候选 1 多一个无用 Manifest；候选 2 对 `Unbreaking > 10` 永不掉耐久，不完全等价于源 1.1.2。候选 3 已修复并通过运行回归。
- **生产世界 Potted Farms 玩家数据损失为 0**：全量实体区扫描发现 73 个原版展示框，但 0 个装斧展示框、0 套可工作的 Potted Farms 结构。世界里只有数据包自动生成的六个调度事件、计分板目标和六个阈值假玩家。
- **正式 1.21.1 / 1.1.1 旧存档兼容 GO**：候选 3 不新增/删除注册 ID，不改变 NBT、计分板名、storage 名或方块实体格式；相对正式 1.1.1 的 102 个实体文件中仅一个 mcfunction 内容变化。隔离旧存档升级、实际收获、保存和重启均通过。
- **公开发布暂为 NO-GO**：原包元数据声明 MIT、作者 Pepsied，但候选目前只是 D 盘本地二进制，尚未建立公开源码仓库/发布页，元数据版本仍显示 `1.1.1`。技术包可进入迁移候选集；对外开源前应补版本号、修改说明、MIT 归属和可复现构建/打包脚本。

## 锁定产物

| 产物 | SHA-256 | 状态 |
|---|---|---|
| 源 1.21.11 `potted-farms-1.1.2.jar` | `D4DFEE8E84F8353A9B512768F8280F33C09C9FD2C2E96BAD9B515D3472502D5D` | 只读基线 |
| 正式 NeoForge 1.21.1 `potted-farms-1.1.1.jar` | `BC086B39E630CE080B761A26AC4F1AFBF695A2568E7866C68602F526733DA281` | 旧存档基线，缺 Mending 玩法 |
| `equivalence1.jar` | `E0D26DE73F5646C21AD6D37C458E6F0B91F7DB6654355ABD9BF8E5467E140066` | 废弃 |
| `equivalence2.jar` | `A35D22ABCFF5CDAF001C58A0F0A3A1493EABA2685C6F5D3964D5C090957C0963` | 废弃：`Unbreaking > 10` 差异 |
| `potted-farms-1.1.1-equivalence3.jar` | `3E58A5C5CF33DE59DA08B175867C482CAD6D0BEBFAF5B07F6D5653646D74BA41` | **最终技术候选** |
| `backport-1.5.jar` | `167534C66D5E6C09DCB01152EBD37D18CED5CF6278A9228C094F937886133AF5` | Pale Oak 必需依赖 |

最终候选路径：

`D:\Trans\migration-audit-work\Potted-Farms-1.21.1-equivalence\potted-farms-1.1.1-equivalence3.jar`

## 静态等价证据

候选 3 与正式 1.1.1 都有 102 个实体文件。逐文件 SHA-256 比较只发现一个变化：

`data/potted_farms/function/take_unbreaking_damage.mcfunction`

正式文件内容哈希为 `7C5A916FDE3636A906F0ECD1B426DCCC4751F6DCDF4D6BB0D16A83B568AEF628`，候选 3 为 `3AB2D3E2DF438F5B61F880C03289BF2875C926E346F434615661C97A2970B795`。因此没有注册表、配方、掉落表、谓词、调度、计分板、资源或存档 schema 变化。

源 1.1.2 与候选 3 的文件比较结果：

- 源 101 个文件，候选 102 个文件；78 个字节完全一致。
- 18 个 `insert/*` 函数仅把 1.21.11 enchantment map 改写为 1.21.1 的 `.levels` 语法。
- `take_unbreaking_damage` 同时保留正式 1.1.1 的 Unbreakable 保护和源 1.1.2 的 Mending 保护。
- 源 1.1.2 对未匹配 1-9 的任意 Unbreaking 等级统一使用 `unbreaking_10`；候选 3 使用 1.21.1 `.levels` 路径恢复同一 catch-all 语义。
- 四个元数据文件只存在 1.1.2/1.1.1 版本字符串差异。
- 候选独有未被引用的 `loottest.mcfunction`，来自正式 1.1.1；它不参与调度或正常玩法。

36 个掉落表、10 个 Unbreaking 概率谓词、六个斧头耐久阈值和调度周期保持不变。Potted Farms 不注册自定义方块、物品、实体或方块实体，玩家农场状态全部由原版展示框、斧头物品组件、花盆和漏斗组成。

## 生产世界数据

全量只读报告：

`D:\Trans\migration-audit-work\Potted-Farms-1.21.1-equivalence\source-world-potted-farms-audit-20260808.json`  
SHA-256 `2A80EA10C7BE4811E10E86A378E2A9BEA1BB073E0939C1696EC1DF7D29F8F91B`

结果：

- 实体 region 解析失败：0。
- 原版 `minecraft:item_frame`：73。
- 装有六类斧头的展示框：0。
- 展示框下方漏斗 + 相邻盆栽 + 相邻定向漏斗的可工作结构：0。
- `level.dat` 中存在六个 `potted_farms:check_*` 调度和启用的数据包记录。
- `scoreboard.dat` 中存在 `potted_farms_damage`、六个阈值假玩家；这是数据包加载时生成的运行状态，不是玩家建造内容。

这里的“工作结构”严格按模组自身的选择器定义：斧头 `item_frame`、其下漏斗、相邻 `potted_*` 方块和定向漏斗必须同时满足。世界中即使有普通装饰花盆或玩家统计里的 `minecraft:potted_*` 记录，也属于原版花盆内容，不代表 Potted Farms 状态，且不会因本移植丢失。

扫描器已在已知夹具世界反证：识别到 2 个装斧展示框和 1 套可工作结构，0 个 region 失败。证据：

`D:\Trans\migration-audit-work\potted-farms-official-upgrade-smoke1\fixture-world-potted-farms-audit.json`  
SHA-256 `51B99530AA7D6A4C98FB70DEFC8E49DE8F3063399FCEF3DBD21843622E7CF44C`

扫描工具：

`<WORKSPACE>\outputs\tools\audit_potted_farms_world.py`

## 旧存档与运行测试

隔离服：NeoForge `21.1.241`、Minecraft `1.21.1`、Content Backport `1.5`。

正式 1.1.1 阶段创建并保存了一个真实农场夹具：

- 展示框 UUID `[I; 1297699617, -1986573549, -1175904634, -899242319]`，规范值 `4d59532189974b13b9e91e86ca66a6b1`。
- 坐标 `[100.5, 80.03125, 176.5]`。
- 铁斧含 Mending、Silk Touch 和持久化 damage；主漏斗预置 3 个钻石。
- 正式 1.1.1 的自动调度在停服前按其旧行为把 damage 从 17 增为 18，并产出 1 个橡木；这发生在替换候选之前，不是升级丢失。

升级后证据：

- UUID、坐标、斧头组件、3 个钻石、两个漏斗和盆栽全部保留。
- 候选收获后橡木持续增加，Mending 斧 damage 始终保持 18。
- 保存并第二次重启后 UUID/坐标/组件仍一致；橡木因正常自动调度继续增加，3 个钻石不变。
- 候选 3 对 `Unbreaking 11` 斧执行 200 次耐久函数后 damage 为 14，确认使用第 10 档概率；候选 2 的静态实现会保持 0。
- 候选 3 启动日志：ERROR 0、FATAL 0、Potted Farms 解析错误 0、`Done` 1；最终通过 RCON 正常停服，所有维度保存完成。

证据目录：

`D:\Trans\migration-audit-work\potted-farms-official-upgrade-smoke1`

关键文件：

- `official-fixture-rcon.txt`，SHA-256 `16F370909737E604C845DC7B6C794F8FB08CED03F714869205F4ACF8D3903D05`
- `candidate-first-start-rcon.txt`，SHA-256 `137EB6C63901980A662CB4F987A339594C121674A90ECFC44BE293A6FFFDEBE0`
- `candidate-second-start-rcon.txt`，SHA-256 `4A159CE19F906805C065A4B6E108957EA301BF48E7E2118D55EE89F1A38180D4`
- `candidate3-unbreaking11-rcon.txt`，SHA-256 `223DF3ED125CDAD34DDD34698DCA3C35292AF2D2138912F838530898C560C4F9`
- `candidate3.stdout.log`，SHA-256 `EC70CA3AF1AC413BF0BA03D5C3D1FC316FF5CF2724C0DEB80E2FD209C4F3556F`

## 部署条件与残余差异

1. 必须同时保留上述精确哈希的 `backport-1.5.jar`。没有它时 Pale Oak 两个掉落表、`insert/pale_oak` 和 `pots/pale_oak` 会因未知 ID 解析失败；带 Backport 时 Potted 相关错误为 0。
2. 候选没有在 mod metadata 中声明 Backport 的强依赖，最终整包 manifest/锁文件必须显式锁定，不能依赖人工记忆。
3. 该模组是服务端数据包逻辑，没有客户端 Java/UI；专服 smoke 覆盖其核心玩法。为保证客户端/服务端模组列表一致，可在两端分发同一 JAR，但客户端没有额外可见玩法需要图形烟测。
4. 候选 3 仍显示版本 `1.1.1`，并保留正式 1.1.1 的未引用 `loottest` 调试函数；两者不改变玩家核心玩法，但对外发布前应把版本标成明确的 1.1.2 等价移植版本并说明调试文件处理决定。
5. 本结论只批准 Potted Farms 组件进入最终整包候选；整包仍需用候选 3 做一次最终资源加载/重载和世界副本 smoke，不能据此单独批准整个迁移上线。
