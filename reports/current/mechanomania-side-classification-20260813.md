# Mechanomania side 分类静态审计（2026-08-13）

状态：`PASS_STATIC_SIDE_CLASSIFICATION`。未知项数量：`0`。

这份报告只解决原合并矩阵中 11 个 side 元数据不完整的模组。它没有启动 Java/Minecraft、没有修改 release 或世界；结论来自本地 JAR 的 CRC/SHA、metadata、mixin 分区、class 常量池和反向依赖。静态通过后仍需专服启动和双轮真实客户端进服测试。

## 结论

| mod ID | 放置 | 服务端 | 客户端 | 选中 JAR | 证据门禁 |
|---|---:|:---:|:---:|---|:---:|
| `byepregen` | `BOTH` | 是 | 是 | `byepregen-1.0.7.jar` | `PASS` |
| `efficient_hashing` | `BOTH` | 是 | 是 | `efficient_hashing-neoforge-1.0.0+1.21.1-mod.jar` | `PASS` |
| `fastrecipesearch` | `BOTH` | 是 | 是 | `fastrecipesearch-1.21.1-26.2-neoforge.jar` | `PASS` |
| `hoporp` | `SERVER_ONLY` | 是 | 否 | `HopoBetterRuinedPortals-[1.21.1-1.21.3]-1.4.4b.jar` | `PASS` |
| `jecharacters` | `CLIENT_ONLY` | 否 | 是 | `jecharacters-1.21-neoforge-4.5.24.jar` | `PASS` |
| `mousetweaks` | `CLIENT_ONLY` | 否 | 是 | `MouseTweaks-neoforge-mc1.21-2.26.1.jar` | `PASS` |
| `mr_dungeons_andtavernsancientcityoverhaul` | `BOTH` | 是 | 是 | `DnT-ancient-city-overhaul-v2 [NeoForge].jar` | `PASS` |
| `mr_epic_structuresvillages` | `BOTH` | 是 | 是 | `Epic Villages 1.3.0 (1.21+).jar` | `PASS` |
| `mr_lukis_crazychambers` | `BOTH` | 是 | 是 | `lukis-crazy-chambers-1.0.2.jar` | `PASS` |
| `rhino` | `BOTH` | 是 | 是 | `rhino-2101.2.7-build.85.jar` | `PASS` |
| `yet_another_config_lib_v3` | `CLIENT_ONLY` | 否 | 是 | `yet_another_config_lib_v3-3.7.1+1.21.1-neoforge.jar` | `PASS` |

汇总：

- BOTH：7 个。
- SERVER_ONLY：1 个。
- CLIENT_ONLY：3 个。
- UNKNOWN_FAIL_CLOSED：0 个。

## 逐项依据

### `byepregen` — `BOTH`

Selected 1.0.7 has shared/server chunk-generation mixins and separately declared client resource/lighting mixins.

- JAR：`byepregen-1.0.7.jar`，SHA256 `12C90DA5BA9163202169CF7FDA6E765C8FD5F1E1C5E97D4350DE34366FD62E6D`，CRC `PASS`。
- 形态：class 184，data 0，assets 0，pure-data `False`。
- mixin：common 79，client 2，server 0。
- 字节码符号：client 4，server 16，shared-game 186。
- 反向依赖：0 条；证据门禁 `PASS`。

排除重复候选：`byepregen-1.0.0.jar`。

### `efficient_hashing` — `BOTH`

The sole common mixin targets shared Vec3i/BlockPos hashing code used independently on client and server.

- JAR：`efficient_hashing-neoforge-1.0.0+1.21.1-mod.jar`，SHA256 `76BB1BD93E211CFFAC01F2879E2E6B54BEE2B5884BC06BEDF0C21D89107AF5AD`，CRC `PASS`。
- 形态：class 5，data 0，assets 1，pure-data `False`。
- mixin：common 1，client 0，server 0。
- 字节码符号：client 0，server 0，shared-game 1。
- 反向依赖：0 条；证据门禁 `PASS`。

### `fastrecipesearch` — `BOTH`

Recipe indexing/synchronization patches common/server resource handling and a separate client packet listener.

- JAR：`fastrecipesearch-1.21.1-26.2-neoforge.jar`，SHA256 `E5944B8159EA7AE45E01C0D3FCBD6F75154B75336A35F01D4AC52F9B22D6CA81`，CRC `PASS`。
- 形态：class 11，data 0，assets 0，pure-data `False`。
- mixin：common 3，client 1，server 0。
- 字节码符号：client 3，server 0，shared-game 38。
- 反向依赖：0 条；证据门禁 `PASS`。

### `hoporp` — `SERVER_ONLY`

Pure data/world-generation pack with explicit IGNORE_SERVER_VERSION: the server consumes the gameplay data and the client copy may be omitted.

- JAR：`HopoBetterRuinedPortals-[1.21.1-1.21.3]-1.4.4b.jar`，SHA256 `C1E68C98EA538167CA7D4AC530C254E9D5DD400BEE408B0D72574B3C7F29E14B`，CRC `PASS`。
- 形态：class 0，data 154，assets 0，pure-data `True`。
- mixin：common 0，client 0，server 0。
- 字节码符号：client 0，server 0，shared-game 0。
- 反向依赖：0 条；证据门禁 `PASS`。

### `jecharacters` — `CLIENT_ONLY`

