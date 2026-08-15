# MCModSync

MCModSync 是一个 Fabric/NeoForge 客户端启动前同步工具。它把 Mod 分成“必须模组”和“推荐模组”，使用 MD5 与 SHA256 双校验，并根据 Windows、Mac、Linux、手机端的兼容性决定推荐组合。清单、客户端配置和升级入口都可以公开审计；本仓库不包含任何生产站点、令牌、账号或私有路径。

> [!WARNING]
> **AI 辅助生成代码警示：** 本项目包含 AI 辅助生成或修改的代码与文档。AI 输出不是安全审计，也不保证没有逻辑错误、兼容性问题或未知风险。部署前请自行审阅源码、扫描依赖、在隔离实例测试并保留可恢复备份。只发布你有权分发且已经验证的 JAR。对外公开日志前请删除签名 URL、内部域名和本机路径。

> [!IMPORTANT]
> 所有示例 URL 都使用不可访问的占位域名（`example.invalid` 或 `example.com`）。它们必须替换为你自己控制的 HTTP/HTTPS 直链。不要把真实的 `modsync.properties` 提交到公共仓库。

## 版本和文件角色

当前公开发布版本为 `1.9.2`，要求 Java 21；同一个公开 JAR 同时提供 Fabric 入口（Fabric Loader `>=0.15.11`）和 NeoForge 入口（NeoForge 1.21.1、`javafml`）。Fabric 元数据精确支持 Minecraft `1.21.1` 与 `1.21.11`，NeoForge 元数据精确支持 Minecraft `1.21.1`。源码同时保留 v1/v2/v3 读取兼容性。加载器和 Minecraft 版本匹配仍由实例自身负责，不能把一个版本或加载器的 Mod 清单装入另一个实例。

电脑端便携更新完成后，置顶进度窗口会明确显示双语 `Restart Required` 提示，并等待玩家点击“确定，返回启动器”；不再于 5 秒后自动消失。手机端及无图形环境继续只写入日志和状态文件，不显示 Swing 弹窗。

推荐把同一个 Minecraft 目标版本和加载器的旧电脑地址、旧手机地址和新版目录分开部署；下面以 Fabric 1.21.1 为例，其他组合必须复制同样结构到独立目录：

```text
legacy-pc/                   # 原电脑端硬编码地址所在目录
├─ mods.txt                  # 只列出下面两个升级组件
├─ MCModSync-1.9.2.jar
└─ MCModSync-Config.jar
legacy-mobile/               # 原手机端硬编码地址所在目录；内容相同
├─ mods.txt
├─ MCModSync-1.9.2.jar
└─ MCModSync-Config.jar
1.21.1/fabric/               # 同一版本/加载器的新电脑端和手机端共用
├─ mods-v4.txt               # 完整正式清单
├─ MCModSync-1.9.2.jar
├─ MCModSync-Config.jar
├─ fabric-api.jar
├─ required-mod.jar
└─ recommended-mod.jar
```

每份清单中的文件名都按该清单 URL 的目录解析。旧电脑和旧手机目录各自只需发布 `mods.txt`、当前同步器和配置引导 JAR；目标目录发布该 Minecraft/加载器组合的 `mods-v4.txt` 与其列出的全部 JAR。两个旧地址可以相同，也可以像旧版本那样分开；它们最终都由配置引导 JAR 切到同一个目标地址。`mods.txt` 是永久升级入口，不要改成 v4 或删除。1.21.11 Fabric 与 1.21.1 NeoForge 都要另建目录，不能复用这里的清单。

### 1.21.1 与 1.21.11 并行部署

1.9.2 的同步核心不调用 Minecraft 游戏类，只通过 Fabric Loader 的 PreLaunch 接口、NeoForge 的客户端 `@Mod` 构造器和 Java 21 标准库工作，因此同一公开 JAR 可以服务目标版本。但“同步器相同”不等于“模组清单相同”：每个 Minecraft 版本和加载器组合必须各自维护独立的 URL、目录、`modsync.properties`、`mods.txt`/`mods-v4.txt`、`catalog-version` 历史和 Mod JAR 集合。推荐的服务器布局如下：

