$ErrorActionPreference='Stop'
$scriptPath=Join-Path $PSScriptRoot 'prepare_candidate14_client_root.ps1'
$tokens=$null;$errors=$null
[Management.Automation.Language.Parser]::ParseFile($scriptPath,[ref]$tokens,[ref]$errors)|Out-Null
if(@($errors).Count-ne 0){throw "Parser errors: $(@($errors).Message -join '; ')"}
$text=Get-Content -Raw -LiteralPath $scriptPath
foreach($needle in @('final-mod-bundles-candidate14-20260812','client-gate-candidate14\.minecraft','9604DAAA949F66CE5B52125C57D5E3FDD0E6ABBEBDB84B8CACEE0BEE3C625818','7D585E8CEF1E47141E90DBAA6107A06082E6CDDEE401444A4E37CF5BB0A1E1A1','4B5598E6D535AD7DD05081DFA9FB77CE98F7FC2F8C9759D5C29FDD48F5C435D1','B695495FCC7B918F326A2DEB82F79A4185F4A2AD9613CC4FF3B90CE73C85663E','mcmodsync_runtime_install=''NOT_INSTALLED''','server_properties_modified=$false')){if(-not$text.Contains($needle)){throw "Missing Candidate14 binding: $needle"}}
foreach($needle in @('Start-Process','java.exe','javaw.exe','prismlauncher.exe')){if($text.Contains($needle)){throw "Forbidden preparation action: $needle"}}
$preflight=& $scriptPath -PreflightOnly|ConvertFrom-Json
if($preflight.status-cne'PREFLIGHT_PASS'-or[int]$preflight.client_file_count-ne 54-or[int]$preflight.server.port-ne 12341-or$preflight.server.accept_remote_resource_pack-ne$false-or$preflight.mcmodsync_runtime_install-cne'NOT_INSTALLED'-or$preflight.writes_performed-ne 0){throw 'Candidate14 preparation preflight contract failed'}
[ordered]@{status='PASS';parser_errors=0;client_jars=54;server_port=12341;remote_resource_pack='REJECT';mcmodsync='NOT_INSTALLED';writes=0;java_started=$false;prism_started=$false}|ConvertTo-Json
