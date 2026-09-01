#!/usr/bin/env python3
"""Build a validated, ranked and de-duplicated APTV playlist using stdlib only."""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import hashlib
import ipaddress
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "Mozilla/5.0 APTV-Live-Aggregator/2.0"
MAX_DOWNLOAD = 512 * 1024


@dataclasses.dataclass
class Candidate:
    name: str
    url: str
    source: str
    group: str = "其他频道"
    tvg_id: str = ""
    logo: str = ""
    key: str = ""
    latency_ms: int = 0
    speed_kbps: int = 0
    width: int = 0
    height: int = 0
    basic_ok: bool = False
    video_ok: bool = False
    score: float = 0.0


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_public_url(newurl):
            raise urllib.error.URLError("unsafe redirect target")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(SafeRedirect())


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def safe_public_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url.split("|", 1)[0])
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            return False
        for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)):
            address = ipaddress.ip_address(item[4][0])
            if not address.is_global:
                return False
        return True
    except (ValueError, OSError, socket.gaierror):
        return False


def request_bytes(url: str, timeout: int, limit: int = MAX_DOWNLOAD):
    clean_url = url.split("|", 1)[0].strip()
    if not safe_public_url(clean_url):
        raise ValueError("URL is not a public HTTP(S) address")
    request = urllib.request.Request(clean_url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    started = time.monotonic()
    with OPENER.open(request, timeout=timeout) as response:
        first_byte = time.monotonic()
        data = response.read(limit)
        finished = time.monotonic()
        return data, response.geturl(), max(first_byte - started, 0.001), max(finished - first_byte, 0.001)


def download_text(url: str, timeout: int) -> str:
    data, _, _, _ = request_bytes(url, timeout, 4 * 1024 * 1024)
    return data.decode("utf-8-sig", errors="replace")


ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def parse_m3u(text: str, source: str) -> list[Candidate]:
    result: list[Candidate] = []
    pending = None
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if line.upper().startswith("#DISABLED-EXTINF:"):
            line = "#EXTINF:" + line.split(":", 1)[1]
            attrs = dict(ATTR_RE.findall(line))
            display = line.rsplit(",", 1)[-1].strip() if "," in line else ""
            pending = (attrs, display)
        elif line.upper().startswith("#EXTINF:"):
            attrs = dict(ATTR_RE.findall(line))
            display = line.rsplit(",", 1)[-1].strip() if "," in line else ""
            pending = (attrs, display)
        elif pending and line.upper().startswith("#DISABLED-URL:"):
            attrs, display = pending
            disabled_url = line.split(":", 1)[1].strip()
            if re.match(r"^https?://", disabled_url, re.I):
                name = attrs.get("tvg-name") or display or attrs.get("tvg-id") or "Unknown"
                result.append(Candidate(
                    name=name.strip(), url=disabled_url, source=source,
                    group=attrs.get("group-title") or "其他频道",
                    tvg_id=attrs.get("tvg-id", ""), logo=attrs.get("tvg-logo", "")
                ))
            pending = None
        elif pending and re.match(r"^https?://", line, re.I):
            attrs, display = pending
            name = attrs.get("tvg-name") or display or attrs.get("tvg-id") or "Unknown"
            result.append(Candidate(
                name=name.strip(), url=line, source=source,
                group=attrs.get("group-title") or "其他频道",
                tvg_id=attrs.get("tvg-id", ""), logo=attrs.get("tvg-logo", "")
            ))
            pending = None
    return result


def folded(value: str) -> str:
    value = value.upper().replace("＋", "+")
    value = re.sub(r"\[[^]]*]", "", value)
    value = re.sub(r"\((?:1080P|720P|576P|480P|SD|HD|FHD|4K)\)", "", value)
    value = re.sub(r"(?:超清|高清|频道|頻道|電視台|电视台|HD|FHD|4K|1080P|720P)", "", value)
    return re.sub(r"[^0-9A-Z+\u3400-\u9fff]", "", value)


def alias_lookup() -> dict[str, str]:
    aliases = load_json(ROOT / "config" / "aliases.json", {})
    lookup: dict[str, str] = {}
    for canonical, values in aliases.items():
        for value in [canonical, *values]:
            lookup[folded(value)] = canonical
    return lookup


def assign_keys(items: list[Candidate]) -> None:
    aliases = alias_lookup()
    for item in items:
        candidates = [item.name, item.tvg_id]
        canonical = next((aliases[folded(x)] for x in candidates if folded(x) in aliases), "")
        item.key = folded(canonical or item.tvg_id or item.name)
        if canonical:
            item.name = canonical


def fetch_feed(feed: dict, timeout: int) -> list[Candidate]:
    for url in feed.get("urls", []):
        for attempt in range(2):
            try:
                text = download_text(url, timeout)
                items = parse_m3u(text, feed["name"])
                if items:
                    print(f"source={feed['name']} entries={len(items)} url={url}")
                    return items
            except Exception as exc:
                print(f"warning: {feed['name']} attempt={attempt + 1}: {exc}", file=sys.stderr)
    return []


def issue_candidates(timeout: int) -> list[Candidate]:
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        return []
    url = f"https://api.github.com/repos/{repository}/issues?state=open&per_page=100"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            issues = json.load(response)
    except Exception as exc:
        print(f"warning: cannot read community issues: {exc}", file=sys.stderr)
        return []
    result = []
    for issue in issues:
        body = issue.get("body") or ""
        title = issue.get("title") or ""
        if "aptv-source-submission" not in body and not title.lower().startswith("[source]"):
            continue
        match_url = re.search(r"https?://[^\s<>]+", body)
        match_name = re.search(r"###\s*(?:Channel name|频道名称)\s*\n+\s*([^\n]+)", body, re.I)
        if match_url and match_name:
            result.append(Candidate(match_name.group(1).strip(), match_url.group(0).rstrip(".,)"), "GitHub Issue"))
    return result


def collect_candidates(config: dict) -> list[Candidate]:
    timeout = int(config["request_timeout_seconds"])
    items: list[Candidate] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(config["feeds"]))) as pool:
        futures = [pool.submit(fetch_feed, feed, timeout) for feed in config["feeds"]]
        for future in concurrent.futures.as_completed(futures):
            items.extend(future.result())
    local_sources = [(path, "own registry") for path in sorted((ROOT / "sources").glob("*.m3u"))]
    local_sources.append((ROOT / "APTV_ALL.m3u", "previous output"))
    for path, source in local_sources:
        if path.exists():
            items.extend(parse_m3u(path.read_text(encoding="utf-8-sig", errors="replace"), source))
    items.extend(issue_candidates(timeout))
    assign_keys(items)
    blocked_urls: set[str] = set()
    regional = load_json(ROOT / "config" / "regional_failures.json", {})
    try:
        expires_at = dt.datetime.fromisoformat(regional.get("expires_at", ""))
        if expires_at > dt.datetime.now(dt.timezone.utc):
            blocked_urls = set(regional.get("urls", []))
    except (TypeError, ValueError):
        pass
    if blocked_urls:
        print(f"regional_blocked_urls={len(blocked_urls)} expires_at={regional.get('expires_at')}")
    unique: dict[str, Candidate] = {}
    priority = {"own registry": 100, "GitHub Issue": 95, "previous output": 90, "Guovin/TV": 80}
    for item in items:
        if not item.key or not re.match(r"^https?://", item.url, re.I):
            continue
        marker = item.url.split("|", 1)[0]
        if marker in blocked_urls:
            continue
        if marker not in unique or priority.get(item.source, 50) > priority.get(unique[marker].source, 50):
            unique[marker] = item
    print(f"candidates={len(unique)}")
    return list(unique.values())


