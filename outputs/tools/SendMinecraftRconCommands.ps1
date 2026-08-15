param(
    [Parameter(Mandatory = $true)][int]$Port,
    [Parameter(Mandatory = $true)][string]$CommandFile,
    [Parameter(Mandatory = $true)][string]$OutputFile,
    [string]$Password = 'cookery-smoke-local-only'
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Read-Exact([IO.Stream]$Stream, [int]$Count) {
    $buffer = New-Object byte[] $Count
    $offset = 0
    while ($offset -lt $Count) {
        $read = $Stream.Read($buffer, $offset, $Count - $offset)
        if ($read -le 0) {
            throw 'RCON connection closed unexpectedly'
        }
        $offset += $read
    }
    return $buffer
}

function Write-Packet([IO.Stream]$Stream, [int]$Id, [int]$Type, [string]$Body) {
    $bodyBytes = [Text.Encoding]::UTF8.GetBytes($Body)
    $length = 4 + 4 + $bodyBytes.Length + 2
    $packet = New-Object byte[] ($length + 4)
    [BitConverter]::GetBytes($length).CopyTo($packet, 0)
    [BitConverter]::GetBytes($Id).CopyTo($packet, 4)
    [BitConverter]::GetBytes($Type).CopyTo($packet, 8)
    $bodyBytes.CopyTo($packet, 12)
    $Stream.Write($packet, 0, $packet.Length)
    $Stream.Flush()
}

function Read-Packet([IO.Stream]$Stream) {
    $length = [BitConverter]::ToInt32((Read-Exact $Stream 4), 0)
    if ($length -lt 10 -or $length -gt 1048576) {
        throw "Invalid RCON packet length: $length"
    }
    $data = Read-Exact $Stream $length
    return [pscustomobject]@{
        Id = [BitConverter]::ToInt32($data, 0)
        Type = [BitConverter]::ToInt32($data, 4)
        Body = [Text.Encoding]::UTF8.GetString($data, 8, $length - 10)
    }
}

$commands = [IO.File]::ReadAllLines((Resolve-Path -LiteralPath $CommandFile)) |
        Where-Object { $_.Trim().Length -gt 0 -and -not $_.TrimStart().StartsWith('#') }
$lines = [Collections.Generic.List[string]]::new()
$client = New-Object Net.Sockets.TcpClient
try {
    $client.Connect('127.0.0.1', $Port)
    $stream = $client.GetStream()
    $stream.ReadTimeout = 10000
    $stream.WriteTimeout = 10000
    Write-Packet $stream 4100 3 $Password
    $auth = Read-Packet $stream
    if ($auth.Id -eq -1) {
        throw 'RCON authentication failed'
    }

    $id = 4200
    foreach ($command in $commands) {
        Write-Packet $stream $id 2 $command
        $response = Read-Packet $stream
        if ($response.Id -ne $id) {
            throw "Unexpected RCON response id $($response.Id), expected $id"
        }
        $lines.Add("COMMAND: $command")
        $lines.Add("RESPONSE: $($response.Body)")
        $lines.Add('')
        $id += 1
    }
} finally {
    $client.Dispose()
}

$outputPath = [IO.Path]::GetFullPath($OutputFile)
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($outputPath)) | Out-Null
[IO.File]::WriteAllLines($outputPath, $lines, $utf8)
Write-Output "RCON commands completed: $($commands.Count)"
Write-Output "Output: $outputPath"
