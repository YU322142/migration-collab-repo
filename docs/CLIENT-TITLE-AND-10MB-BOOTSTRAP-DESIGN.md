# 客户端标题与 10MB 启动包设计分析

本文只解释原理和发布边界，不恢复旧主界面，也不修改当前客户端。

## 原整合包的标题系统

原整合包把“窗口标题”和“游戏主界面”分成了两条互不相同的链路。

### 游戏窗口标题

窗口标题来自 KubeJS 客户端配置：

- 原配置文件：`kubejs/config/client.json`
- 关键字段：`window_title`

该字段只负责操作系统窗口标题，不改变标题画面、按钮布局或 NeoForge 品牌文字。当前 Motiquies 配置将其留空，因此使用运行时默认标题。

### 标题画面资源

旧 C6C JAR 直接覆盖了 Minecraft 的标准标题资源位置：

- `assets/minecraft/textures/gui/title/minecraft.png`
- `assets/minecraft/textures/gui/title/edition.png`
- `assets/minecraft/textures/gui/title/background/panorama_overlay.png`
- `assets/minecraft/lang/en_us.json`
- `assets/minecraft/lang/zh_cn.json`

这层的本质是资源替换。只要保留原版布局，仅制作自定义 Logo、版本副标题或全景叠层，不需要改变游戏逻辑。

### 标题画面行为

旧 C6C 通过三个客户端相关 Mixin 改变行为：

- `BrandingControlMixin`：隐藏 NeoForge/Minecraft 的品牌文字列表。
- `LogoRendererMixin`：继续使用标准 Logo 资源位置，但重新控制 Logo 和 edition 图片的绘制尺寸、位置与淡入。
- `TitleScreenMixin`：取消原版标题页初始化，重新组织按钮，并替换一个按钮的行为。

语言 JSON 只改变按钮文字；按钮位置、数量和点击动作仍由 `TitleScreenMixin` 决定。旧实现还把一个按钮导向外部推广页面，这与标题视觉并不是同一职责。

### 合理的新设计边界

制作新标题时建议把职责拆开：

1. 窗口标题继续由客户端配置管理。
2. Logo、edition、panorama overlay 等纯视觉内容放在独立客户端资源层。
3. 只有确实要改变按钮结构时才使用独立客户端标题模组。
4. 不把标题逻辑重新塞回承担服务端玩法规则的 C6C。
5. 标题模组缺失时应退回原版标题页，而不是阻止客户端启动或入服。

这样可以独立更换美术、标题文字和按钮布局，也不会因为 C6C 玩法更新而重新合并 UI 补丁。

## Motiquies 2.0.1 轻量包结构

参考文件：`<DOWNLOAD_ROOT>/Motiquies - 动静交映 - 2.0.1.zip`

- ZIP 大小：5,690,321 bytes。
- 文件数：917。
- 解压后总量：8,787,954 bytes。
- `manifest.json` 的 `files` 数组为空，仅声明 Minecraft 1.21.1、NeoForge 21.1.241 和 8GiB 推荐内存。
- 内置 MCModSync 1.9.6：249,336 bytes，SHA-256 `9171B0FEC763AFAA03014EAA657430387411D659B28347516DED8E46482373AE`。
- 内置 MCModSync-Config：1,137 bytes，SHA-256 `8FE87B233286EE596D942015197A4EA88EF74F1073D4CDAA17073BC0EAD98226`。
- `modsync.properties` 与 Config JAR 内的 bootstrap 配置指向同一套模组、资源包和服务器列表清单。
- `strict=true`、`requireManifest=true`，清单不可用时按失败关闭处理。

压缩体积主要来自：

| 类别 | 文件数 | 压缩后大小 |
| --- | ---: | ---: |
| `overrides/kubejs` | 193 | 3,718,826 bytes |
| `overrides/config` | 700 | 759,369 bytes |
| `.sable` native | 1 | 736,101 bytes |
| MCModSync 两个 JAR | 2 | 239,462 bytes |

