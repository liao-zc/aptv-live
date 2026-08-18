[CmdletBinding()]
param(
    [string]$Playlist,
    [int]$TimeoutSeconds = 5,
    [int]$Concurrency = 64,
    [int]$MinimumChannels = 150
)

$ErrorActionPreference = 'Stop'
if (-not $Playlist) { $Playlist = Join-Path $PSScriptRoot 'APTV_ALL.m3u' }

if (-not ('AptvHealth' -as [type])) {
    Add-Type -Language CSharp -ReferencedAssemblies 'System.Net.Http.dll' -TypeDefinition @'
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
public static class AptvHealth {
  public static IDictionary<string,bool> Check(string[] urls, int timeout, int concurrency) {
    var result = new ConcurrentDictionary<string,bool>();
    ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
    ServicePointManager.DefaultConnectionLimit = Math.Max(32, concurrency);
    Parallel.ForEach(urls, new ParallelOptions { MaxDegreeOfParallelism = concurrency }, url => {
      if (url.StartsWith("udp:") || url.StartsWith("rtsp:") || url.StartsWith("rtmp:")) { result[url] = true; return; }
      try {
        using (var handler = new HttpClientHandler { AllowAutoRedirect = true, AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate })
        using (var client = new HttpClient(handler))
        using (var cts = new CancellationTokenSource(TimeSpan.FromSeconds(timeout))) {
          client.DefaultRequestHeaders.UserAgent.ParseAdd("Mozilla/5.0 APTV-Cleaner/1.0");
          var response = client.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, cts.Token).GetAwaiter().GetResult();
          if (!response.IsSuccessStatusCode) { result[url] = false; return; }
          using (var stream = response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()) {
            var buffer = new byte[1];
            result[url] = stream.ReadAsync(buffer, 0, 1, cts.Token).GetAwaiter().GetResult() == 1;
          }
        }
      } catch { result[url] = false; }
    });
    return result;
  }
}
'@
}

$text = [IO.File]::ReadAllText((Resolve-Path $Playlist), [Text.Encoding]::UTF8)
$header = ($text -split "`r?`n" | Where-Object { $_ -like '#EXTM3U*' } | Select-Object -First 1)
$items = [Collections.Generic.List[object]]::new()
$info = $null
foreach ($raw in ($text -split "`r?`n")) {
    $line = $raw.Trim()
    if ($line -like '#EXTINF:*') { $info = $line; continue }
    if ($info -and $line -match '^(?:https?|rtsp|rtmp|udp)://') {
        if ($info -match 'tvg-id="([^"]+)"') { $key = $matches[1] }
        elseif ($info -match 'tvg-name="([^"]+)"') { $key = $matches[1] }
        elseif ($info -match ',([^,]+)$') { $key = $matches[1] }
        else { $key = $line }
        $isTimestamp = $info -match ',\s*\d{4}-\d{2}-\d{2}'
        $items.Add([pscustomobject]@{ Key=$key.Trim().ToUpperInvariant(); Info=$info; Url=$line; Timestamp=$isTimestamp })
        $info = $null
    }
}

$urls = [string[]]($items.Url | Select-Object -Unique)
Write-Host "Checking $($urls.Count) stream URLs..."
$health = [AptvHealth]::Check($urls, $TimeoutSeconds, $Concurrency)

$kept = [Collections.Generic.List[object]]::new()
$usedUrls = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$removedInvalid = 0
foreach ($group in ($items | Group-Object Key)) {
    $choice = $group.Group | Where-Object { -not $_.Timestamp -and $health[$_.Url] -and -not $usedUrls.Contains($_.Url) } | Select-Object -First 1
    if (-not $choice) { $removedInvalid++; continue }
    $kept.Add($choice)
    [void]$usedUrls.Add($choice.Url)
}

if ($kept.Count -lt $MinimumChannels) {
    throw "Only $($kept.Count) channels passed validation (minimum: $MinimumChannels). The existing playlist was not changed."
}

$output = [Collections.Generic.List[string]]::new()
$output.Add($header)
foreach ($item in $kept) { $output.Add($item.Info); $output.Add($item.Url) }
$backup = "$Playlist.$(Get-Date -Format 'yyyyMMdd-HHmmss').bak"
[IO.File]::Copy($Playlist, $backup, $false)
[IO.File]::WriteAllLines($Playlist, $output, [Text.UTF8Encoding]::new($false))
Write-Host "Done: original=$($items.Count), kept=$($kept.Count), removedDuplicates=$($items.Count-$kept.Count-$removedInvalid), removedInvalidChannels=$removedInvalid"
Write-Host "Backup: $backup"
