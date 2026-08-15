# MCModSync 1.9.2：Minecraft 1.21.1 / 1.21.11 并行更新可行性审计

审计日期：2026-08-13

## 一、结论

公开版 `MCModSync-1.9.2.jar` 可以作为同一个同步器二进制文件用于 Fabric Minecraft `1.21.1`/`1.21.11`，以及 NeoForge Minecraft `1.21.1`。运行要求为 Java 21；Fabric 元数据声明 Loader `>=0.15.11`，NeoForge 元数据声明 `javafml`、Minecraft `[1.21.1]` 和 NeoForge `[21.1.0,)`。公开 JAR 不使用 `>=1.21.1` 之类会意外放行其他版本的范围。

并行更新可行，但有一个不可放宽的部署条件：两个 Minecraft 版本必须使用彼此独立的 URL、服务器目录、本地 `modsync.properties`、永久 `mods.txt`、正式 `mods-v4.txt`、`catalog-version` 历史、配置引导 JAR 和 Mod JAR 集合。公开同步器可以相同，业务清单不能合并。

| 审计项 | 结论 | 约束 |
| --- | --- | --- |
| 同一公开同步器 JAR | 可行 | Fabric MC 1.21.1 / 1.21.11，或 NeoForge MC 1.21.1；Java 21 |
| 同一份 `mods-v4.txt` | 不可行 | 两个版本必须分开生成和发布 |
| 同一份 `modsync.properties` | 不建议且不作为支持方案 | 每个实例必须明确指向自己的版本目录 |
| 同一个 `catalog-version` 历史 | 不可行 | 两个目标版本独立递增、独立回滚 |
| 1.6.x/1.7 硬编码地址升级 | 可行 | 每个旧地址必须归属一个明确目标版本 |
| 私有 1.21.11 迁移阻止版 | 可行 | 只私下部署，不进入 GitHub、公开清单或 1.21.1 实例 |

## 二、代码与元数据依据

