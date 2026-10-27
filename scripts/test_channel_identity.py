import types
import unittest
from channel_identity import unique_playback_urls


class ChannelIdentityTests(unittest.TestCase):
    def test_shared_url_retains_only_one_active_label(self):
        old = types.SimpleNamespace(source="own registry", score=1, url="https://test/live", key="old")
        new = types.SimpleNamespace(source="Guovin/iptv-api", score=999, url="https://test/live", key="new")
        self.assertEqual(unique_playback_urls([new, old]), [old])

    def test_different_urls_keep_both_channels(self):
        items = [types.SimpleNamespace(source="test", score=1, url=url) for url in ("https://test/a", "https://test/b")]
        self.assertEqual(len(unique_playback_urls(items)), 2)
