[CmdletBinding()]
param(
    [string]$Playlist,
    [string]$Source = 'https://raw.githubusercontent.com/Guovin/TV/gd/output/result.m3u',
    [int]$MinimumEntries = 500
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if (-not $Playlist) { $Playlist = Join-Path $PSScriptRoot 'APTV_ALL.m3u' }

Write-Host "Downloading speed-tested playlist from $Source ..."
$response = Invoke-WebRequest -UseBasicParsing -Uri $Source -TimeoutSec 60
$text = [string]$response.Content
$lines = @($text -split "`r?`n")
$entryCount = @($lines | Where-Object { $_ -like '#EXTINF:*' }).Count
$urlCount = @($lines | Where-Object { $_ -match '^(?:https?|rtsp|rtmp|udp)://' }).Count

if (-not $text.TrimStart().StartsWith('#EXTM3U')) {
    throw 'Downloaded content is not an M3U playlist; the existing file was not changed.'
}
if ($entryCount -lt $MinimumEntries -or $urlCount -lt $MinimumEntries) {
    throw "Downloaded playlist is unexpectedly small (entries=$entryCount, URLs=$urlCount); the existing file was not changed."
}

$directory = Split-Path -Parent ([IO.Path]::GetFullPath($Playlist))
$temp = Join-Path $directory 'APTV_ALL.m3u.download'
$backup = "$Playlist.$(Get-Date -Format 'yyyyMMdd-HHmmss').bak"
[IO.File]::WriteAllText($temp, ($lines -join "`n").TrimEnd() + "`n", [Text.UTF8Encoding]::new($false))

if (Test-Path -LiteralPath $Playlist) { [IO.File]::Copy($Playlist, $backup, $false) }
[IO.File]::Copy($temp, $Playlist, $true)
Remove-Item -LiteralPath $temp -Force

Write-Host "Updated: entries=$entryCount, URLs=$urlCount"
if (Test-Path -LiteralPath $backup) { Write-Host "Backup: $backup" }

