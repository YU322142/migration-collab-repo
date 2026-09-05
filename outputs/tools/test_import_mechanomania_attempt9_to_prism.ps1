$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'import_mechanomania_attempt9_to_prism.ps1'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$tokens = $null; $errors = $null
[Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors) | Out-Null
if (@($errors).Count -ne 0) { throw "Parser errors: $(@($errors).Message -join '; ')" }

$text = [IO.File]::ReadAllText($scriptPath, [Text.Encoding]::UTF8)
foreach ($needle in @(
    'Mechanomania-Matched-Attempt9-NeoForge-1.21.1-20260814',
    'Minecraft 1.21.1 / NeoForge 21.1.241',
    'Refusing to overwrite existing Mechanomania Attempt9 Prism instance',
    'Attempt9 PASS gate report required before Prism import',
    'GLOBALLY_DISABLED',
    '127.0.0.1:12341',
    'acceptTextures',
    'JoinServerOnLaunch=false',
    'permanent_mod_count_cap = $false',
    "@('assets', 'libraries', 'versions')",
    "@('config', 'data', 'defaultconfigs', 'mods', 'resourcepacks', 'xaero')",
    '[IO.FileMode]::CreateNew',
    'java_started_by_importer = $false',
    'prism_started_by_importer = $false'
)) {
    if (-not $text.Contains($needle)) { throw "Missing Attempt9 Prism importer safety binding: $needle" }
}
foreach ($needle in @('Start-Process', 'prismlauncher.exe', 'java.exe', 'javaw.exe', 'JoinServerOnLaunch=true')) {
    if ($text.Contains($needle)) { throw "Forbidden Attempt9 Prism importer action: $needle" }
}

$tag = [Guid]::NewGuid().ToString('N')
$report = Join-Path $workspace ("outputs\test-mechanomania-attempt9-prism-preflight-$tag.json")
$sidecar = $report + '.sha256'
$missingGate = "<AUDIT_ROOT>\test-only-missing-attempt9-gate-$tag.json"
try {
    if (Test-Path -LiteralPath $missingGate) { throw "Test-only missing gate unexpectedly exists: $missingGate" }
    $summary = & $scriptPath -PreflightOnly -GateReport $missingGate -Report $report | ConvertFrom-Json
    if ($summary.status -cne 'PREFLIGHT_PASS' -or $summary.gate_status -cne 'PENDING' -or $summary.import_allowed -ne $false -or $summary.java_started -ne $false -or $summary.prism_started -ne $false) { throw 'Attempt9 Prism preflight stdout contract failed' }
    if (-not (Test-Path -LiteralPath $report -PathType Leaf) -or -not (Test-Path -LiteralPath $sidecar -PathType Leaf)) { throw 'Attempt9 Prism preflight evidence/sidecar missing' }
    $value = [IO.File]::ReadAllText($report, [Text.Encoding]::UTF8) | ConvertFrom-Json
    $expectedTargetLeaf = ([char]0x52A8) + ([char]0x9759) + ([char]0x4EA4) + ([char]0x6620) + '-Mechanomania-Matched-Attempt9-NeoForge-1.21.1-20260814'
    if (
        $value.status -cne 'PREFLIGHT_PASS' -or [int]$value.attempt -ne 9 -or
        [IO.Path]::GetFileName([string]$value.target_instance) -cne $expectedTargetLeaf -or
        $value.target_already_exists -ne $false -or $value.import_blocked_until_matching_gate_pass -ne $true -or
        [string]$value.minecraft -cne '1.21.1' -or [string]$value.neoforge -cne '21.1.241' -or
        [int]$value.memory.minimum_mb -ne 2048 -or [int]$value.memory.maximum_mb -ne 4096 -or
        [string]$value.server.address -cne '127.0.0.1:12341' -or $value.server.acceptTextures -ne $false -or $value.server.auto_join -ne $false -or
        [int]$value.mcmodsync.active_mods -ne 0 -or [int]$value.mcmodsync.active_config -ne 0 -or [string]$value.mcmodsync.policy -cne 'GLOBALLY_DISABLED' -or
        [int]$value.mods.active_jar_count -lt 247 -or $value.mods.permanent_mod_count_cap -ne $false -or
        @($value.copied_mutable_directories | Where-Object { $_ -in @('mods', 'resourcepacks', 'xaero') }).Count -ne 3 -or
        [string]$value.local_resource_pack.sha256 -cne '614ABDF34F7CFDB7974474A645BFA71CC4CA2E67F609983616E61474A57E3364' -or
        [string]$value.shared_junction_targets.assets -notmatch '^D:\\' -or [string]$value.shared_junction_targets.libraries -notmatch '^D:\\' -or [string]$value.shared_junction_targets.versions -notmatch '^D:\\' -or
        [int]$value.source_or_prism_instance_writes -ne 0 -or $value.java_started -ne $false -or $value.prism_started -ne $false
    ) { throw 'Attempt9 Prism preflight evidence contract failed' }
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $report).Hash.ToUpperInvariant()
    $sidecarText = [IO.File]::ReadAllText($sidecar, [Text.Encoding]::UTF8)
    if (-not $sidecarText.StartsWith($actualHash + '  ', [StringComparison]::Ordinal)) { throw 'Attempt9 Prism preflight SHA256 sidecar mismatch' }
    [ordered]@{
        status = 'PASS'; parser_errors = 0; attempt = 9; active_client_jars = [int]$value.mods.active_jar_count
        copied_mutable_directories = @($value.copied_mutable_directories).Count; xaero_copied = $true; resourcepacks_copied = $true
        mcmodsync_active_mods = 0; mcmodsync_active_config = 0; minecraft = '1.21.1'; neoforge = '21.1.241'
        memory = '2048-4096 MiB'; manual_server = '127.0.0.1:12341'; acceptTextures = $false; auto_join = $false
        gate_required_for_real_import = $true; target_writes = 0; java_started = $false; prism_started = $false
    } | ConvertTo-Json -Depth 6
} finally {
    if (Test-Path -LiteralPath $sidecar -PathType Leaf) { Remove-Item -LiteralPath $sidecar -Force }
    if (Test-Path -LiteralPath $report -PathType Leaf) { Remove-Item -LiteralPath $report -Force }
}
