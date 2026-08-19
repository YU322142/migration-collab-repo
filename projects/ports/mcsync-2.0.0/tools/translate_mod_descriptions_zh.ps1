param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [int]$ThrottleLimit = 12
)

$ErrorActionPreference = 'Stop'
$manifest = (Resolve-Path -LiteralPath $ManifestPath).Path
$backup = [System.IO.Path]::GetFullPath($BackupPath)
$document = Get-Content -Raw -LiteralPath $manifest | ConvertFrom-Json
$mods = @($document.files | Where-Object { $_.kind -eq 'mod' })

function Set-JsonField([object]$Object, [string]$Name, [object]$Value) {
    if ($null -ne $Object.PSObject.Properties[$Name]) {
        $Object.$Name = $Value
    } else {
        $Object | Add-Member -MemberType NoteProperty -Name $Name -Value $Value
    }
}

$manual = @{
    'mods/MCSync-2.0.0.jar' = @{
        Name = 'MCSync'; Version = '2.0.0'
        Zh = '在游戏启动早期检查并同步必须/推荐模组、资源包、光影、服务器列表和受管配置，支持哈希校验、防降级与自更新。'
    }
    'mods/backport-1.5-cat-serializer-fix.1.jar' = @{
        Zh = '将新版 Minecraft 的内容和兼容行为回移到 1.21.1，并包含本整合包所需的动物变体序列化修复。'
    }
    'mods/biomespy-neoforge-1.21.1-1.3.3.jar' = @{
        Zh = '用于查看和分析生物群系信息的客户端辅助工具；不安装也能加入服务器。'
    }
    'mods/c6c-1.2.5.1-purified-sp-parity.1.jar' = @{
        Name = 'C6C 单人玩法一致性补丁'
        Zh = '让单人游戏复现服务器中的 C6C 女仆收集、组合增益和相关玩法规则；登录系统除外。'
    }
    'mods/c6c-1.2.5.1-purified.jar' = @{
        Zh = '围绕东方女仆模型的收集与组合提供增益、任务和配套玩法机制。'
    }
    'mods/immersive_paintings-neoforge-1.21.1-0.7.14-motiquies.7.jar' = @{
        Name = 'Immersive Paintings（沉浸式画作）'
        Zh = '允许玩家上传并在世界中展示自定义图片，并包含本整合包的 MineAstr 图片翻译与准星显示兼容。'
    }
    'mods/xiyuslogin-1.4-migration6.jar' = @{
        Name = 'XiyusLogin'
        Zh = '为离线模式专用服务器提供密码登录保护，并与 TrueUUID 正版验证联动；单人游戏自动绕过登录流程。'
    }
}

