param(
    [Parameter(Mandatory = $true)] [int] $TargetProcessId,
    [Parameter(Mandatory = $true)] [string] $Message
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
if (-not ('ClientGateInputNative' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class ClientGateInputNative {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetClassName(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int command);
}
'@
}

$handles = [System.Collections.Generic.List[IntPtr]]::new()
$callback = [ClientGateInputNative+EnumWindowsProc]{
    param([IntPtr] $handle, [IntPtr] $state)
    [uint32] $owner = 0
    [void][ClientGateInputNative]::GetWindowThreadProcessId($handle, [ref]$owner)
    if ($owner -eq $TargetProcessId -and [ClientGateInputNative]::IsWindowVisible($handle)) {
        $className = [Text.StringBuilder]::new(256)
        [void][ClientGateInputNative]::GetClassName($handle, $className, $className.Capacity)
        if ($className.ToString() -eq 'GLFW30') {
            $handles.Add($handle)
        }
    }
    return $true
}
[void][ClientGateInputNative]::EnumWindows($callback, [IntPtr]::Zero)
if ($handles.Count -ne 1) {
    throw "Expected one visible GLFW30 window for process $TargetProcessId; found $($handles.Count)"
}

$handle = $handles[0]
[void][ClientGateInputNative]::ShowWindow($handle, 9)
[void][ClientGateInputNative]::BringWindowToTop($handle)
if (-not [ClientGateInputNative]::SetForegroundWindow($handle)) {
    throw 'SetForegroundWindow returned false'
}
Start-Sleep -Milliseconds 500
[Windows.Forms.SendKeys]::SendWait('t')
Start-Sleep -Milliseconds 200
[Windows.Forms.SendKeys]::SendWait($Message)
[Windows.Forms.SendKeys]::SendWait('{ENTER}')

[pscustomobject]@{
    processId = $TargetProcessId
    handle = $handle
    characters = $Message.Length
}
