# GitHub 公开仓库重复审计与人工辨认

审计日期：2026-09-05

## 结论

- **仓库名重复：0 个。** 对账号 `YU322142` 的公开仓库按不区分大小写的完整名称分组，没有发现两个仓库使用同一个名称。
- **本次新增公开仓库：20 个。** 全部为公开仓库，默认分支为 `main`；每个仓库都有独立 README 和构建边界。
- **源码内容的有意重叠：存在。** 20 个独立仓库来自 `migration-collab-repo` 的对应源码路径。这是“项目仓库 + 协作总索引”的有意镜像，不是误创建的重复项目。

## 人工辨认规则

### 1. 先区分仓库角色

| 看到的仓库 | 角色 | 是否保留 |
| --- | --- | --- |
| `migration-collab-repo` | 总索引、审计、迁移脚本、跨项目文档 | 保留，不能删除 |
| 20 个本次新增仓库 | 单项目源码/补丁/数据快照 | 保留，作为项目主页 |
| `MCSync`、`MineAstr`、`Chest-Colorizer-NeoForge`、`ImmersivePaintings`、`Toms-Storage` | 已有独立维护项目 | 保留，不与总索引合并 |
| `Create-Fly`、`sable`、`Veil`、`Simulated-Project` 等已归档项目 | 历史/未完成快照 | 保持归档，不当作当前项目 |

### 2. 再按项目名称确认

本次新增仓库的唯一对应关系如下。GitHub 页面、网站链接和发布工具都应使用右侧独立仓库；左侧路径只用于在总索引中追溯来源。

| 总索引源码路径 | 独立仓库 |
| --- | --- |
| `outputs/projects/cctweaked-startup-shutdown-guard-neoforge` | `CCTweaked-Startup-Shutdown-Guard` |
| `outputs/projects/create-carriage-orientation-guard-neoforge` | `Create-Carriage-Orientation-Guard` |
| `outputs/projects/create-chute-unload-guard-neoforge` | `Create-Chute-Unload-Guard` |
| `outputs/projects/create-dynamic-blocking-neoforge` | `Create-Dynamic-Blocking` |
| `outputs/projects/create-saveddata-probe` | `Create-SavedData-Probe` |
| `outputs/projects/deferred-content-protection-neoforge` | `Deferred-Content-Protection` |
| `outputs/projects/hardcore-revival-death-message-fix-neoforge` | `Hardcore-Revival-Death-Message-Fix` |
| `outputs/projects/heightmap-384-to-544-compat-neoforge` | `Heightmap-384-to-544-Compat` |
| `outputs/projects/kaleidoscope-cookery-scarecrow-compat` | `Kaleidoscope-Cookery-Scarecrow-Compat` |
| `outputs/projects/kaleidoscope-nether-backport` | `Kaleidoscope-Nether-Backport` |
| `outputs/projects/mishanguc-pale-oak-equivalence` | `MishangUC-Pale-Oak-Equivalence` |
| `outputs/projects/poi-migration-diagnostic` | `POI-Migration-Diagnostic` |
| `outputs/projects/potted-farms-1.21.1-equivalence` | `Potted-Farms-1.21.1-Equivalence` |
| `outputs/projects/recipe-set-diagnostic` | `Recipe-Set-Diagnostic` |
| `outputs/projects/resource-error-overlay-1.21.1` | `Migration-Resource-Error-Overlay` |
| `outputs/projects/waypoint-fire-equivalence` | `Waypoint-Fire-Equivalence` |
| `projects/patches/tlm-patchouli-spawn-box-balance` | `TLM-Patchouli-Spawn-Box-Balance` |
| `projects/patches/worldedit-7.3.8-direction-property-fix` | `WorldEdit-Direction-Property-Fix` |
| `projects/patches/xiyuslogin-auto-session-ota` | `XiyusLogin-Auto-Session-OTA` |
| `projects/patches/yuushya-2.3.0-patchouli-safety` | `Yuushya-2.3.0-Patchouli-Safety` |

### 3. 遇到“看起来重复”的项目时这样判断

- `MCSync` 与 `migration-collab-repo`：前者是同步软件，后者是迁移协作仓库，不重复。
- `MineAstr` 的主分支与 `astrbot-plugin` 分支：同一仓库内的模组端和 Bot 端，不重复。
- `ImmersivePaintings` 与 `projects/patches/immersive-paintings-mineastr-compat`：前者是完整项目，后者是针对迁移 JAR 的覆盖补丁；补丁没有再创建第二个独立仓库。
- `MishangUC-Pale-Oak-Equivalence` 与 `projects/ports/mishanguc-1.21.1-equivalence`：前者是当前苍白橡木等价模块，后者是完整移植参考线；相关但不应合并。
- `Kaleidoscope-Nether-Backport` 与 `projects/ports/kaleidoscope-nether-1.21.1-equivalence`：前者是当前可独立构建的回移植工程，后者是历史/参考线；相关但不应互相覆盖。
- `Potted-Farms-1.21.1-Equivalence` 与 `projects/ports/potted-farms-1.21.1-equivalence-full`：前者是当前数据快照，后者是完整打包参考工程；使用前者做小范围数据发布。

## 人工操作步骤（GitHub 网页）

1. 打开 `github.com/YU322142` 的 Repositories 页面。
2. 看到仓库后先看右侧是否为 `Public`，再看是否有 `Archived` 标记。
3. 将仓库名与上表逐字比较；**同名项目优先使用独立仓库，`migration-collab-repo` 只作为总索引**。
4. 打开仓库 README，确认它属于“源码模组”“诊断工具”还是“补丁/脚本”。补丁仓库没有上游 JAR 是正常的，不要因此重新创建一个包含 JAR 的仓库。
5. 需要确认模组身份时，打开 `gradle.properties`，核对 `mod_id` 和 `mod_name`；数据/补丁项目则核对 README 的项目边界。
6. 只有当仓库名、README 角色和 `mod_id`（如有）都一致时，才认为它是同一个项目；仅仅功能相关或来源相同，不算重复。

## 命令行复核（可选）

```powershell
# 检查账号下是否存在不区分大小写的同名仓库
$repos = gh repo list YU322142 --limit 200 --json name,url,isArchived,isPrivate | ConvertFrom-Json
$repos | Group-Object { $_.name.ToLowerInvariant() } |
  Where-Object Count -gt 1 | Select-Object -ExpandProperty Group

# 检查每个新仓库是否仍是公开、main 分支
gh repo view YU322142/<REPO> --json name,visibility,isArchived,defaultBranchRef,url
```

第一条命令无输出即表示没有精确同名重复。不要用“文件数量相同”判断重复，因为总索引仓库和独立仓库本来就会共享源码快照。

## 处理原则

- 不删除 `migration-collab-repo`，它承载跨项目审计、脱敏规则和迁移工具。
- 不把第三方 JAR、世界、玩家数据、认证数据库或真实配置上传到任何公开仓库。
- 不把历史归档仓库重新当作当前版本入口。
- 新功能优先提交到对应独立仓库，再在总索引登记路径、版本和边界。