1. [`fabric.mod.json`](../src/main/resources/fabric.mod.json) 的 Fabric 依赖为精确版本数组 `1.21.1`、`1.21.11`，Fabric Loader 下限为 `0.15.11`，Java 下限为 21。Fabric 官方文档允许依赖值使用版本范围数组，并将其中任一匹配视为满足依赖：[Fabric Mod JSON 规范](https://docs.fabricmc.net/develop/loader/fabric-mod-json)。
2. [`META-INF/neoforge.mods.toml`](../src/main/resources/META-INF/neoforge.mods.toml) 使用 NeoForge 1.21.1 官方格式：`modLoader="javafml"`、`loaderVersion="[1,)"`、`@Mod` 类入口、客户端依赖 Minecraft `[1.21.1]`。格式和构造器规则见 [NeoForge 1.21.1 Mod Files](https://docs.neoforged.net/docs/1.21.1/gettingstarted/modfiles/)。
3. 主同步核心没有导入 `net.minecraft.*`、映射名称或 Fabric API 游戏事件。Fabric 适配器只使用 `PreLaunchEntrypoint`；NeoForge 适配器只使用官方 `@Mod` 注解并通过反射读取 `FMLPaths.GAMEDIR.get()`。同步、哈希、文件移动、HTTP、Swing 和日志逻辑使用 Java 21 标准库。
4. NeoForge 普通 `@Mod` 构造器发生在模组发现和依赖验证之后，并可能与其他模组构造并行。因此入口只做只读探测并安排退出后的 helper；不能在构造器里直接替换仍被 SecureJar 打开的 JAR。桌面更新完成后必须重新启动，手机路径仍遵循启动器自动更新策略。
5. v4 清单条目记录哈希、Mod ID、文件名、类型、平台排除、名称、版本和双语描述，但不包含用于在同一清单内按 Minecraft 版本或加载器选择不同 JAR 的目标字段。相同 Mod ID 的两份目标 JAR 也不应同时出现在一个客户端实例中。因此，按 Minecraft 版本和加载器拆分清单是数据模型本身要求的边界。

以上结论是源码、官方 API 和元数据层面的兼容性结论。正式发布仍应在真实 Minecraft 1.21.1 Fabric、1.21.11 Fabric、1.21.1 NeoForge 实例中各完成一次启动前同步、下载后正常退出、第二次启动校验和推荐选择测试；不能用只运行发布器、compile-only stub 或单元测试代替真实客户端验收。

## 三、推荐目录结构

```text
https://files.example.com/minecraft/
├─ 1.21.1/fabric/
│  ├─ mods.txt
│  ├─ mods-v4.txt
│  ├─ MCModSync-1.9.2.jar
│  ├─ MCModSync-Config.jar
│  └─ 仅适用于 1.21.1 Fabric 的其他 JAR
├─ 1.21.1/neoforge/
│  ├─ mods.txt
│  ├─ mods-v4.txt
│  ├─ MCModSync-1.9.2.jar
│  ├─ MCModSync-Config.jar
│  └─ 仅适用于 1.21.1 NeoForge 的其他 JAR
└─ 1.21.11/fabric/
   ├─ mods.txt
   ├─ mods-v4.txt
   ├─ MCModSync-1.9.2.jar
   ├─ MCModSync-Config.jar
   └─ 仅适用于 1.21.11 Fabric 的其他 JAR
```

这里的“同一个公开 JAR”只指三个目录中的 `MCModSync-1.9.2.jar` 字节可以相同。`MCModSync-Config.jar` 应分别从各自游戏根目录的模板生成，因为它写入的 `manifest` URL 不同。其他 JAR 即使文件名相同，也必须按目标版本和加载器分别验证并计算 MD5/SHA256。

禁止以下布局：

```text
https://files.example.com/minecraft/merged/mods-v4.txt
└─ 同时列出 1.21.1 与 1.21.11 的两个版本 JAR   # 禁止
```

不要依赖客户端操作系统的“不兼容平台”列来区分 Minecraft 版本。该列只用于 `windows`、`mac`、`linux`、`mobile`，不是游戏版本路由。

## 四、两套本地发布工作区

```text
D:\Release\MCModSync\
├─ 1.21.1\
│  ├─ modsync.properties
│  └─ mods\
│     ├─ MCModSync-1.9.2.jar
│     └─ 1.21.1 目标 Mod
└─ 1.21.11\
   ├─ modsync.properties
   └─ mods\
      ├─ MCModSync-1.9.2.jar
      └─ 1.21.11 目标 Mod
```

1.21.1 模板：

```properties
manifest=https://files.example.com/minecraft/1.21.1/fabric/mods-v4.txt
syncResourcePacks=false
syncServerList=false
strict=true
requireManifest=true
```

1.21.11 模板：

```properties
manifest=https://files.example.com/minecraft/1.21.11/fabric/mods-v4.txt
syncResourcePacks=false
syncServerList=false
strict=true
requireManifest=true
```

如果手机端和电脑端在同一个 Minecraft 目标版本中共用清单，不填写 `mobileManifest`，手机会回退到该实例的 `manifest`。如果确实需要长期维护手机专用清单，其 URL 也必须留在相同 Minecraft 版本目录内，不能跨版本。

## 五、清单和历史命名规则

两个目录内的正式文件仍都叫 `mods-v4.txt`，客户端配置依靠完整 URL 区分。建议让 `catalog-version` 自带目标版本前缀，便于日志和回滚判断：

```text
# 1.21.1/mods-v4.txt
# catalog-version=mc1.21.1-2026-08-10-r1

# 1.21.11/mods-v4.txt
# catalog-version=mc1.21.11-2026-08-10-r1
```

每套清单都应独立保存：

- 本次 `mods-v4.txt` 和上一次可回滚副本；
- 本次 `mods.txt` 和配置引导 JAR；
- 全部已发布 JAR 的 SHA256、MD5、文件大小和来源记录；
- `catalog-version` 变更说明；
- 桌面推荐选择和手机一次处理行为的验收记录。

在图形发布器中“扫描后选择上次清单”时，只能为 1.21.1 工作区打开上一次 1.21.1 清单，为 1.21.11 工作区打开上一次 1.21.11 清单。不要跨版本继承类型、哈希或描述后直接发布；需要复用双语描述时也要逐项核对 Mod ID 和目标版本。

## 六、发布顺序

每个目标版本独立执行以下流程：

1. 完全停止该目标版本的发布任务，确认没有另一进程写同一目录。
2. 在隔离实例验证全部必须 Mod 和推荐 Mod 确实适配目标 Minecraft/加载器组合。
3. 用该版本工作区生成新的 `mods-v4.txt`、永久 `mods.txt` 和 `MCModSync-Config.jar`。
4. 检查清单中的同步器版本为 1.9.2，检查所有 JAR 的 MD5/SHA256，检查 `client-config.manifest` 指向本版本 URL。
5. 先上传该版本目录中的全部 JAR，并验证 HTTP 状态、文件长度和 SHA256。
6. 再上传该版本的 `MCModSync-Config.jar` 和永久 `mods.txt` 所需文件。
7. 上传该版本的新 `mods-v4.txt`，最后才更新属于该版本的旧硬编码 URL 下的 `mods.txt`。
8. 清理 CDN 缓存，并从外部网络重新下载清单和至少一个 JAR 验证。
9. 只在该目标版本的真实实例执行验收，不要用另一版本的成功结果代替。

发布某个 Minecraft/加载器组合时不修改其他版本或加载器目录。三边可以使用不同发布时间和不同 `catalog-version`，无需锁步。

## 七、回滚和故障隔离

某一版本出现问题时：

1. 立即停止该版本的 `mods.txt`/`mods-v4.txt` 更新，不动另一个版本目录。
2. 恢复该版本上一次清单及其对应 JAR，不能只回滚清单而保留不匹配的文件集合。
3. 清理该版本 URL 的 CDN 缓存，重新验证 SHA256。
4. 检查客户端 `.modsync/progress.log`、`.modsync/helper.log`、`.modsync/ui-status.txt` 和 `logs/latest.log`。
5. 若必须 Mod 不完整，客户端应输出 `STARTUP_BLOCKED` 并以退出码 `0` 正常结束；不要为了临时进入游戏关闭 `strict` 或 `requireManifest`。

因为两个版本的 URL、配置和历史独立，单边回滚不会更改另一边已验证的组合。这是并行更新方案的主要隔离收益。

## 八、1.6.x/1.7 旧地址迁移

旧客户端只认识硬编码地址下的 v1/v2 `mods.txt`。每个旧地址必须先登记目标版本：

| 旧地址 | 目标版本 | 配置引导写入的新地址 |
| --- | --- | --- |
| `https://old-1-21-1.example.com/client/` | 1.21.1 Fabric | `https://files.example.com/minecraft/1.21.1/fabric/mods-v4.txt` |
| `https://old-1-21-11.example.com/client/` | 1.21.11 Fabric | `https://files.example.com/minecraft/1.21.11/fabric/mods-v4.txt` |

旧地址继续永久提供只包含同步器和配置引导 JAR 的 `mods.txt`。升级后，1.9.2 从固定名 `MCModSync-Config.jar` 创建或更新游戏根目录的 `modsync.properties`，以后只读取该目标版本/加载器的新地址。手机端与电脑端可在同一组合内合并 URL，但不能把不同 Minecraft 版本或加载器合并。

对无法确定目标版本的旧地址，不要自动猜测或统一重定向。先从原整合包、启动器实例目录或服务端发布记录确认 Minecraft 版本，再生成对应配置引导 JAR。

## 九、1.21.11 私有迁移阻止版

私有迁移阻止版用于让已经退役的 Minecraft 1.21.11 客户端始终停止在启动前，并引导玩家更换为 1.21.1 客户端。它应满足以下发布边界：

- 只声明 Minecraft `1.21.11`，不在 1.21.1 加载；
- 使用与同步器相同的 Mod ID，部署时替换普通同步器，避免同时加载两个实现；
- 在 PreLaunch 阶段写入清晰日志，并显示中英双语更换客户端提示；
- 从该实例配置的 Mod 清单 URL 同目录自动下载 UTF-8 `migration-message.txt`；网络失败时使用 JAR 内置副本；
- 无论玩家关闭窗口还是确认提示，都不运行 Minecraft 主类；
- 最终调用正常退出路径并返回退出码 `0`，让启动器显示正常退出而不是崩溃；
- 只通过私下渠道分发，不提交 Git、不创建 GitHub Release、不放入公开源码包；
- 不放入公开 1.9.2 的 `mods-v4.txt`，也不放入任何 1.21.1 目录；
- 保存私有 JAR 的 SHA256、部署日期、目标旧地址和撤回方案。

该阻止版不是普通并行更新节点。一旦某个 1.21.11 地址切换到阻止版，该地址的业务目标就是引导迁移，而不是继续同步 1.21.11 Mod。仍要运营 1.21.11 的其他实例必须使用另一个独立 URL 和普通公开版 1.9.2。

## 十、发布验收表

1. 在 JAR 内检查 Fabric `fabric.mod.json` 和 NeoForge `META-INF/neoforge.mods.toml`：版本 1.9.2；Fabric Minecraft 精确为 1.21.1/1.21.11；NeoForge Minecraft 精确为 1.21.1；Java >=21。
2. 在真实 1.21.1 Fabric 实例中完成首次同步、更新后正常退出、重新启动和进入游戏。
3. 在真实 1.21.1 NeoForge 实例重复同样流程，并确认 `FMLPaths.GAMEDIR` 下的目录被使用。
4. 在真实 1.21.11 Fabric 实例重复同样流程。
5. 确认三个实例的 `modsync.properties` 指向不同 URL。
6. 确认三个 `mods-v4.txt` 的 Mod JAR 均只适配各自目标版本/加载器。
7. 确认三个清单使用独立 `catalog-version`，更新一边不会让另一边重新询问推荐组合。
8. 破坏各组合的一个必须 JAR，确认自动修复；使清单不可访问，确认 `STARTUP_BLOCKED`、退出码 0、游戏主类未运行。
9. 验证 Windows、Mac、Linux、手机“不兼容平台”规则，但不把它当作 Minecraft 版本或加载器筛选机制。
10. 用真实 1.6.x/1.7 包分别验证所属组合的永久 `mods.txt` -> 配置引导 -> 对应 `mods-v4.txt` 链路。
11. 在隔离的 1.21.11 旧实例验证私有阻止版：双语提示、关闭/确认均阻止启动、退出码 0；同时确认 Git 状态、公开构建产物和公开清单中都没有该私有 JAR。

只有以上检查在三个支持组合分别通过，才能把“同一公开 JAR 支持多个版本/加载器”视为已完成运行时验收。源码审计本身只能说明移植路径合理，不能替代实际模组组合测试。
