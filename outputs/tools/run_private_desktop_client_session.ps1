param(
    [Parameter(Mandatory = $true)] [string] $MinecraftRoot,
    [Parameter(Mandatory = $true)] [string] $ServerAddress,
    [Parameter(Mandatory = $true)] [string] $Username,
    [Parameter(Mandatory = $true)] [string] $Uuid,
    [Parameter(Mandatory = $true)] [string] $StatePath,
    [Parameter(Mandatory = $true)] [string] $StopPath,
    [string] $Launcher = '',
    [string] $Java = 'C:\Program Files\Java\jdk-21.0.10\bin\java.exe',
    [int] $MaximumMemoryMb = 2048,
    [int] $LaunchTimeoutSeconds = 150,
    [int] $SessionTimeoutSeconds = 240
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($Launcher)) {
    $Launcher = Join-Path $PSScriptRoot 'launch_neoforge_client_isolated.ps1'
}
$root = [IO.Path]::GetFullPath($MinecraftRoot)
$launcherPath = [IO.Path]::GetFullPath($Launcher)
$javaPath = [IO.Path]::GetFullPath($Java)
$stateFile = [IO.Path]::GetFullPath($StatePath)
$stopFile = [IO.Path]::GetFullPath($StopPath)
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\') + '\'
$externalRoot = 'D:\Trans\migration-audit-work\'.ToLowerInvariant()
$rootLower = $root.ToLowerInvariant()
if (-not $root.StartsWith($workspaceRoot, [StringComparison]::OrdinalIgnoreCase) -and
    -not $rootLower.StartsWith($externalRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'MinecraftRoot must be inside the current workspace or D:\Trans\migration-audit-work'
}
if ($rootLower.StartsWith('d:\trans\20260807\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'MinecraftRoot may not be inside the historical source backup'
}
if ((Get-Item -LiteralPath $root -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'MinecraftRoot itself may not be a junction/reparse point'
}
foreach ($mutableName in @('mods', 'resourcepacks', 'natives')) {
    $mutablePath = Join-Path $root $mutableName
    if (Test-Path -LiteralPath $mutablePath -PathType Container) {
        if ((Get-Item -LiteralPath $mutablePath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "MinecraftRoot mutable directory may not be linked: $mutablePath"
        }
    }
}
foreach ($path in @($root, $launcherPath, $javaPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path is missing: $path" }
}
if ($ServerAddress -notmatch '^127\.0\.0\.1:[0-9]{1,5}$') { throw 'ServerAddress must be an isolated loopback endpoint' }
if ($Username -notmatch '^[A-Za-z0-9_]{1,16}$') { throw 'Unsafe synthetic username' }
if ($Uuid -notmatch '^[0-9a-fA-F-]{36}$') { throw 'Unsafe synthetic UUID' }

if (-not ('PrivateAuthClientNative' -as [type])) {
    Add-Type @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

public static class PrivateAuthClientNative {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct STARTUPINFO {
        public int cb;
        public string lpReserved;
        public string lpDesktop;
        public string lpTitle;
        public int dwX;
        public int dwY;
        public int dwXSize;
        public int dwYSize;
        public int dwXCountChars;
        public int dwYCountChars;
        public int dwFillAttribute;
        public int dwFlags;
        public short wShowWindow;
        public short cbReserved2;
        public IntPtr lpReserved2;
        public IntPtr hStdInput;
        public IntPtr hStdOutput;
        public IntPtr hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PROCESS_INFORMATION {
        public IntPtr hProcess;
        public IntPtr hThread;
        public int dwProcessId;
        public int dwThreadId;
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr CreateDesktop(
        string desktop, IntPtr device, IntPtr devmode, int flags,
        uint desiredAccess, IntPtr securityAttributes);
    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool CloseDesktop(IntPtr desktop);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CreateProcess(
        string applicationName, StringBuilder commandLine,
        IntPtr processAttributes, IntPtr threadAttributes,
        bool inheritHandles, uint creationFlags, IntPtr environment,
        string currentDirectory, ref STARTUPINFO startupInfo,
        out PROCESS_INFORMATION processInformation);
    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr handle);

    public static int LaunchOnDesktop(
        string desktopName, string executable, string commandLine, string workingDirectory) {
        STARTUPINFO startup = new STARTUPINFO();
        startup.cb = Marshal.SizeOf(typeof(STARTUPINFO));
        startup.lpDesktop = desktopName;
        PROCESS_INFORMATION process;
        const uint CREATE_UNICODE_ENVIRONMENT = 0x00000400;
        const uint CREATE_NO_WINDOW = 0x08000000;
        if (!CreateProcess(
            executable, new StringBuilder(commandLine), IntPtr.Zero, IntPtr.Zero,
            false, CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW, IntPtr.Zero,
            workingDirectory, ref startup, out process)) {
            throw new Win32Exception(Marshal.GetLastWin32Error());
        }
        int pid = process.dwProcessId;
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
        return pid;
    }
}
'@
}

function Quote-WindowsArgument([string] $Value) {
    if ($Value.Contains('"')) { throw 'Arguments containing quotes are not supported' }
    if ($Value -match '\s') { return '"' + $Value + '"' }
    return $Value
}

function Write-State(
    [string] $Status,
    [Nullable[int]] $JavaPid,
    [Nullable[int]] $LauncherPid,
    [string] $Stdout,
    [string] $Stderr,
    [string] $ErrorText,
    [Nullable[int]] $ExitCode,
    [object] $StartupEvidence
) {
    $value = [ordered]@{
        schema = 2
        status = $Status
        private_desktop = $true
        foreground_activation = $false
        java_pid = $JavaPid
        launcher_pid = $LauncherPid
        stdout = $Stdout
        stderr = $Stderr
        exit_code = $ExitCode
        startup_evidence = $StartupEvidence
        error = $ErrorText
        checked_at_utc = [DateTime]::UtcNow.ToString('o')
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $stateFile) -Force | Out-Null
    $temporary = $stateFile + '.tmp'
    [IO.File]::WriteAllText(
        $temporary,
        ($value | ConvertTo-Json -Depth 5) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporary -Destination $stateFile -Force
}

function Read-JsonFile([string] $Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
    catch { return $null }
}

function Wait-ExitRecord([string] $Path, [int] $TimeoutMilliseconds) {
    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
    do {
        $value = Read-JsonFile $Path
        if ($null -ne $value) { return $value }
        if ([DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
    } while ([DateTime]::UtcNow -lt $deadline)
    return $null
}

function Get-StartupEvidence(
    [string] $Stdout,
    [string] $LatestLog,
    [long] $LatestLengthBefore,
    [DateTime] $LaunchedAtUtc
) {
    if (-not [string]::IsNullOrWhiteSpace($Stdout) -and
        (Test-Path -LiteralPath $Stdout -PathType Leaf)) {
        try {
            $stdoutText = [IO.File]::ReadAllText($Stdout)
            foreach ($marker in @('JVM info:', 'ModLauncher running:')) {
                if ($stdoutText.Contains($marker)) {
                    return [ordered]@{
                        kind = 'stdout_marker'
                        marker = $marker
                        path = $Stdout
                        observed_at_utc = [DateTime]::UtcNow.ToString('o')
                    }
                }
            }
        } catch {}
    }
    if (Test-Path -LiteralPath $LatestLog -PathType Leaf) {
        try {
            $item = Get-Item -LiteralPath $LatestLog
            if ($item.Length -gt 0 -and
                ($item.Length -ne $LatestLengthBefore -or $item.LastWriteTimeUtc -ge $LaunchedAtUtc)) {
                return [ordered]@{
                    kind = 'latest_log_update'
                    marker = 'nonempty_fresh_latest_log'
                    path = $LatestLog
                    observed_at_utc = [DateTime]::UtcNow.ToString('o')
                }
            }
        } catch {}
    }
    return $null
}

function Early-ExitMessage([Nullable[int]] $ExitCode, [string] $Stdout, [string] $Stderr) {
    $code = if ($null -eq $ExitCode) { 'unavailable' } else { [string]$ExitCode }
    return "Client Java exited before controlled stop (exit_code=$code; stdout=$Stdout; stderr=$Stderr)"
}

$desktopName = 'CodexPrivateAuth_' + [Guid]::NewGuid().ToString('N')
$desktop = [PrivateAuthClientNative]::CreateDesktop(
    $desktopName, [IntPtr]::Zero, [IntPtr]::Zero, 0, [uint32]0x01FF, [IntPtr]::Zero
)
if ($desktop -eq [IntPtr]::Zero) { throw 'Unable to create the private client desktop' }

$launchResult = Join-Path $root ('.private-auth-launch-' + [Guid]::NewGuid().ToString('N') + '.json')
$launchExit = Join-Path $root ('.private-auth-exit-' + [Guid]::NewGuid().ToString('N') + '.json')
$javaPid = $null
$launcherPid = $null
$stdoutPath = ''
$stderrPath = ''
$exitCode = $null
$startupEvidence = $null
$controlledStop = $false
$failure = $null
$latestLog = Join-Path $root 'logs\latest.log'
$latestLengthBefore = if (Test-Path -LiteralPath $latestLog -PathType Leaf) {
    (Get-Item -LiteralPath $latestLog).Length
} else { [long]-1 }
try {
    if (Test-Path -LiteralPath $stateFile) { Remove-Item -LiteralPath $stateFile -Force }
    if (Test-Path -LiteralPath $stopFile) { Remove-Item -LiteralPath $stopFile -Force }
    Write-State 'STARTING' $null $null '' '' '' $null $null
    $powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $arguments = @(
        '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', $launcherPath,
        '-MinecraftRoot', $root,
        '-ServerAddress', $ServerAddress,
        '-Username', $Username,
        '-Uuid', $Uuid,
        '-Java', $javaPath,
        '-MaximumMemoryMb', [string]$MaximumMemoryMb,
        '-ResultPath', $launchResult,
        '-ExitPath', $launchExit
    )
    $commandLine = (@($powershell) + $arguments | ForEach-Object { Quote-WindowsArgument ([string]$_) }) -join ' '
    $launcherPid = [PrivateAuthClientNative]::LaunchOnDesktop(
        $desktopName, $powershell, $commandLine, $root
    )

    $launchedAtUtc = [DateTime]::UtcNow
    $launchDeadline = [DateTime]::UtcNow.AddSeconds($LaunchTimeoutSeconds)
    while (-not (Test-Path -LiteralPath $launchResult) -and [DateTime]::UtcNow -lt $launchDeadline) {
        if ($null -eq (Get-Process -Id $launcherPid -ErrorAction SilentlyContinue)) {
            throw 'Private launcher exited before producing a launch result'
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not (Test-Path -LiteralPath $launchResult)) { throw 'Private launcher did not produce a result' }
    $launch = Get-Content -LiteralPath $launchResult -Raw | ConvertFrom-Json
    $javaPid = [int]$launch.pid
    $stdoutPath = [string]$launch.stdout
    $stderrPath = [string]$launch.stderr

    while ($null -eq $startupEvidence -and [DateTime]::UtcNow -lt $launchDeadline) {
        $startupEvidence = Get-StartupEvidence $stdoutPath $latestLog `
            $latestLengthBefore $launchedAtUtc
        if ($null -ne $startupEvidence) { break }
        if ($null -eq (Get-Process -Id $javaPid -ErrorAction SilentlyContinue)) {
            $exitRecord = Wait-ExitRecord $launchExit 5000
            if ($null -ne $exitRecord) { $exitCode = [int]$exitRecord.exit_code }
            throw (Early-ExitMessage $exitCode $stdoutPath $stderrPath)
        }
        Start-Sleep -Milliseconds 250
    }
    if ($null -eq $startupEvidence) {
        throw "Client Java produced no startup evidence within $LaunchTimeoutSeconds seconds (stdout=$stdoutPath; stderr=$stderrPath)"
    }
    Write-State 'RUNNING' $javaPid $launcherPid $stdoutPath $stderrPath '' $null $startupEvidence

    $sessionDeadline = [DateTime]::UtcNow.AddSeconds($SessionTimeoutSeconds)
    while ([DateTime]::UtcNow -lt $sessionDeadline) {
        if (Test-Path -LiteralPath $stopFile) {
            $controlledStop = $true
            break
        }
        if ($null -eq (Get-Process -Id $javaPid -ErrorAction SilentlyContinue)) {
            $exitRecord = Wait-ExitRecord $launchExit 5000
            if ($null -ne $exitRecord) { $exitCode = [int]$exitRecord.exit_code }
            throw (Early-ExitMessage $exitCode $stdoutPath $stderrPath)
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $controlledStop) {
        throw "Private client session timed out before the controlled stop after $SessionTimeoutSeconds seconds"
    }
} catch {
    $failure = $_.Exception.Message
    throw
} finally {
    if ($null -ne $javaPid) {
        $process = Get-Process -Id $javaPid -ErrorAction SilentlyContinue
        if ($null -ne $process) {
            Stop-Process -Id $javaPid -Force -ErrorAction SilentlyContinue
            try { Wait-Process -Id $javaPid -Timeout 20 -ErrorAction SilentlyContinue } catch {}
        }
    }
    if ($null -ne $javaPid) {
        $exitRecord = Wait-ExitRecord $launchExit 10000
        if ($null -ne $exitRecord) { $exitCode = [int]$exitRecord.exit_code }
    }
    if ($null -ne $launcherPid) {
        $launcherProcess = Get-Process -Id $launcherPid -ErrorAction SilentlyContinue
        if ($null -ne $launcherProcess) {
            try { Wait-Process -Id $launcherPid -Timeout 10 -ErrorAction SilentlyContinue } catch {}
            $launcherProcess = Get-Process -Id $launcherPid -ErrorAction SilentlyContinue
            if ($null -ne $launcherProcess) {
                Stop-Process -Id $launcherPid -Force -ErrorAction SilentlyContinue
            }
        }
    }
    Start-Sleep -Seconds 1
    [void][PrivateAuthClientNative]::CloseDesktop($desktop)
    if (Test-Path -LiteralPath $launchResult) { Remove-Item -LiteralPath $launchResult -Force }
    if (Test-Path -LiteralPath $launchExit) { Remove-Item -LiteralPath $launchExit -Force }
    if ($null -eq $failure) {
        Write-State 'STOPPED' $javaPid $launcherPid $stdoutPath $stderrPath '' $exitCode $startupEvidence
    } else {
        Write-State 'FAILED' $javaPid $launcherPid $stdoutPath $stderrPath $failure $exitCode $startupEvidence
    }
}
