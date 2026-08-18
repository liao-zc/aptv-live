[CmdletBinding()]
param(
    [string]$Playlist,
    [string]$Source = 'https://raw.githubusercontent.com/Guovin/TV/gd/output/result.m3u',
    [int]$MinimumEntries = 500
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if (-not $Playlist) { $Playlist = Join-Path $PSScriptRoot 'APTV_ALL.m3u' }

$sources = @(
    $Source,
    'https://cdn.jsdelivr.net/gh/Guovin/TV@gd/output/result.m3u'
) | Select-Object -Unique

$text = $null
foreach ($candidate in $sources) {
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Write-Host "Downloading $candidate (attempt $attempt/3)..."
            $response = Invoke-WebRequest -UseBasicParsing -Uri $candidate -TimeoutSec 60
            $downloaded = [string]$response.Content
            $candidateLines = @($downloaded -split "`r?`n")
            $candidateEntries = @($candidateLines | Where-Object { $_ -like '#EXTINF:*' }).Count
            $candidateUrls = @($candidateLines | Where-Object { $_ -match '^(?:https?|rtsp|rtmp|udp)://' }).Count
            if ($downloaded.TrimStart().StartsWith('#EXTM3U') -and $candidateEntries -ge $MinimumEntries -and $candidateUrls -ge $MinimumEntries) {
                $text = $downloaded; $lines = $candidateLines
                $entryCount = $candidateEntries; $urlCount = $candidateUrls
                break
            }
            Write-Warning "Rejected incomplete playlist: entries=$candidateEntries, URLs=$candidateUrls"
        } catch { Write-Warning $_.Exception.Message }
        if ($attempt -lt 3) { Start-Sleep -Seconds 5 }
    }
    if ($text) { break }
}
if (-not $text) { throw 'All playlist mirrors failed validation; the existing file was not changed.' }

$directory = Split-Path -Parent ([IO.Path]::GetFullPath($Playlist))
$temp = Join-Path $directory 'APTV_ALL.m3u.download'
$backup = "$Playlist.$(Get-Date -Format 'yyyyMMdd-HHmmss').bak"
[IO.File]::WriteAllText($temp, ($lines -join "`n").TrimEnd() + "`n", [Text.UTF8Encoding]::new($false))

if (Test-Path -LiteralPath $Playlist) { [IO.File]::Copy($Playlist, $backup, $false) }
[IO.File]::Copy($temp, $Playlist, $true)
Remove-Item -LiteralPath $temp -Force

Write-Host "Updated: entries=$entryCount, URLs=$urlCount"
if (Test-Path -LiteralPath $backup) { Write-Host "Backup: $backup" }
