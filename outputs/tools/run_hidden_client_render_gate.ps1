param(
    [Parameter(Mandatory = $true)] [string] $MinecraftRoot,
    [Parameter(Mandatory = $true)] [string] $SingleplayerWorld,
    [Parameter(Mandatory = $true)] [string] $Username,
    [Parameter(Mandatory = $true)] [string] $Uuid,
    [Parameter(Mandatory = $true)] [string] $OutputPath,
    [Parameter(Mandatory = $true)] [string] $ResultReport,
    [string] $Launcher = '',
    [string] $Java = 'C:\Program Files\Java\jdk-21.0.10\bin\java.exe',
    [int] $MaximumMemoryMb = 4096,
    [int] $StartupTimeoutSeconds = 210,
    [int] $CaptureDelaySeconds = 10,
    [int] $GracefulWorldStopSeconds = 75
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
if ([string]::IsNullOrWhiteSpace($Launcher)) {
    $Launcher = Join-Path $PSScriptRoot 'launch_neoforge_client_isolated.ps1'
}
$root = [IO.Path]::GetFullPath($MinecraftRoot)
$launcherPath = [IO.Path]::GetFullPath($Launcher)
$javaPath = [IO.Path]::GetFullPath($Java)
$capturePath = [IO.Path]::GetFullPath($OutputPath)
$reportPath = [IO.Path]::GetFullPath($ResultReport)
foreach ($path in @($root, $launcherPath, $javaPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path is missing: $path" }
}
$auditRoot = [IO.Path]::GetFullPath('<AUDIT_ROOT>').TrimEnd('\') + '\'
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\') + '\'
if (-not $root.StartsWith($auditRoot, [StringComparison]::OrdinalIgnoreCase) -and
    -not $root.StartsWith($workspaceRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'MinecraftRoot must be inside the audit D: tree or the current workspace'
}
if ($Username -notmatch '^[A-Za-z0-9_]{1,16}$') { throw 'Unsafe synthetic username' }
if ($Uuid -notmatch '^[0-9a-fA-F-]{36}$') { throw 'Unsafe synthetic UUID' }

if (-not ('HiddenClientGateNative' -as [type])) {
    Add-Type @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

public static class HiddenClientGateNative {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

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

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr CreateDesktop(
        string desktop, IntPtr device, IntPtr devmode, int flags,
        uint desiredAccess, IntPtr securityAttributes);
    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool CloseDesktop(IntPtr desktop);
    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool EnumDesktopWindows(
        IntPtr desktop, EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetClassName(IntPtr window, StringBuilder text, int count);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr window, StringBuilder text, int count);
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr window, out RECT rect);
    [DllImport("user32.dll")]
    public static extern bool PrintWindow(IntPtr window, IntPtr hdc, uint flags);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool PostMessage(
        IntPtr window, uint message, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern IntPtr GetWindowDC(IntPtr window);
    [DllImport("user32.dll")]
    public static extern int ReleaseDC(IntPtr window, IntPtr hdc);
    [DllImport("gdi32.dll", SetLastError = true)]
    public static extern bool BitBlt(
        IntPtr destination, int x, int y, int width, int height,
        IntPtr source, int sourceX, int sourceY, uint rasterOperation);

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

function Find-GlfwWindow([IntPtr] $Desktop, [int] $ProcessId) {
    $windows = [Collections.Generic.List[object]]::new()
    $callback = [HiddenClientGateNative+EnumWindowsProc]{
        param([IntPtr] $handle, [IntPtr] $state)
        [uint32] $owner = 0
        [void][HiddenClientGateNative]::GetWindowThreadProcessId($handle, [ref]$owner)
        if ($owner -eq $ProcessId -and [HiddenClientGateNative]::IsWindowVisible($handle)) {
            $className = [Text.StringBuilder]::new(256)
            $title = [Text.StringBuilder]::new(1024)
            [void][HiddenClientGateNative]::GetClassName($handle, $className, $className.Capacity)
            [void][HiddenClientGateNative]::GetWindowText($handle, $title, $title.Capacity)
            $rect = [HiddenClientGateNative+RECT]::new()
            [void][HiddenClientGateNative]::GetWindowRect($handle, [ref]$rect)
            $windows.Add([pscustomobject]@{
                handle = $handle
                className = $className.ToString()
                title = $title.ToString()
                width = $rect.Right - $rect.Left
                height = $rect.Bottom - $rect.Top
            })
        }
        return $true
    }
    [void][HiddenClientGateNative]::EnumDesktopWindows($Desktop, $callback, [IntPtr]::Zero)
    return $windows |
        Where-Object { $_.className -eq 'GLFW30' -and $_.width -gt 0 -and $_.height -gt 0 } |
        Sort-Object { $_.width * $_.height } -Descending |
        Select-Object -First 1
}

function Get-BitmapStats([Drawing.Bitmap] $Bitmap) {
    $colors = [Collections.Generic.HashSet[int]]::new()
    $minimum = 255
    $maximum = 0
    for ($y = 0; $y -lt $Bitmap.Height; $y += 16) {
        for ($x = 0; $x -lt $Bitmap.Width; $x += 16) {
            $pixel = $Bitmap.GetPixel($x, $y)
            [void]$colors.Add($pixel.ToArgb())
            $luminance = [int](0.2126 * $pixel.R + 0.7152 * $pixel.G + 0.0722 * $pixel.B)
            if ($luminance -lt $minimum) { $minimum = $luminance }
            if ($luminance -gt $maximum) { $maximum = $luminance }
        }
    }
    return [pscustomobject]@{
        sampled_unique_colors = $colors.Count
        sampled_luminance_min = $minimum
        sampled_luminance_max = $maximum
    }
}

function Capture-MinecraftScreenshot(
    [object] $Window,
    [string] $MinecraftRoot,
    [string] $Destination
) {
    $screenshots = Join-Path $MinecraftRoot 'screenshots'
    New-Item -ItemType Directory -Path $screenshots -Force | Out-Null
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    $existing = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    Get-ChildItem -LiteralPath $screenshots -Filter '*.png' -File -ErrorAction SilentlyContinue |
        ForEach-Object { [void]$existing.Add($_.FullName) }
    $requestedAt = [DateTime]::UtcNow
    # F2 is VK_F2 (0x71), scan code 0x3c. Post directly to the GLFW window on
    # the private desktop so the user's active desktop and keyboard are untouched.
    $down = [HiddenClientGateNative]::PostMessage(
        $Window.handle, [uint32]0x0100, [IntPtr]0x71, [IntPtr]0x003C0001
    )
    Start-Sleep -Milliseconds 80
    $up = [HiddenClientGateNative]::PostMessage(
        $Window.handle, [uint32]0x0101, [IntPtr]0x71, [IntPtr]([int64]0xC03C0001)
    )
    if (-not $down -or -not $up) { return $null }
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    $source = $null
    while ([DateTime]::UtcNow -lt $deadline -and $null -eq $source) {
        $candidate = Get-ChildItem -LiteralPath $screenshots -Filter '*.png' -File -ErrorAction SilentlyContinue |
            Where-Object {
                -not $existing.Contains($_.FullName) -and
                $_.LastWriteTimeUtc -ge $requestedAt.AddSeconds(-1)
            } |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        if ($null -ne $candidate -and $candidate.Length -gt 0) {
            $firstLength = $candidate.Length
            Start-Sleep -Milliseconds 250
            $candidate.Refresh()
            if ($candidate.Length -eq $firstLength -and $candidate.Length -gt 0) {
                try {
                    $probe = [Drawing.Bitmap]::new($candidate.FullName)
                    $probe.Dispose()
                    $source = $candidate
                } catch {
                    $source = $null
                }
            }
        }
        if ($null -eq $source) { Start-Sleep -Milliseconds 250 }
    }
    if ($null -eq $source) { return $null }
    Copy-Item -LiteralPath $source.FullName -Destination $Destination -Force
    $bitmap = [Drawing.Bitmap]::new($Destination)
    $width = $bitmap.Width
    $height = $bitmap.Height
    try { $stats = Get-BitmapStats $bitmap }
    finally { $bitmap.Dispose() }
    return [pscustomobject]@{
        path = $Destination
        bytes = (Get-Item -LiteralPath $Destination).Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash
        width = $width
        height = $height
        sampled_unique_colors = $stats.sampled_unique_colors
        sampled_luminance_min = $stats.sampled_luminance_min
        sampled_luminance_max = $stats.sampled_luminance_max
        capture_method = 'MinecraftF2PostMessage'
        print_window = $false
        foreground_activation = $false
        source_screenshot = $source.FullName
    }
}

function Capture-HiddenWindow([object] $Window, [string] $Destination) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    $bitmap = [Drawing.Bitmap]::new($Window.width, $Window.height)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    $hdc = $graphics.GetHdc()
    $captured = $false
    try {
        $captured = [HiddenClientGateNative]::PrintWindow($Window.handle, $hdc, 2)
    } finally {
        $graphics.ReleaseHdc($hdc)
        $graphics.Dispose()
    }
    $stats = Get-BitmapStats $bitmap
    $captureMethod = 'PrintWindow'
    # GLFW's OpenGL surface may return a uniform white DWM surface to PrintWindow
    # on a non-interactive desktop. Copy the window DC as a second, still hidden,
    # capture path before classifying the frame as blank.
    if (-not $captured -or $stats.sampled_unique_colors -lt 64) {
        $replacement = [Drawing.Bitmap]::new($Window.width, $Window.height)
        $graphics = [Drawing.Graphics]::FromImage($replacement)
        $destinationHdc = $graphics.GetHdc()
        $sourceHdc = [HiddenClientGateNative]::GetWindowDC($Window.handle)
        $bitBltCaptured = $false
        try {
            if ($sourceHdc -ne [IntPtr]::Zero) {
                $bitBltCaptured = [HiddenClientGateNative]::BitBlt(
                    $destinationHdc, 0, 0, $Window.width, $Window.height,
                    $sourceHdc, 0, 0, [uint32]0x40CC0020)
            }
        } finally {
            if ($sourceHdc -ne [IntPtr]::Zero) {
                [void][HiddenClientGateNative]::ReleaseDC($Window.handle, $sourceHdc)
            }
            $graphics.ReleaseHdc($destinationHdc)
            $graphics.Dispose()
        }
        if ($bitBltCaptured) {
            $bitmap.Dispose()
            $bitmap = $replacement
            $stats = Get-BitmapStats $bitmap
            $captureMethod = 'BitBlt'
        } else {
            $replacement.Dispose()
            $captureMethod = 'PrintWindowBitBltUnavailable'
        }
    }
    try { $bitmap.Save($Destination, [Drawing.Imaging.ImageFormat]::Png) }
    finally { $bitmap.Dispose() }
    $sha256 = $null
    for ($attempt = 0; $attempt -lt 20 -and $null -eq $sha256; $attempt++) {
        try { $sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash }
        catch { Start-Sleep -Milliseconds 250 }
    }
    return [pscustomobject]@{
        path = $Destination
        bytes = (Get-Item -LiteralPath $Destination).Length
        sha256 = $sha256
        width = $Window.width
        height = $Window.height
        sampled_unique_colors = $stats.sampled_unique_colors
        sampled_luminance_min = $stats.sampled_luminance_min
        sampled_luminance_max = $stats.sampled_luminance_max
        capture_method = $captureMethod
        print_window = ($captureMethod -eq 'PrintWindow')
        foreground_activation = $false
    }
}

function Get-FileHashWithRetry([string] $Path) {
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash }
        catch { Start-Sleep -Milliseconds 250 }
    }
    return $null
}

$desktopName = 'CodexHiddenClientGate_' + [Guid]::NewGuid().ToString('N')
$desktopAccess = [uint32]0x01FF
$desktop = [HiddenClientGateNative]::CreateDesktop(
    $desktopName, [IntPtr]::Zero, [IntPtr]::Zero, 0, $desktopAccess, [IntPtr]::Zero
)
if ($desktop -eq [IntPtr]::Zero) { throw 'Unable to create the private client desktop' }

$launchResult = Join-Path $root ('.hidden-client-launch-' + [Guid]::NewGuid().ToString('N') + '.json')
$javaPid = $null
$capture = $null
$joined = $false
$blockers = [Collections.Generic.List[string]]::new()
$latestLog = Join-Path $root 'logs\latest.log'
try {
    $powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $arguments = @(
        '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', $launcherPath,
        '-MinecraftRoot', $root,
        '-SingleplayerWorld', $SingleplayerWorld,
        '-Username', $Username,
        '-Uuid', $Uuid,
        '-Java', $javaPath,
        '-MaximumMemoryMb', [string]$MaximumMemoryMb,
        '-ResultPath', $launchResult
    )
    $commandLine = (@($powershell) + $arguments | ForEach-Object { Quote-WindowsArgument ([string]$_) }) -join ' '
    [void][HiddenClientGateNative]::LaunchOnDesktop(
        $desktopName, $powershell, $commandLine, $root
    )

    $launchDeadline = [DateTime]::UtcNow.AddSeconds(120)
    while (-not (Test-Path -LiteralPath $launchResult) -and [DateTime]::UtcNow -lt $launchDeadline) {
        Start-Sleep -Milliseconds 250
    }
    if (-not (Test-Path -LiteralPath $launchResult)) { throw 'Hidden launcher did not produce a result' }
    $launch = Get-Content -LiteralPath $launchResult -Raw | ConvertFrom-Json
    $javaPid = [int]$launch.pid

    $deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
    $window = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($null -eq (Get-Process -Id $javaPid -ErrorAction SilentlyContinue)) { break }
        $window = Find-GlfwWindow $desktop $javaPid
        if (Test-Path -LiteralPath $latestLog) {
            $logText = Get-Content -LiteralPath $latestLog -Raw -ErrorAction SilentlyContinue
            # NeoForge may insert "(formerly known as ...)" between the
            # username and the join phrase when the synthetic profile name
            # was reused. Match the server's stable join event, not that
            # optional decoration.
            if ($logText -match ([regex]::Escape($Username) + '.*joined the game')) {
                $joined = $true
                break
            }
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $joined) { [void]$blockers.Add('CLIENT_WORLD_JOIN_NOT_OBSERVED') }
    if ($joined) { Start-Sleep -Seconds $CaptureDelaySeconds }
    $window = Find-GlfwWindow $desktop $javaPid
    if ($null -eq $window) { [void]$blockers.Add('HIDDEN_GLFW_WINDOW_NOT_FOUND') }
    else {
        $capture = Capture-MinecraftScreenshot $window $root $capturePath
        if ($null -eq $capture) {
            $capture = Capture-HiddenWindow $window $capturePath
        }
        if ($capture.sampled_unique_colors -lt 64 -or
            ($capture.sampled_luminance_max - $capture.sampled_luminance_min) -lt 32) {
            [void]$blockers.Add('CAPTURE_PIXEL_VARIANCE_TOO_LOW')
        }
    }

    $stopDeadline = [DateTime]::UtcNow.AddSeconds($GracefulWorldStopSeconds)
    while ([DateTime]::UtcNow -lt $stopDeadline -and
        $null -ne (Get-Process -Id $javaPid -ErrorAction SilentlyContinue)) {
        $logText = Get-Content -LiteralPath $latestLog -Raw -ErrorAction SilentlyContinue
        if ($logText -match 'Stopping singleplayer server' -and $logText -match 'Saving worlds') { break }
        Start-Sleep -Seconds 1
    }
} finally {
    if ($null -ne $javaPid) {
        $process = Get-Process -Id $javaPid -ErrorAction SilentlyContinue
        if ($null -ne $process) {
            Stop-Process -Id $javaPid -Force -ErrorAction SilentlyContinue
            try { Wait-Process -Id $javaPid -Timeout 15 -ErrorAction SilentlyContinue } catch {}
        }
    }
    Start-Sleep -Seconds 2
    [void][HiddenClientGateNative]::CloseDesktop($desktop)
    if (Test-Path -LiteralPath $launchResult) {
        Remove-Item -LiteralPath $launchResult -Force
    }
}

$finalLog = if (Test-Path -LiteralPath $latestLog) {
    Get-Content -LiteralPath $latestLog -Raw -ErrorAction SilentlyContinue
} else { '' }
$teaWarnings = ([regex]::Matches($finalLog, 'ender_dragon_tea.*missing model for variant')).Count
$blowgunWarnings = ([regex]::Matches($finalLog, 'blowgun_pulling_[012]')).Count
$hardMixinErrors = ([regex]::Matches(
    $finalLog,
    'MixinApplyError|MixinTransformerError|InjectionError|InvalidInjectionException|critical injection failure|mixin apply failed',
    [Text.RegularExpressions.RegexOptions]::IgnoreCase
)).Count
if ($teaWarnings -ne 0) { [void]$blockers.Add('ENDER_DRAGON_TEA_MODEL_WARNINGS') }
if ($blowgunWarnings -ne 0) { [void]$blockers.Add('BLOWGUN_MODEL_WARNINGS') }
if ($hardMixinErrors -ne 0) { [void]$blockers.Add('HARD_MIXIN_ERROR') }
if ($null -ne $javaPid -and
    $null -ne (Get-Process -Id $javaPid -ErrorAction SilentlyContinue)) {
    [void]$blockers.Add('JAVA_PROCESS_STILL_RUNNING')
}

$report = [ordered]@{
    schema = 1
    status = if ($blockers.Count -eq 0) { 'PASS' } else { 'NO_GO' }
    category = 'hidden_client_render_gate'
    generated_at_utc = [DateTime]::UtcNow.ToString('o')
    private_desktop = $true
    foreground_activation = $false
    synthetic_account = $true
    minecraft_root = $root
    singleplayer_world = $SingleplayerWorld
    username = $Username
    world_join_observed = $joined
    capture = $capture
    log = [ordered]@{
        path = $latestLog
        bytes = if (Test-Path -LiteralPath $latestLog) { (Get-Item -LiteralPath $latestLog).Length } else { 0 }
        sha256 = if (Test-Path -LiteralPath $latestLog) { Get-FileHashWithRetry $latestLog } else { $null }
        ender_dragon_tea_model_warnings = $teaWarnings
        blowgun_model_warnings = $blowgunWarnings
        hard_mixin_errors = $hardMixinErrors
    }
    blockers = @($blockers | Sort-Object -Unique)
}
New-Item -ItemType Directory -Path (Split-Path -Parent $reportPath) -Force | Out-Null
[IO.File]::WriteAllText(
    $reportPath,
    ($report | ConvertTo-Json -Depth 12) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)
$report
if ($blockers.Count -eq 0) { exit 0 }
exit 2