$nameCorrections = @{
    'Better Advancements' = '改善模组环境中的 Minecraft 进度界面与操作体验。'
    'Configured Defaults' = '为整合包中的配置等缺省文件提供默认内容，是整合包制作与维护工具。'
    'Construction Sticks' = '提供建筑手杖，可一次延伸放置大量方块，并通过不同核心实现隔空搭建、背面放置和快速拆除。'
    'Create: Cyber Goggles' = '机械动力客户端辅助模组，通过可组合的功能模块提供信息显示与操作帮助。'
    'Create: Dragons Plus' = '为 DragonsPlusMinecraft 系列机械动力附属提供共用功能的前置库。'
    'Dungeons and Taverns Ancient City Overhaul' = '《Dungeons and Taverns》远古城市重制内容的独立分支版本。'
    'Forge Config API Port' = '将 NeoForge/Forge 配置系统带到其他模组加载平台，为多加载器模组提供统一配置接口。'
    'Hopo Better Ruined Portal' = '重新设计废弃传送门结构，使其在世界中拥有更丰富、更自然的外观。'
    'IMBlocker' = '在不输入文字时自动关闭输入法，减少游戏按键被输入法错误拦截的问题。'
    'Inventory Profiles Next' = '提供物品栏整理、自动补货、锁定槽位和物品栏配置档案等客户端功能。'
    'Jade' = '在准星指向方块或实体时显示其名称、状态与模组信息，是 Hwyla 的现代化分支。'
    'Jade Addons' = '为 Jade 增加更多模组内容的信息显示支持。'
    'Nature''s Compass' = '使用自然罗盘搜索指定生物群系，并查看距离、坐标等相关信息。'
    'Placebo' = 'Apotheosis 等模组使用的共用前置库，本身几乎不添加独立玩法内容。'
    'Retraining' = '允许刷新或重新选择村民交易，减少反复更换村民工作站的操作。'
    'Searchables' = '为配置界面等功能提供带自动补全和多种匹配方式的搜索栏前置库。'
    'Simple Backups' = '按照计划自动创建世界备份的服务端备份模组。'
    'UsefulSlime' = '为黏液球和黏液相关材料增加更多实用配方与用途。'
    'Advanced Netherite' = '在原版下界合金之上增加更多装备等级，与原版和其他附属模组保持良好兼容。'
    'Architectury' = '为多加载器模组提供通用开发接口，减少 Fabric 与 NeoForge 平台间的重复实现。'
    'Balm' = '为 Blay 系列多平台模组提供通用抽象层和共用功能。'
    'Baubley Heart Canisters' = '增加可装备在 Curios 饰品槽中的心之容器，用于提升角色生命值。'
    'BiggerBetterEndCities' = '重制末地城生成，使结构规模更大、布局更丰富。'
    'Create Bits ''n'' Bobs' = '为机械动力增加装饰方块与多种小型机械组件。'
    'Carry On' = '允许玩家徒手搬起方块实体和部分生物，并将它们移动到其他位置。'
    'Chefs Delight' = '农夫乐事附属，为村民增加厨师相关职业与配套内容。'
    'Chest Colorizer' = '为原版箱子和木桶提供客户端颜色标记，并兼容整合包既有的 colorizer.csv 格式。'
    'Colorful Hearts' = '用彩色心形将多行生命值压缩为一行显示的客户端界面模组。'
    'Colorwheel' = '为 Iris 光影与 Flywheel/机械动力渲染提供兼容支持。'
    'Configured' = '为模组配置提供统一、易用的游戏内图形设置界面。'
    'connector' = '使部分 Fabric 模组能够在 NeoForge 环境中运行的兼容层。'
    'Create' = '以旋转动力、传动机构和自动化生产线为核心的机械工程模组。'
    'Create Aeronautics' = '以物理化移动结构扩展机械动力，可建造汽车、飞艇和飞机；本整合版本包含 Simulated、Aeronautics 与 Offroad。'
    'Create: Central Kitchen' = '将农夫乐事等烹饪内容接入机械动力自动化系统。'
    'Create: Enchantment Industry' = '使用机械动力设备自动处理附魔、经验、强化与相关魔法工序。'
    'Create: Not Enough Resources For A Dummy' = '调整机械动力 Fly 更新后的混合与压实配方，维持整合包既有生产流程。'
    'Create: Avionics' = '为机械动力航空载具提供航电与资源处理相关组件。'
    'Create: Easy Structures' = '在世界中加入使用机械动力方块构成的特色结构。'
    'Create Tweaked Controllers' = '机械动力附属，通过高级控制器为移动结构提供更灵活的操控方式，兼容 Create 6.0.0 及以上版本。'
    'Create Big Cannons' = '为机械动力加入火炮、弹药、装填设备和完整的火炮工程系统。'
    'Create: Gears and Tavern' = '将万花筒酒馆的酿造与加工内容接入机械动力自动化。'
    'Create: Rail Grinding' = '为机械动力列车轨道加入滑轨玩法，可穿戴潜水靴在轨道上滑行。'
    'Create: Extra Gauges' = '为 Create: Connected 增加更多仪表与状态显示组件。'
    'Create: Storage' = '由 FoxyNoTail 制作的机械动力风格存储系统。'
    'Deployer' = '用于简化机械动力附属开发中常见功能的前置库。'
    'Drive By Wire' = '将线控驾驶功能移植到 Sable，使玩家能够通过线缆控制物理载具。'
    'End''s Delight' = '农夫乐事的末地附属，增加末地食材、料理和烹饪玩法。'
    'Create: Escalated' = '为机械动力建筑加入垂直运输和高处施工相关内容。'
    'Fabric Language Kotlin' = '为 Fabric 模组提供 Kotlin 语言加载与运行支持。'
    'Flat Bedrock' = '将主世界和下界底部不规则的原版基岩层改为平整基岩层。'
    'Forgified Fabric API' = '为 NeoForge 上运行的 Fabric 模组提供 Fabric API 核心接口与兼容钩子。'
    'FTB Library' = 'FTB 系列模组共用的基础前置库，本身不提供独立玩法内容。'
    'FTB Quests' = '提供可视化任务编辑、任务进度、奖励和多人协作任务系统。'
    'FTB Teams' = '提供队伍创建、成员管理以及任务等模组需要的团队数据。'
    'GeckoLib 4' = '面向 Minecraft 模组的高级动画引擎，支持 3D 关键帧、缓动、并行动画、声音与粒子事件。'
    'Hot Bath' = '增加浴缸、淋浴与配套浴室装饰，让玩家可以在清水与热水中沐浴。'
    'Iron''s Lib' = '为 Iron431 系列模组提供共用代码、数据结构和功能支持。'
    'KubeJS' = '使用 JavaScript 定制整合包或服务器的配方、事件、资源与玩法逻辑。'
    'L2Hostility' = '强化敌对生物并赋予其特殊词条、能力与成长机制。'
    'Mechanicals Lib' = '为相关机械类附属模组提供共用功能的前置库。'
    'Moog''s End Structures' = '使用原版方块与实体在末地生成多种新结构、敌人和战利品，同时保持接近原版的视觉风格。'
    'Modular Golems' = '以类似匠魂的模块化方式组装金属傀儡和人形傀儡。'
    'Particular Reforged' = '通过大量精心制作的粒子和视觉效果增强 Minecraft 的环境氛围。'
    'Repurposed Structures' = '将原版结构重新组合并扩展到更多生物群系，增加世界生成的多样性。'
    'Resourcefulconfig' = '为跨平台模组提供统一的配置文件创建与管理前置库。'
    'Resourceful Lib' = 'Team Resourceful 系列模组使用的共用前置库。'
    'Rhino' = '经模组环境适配的 Mozilla Rhino JavaScript 引擎分支，是 KubeJS 的重要前置。'
    'ServerWarashi' = '用于管理区块加载与服务器区块状态的服务端工具模组。'
    'Showcase Item' = '允许玩家在聊天消息中展示手持物品及其详细信息。'
    'Simulated Gauges' = '为 Create: Simulated 增加可由机械手操作的仪表，并可与 Extra Gauges 配合使用。'
    'Create: Smart Bounds' = '优化机械动力方块实体的渲染边界，减少不必要的区块渲染开销。'
    'Tom''s Simple Storage Mod - Unofficial Stability Fork' = 'Tom 简易存储的非官方 NeoForge 1.21.1 稳定性分支；保留完整功能，并修复大型存储网络、机械动力物品保险库去重、重启恢复、终端容量和按数量转移配方等问题。'
    'Touhou Little Maid' = '受 LittleMaidReengaged 启发的新版东方女仆模组，提供女仆养成、工作、战斗、模型包和相关玩法。'
    'Create Tracks' = '为 Create: Simulated Offroad 增加可调悬挂控制键和由 Sable 驱动的履带方块。'
    'Create: Trading Floor' = '使用机械动力设备自动完成与村民的交易。'
    'TrueUUID' = '用于离线模式服务器的正版身份验证模组；登录时安全验证正版账号，访问令牌始终保留在玩家客户端。'
    'Untitled Duck Mod' = '为 Forge/Fabric 加入鸭子和鹅，并使用 GeckoLib 与 Architectury 提供跨平台动画支持。'
    'Veil' = '为模组开发者提供现代渲染管线与游戏引擎功能的高级前置库。'
    'William Wythers'' Overhauled Overworld' = '以更真实、更有氛围的方式重制原版主世界生物群系。'
    'Fast Noise Mod' = '优化世界生成使用的噪声计算，提高地形与生物群系生成性能。'
}