该样本证明“10MB 启动壳”是可行的，但它不是一个适合直接发布的干净快照。

## 样本中不应发布的运行态文件

以下内容不是启动壳的权威配置，应在正式构建时排除：

- `.sable/natives/`
- `.mixin.out/`
- `debug/`
- `config/worldedit/.archive-unpack/`
- `fabricloader.log`
- `usercache.json`、`usernamecache.json`
- `command_history.txt`
- `servers.dat_old`
- 各类缓存和空下载目录

`servers.dat` 已由 MCModSync 的服务器列表清单管理时，也不应再作为普通覆盖文件重复携带。

这些文件在样本中共占约 1,105,748 bytes 压缩空间。按当前内容简单排除后，启动包预计约 4,584,573 bytes。

## 推荐的 10MB 分层

### 启动壳内置

- CurseForge/启动器 `manifest.json`。
- MCModSync 主 JAR。
- 与该版本精确匹配的 MCModSync-Config JAR。
- `modsync.properties`。
- 首次启动前必须存在的客户端配置。
- 单人世界与专用服务器玩法一致所需的 KubeJS 数据和脚本。
- 体积很小且不适合远程失效的标题资源、实例图标和基础语言文件。

### MCModSync 模组清单

- 所有普通模组 JAR。
- 必须模组标记为 required；缺失时不得进入服务器。
- 不影响协议、注册表和入服的客户端体验模组才可标记为 recommended。
- MCModSync 自身和 Config JAR 不进入自己的玩法清单，避免自替换和启动环。

### 资源包清单

- 大型纹理、音效和可选视觉资源包。
- 手机/低配资源包使用独立清单。
- 不把资源包压回启动壳。

### 女仆自定义模型包

当前 `tlm_custom_pack` 有 1,260 个文件、39,182,891 bytes；单独 ZIP 高压缩后仍约 16,554,375 bytes。因此只要把它直接放进 overrides，10MB 目标必然失败。

当前 MCModSync 只直接管理模组、资源包和服务器列表，不能把普通目录安全部署到 `tlm_custom_pack`。正式方案必须先完成以下二选一的动态验证：

1. 将模型包整理为 TLM 能从模组资源中识别的独立客户端内容模组，并由模组清单下载。
2. 为 MCModSync 增加带目标目录、路径白名单、哈希和事务回滚的通用内容包能力。

在其中一种方案通过加载测试前，不能宣称 10MB 启动包已经包含完整女仆模型体验。

## 防止 MCModSync 降级客户端

1. 每个发行版使用不可变的清单目录，不复用会被覆盖的通用 `mods-v4.txt`。
2. 清单从当前客户端权威基线生成；本仓库当前基线位于 `artifacts/client-baselines/motiquies-2.0.0-mods.json`。
3. 发布门禁必须拒绝清单中版本低于客户端基线、文件名回退或 SHA 不一致的条目。
4. 先上传全部 JAR/资源，再原子发布清单；不要先发布会引用不存在文件的清单。
5. 修复或回滚通过发布新清单版本完成，不覆盖旧版本目录中的文件。
6. 测试时可以禁用 MCModSync；最终发布前恢复两个 bootstrap JAR 和匹配配置，并先在一次性实例验证。
7. 推荐模组的删除或升级不得改变 required 模组、注册表和网络协议闭包。

## 建议的发布结果

一个合理的成品不是“把完整客户端强行压到 10MB”，而是：

- 约 4.5–6MB 的可导入启动壳。
- 一个不可变、哈希锁定的模组仓库。
- 独立资源包清单。
- 经验证的女仆模型外部分发层。
- 当前客户端基线与清单差异为零的发布报告。

这个结构既能保持首包小，也能避免 MCModSync 把用户当前较新的 MineAstr、Immersive Paintings 或其他客户端模组降级。
