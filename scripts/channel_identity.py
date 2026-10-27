"""Keep channel identity separate from a potentially shared upstream URL."""


def unique_playback_urls(items):
    """Keep one active label per shared URL; other identities remain disabled."""
    priority = {"own registry": 5, "previous output": 4, "GitHub Issue": 3}
    ordered = sorted(items, key=lambda item: (-priority.get(item.source, 1), -item.score))
    used = set()
    result = []
    for item in ordered:
        url = item.url.split("|", 1)[0]
        if url not in used:
            used.add(url)
            result.append(item)
    return result