$requests = @()
foreach ($mod in $mods) {
    if ($manual.ContainsKey([string]$mod.path)) { continue }
    $english = [string]$mod.descriptionEn
    if ([string]::IsNullOrWhiteSpace($english)) { continue }
    $requests += [pscustomobject]@{ Path = [string]$mod.path; Text = $english.Trim() }
}

$translations = $requests | ForEach-Object -Parallel {
    $item = $_
    $translated = $null
    $lastError = $null
    for ($attempt = 1; $attempt -le 4 -and [string]::IsNullOrWhiteSpace($translated); $attempt++) {
        try {
            $query = [uri]::EscapeDataString($item.Text)
            $uri = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q=$query"
            $response = Invoke-RestMethod -Uri $uri -TimeoutSec 30
            $parts = @($response[0] | ForEach-Object { [string]$_[0] })
            $translated = ($parts -join '').Trim()
        } catch {
            $lastError = $_.Exception.Message
            Start-Sleep -Milliseconds (250 * $attempt)
        }
    }
    [pscustomobject]@{ Path = $item.Path; Text = $translated; Error = $lastError }
} -ThrottleLimit $ThrottleLimit

$byPath = @{}
foreach ($translation in $translations) { $byPath[[string]$translation.Path] = $translation }
$failed = @()
foreach ($mod in $mods) {
    $path = [string]$mod.path
    if ($manual.ContainsKey($path)) {
        $value = $manual[$path]
        if ($value.Name) { Set-JsonField $mod 'displayName' $value.Name }
        if ($value.Version) { Set-JsonField $mod 'version' $value.Version }
        Set-JsonField $mod 'descriptionZh' $value.Zh
        continue
    }
    $translation = $byPath[$path]
    $chinese = if ($null -ne $translation) { [string]$translation.Text } else { '' }
    $chinese = $chinese -replace '§[0-9A-FK-ORa-fk-or]', ''
    $chinese = $chinese -replace '《?我的世界》?', 'Minecraft'
    $chinese = $chinese -replace '客户端侧', '客户端'
    $chinese = $chinese -replace '服务器端', '服务端'
    $chinese = $chinese -replace '\bmod\b', '模组'
    $chinese = $chinese.Trim()
    if ($chinese -notmatch '[\u3400-\u9fff]') {
        $role = if ([bool]$mod.required) {
            '为整合包提供玩法内容、兼容功能或必要依赖，加入服务器时必须安装。'
        } else {
            '提供客户端界面、渲染、性能或辅助功能，不安装也能加入服务器。'
        }
        $name = if ([string]::IsNullOrWhiteSpace([string]$mod.displayName)) { [string]$mod.path } else { [string]$mod.displayName }
        $chinese = "$name：$role"
        $failed += $path
    }
    Set-JsonField $mod 'descriptionZh' $chinese
}

foreach ($mod in $mods) {
    $name = [string]$mod.displayName
    if ($nameCorrections.ContainsKey($name)) {
        Set-JsonField $mod 'descriptionZh' $nameCorrections[$name]
    }
}

$backupDirectory = Split-Path -Parent $backup
if ($backupDirectory) { [System.IO.Directory]::CreateDirectory($backupDirectory) | Out-Null }
if (-not (Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $manifest -Destination $backup }
$json = $document | ConvertTo-Json -Depth 100 -Compress
[System.IO.File]::WriteAllText($manifest, $json + "`n", [System.Text.UTF8Encoding]::new($false))

$remaining = @($mods | Where-Object { [string]$_.descriptionZh -notmatch '[\u3400-\u9fff]' })
if ($remaining.Count -ne 0) { throw "仍有 $($remaining.Count) 个 Mod 缺少中文描述" }
Write-Host "Translated=$($mods.Count - $manual.Count) Manual=$($manual.Count) Fallback=$($failed.Count) Total=$($mods.Count)"
if ($failed.Count -gt 0) { Write-Host ("Fallback paths: " + ($failed -join ', ')) }
