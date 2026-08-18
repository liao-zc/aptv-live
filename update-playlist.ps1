[CmdletBinding()]
param(
    [string]$Playlist,
    [string]$Source = 'https://raw.githubusercontent.com/Guovin/TV/gd/output/result.m3u',
    [int]$MinimumEntries = 500
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if (-not $Playlist) { $Playlist = Join-Path $PSScriptRoot 'APTV_ALL.m3u' }

function Get-ValidPlaylist([string]$Name, [string[]]$Urls, [int]$Minimum) {
    foreach ($candidate in ($Urls | Select-Object -Unique)) {
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            try {
                Write-Host "[$Name] Downloading $candidate (attempt $attempt/3)..."
                $response = Invoke-WebRequest -UseBasicParsing -Uri $candidate -TimeoutSec 60
                $downloaded = [string]$response.Content
                $candidateLines = @($downloaded -split "`r?`n")
                $candidateEntries = @($candidateLines | Where-Object { $_ -like '#EXTINF:*' }).Count
                $candidateUrls = @($candidateLines | Where-Object { $_ -match '^(?:https?|rtsp|rtmp|udp)://' }).Count
                if ($downloaded.TrimStart().StartsWith('#EXTM3U') -and $candidateEntries -ge $Minimum -and $candidateUrls -ge $Minimum) {
                    return [pscustomobject]@{ Name=$Name; Lines=$candidateLines; Entries=$candidateEntries; Urls=$candidateUrls }
                }
                Write-Warning "[$Name] Rejected incomplete playlist: entries=$candidateEntries, URLs=$candidateUrls"
            } catch { Write-Warning "[$Name] $($_.Exception.Message)" }
            if ($attempt -lt 3) { Start-Sleep -Seconds 5 }
        }
    }
    return $null
}

# Prefer the speed-tested primary upstream and its CDN mirror.
$selected = Get-ValidPlaylist 'Guovin/TV' @(
    $Source,
    'https://cdn.jsdelivr.net/gh/Guovin/TV@gd/output/result.m3u'
) $MinimumEntries

if ($selected) {
    $lines = $selected.Lines
    $entryCount = $selected.Entries
    $urlCount = $selected.Urls
    Write-Host 'Using primary upstream: Guovin/TV'
} else {
    # Independent disaster-recovery upstreams. They are combined only when
    # the primary source and its mirror are both unavailable or invalid.
    Write-Warning 'Primary upstream failed. Aggregating independent fallback upstreams.'
    $fallbacks = @(
        @{ Name='iptv-org/iptv'; Minimum=300; Urls=@('https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u','https://cdn.jsdelivr.net/gh/iptv-org/iptv@master/streams/cn.m3u') },
        @{ Name='YanG-1989/m3u'; Minimum=80; Urls=@('https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u','https://cdn.jsdelivr.net/gh/YanG-1989/m3u@main/Gather.m3u') },
        @{ Name='fanmingming/live'; Minimum=50; Urls=@('https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u','https://live.fanmingming.com/tv/m3u/ipv6.m3u') }
    )
    $parts = [Collections.Generic.List[object]]::new()
    foreach ($fallback in $fallbacks) {
        $part = Get-ValidPlaylist $fallback.Name $fallback.Urls $fallback.Minimum
        if ($part) { $parts.Add($part) }
    }
    if ($parts.Count -eq 0) { throw 'All independent upstreams failed; the existing file was not changed.' }
    $combined = [Collections.Generic.List[string]]::new()
    $combined.Add('#EXTM3U')
    foreach ($part in $parts) {
        foreach ($line in $part.Lines) { if ($line -and $line -notlike '#EXTM3U*') { $combined.Add($line) } }
    }
    $lines = $combined.ToArray()
    $entryCount = ($parts | Measure-Object Entries -Sum).Sum
    $urlCount = ($parts | Measure-Object Urls -Sum).Sum
    if ($entryCount -lt 150 -or $urlCount -lt 150) { throw 'Fallback upstream total is too small; the existing file was not changed.' }
    Write-Host "Using fallback upstreams: $($parts.Name -join ', ')"
}

# Add a curated set of commonly requested Taiwan channels on every run.
# The health/deduplication stage decides which of them are currently usable.
$taiwanIds = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
@(
    'CTiVariety.tw@SD', 'CTS.tw@SD', 'CTSNews.tw@SD',
    'DaAi1.tw@SD', 'DaAi2.tw@SD',
    'EBCFinancialNews.tw@SD', 'EBCNews.tw@SD',
    'FTV.tw@SD', 'FTVOne.tw@SD', 'FTVTaiwan.tw@SD',
    'IndigenousTV.tw@SD', 'TaiwanPlusTV.tw@SD',
    'TVBSNews.tw@SD', 'TTV.tw@SD'
) | ForEach-Object { [void]$taiwanIds.Add($_) }

$taiwan = Get-ValidPlaylist 'iptv-org Taiwan supplement' @(
    'https://raw.githubusercontent.com/iptv-org/iptv/master/streams/tw.m3u',
    'https://cdn.jsdelivr.net/gh/iptv-org/iptv@master/streams/tw.m3u'
) 30

if ($taiwan) {
    $expanded = [Collections.Generic.List[string]]::new()
    foreach ($line in $lines) { $expanded.Add($line) }
    $info = $null; $addedTaiwan = 0
    foreach ($raw in $taiwan.Lines) {
        $line = $raw.Trim()
        if ($line -like '#EXTINF:*') { $info = $line; continue }
        if ($info -and $line -match '^(?:https?|rtsp|rtmp|udp)://') {
            if ($info -match 'tvg-id="([^"]+)"' -and $taiwanIds.Contains($matches[1])) {
                $expanded.Add($info); $expanded.Add($line); $addedTaiwan++
            }
            $info = $null
        }
    }
    $lines = $expanded.ToArray()
    $entryCount += $addedTaiwan; $urlCount += $addedTaiwan
    Write-Host "Added $addedTaiwan curated Taiwan candidates."
} else {
    Write-Warning 'Taiwan supplement was unavailable; continuing with the primary playlist.'
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