def hls_media_probe(url: str, timeout: int, depth: int = 0):
    data, final_url, latency, transfer = request_bytes(url, timeout)
    text = data[:65536].decode("utf-8", errors="ignore")
    speed = int((len(data) * 8 / 1000) / transfer)
    if "#EXTM3U" not in text.upper():
        return latency, speed, len(data) > 0
    choices = [x.strip() for x in text.replace("\r", "").split("\n") if x.strip() and not x.startswith("#")]
    if not choices:
        return latency, speed, False
    child = urllib.parse.urljoin(final_url, choices[0])
    if depth < 1 and (".m3u8" in child.lower() or "#EXT-X-STREAM-INF" in text.upper()):
        child_latency, child_speed, ok = hls_media_probe(child, timeout, depth + 1)
        return latency + child_latency, max(speed, child_speed), ok
    segment, _, segment_latency, segment_transfer = request_bytes(child, timeout)
    segment_speed = int((len(segment) * 8 / 1000) / segment_transfer)
    return latency + segment_latency, max(speed, segment_speed), len(segment) >= 188


def basic_probe(item: Candidate, timeout: int) -> Candidate:
    try:
        latency, speed, ok = hls_media_probe(item.url, timeout)
        item.latency_ms = int(latency * 1000)
        item.speed_kbps = speed
        item.basic_ok = ok
    except Exception:
        item.basic_ok = False
    return item