```text
/minecraft/1.21.1/fabric/
├─ mods.txt                  # 1.21.1 旧版升级入口（如仍需兼容硬编码地址）
├─ mods-v4.txt               # 只列 1.21.1 可用的 Mod
├─ MCModSync-1.9.2.jar
├─ MCModSync-Config.jar
└─ 1.21.1 版本的其他 JAR

/minecraft/1.21.11/fabric/
├─ mods.txt                  # 1.21.11 旧版升级入口（如仍需兼容硬编码地址）
├─ mods-v4.txt               # 只列 1.21.11 可用的 Mod
├─ MCModSync-1.9.2.jar
├─ MCModSync-Config.jar
└─ 1.21.11 版本的其他 JAR
```

每个游戏实例的配置都指向对应目录，例如：

```properties
# 1.21.1 实例
manifest=https://files.example.com/minecraft/1.21.1/fabric/mods-v4.txt

# 1.21.11 实例
manifest=https://files.example.com/minecraft/1.21.11/fabric/mods-v4.txt
```

不要把两个版本的 JAR 合并到一份清单，也不要让两个 URL 互相重定向。相同 Mod ID 如果需要不同构建，应在两份清单中分别记录各自文件名、版本、MD5 和 SHA256；发布某一版本时先上传该目录的全部 JAR，再上传对应清单，并单独递增该目录的 `catalog-version`。旧版硬编码 URL 只应切换到它所属 Minecraft 版本的 `mods.txt`。完整审计、发布顺序和回滚检查见 [`docs/minecraft-1.21.1-1.21.11-parallel-update-audit.zh-CN.md`](docs/minecraft-1.21.1-1.21.11-parallel-update-audit.zh-CN.md)。

### NeoForge 1.21.1

公开的 `MCModSync-1.9.2.jar` 同时包含 `fabric.mod.json` 和 `META-INF/neoforge.mods.toml`。在 NeoForge 1.21.1 中把同一个 JAR 放入 `mods` 即可，不需要另一个 MCModSync 构建；自动生成的 `MCModSync-Config.jar` 也同时包含两套元数据。主模组使用 `javafml` 的 `@Mod` 入口；配置引导包没有代码，NeoForge 元数据使用 `lowcodefml`，因此不会要求不存在的构造器类。

Fabric 和 NeoForge 的普通模组不能混在一份清单里。建议至少使用以下独立目录：

```text
/minecraft/1.21.1/fabric/
├─ mods-v4.txt
├─ MCModSync-1.9.2.jar
└─ 仅 Fabric 1.21.1 模组

/minecraft/1.21.1/neoforge/
├─ mods-v4.txt
├─ MCModSync-1.9.2.jar
└─ 仅 NeoForge 1.21.1 模组
```

