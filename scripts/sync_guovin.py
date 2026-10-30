"""Keep the published Guovin candidates and log channel-level merge coverage."""

import json
import sys
from build_playlist import ROOT, assign_keys, canonical_group, download_text, parse_m3u`nfrom playlist_output import attr


def main():
    target = ROOT / "sources" / "guovin-iptv-api.m3u"
    url = "https://guovin.github.io/iptv-api/result.m3u"
    try:
        text = download_text(url, 20)
        candidates = parse_m3u(text, "Guovin/iptv-api")
        if len(candidates) < 10:
            raise ValueError("upstream returned fewer than ten candidates")
    except Exception as exc:
        print(f"warning: Guovin sync unavailable, retaining existing candidates: {exc}", file=sys.stderr)
        return 0
    current_path = ROOT / "IPTV_ALL.m3u"
    current = parse_m3u(current_path.read_text(encoding="utf-8-sig"), "previous output") if current_path.exists() else []
    assign_keys(candidates)
    assign_keys(current)
    existing = {item.key for item in current}
    missing = {item.key: item for item in candidates if item.key not in existing}
    lines = ["#EXTM3U"]
    seen = set()
    for item in candidates:
        if (item.key, item.url) in seen:
            continue
        seen.add((item.key, item.url))
        group = canonical_group(item)
        lines.extend([
            f'#EXTINF:-1 tvg-id="{attr(item.tvg_id or item.name)}" tvg-name="{attr(item.name)}" '
            f'tvg-logo="{attr(item.logo)}" group-title="{group}",{item.name}',
            item.url,
        ])
    target.parent.mkdir(exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(target)
    report = {
        "upstream": url,
        "candidate_count": len(candidates),
        "unique_channel_count": len({item.key for item in candidates}),
        "missing_before_merge_count": len(missing),
        "missing_before_merge": [{"name": item.name, "group": canonical_group(item)} for item in missing.values()],
    }
    report_path = ROOT / "reports" / "upstream-merge.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Guovin candidates={len(candidates)} missing_channels={len(missing)}; all candidates retained for validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
