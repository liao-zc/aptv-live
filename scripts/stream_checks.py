"""Balanced candidate sampling and media-based playback checks."""

import collections
import json
import shutil
import statistics
import subprocess
import urllib.parse


def balanced_candidates(values, limit):
    """Round-robin sources so a large old registry cannot exclude a new feed."""
    buckets = collections.OrderedDict()
    for value in values:
        buckets.setdefault(value.source, collections.deque()).append(value)
    result = []
    while buckets and len(result) < limit:
        for source in list(buckets):
            result.append(buckets[source].popleft())
            if not buckets[source]:
                del buckets[source]
            if len(result) >= limit:
                break
    return result


def media_probe(request_bytes, url, timeout, depth=0):
    data, final_url, latency, transfer = request_bytes(url, timeout)
    text = data[:65536].decode("utf-8", errors="ignore")
    if not text.lstrip().startswith("#EXTM3U"):
        # HTML/login/error responses must never count as playable media.
        content = data.lstrip().lower()
        valid = len(data) >= 188 and not content.startswith((b"<", b"{", b"["))
        return latency, int(len(data) * 8 / 1000 / transfer), valid
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if "#EXT-X-ENDLIST" in text:
        return latency, 0, False
    urls = [urllib.parse.urljoin(final_url, line) for line in lines if not line.startswith("#")]
    if not urls:
        return latency, 0, False
    if any(line.startswith("#EXT-X-STREAM-INF") for line in lines):
        if depth >= 3:
            return latency, 0, False
        child_latency, speed, valid = media_probe(request_bytes, urls[0], timeout, depth + 1)
        return latency + child_latency, speed, valid
    # Measure two recent complete segments, not the tiny manifest response.
    speeds = []
    for segment_url in urls[-2:]:
        segment, _, first_byte, elapsed = request_bytes(segment_url, timeout)
        if len(segment) < 188 or segment.lstrip().lower().startswith((b"<", b"{", b"[")):
            return latency + first_byte, 0, False
        latency = max(latency, first_byte)
        speeds.append(int(len(segment) * 8 / 1000 / elapsed))
    return latency, int(statistics.median(speeds)), True


def decode_video(item, timeout, user_agent):
    """Require both video metadata and decoded frames; fail closed without tools."""
    item.video_ok = False
    probe = shutil.which("ffprobe")
    decoder = shutil.which("ffmpeg")
    if not probe or not decoder:
        return item
    options = ["-v", "error", "-rw_timeout", str(timeout * 1_000_000), "-user_agent", user_agent]
    url = item.url.split("|", 1)[0]
    try:
        result = subprocess.run(
            [probe, *options, "-show_entries", "stream=codec_type,width,height", "-of", "json", url],
            capture_output=True, text=True, timeout=timeout + 3, check=False,
        )
        videos = [s for s in json.loads(result.stdout or "{}").get("streams", []) if s.get("codec_type") == "video"]
        if result.returncode or not videos:
            return item
        item.width = max(int(s.get("width") or 0) for s in videos)
        item.height = max(int(s.get("height") or 0) for s in videos)
        decoded = subprocess.run(
            [decoder, *options, "-i", url, "-map", "0:v:0", "-an", "-frames:v", "3",
             "-progress", "pipe:1", "-nostats", "-f", "null", "-"],
            capture_output=True, text=True, timeout=timeout + 5, check=False,
        )
        frames = [int(line.split("=", 1)[1]) for line in decoded.stdout.splitlines() if line.startswith("frame=")]
        item.video_ok = decoded.returncode == 0 and bool(frames) and max(frames) >= 3
    except (OSError, ValueError, subprocess.TimeoutExpired):
        item.video_ok = False
    return item


def select_decoded(values, validate, quality, score):
    """Pick the fastest validated source, using stability score to break ties."""
    ordered = sorted(values, key=lambda item: (-item.speed_kbps, item.latency_ms, -item.score))
    for candidate in ordered:
        validate(candidate)
        if quality(candidate):
            candidate.score = score(candidate)
            return candidate
    return None
