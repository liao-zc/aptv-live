"""Write the public and adult-only IPTV playlists from one probe result."""


def attr(value):
    return value.replace("&", "&amp;").replace('"', "&quot;")


def write_one(target, items, disabled, sort_key):
    lines = ['#EXTM3U x-tvg-url="https://epg.112114.xyz/pp.xml.gz,https://assets.livednow.com/epg.xml"']
    used_urls = set()
    for item in sorted(items, key=sort_key):
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
    for item in sorted(disabled, key=sort_key):
        info = f'#DISABLED-EXTINF:-1 tvg-id="{attr(item.tvg_id or item.name)}" tvg-name="{attr(item.name)}"'
        if item.logo:
            info += f' tvg-logo="{attr(item.logo)}"'
        info += f' group-title="{attr(item.group)}",{item.name}'
        lines.extend([
            f'# APTV-DISABLED channel="{attr(item.name)}" reason="no currently playable candidate"',
            info,
            f'#DISABLED-URL:{item.url}',
        ])
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(target)


def write_playlists(root, selected, disabled, sort_key):
    adult_group = "成人频道"
    adult_selected = [item for item in selected if item.group == adult_group]
    adult_disabled = [item for item in disabled if item.group == adult_group]
    public_selected = [item for item in selected if item.group != adult_group]
    # Keep eligible adult channels in the main file as comments by default.
    public_disabled = list(disabled) + adult_selected
    write_one(root / "IPTV_ALL.m3u", public_selected, public_disabled, sort_key)
    write_one(root / "IPTV_ADULT.m3u", adult_selected, adult_disabled, sort_key)