发布器会先读取 `fabric.mod.json`，没有 Fabric 元数据时再读取 NeoForge 的第一个 `[[mods]]` 表，因此 NeoForge-only JAR 也能按 Mod ID 和版本自动替换。NeoForge 的普通 `@Mod` 入口发生在模组扫描之后；MCModSync 在该进程中只探测变化，桌面端由独立 helper 等待 JVM 退出后再改 `mods`，更新完成后显示 `Restart Required`。这避免在 NeoForge/SecureJar 仍占用文件时直接替换。官方格式说明见 [NeoForge 1.21.1 Mod Files](https://docs.neoforged.net/docs/1.21.1/gettingstarted/modfiles/)。

#### 1.21.11 私有迁移阻止版

需要停用旧 1.21.11 客户端时，可以在该旧实例的 `mods` 目录单独替换同步器为私有的迁移阻止版。它不是公开 1.9.2，也不会提交或发布到 GitHub，不应放入公开清单或 1.21.1 目录。该 JAR 只匹配 Minecraft 1.21.11，启动前始终显示中英双语提示“请更换为 Minecraft 1.21.1”，然后以退出码 `0` 正常结束，使启动器显示正常退出而不是崩溃。迁移阻止版会从现有 `modsync.properties` 的 `manifest`（或旧 `-javaagent` 的 `manifest=...` 参数）取 Mod 下载目录，自动请求同目录的 `migration-message.txt`；也可用 `-Dmcmodsync.migrationMessageUrl=https://.../migration-message.txt` 指定直链。云端 TXT 使用 UTF-8，大小上限 128 KiB，网络不可用时回退到 JAR 内置 TXT。迁移阻止版的实际文件应通过你自己的私下分发渠道提供，并在发布记录中保存校验值。

## 运行规则

### 必须模组 / Required

- 所有平台都必须存在。
- 缺失、文件名不匹配、MD5 不符或 SHA256 不符时自动下载或修复。
- 清单不可用、下载失败或双哈希失败时阻止游戏主类启动。
- 阻止启动、需要重启更新、配置更新后的重启都以退出码 `0` 正常结束，让启动器显示“正常退出”，而不是崩溃。

### 推荐模组 / Recommended

电脑端第一次遇到清单，或 `catalog-version` 发生变化时，会在启动前打开选择窗口：

- 所有当前平台兼容项默认勾选；云端标记为当前平台不兼容的项默认不勾选且禁止勾选。
- 每行“必须 / Required”和“推荐 / Recommended”只能选择一个。
- 提供“一键取消所有推荐模组”，全部不选也允许启动。
- 点击取消或关闭窗口等同于按当前勾选继续，不会强制选择全部。
- 已安装但被取消的推荐 JAR 会移动到 `.modsync/backups`，不会直接删除。
- 选择保存在 `.modsync/recommended-selection.properties`，同一清单版本以后直接复用。

手机端不会显示窗口，会自动下载当前平台兼容的全部推荐模组。每个 `catalog-version` 只自动处理一次；用户之后删除或破坏推荐 JAR 时不二次下载，日志会给出手动下载 URL、SHA256 和目标路径。清单版本更新会在日志中提示并开启新批次的一次自动处理。推荐模组缺失允许继续启动，必须模组仍严格阻止启动。

只有以下启动器识别为手机端：`PojavLauncher`、`MCinaBox`、`FCL`、`Zalith Launcher 2`。其他启动器均按电脑端处理。

## 第一次发布

### 1. 准备发布目录

发布目录的父目录被视为游戏根目录。例如 `D:\Release\1.21.1-fabric\mods` 的配置模板必须是 `D:\Release\1.21.1-fabric\modsync.properties`（NeoForge 工作区使用同样布局但必须分目录）。把当前 `MCModSync-1.9.2.jar` 放进 `mods` 目录；发布器会把它作为必须模组写入完整 v4，并与固定名 `MCModSync-Config.jar` 一起写入升级专用 v2。

复制 [`modsync.properties.example`](modsync.properties.example) 到游戏根目录并改名为 `modsync.properties`，至少修改：

```properties
manifest=https://files.example.com/minecraft/1.21.1/fabric/mods-v4.txt
syncResourcePacks=false
syncServerList=false
strict=true
requireManifest=true
```

`manifest` 必须以 `/mods-v4.txt` 结尾。要让同一个目标版本的手机和电脑统一使用该版本地址，请不要配置 `mobileManifest`；手机端会自动回退使用 `manifest`。只有确实要长期维护第二份手机清单时才填写它，而且仍必须位于同一个 Minecraft 版本目录。资源包和服务器列表是可选的，启用时必须提供有效清单 URL。这个文件既是客户端配置，也是发布器的配置模板。发布器只读取其中的服务器管理项，不会把本地语言、超时、重试和文件大小限制写入远程文件。

### 2. 用图形发布器编辑

运行 `MCModSync-1.9.2.jar`，选择已经测试完成的 Fabric 或 NeoForge `mods` 目录，然后打开必须/推荐清单编辑器。

1. 如需接着上次发布的清单修改，勾选“扫描后选择上次清单”。工具先扫描当前 `mods`，再打开你选择的 v3/v4 清单；当前文件夹决定最终条目集合，已删除 JAR 不会残留。
2. 每行只能勾选一个类型。加载器 API、前置库和服务器要求的内容选择 `required`；可选性能、地图、光影等选择 `recommended`。
3. 推荐项填写“不兼容的平台”。这是排除列表；不勾选表示四个平台都兼容。可选值为 `windows`、`mac`、`linux`、`mobile`。
4. 编辑显示名称、版本、中文描述和 English description。JAR 的 `fabric.mod.json` 或 `neoforge.mods.toml` 通常只有一个描述字段：含中文时先填中文列，否则填英文列；发布器不会自动翻译。继续使用上次清单可以保留人工填写的双语内容。
5. 更新 `catalog-version`。新增/删除推荐项、类型、平台兼容性、默认组合或说明发生变化时都应增加版本号。
6. 生成清单。工具会计算 MD5/SHA256、把全部模组写入 `mods-v4.txt`，把同步器和配置引导两个升级组件写入永久 `mods.txt`，并生成或更新 `MCModSync-Config.jar`。

表格底部的“所选设为必须模组”和“所选设为推荐模组”支持批量操作；没有选择行时会作用于全部条目。`required`/`recommended` 互斥约束在界面和清单解析阶段都会检查。

### 3. 命令行发布

命令行扫描并生成 v4 清单，所有扫描到的条目默认为必须模组；需要推荐分类、双语描述和平台排除列表时请使用图形编辑器：

```powershell
java -jar MCModSync-1.9.2.jar "D:\Release\1.21.1-fabric\mods"
```

默认输出为 `mods-v4.txt`，并在 `mods` 目录旁生成永久 `mods.txt`。也可以指定 v4 输出路径：

```powershell
java -jar MCModSync-1.9.2.jar "D:\Release\1.21.1-fabric\mods" "D:\Publish\mods-v4.txt"
```

## 从 1.6.x/1.7 无缝升级

旧版客户端只理解 v1/v2，不理解 v4。当前方案不要求玩家修改旧客户端：旧电脑/手机硬编码 URL 继续返回 `mods.txt`，但这个 v2 文件只下发当前同步器与配置引导 JAR。配置引导中写入所属 Minecraft 版本的 `mods-v4.txt` 地址，新版随后从那里恢复完整模组集。

假设原电脑端和手机端地址不同，分别部署：

```text
https://old-pc.example.com/client/
├─ mods.txt
├─ MCModSync-1.9.2.jar
└─ MCModSync-Config.jar

https://old-mobile.example.com/client/
├─ mods.txt
├─ MCModSync-1.9.2.jar
└─ MCModSync-Config.jar

https://files.example.com/minecraft/1.21.1/fabric/
├─ mods-v4.txt
├─ MCModSync-1.9.2.jar
├─ MCModSync-Config.jar
└─ mods-v4.txt 中列出的全部其他 JAR
```

两个旧目录里的三个文件内容可以完全相同。因为 v2 使用相对下载地址，两个目录都必须能直接下载那两个 JAR，或者配置等价的 HTTP 重定向。发布模板只写：

```properties
manifest=https://files.example.com/minecraft/1.21.1/fabric/mods-v4.txt
# 不填写 mobileManifest；同一目标版本的手机与电脑共用 manifest
```

旧客户端升级流程：

1. 读取原来的 v2 `mods.txt`。
2. 旧清单中不再出现的服务器管理 Mod 会移入 `.modsync/backups/<批次>/`；手机端自动执行，桌面有窗口时会询问。文件不是永久删除。
3. 下载并校验 `MCModSync-1.9.2.jar`，按 Mod ID `mcmodsync` 自动替换旧版本，同时下载固定名 `MCModSync-Config.jar`。
4. 本次以退出码 `0` 正常结束，启动器显示正常退出。
5. 再启动时，1.9.2 从配置引导 JAR 自动创建/更新游戏根目录的 `modsync.properties`，保留本地语言、超时、重试、文件大小限制等本地键，并读取所属 Minecraft/加载器组合的 `mods-v4.txt`。
6. 因为旧版入口只保留升级组件，这次通常会重新下载完整必须模组和所选/手机自动选择的推荐模组，然后再次正常退出。
7. 下载完成后再启动一次，完整校验通过后进入游戏。

因此从旧版升级通常需要启动两至三次，这是正常的安全更新流程。手机端读取旧地址只发生在升级阶段；安装新版并写入配置后，后续全部读取所属版本地址。已经发布过写死地址的 1.6.x/1.7 客户端无需预先拥有 `modsync.properties`，也无需玩家手工创建。

不要把过渡内容覆盖到 v4 文件，也不要把 v2 清单另存为旧客户端不知道的 URL。旧地址的 `mods.txt` 应永久保留；每个 Minecraft 版本的完整清单都叫 `mods-v4.txt`，但必须位于不同 URL 目录。

也可以只生成永久 v2 入口：

```powershell
java -jar MCModSync-1.9.2.jar --upgrade-v2 "D:\Release\1.21.1-fabric\mods"
```

这个命令默认写入 `D:\Release\1.21.1-fabric\mods\mods.txt`，仍会读取配置模板并确保配置引导 JAR 在清单中。把生成的 `mods.txt`、当前同步器和配置引导 JAR 复制到 1.21.1 Fabric 对应的旧 URL 目录；NeoForge 和 1.21.11 工作区另行执行并上传到各自的版本/加载器目录。

## 清单格式和配置管理

典型 v4 文件包含：

```text
# mcmod-sync-v4
# catalog-version=2026-07-30-01
# client-config.manifest=https://files.example.com/minecraft/1.21.1/fabric/mods-v4.txt
# 合并发布时不写 client-config.mobileManifest
# client-config.syncResourcePacks=false
# client-config.syncServerList=false
# client-config.strict=true
# client-config.requireManifest=true
# SHA256<TAB>MD5<TAB>Mod ID<TAB>文件名<TAB>类型<TAB>不兼容平台<TAB>名称<TAB>版本<TAB>中文描述<TAB>English description
<sha256>\t<md5>\tsodium\tsodium.jar\trecommended\tmobile\tSodium\t1.0\t渲染优化\tRendering optimization
```

只有以下服务器管理项允许出现在 `client-config.*` 中：`manifest`、`mobileManifest`、`syncResourcePacks`、`resourcePackManifest`、`mobileResourcePackManifest`、`syncServerList`、`serverListManifest`、`strict`、`requireManifest`。`requireManifest=false` 会被拒绝，未知项也会让清单失效。

文件大小限制不属于远程配置：客户端未填写 `maxFileBytes` 时默认不主动限制下载文件大小；只有玩家/整合包在本地 `modsync.properties` 中显式填写时才启用该限制。`maxFileBytes`、`language`、超时和重试参数不会写进 v4 清单或配置引导 JAR，也不会被服务器覆盖。

远程配置更新时，新客户端会原子更新 `modsync.properties`，保留全部本地专属键，并在需要时正常退出一次让新配置生效。配置引导 JAR 使用固定文件名和固定资源路径，客户端不会扫描或信任其他普通 Mod JAR 中的配置资源。

## 玩家配置、语言和卸载

1. 把 `MCModSync-1.9.2.jar` 放入 Fabric 或 NeoForge 1.21.1 实例的 `mods` 目录。
2. 将 [`modsync.properties.example`](modsync.properties.example) 复制到游戏根目录并改名为 `modsync.properties`。
3. 修改自己的 v4 直链。`language=auto` 会让推荐窗口、同步提示、`helper.log`、`progress.log`、`ui-status.txt` 和主要运行日志跟随 Windows/操作系统语言，不读取 Minecraft 的 `options.txt`；也可填 `zh_cn` 或 `en_us` 固定语言，或用 `-Dmodsync.language=en_us` 临时覆盖。
4. 不使用资源包或服务器列表时，把 `syncResourcePacks`/`syncServerList` 设为 `false`。

卸载时完全退出游戏和所有 Java 进程：

1. 从实例 `mods` 删除 `MCModSync-1.9.2.jar` 和 `MCModSync-Config.jar`。
2. 删除游戏根目录 `modsync.properties`。
3. 如果使用过 `-javaagent:`，从启动器 JVM 参数删除对应参数。
4. 需要恢复被取消的推荐 Mod 时，先从 `.modsync/backups/<批次>/` 手动移回并检查哈希，再决定是否删除 `.modsync`。卸载不会自动删除或恢复其他 Mod。

## 可选资源包和服务器列表

```powershell
java -jar MCModSync-1.9.2.jar --resourcepack "D:\Publish\server-pack.zip"
java -jar MCModSync-1.9.2.jar --serverlist "D:\Publish\servers.dat"
```

分别生成资源包和服务器列表清单。将清单和对应文件放到直链目录，并在本地配置中启用对应开关。Mod v4 使用 MD5+SHA256；资源包和服务器列表继续使用各自格式。

服务器列表同步采用“明确所有权”规则：

- MCModSync 只会更新或删除 `.modsync/server-list-managed-v1.dat` 能够唯一确认、且此前确实由 MCModSync 写入的服务器条目。
- 玩家自行添加的服务器永远不会因为地址与云端相同而被认领、覆盖或删除；玩家列表中的重复地址也会全部保留。
- 已有云端管理条目在原位置更新；云端移除时只删除对应受管条目；其他条目的原位置和相对顺序不变。
- 云端新增且本地不存在的服务器只追加到列表末尾。单纯改变云端 `servers.dat` 的条目顺序不会重排玩家列表。
- 从旧版升级时，旧 `.modsync/server-list-cloud.dat` 只作为云端版本缓存，不能证明本地条目属于云端；因此不会自动认领任何已有服务器。台账缺失、损坏、条目被玩家修改或出现歧义时进入保守模式：保留既有条目，只在地址不存在时追加云端新项。

不要手工编辑 `server-list-managed-v1.dat`。如果删除它，现有服务器会失去 MCModSync 管理身份并按玩家条目保护；后续仍可追加本地不存在的云端服务器，但不会凭地址删除旧条目。

## 排错和状态文件

- `.modsync/recommended-selection.properties`：电脑端选择和手机端一次处理状态。
- `.modsync/server-manifest.txt`：最近一次远程 Mod 清单缓存。
- `.modsync/server-list-cloud.dat`：最近一次已校验的云端 `servers.dat` 缓存，只用于版本判断。
- `.modsync/server-list-managed-v1.dat`：服务器列表所有权台账；只有其中能与本地唯一、完整匹配的条目才允许更新或删除。
- `.modsync/backups/`：被替换或取消的文件。
- `.modsync/progress.log`、`.modsync/helper.log`、`.modsync/ui-status.txt`：下载、辅助更新和无弹窗状态。
- `logs/latest.log`：Fabric/NeoForge/游戏日志。

如果启动器控制台出现 `Could not find or load main class io.github.mcmodsync.PortableUpdateHelper`，先升级到当前 1.9.2（路径修复自 1.8.6 起包含）。真实故障包已证明 1.8.5 的辅助 JAR 完整、SHA256 正确且主类存在；故障位于该 Windows Java 环境解析/装载完整 `-cp` 启动路径的阶段，而不是 JAR 下载或内容，带分号的完整路径也已在回归测试中复现同类错误。1.8.6 起改用隔离的 `helper-runtime-v2`、`.part` 原子提交、显式新时间戳和 MD5/SHA256 双校验；子 Java 以辅助目录为工作目录，只接收 ASCII JAR 文件名并通过 `-jar` 启动。父进程必须收到子进程的 ready 信号后才正常退出；提前退出、PID 异常或 10 秒超时会终止子进程、阻止本次启动并把明确原因写入日志。升级无需删除配置、清单或推荐选择记录。

清单版本更新时日志会输出旧版本和新版本。手机端同版本删除推荐 Mod 后只记录手动恢复方式；电脑端重新选择即可。启动阻止应看到 `STARTUP_BLOCKED`，但退出码为 `0`，且游戏主类不会运行。

发布顺序建议：先把全部 JAR 上传到合并目录，把两个升级 JAR 上传到每个旧地址并确认直链，再上传合并目录的 `mods-v4.txt`，最后更新各旧目录的 `mods.txt`。CDN 有缓存时先处理缓存失效，避免清单和 JAR 跨版本混用。

## 构建和测试

```powershell
./build.ps1
```

脚本会编译主类和测试、运行完整测试、构建 `build/dist/MCModSync-1.9.2.jar`，检查 Fabric/NeoForge 双元数据和入口，并执行正常退出、便携模式、资源同步和清单兼容性检查。要验证真实旧版升级：

```powershell
$env:MCMODSYNC_LEGACY_JAR = 'D:\Legacy\MCModSync-1.6.10.jar'
$env:MCMODSYNC_LEGACY_ENTRYPOINT = 'your.legacy.package.FabricPreLaunchEntrypoint'
./build.ps1
```

`MCMODSYNC_LEGACY_ENTRYPOINT` 必须填写旧 JAR 实际的入口类全名；脚本不会猜测或写入旧项目包名。1.7 验证同样设置该变量。构建输出会复制到仓库上级 `outputs` 目录。发布前请检查 `git diff` 和敏感信息扫描。

## 许可证

本项目采用 [MIT License](LICENSE)。