JEI/pinyin search integration hard-links client UI/search classes and has no server mixin or required server dependent.

- JAR：`jecharacters-1.21-neoforge-4.5.24.jar`，SHA256 `F7F2B4D9EC81BAD95BECA92C56444F87AA4A993DA80AB8DA184670BA7F879E83`，CRC `PASS`。
- 形态：class 25，data 0，assets 3，pure-data `False`。
- mixin：common 0，client 0，server 0。
- 字节码符号：client 6，server 0，shared-game 7。
- 反向依赖：0 条；证据门禁 `PASS`。

### `mousetweaks` — `CLIENT_ONLY`

Inventory screen input behavior is implemented entirely through client classes and a client-only screen mixin.

- JAR：`MouseTweaks-neoforge-mc1.21-2.26.1.jar`，SHA256 `68E6F4201C5DE97B77929A7215C9552495696CA6A3BF3AE4EACC34E135F6CC8B`，CRC `PASS`。
- 形态：class 22，data 0，assets 0，pure-data `False`。
- mixin：common 0，client 2，server 0。
- 字节码符号：client 27，server 0，shared-game 15。
- 反向依赖：0 条；证据门禁 `PASS`。

### `mr_dungeons_andtavernsancientcityoverhaul` — `BOTH`

Pure server-consumed gameplay data, but its NeoForge wrapper has no explicit missing-client/display-test exemption. Fail-closed bundle placement is BOTH until a dedicated-server/client handshake proves client omission safe.

- JAR：`DnT-ancient-city-overhaul-v2 [NeoForge].jar`，SHA256 `890882EC1239FFF1CD5CC5F1DA1FE4BE98A31E748D418220BEE5F2B9F3D8FD91`，CRC `PASS`。
- 形态：class 0，data 164，assets 0，pure-data `True`。
- mixin：common 0，client 0，server 0。
- 字节码符号：client 0，server 0，shared-game 0。
- 反向依赖：0 条；证据门禁 `PASS`。

### `mr_epic_structuresvillages` — `BOTH`

Pure server-consumed gameplay data, but its NeoForge wrapper has no explicit missing-client/display-test exemption. Fail-closed bundle placement is BOTH until a dedicated-server/client handshake proves client omission safe.

- JAR：`Epic Villages 1.3.0 (1.21+).jar`，SHA256 `0A49C689131AFFE588F0EB168873169DED54AC9F10B337410969D836E3DA32EB`，CRC `PASS`。
- 形态：class 0，data 161，assets 0，pure-data `True`。
- mixin：common 0，client 0，server 0。
- 字节码符号：client 0，server 0，shared-game 0。
- 反向依赖：0 条；证据门禁 `PASS`。

### `mr_lukis_crazychambers` — `BOTH`

Pure server-consumed gameplay data, but its NeoForge wrapper has no explicit missing-client/display-test exemption. Fail-closed bundle placement is BOTH until a dedicated-server/client handshake proves client omission safe.

- JAR：`lukis-crazy-chambers-1.0.2.jar`，SHA256 `59DDE0047528843664309B546A9FBD7AFA8A065472F6FEFD457FE6A40FAD23EF`，CRC `PASS`。
- 形态：class 0，data 81，assets 0，pure-data `True`。
- mixin：common 0，client 0，server 0。
- 字节码符号：client 0，server 0，shared-game 0。
- 反向依赖：0 条；证据门禁 `PASS`。

### `rhino` — `BOTH`

Rhino is the script runtime required by KubeJS on side BOTH; the library itself is side-neutral.

- JAR：`rhino-2101.2.7-build.85.jar`，SHA256 `95DF92CE578B2504CB16D8C9FC285303BF062EB15452246A18E57B7CF091C19A`，CRC `PASS`。
- 形态：class 346，data 0，assets 0，pure-data `False`。
- mixin：common 0，client 0，server 0。
- 字节码符号：client 0，server 0，shared-game 0。
- 反向依赖：1 条；证据门禁 `PASS`。

### `yet_another_config_lib_v3` — `CLIENT_ONLY`

YACL supplies configuration GUI/API code; all declared mixins are client-only and its only required reverse dependency is client-scoped.

- JAR：`yet_another_config_lib_v3-3.7.1+1.21.1-neoforge.jar`，SHA256 `673FECBFFAD26BB6D025FB5F60560CF6340E542BDF091D8D66074490515292F3`，CRC `PASS`。
- 形态：class 350，data 0，assets 29，pure-data `False`。
- mixin：common 0，client 7，server 0。
- 字节码符号：client 80，server 0，shared-game 23。
- 反向依赖：2 条；证据门禁 `PASS`。

## 合并约束

- `SERVER_ONLY` 不进入客户端 bundle；`CLIENT_ONLY` 不进入专用服务端 bundle。
- `BOTH` 的服务端和客户端必须使用报告锁定的同一 SHA。
- 任一 JAR、mixin、依赖 side 或类引用漂移时，validator 必须失败，回到 `BLOCKED_FAIL_CLOSED`。
- 本报告不是永久模组白名单，不锁死后续 MCModSync OTA 扩展；新增/替换模组仍走同一 side、依赖和运行时门禁。

## 未执行事项

- 未启动 Java 或 Minecraft。
- 未修改原服务器配置、世界、当前 staging 或 release。
- 静态分类不替代专服启动、注册表核对和双轮真实客户端进服测试。