def ffprobe(item: Candidate, timeout: int) -> Candidate:
    executable = shutil.which("ffprobe")
    if not executable:
        item.video_ok = item.basic_ok
        return item
    command = [
        executable, "-v", "error", "-rw_timeout", str(timeout * 1_000_000),
        "-show_entries", "stream=codec_type,width,height", "-of", "json",
        item.url.split("|", 1)[0]
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 3, check=False)
        streams = json.loads(result.stdout or "{}").get("streams", [])
        videos = [x for x in streams if x.get("codec_type") == "video"]
        if videos:
            item.video_ok = True
            item.width = max(int(x.get("width") or 0) for x in videos)
            item.height = max(int(x.get("height") or 0) for x in videos)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        item.video_ok = False
    return item


def history_score(item: Candidate, history: dict) -> float:
    record = history.get(hashlib.sha256(item.url.encode()).hexdigest(), {})
    good = int(record.get("successes", 0)); bad = int(record.get("failures", 0))
    reliability = (good + 1) / (good + bad + 2)
    resolution = item.width * item.height / 10000
    return reliability * 1000 + math.log2(max(item.speed_kbps, 1)) * 30 + resolution - item.latency_ms / 25


def quality_ok(item: Candidate, config: dict, history: dict, require_video: bool = False) -> bool:
    if not item.basic_ok:
        return False
    if item.speed_kbps < int(config["minimum_speed_kbps"]):
        return False
    if item.latency_ms > int(config["maximum_latency_ms"]):
        return False
    record = history.get(hashlib.sha256(item.url.encode()).hexdigest(), {})
    good = int(record.get("successes", 0)); bad = int(record.get("failures", 0))
    if good < int(config["minimum_prior_successes"]):
        return False
    samples = good + bad
    if samples >= int(config["minimum_history_samples"]):
        if good / samples < float(config["minimum_history_success_ratio"]):
            return False
    if require_video:
        if not item.video_ok:
            return False
        if item.width < int(config["minimum_video_width"]) or item.height < int(config["minimum_video_height"]):
            return False
    return True


