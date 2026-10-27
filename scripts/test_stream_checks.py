import types
import unittest
from stream_checks import balanced_candidates, media_probe, select_decoded


class StreamChecksTest(unittest.TestCase):
    def test_each_source_has_a_chance(self):
        old = [types.SimpleNamespace(source="old") for _ in range(12)]
        new = types.SimpleNamespace(source="Guovin/iptv-api")
        self.assertIn(new, balanced_candidates(old + [new], 8))

    def test_manifest_speed_does_not_inflate_media_speed(self):
        responses = {
            "https://test/live": (b"#EXTM3U\n#EXTINF:6,\na.ts\n#EXTINF:6,\nb.ts\n", .001),
            "https://test/a.ts": (b"x" * 2000, 1),
            "https://test/b.ts": (b"x" * 4000, 1),
        }
        def request(url, timeout):
            data, duration = responses[url]
            return data, url, .01, duration
        _, speed, valid = media_probe(request, "https://test/live", 6)
        self.assertTrue(valid)
        self.assertEqual(speed, 24)

    def test_reject_html_and_finished_playlist(self):
        for data in (b"<html>" + b"x" * 2000, b"#EXTM3U\n#EXTINF:6,\na.ts\n#EXT-X-ENDLIST"):
            self.assertFalse(media_probe(lambda u, t: (data, u, .01, .01), "https://test/live", 6)[2])

    def test_fastest_valid_candidate_and_fallback(self):
        fast = types.SimpleNamespace(speed_kbps=3000, latency_ms=100, score=1, good=False)
        slow = types.SimpleNamespace(speed_kbps=2000, latency_ms=100, score=999, good=True)
        pick = select_decoded([slow, fast], lambda x: None, lambda x: x.good, lambda x: x.score)
        self.assertIs(pick, slow)
        fast.good = True
        self.assertIs(select_decoded([slow, fast], lambda x: None, lambda x: x.good, lambda x: x.score), fast)


if __name__ == "__main__":
    unittest.main()
