param(
    [Parameter(Mandatory = $true)] [int] $TargetProcessId,
    [Parameter(Mandatory = $true)] [string] $OutputPath,
    [switch] $ScreenCapture
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
if (-not ('ClientGateNative' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class ClientGateNative {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }

    [DllImport("user32.dll")]
    public static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetClassName(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")]
    public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
    [DllImport("user32.dll")]
    public static extern bool SetWindowPos(IntPtr hWnd, IntPtr insertAfter, int x, int y, int width, int height, uint flags);
    [DllImport("dwmapi.dll")]
    public static extern int DwmFlush();
}
'@
}

[void][ClientGateNative]::SetProcessDpiAwarenessContext([IntPtr](-4))
$windows = [System.Collections.Generic.List[object]]::new()
$callback = [ClientGateNative+EnumWindowsProc]{
    param([IntPtr] $handle, [IntPtr] $state)
    [uint32] $owner = 0
    [void][ClientGateNative]::GetWindowThreadProcessId($handle, [ref]$owner)
    if ($owner -eq $TargetProcessId -and [ClientGateNative]::IsWindowVisible($handle)) {
        $title = [Text.StringBuilder]::new(1024)
        $className = [Text.StringBuilder]::new(256)
        [void][ClientGateNative]::GetWindowText($handle, $title, $title.Capacity)
        [void][ClientGateNative]::GetClassName($handle, $className, $className.Capacity)
        $rect = [ClientGateNative+RECT]::new()
        [void][ClientGateNative]::GetWindowRect($handle, [ref]$rect)
        $windows.Add([pscustomobject]@{
            handle = $handle
            title = $title.ToString()
            className = $className.ToString()
            left = $rect.Left
            top = $rect.Top
            width = $rect.Right - $rect.Left
            height = $rect.Bottom - $rect.Top
        })
    }
    return $true
}
[void][ClientGateNative]::EnumWindows($callback, [IntPtr]::Zero)
$window = $windows |
    Where-Object { $_.className -eq 'GLFW30' -and $_.width -gt 0 -and $_.height -gt 0 } |
    Sort-Object { $_.width * $_.height } -Descending |
    Select-Object -First 1
if ($null -eq $window) {
    throw "No visible GLFW30 window belongs to process $TargetProcessId"
}

$destination = [IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
$bitmap = [Drawing.Bitmap]::new($window.width, $window.height)
$graphics = [Drawing.Graphics]::FromImage($bitmap)
$captureMethod = 'PrintWindow'
if ($ScreenCapture) {
    $captureMethod = 'CopyFromScreen'
    $topmost = [IntPtr](-1)
    $notTopmost = [IntPtr](-2)
    $noMoveNoSizeNoActivate = [uint32]0x13
    [void][ClientGateNative]::SetWindowPos($window.handle, $topmost, 0, 0, 0, 0, $noMoveNoSizeNoActivate)
    try {
        [void][ClientGateNative]::DwmFlush()
        Start-Sleep -Milliseconds 750
        $graphics.CopyFromScreen($window.left, $window.top, 0, 0, [Drawing.Size]::new($window.width, $window.height), [Drawing.CopyPixelOperation]::SourceCopy)
    } finally {
        [void][ClientGateNative]::SetWindowPos($window.handle, $notTopmost, 0, 0, 0, 0, $noMoveNoSizeNoActivate)
    }
} else {
    $hdc = $graphics.GetHdc()
    try {
        if (-not [ClientGateNative]::PrintWindow($window.handle, $hdc, 2)) {
            throw 'PrintWindow returned false'
        }
    } finally {
        $graphics.ReleaseHdc($hdc)
    }
}
$graphics.Dispose()
try {
    $bitmap.Save($destination, [Drawing.Imaging.ImageFormat]::Png)
} finally {
    $bitmap.Dispose()
}

[pscustomobject]@{
    processId = $TargetProcessId
    handle = $window.handle
    title = $window.title
    className = $window.className
    left = $window.left
    top = $window.top
    width = $window.width
    height = $window.height
    captureMethod = $captureMethod
    output = $destination
    sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash
}