def select_streams(items: list[Candidate], config: dict, history: dict) -> tuple[list[Candidate], list[Candidate]]:
    groups: dict[str, list[Candidate]] = {}
    source_priority = {"own registry": 5, "previous output": 4, "GitHub Issue": 3, "Guovin/TV": 2}
    for item in items:
        groups.setdefault(item.key, []).append(item)
    capped = []
    limit = int(config["max_candidates_per_channel"])
    for values in groups.values():
        values.sort(key=lambda x: source_priority.get(x.source, 1), reverse=True)
        capped.extend(values[:limit])
    timeout = int(config["request_timeout_seconds"])
    print(f"basic_probes={len(capped)} channels={len(groups)}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=48) as pool:
        probed = list(pool.map(lambda x: basic_probe(x, timeout), capped))
    passing: dict[str, list[Candidate]] = {}
    for item in probed:
        if quality_ok(item, config, history):
            item.score = history_score(item, history)
            passing.setdefault(item.key, []).append(item)
    for values in passing.values():
        values.sort(key=lambda x: x.score, reverse=True)

    def validate_group(values):
        for candidate in values[:5]:
            ffprobe(candidate, timeout)
            # Re-read HLS and a media segment immediately before publishing.
            basic_probe(candidate, timeout)
            if quality_ok(candidate, config, history, require_video=True):
                candidate.score = history_score(candidate, history)
                return candidate
        return None

    selected = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        for result in pool.map(validate_group, passing.values()):
            if result:
                selected.append(result)
    selected.sort(key=lambda x: (x.group, x.name))
    return selected, probed


def update_history(history_doc: dict, probed: list[Candidate], retention_days: int) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    streams = history_doc.setdefault("streams", {})
    for item in probed:
        key = hashlib.sha256(item.url.encode()).hexdigest()
        record = streams.setdefault(key, {"url": item.url, "channel": item.name, "successes": 0, "failures": 0})
        field = "successes" if item.basic_ok else "failures"
        record[field] = int(record.get(field, 0)) + 1
        record["last_checked"] = now.isoformat()
        if item.basic_ok:
            record["last_success"] = now.isoformat()
            record["speed_kbps"] = item.speed_kbps
            record["latency_ms"] = item.latency_ms
    cutoff = now - dt.timedelta(days=retention_days)
    for key, record in list(streams.items()):
        try:
            checked = dt.datetime.fromisoformat(record.get("last_checked", ""))
        except ValueError:
            checked = now
        if checked < cutoff:
            del streams[key]


def attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;")


def playlist_sort_key(item: Candidate):
    """Stable order: CCTV, satellite, HK/Macao/Taiwan, local, other."""
    name = item.name.strip()
    group = item.group
    upper = name.upper()
    cctv = re.match(r"^CCTV[- ]?(\d{1,2})(\+)?(?:\b|$)", upper)
    if cctv:
        number = int(cctv.group(1))
        plus_rank = 1 if cctv.group(2) else 0
        suffix_rank = 0 if re.fullmatch(r"CCTV[- ]?\d{1,2}\+?", upper) else 1
        return (0, number, plus_rank, suffix_rank, folded(name))
    if "央视" in group or "央视频道" in group:
        return (0, 100, 0, 0, folded(name))

    hk_tw_words = (
        "港·澳·台", "港澳台", "香港", "澳门", "澳門", "台湾", "台灣",
        "TVBS", "三立", "东森", "東森", "纬来", "緯來", "台视", "台視",
        "华视", "華視", "民视", "民視", "公视", "公視", "凤凰", "鳳凰",
        "翡翠", "明珠", "VIUTV", "TAIWANPLUS"
    )
    if item.tvg_id.lower().endswith(".tw@sd") or any(word.upper() in (group + name).upper() for word in hk_tw_words):
        return (2, 0, 0, 0, folded(name))

    if "卫视频道" in group or "衛視頻道" in group or name.endswith(("卫视", "衛視")):
        return (1, 0, 0, 0, folded(name))

    local_markers = (
        "浙江", "江苏", "四川", "河北", "湖北", "福建", "广东", "黑龙江",
        "上海", "安徽", "湖南", "山东", "广西", "河南", "吉林", "甘肃",
        "海南", "辽宁", "云南", "山西", "新疆", "青海", "贵州", "北京",
        "天津", "重庆", "陕西", "宁夏", "内蒙古", "西藏", "地方频道"
    )
    if group.startswith("☘") or any(word in group for word in local_markers):
        return (3, 0, 0, 0, folded(name))
    return (4, 0, 0, 0, folded(name))


def write_playlist(items: list[Candidate], disabled: list[Candidate]) -> None:
    lines = ['#EXTM3U x-tvg-url="https://epg.112114.xyz/pp.xml.gz,https://assets.livednow.com/epg.xml"']
    used_urls = set()
    for item in sorted(items, key=playlist_sort_key):
        if item.url in used_urls:
            continue
        used_urls.add(item.url)
        info = f'#EXTINF:-1 tvg-id="{attr(item.tvg_id or item.name)}" tvg-name="{attr(item.name)}"'
        if item.logo:
            info += f' tvg-logo="{attr(item.logo)}"'
        info += f' group-title="{attr(item.group)}",{item.name}'
        lines.extend([info, item.url])
    if disabled:
        lines.extend(["", "# Disabled channels are retried automatically every run."])
    for item in sorted(disabled, key=playlist_sort_key):
        info = f'#DISABLED-EXTINF:-1 tvg-id="{attr(item.tvg_id or item.name)}" tvg-name="{attr(item.name)}"'
        if item.logo:
            info += f' tvg-logo="{attr(item.logo)}"'
        info += f' group-title="{attr(item.group)}",{item.name}'
        lines.extend([
            f'# APTV-DISABLED channel="{attr(item.name)}" reason="no currently playable candidate"',
            info,
            f'#DISABLED-URL:{item.url}'
        ])
    target = ROOT / "APTV_ALL.m3u"
    temp = target.with_suffix(".m3u.tmp")
    temp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temp.replace(target)


def report_for(items: list[Candidate], candidates: int, node: str, disabled: list[Candidate] | None = None) -> dict:
    return {
        "version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "node": node,
        "candidate_count": candidates,
        "channel_count": len(items),
        "disabled_channel_count": len(disabled or []),
        "disabled_channels": [x.name for x in (disabled or [])],
        "channels": [dataclasses.asdict(item) for item in items]
    }


def merge_fresh_probe_reports(selected: list[Candidate]) -> list[Candidate]:
    by_key = {x.key: x for x in selected}
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    probe_paths = (ROOT / "reports" / "probes").glob("*.json") if (ROOT / "reports" / "probes").exists() else []
    for path in probe_paths:
        report = load_json(path, {})
        try:
            generated = dt.datetime.fromisoformat(report.get("generated_at", ""))
        except ValueError:
            continue
        if generated < cutoff:
            continue
        for raw in report.get("channels", []):
            try:
                item = Candidate(**{k: v for k, v in raw.items() if k in Candidate.__dataclass_fields__})
            except TypeError:
                continue
            if item.key and item.video_ok and (item.key not in by_key or item.score > by_key[item.key].score):
                by_key[item.key] = item
    return sorted(by_key.values(), key=lambda x: (x.group, x.name))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", default=os.environ.get("APTV_PROBE_NODE", "github-default"))
    parser.add_argument("--probe-only", metavar="PATH")
    args = parser.parse_args()
    config = load_json(ROOT / "config" / "upstreams.json", {})
    history_doc = load_json(ROOT / "data" / "history.json", {"version": 1, "streams": {}})
    candidates = collect_candidates(config)
    selected, probed = select_streams(candidates, config, history_doc.get("streams", {}))
    selected_keys = {x.key for x in selected}
    disabled_by_key: dict[str, Candidate] = {}
    for item in candidates:
        if item.key and item.key not in selected_keys and item.key not in disabled_by_key:
            disabled_by_key[item.key] = item
    disabled = sorted(disabled_by_key.values(), key=lambda x: (x.group, x.name))
    report = report_for(selected, len(candidates), args.node, disabled)
    if args.probe_only:
        atomic_json(ROOT / args.probe_only, report)
        print(f"probe-only channels={len(selected)}")
        return 0
    selected = merge_fresh_probe_reports(selected)
    selected_keys = {x.key for x in selected}
    disabled = [x for x in disabled if x.key not in selected_keys]
    minimum = int(config["minimum_output_channels"])
    if len(selected) < minimum:
        print(f"error: only {len(selected)} channels passed; minimum is {minimum}", file=sys.stderr)
        return 2
    update_history(history_doc, probed, int(config["history_retention_days"]))
    atomic_json(ROOT / "data" / "history.json", history_doc)
    atomic_json(ROOT / "reports" / "latest.json", report_for(selected, len(candidates), args.node, disabled))
    write_playlist(selected, disabled)
    print(f"published_channels={len(selected)} disabled_channels={len(disabled)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
