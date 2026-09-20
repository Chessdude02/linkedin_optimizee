"""Unit tests for scripts/parse_post_url.py's URN extraction -- this had a
real bug during live testing (it only recognized 'activity-' URLs, and
silently failed on a real 'ugcPost-' shaped URL from an actual LinkedIn
post)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from parse_post_url import parse  # noqa: E402


class TestParsePostUrl(unittest.TestCase):
    def test_activity_url(self):
        url = "https://www.linkedin.com/posts/someone_a-b-c-activity-7448808898326654978-iW20"
        self.assertEqual(parse(url), "urn:li:activity:7448808898326654978")

    def test_share_url(self):
        url = "https://www.linkedin.com/posts/someone_a-b-c-share-7449000000000000000-abcd"
        self.assertEqual(parse(url), "urn:li:share:7449000000000000000")

    def test_ugcpost_url(self):
        # The exact real-world shape that broke the old activity-only regex.
        url = (
            "https://www.linkedin.com/posts/hiteshkapure_businessanalytics-capstone-"
            "dataanalytics-ugcPost-7506114354996473856-PL1X/?utm_source=share"
        )
        self.assertEqual(parse(url), "urn:li:ugcPost:7506114354996473856")

    def test_already_a_urn_passes_through(self):
        self.assertEqual(parse("urn:li:ugcPost:7506114354996473856"), "urn:li:ugcPost:7506114354996473856")
        self.assertEqual(parse("urn:li:activity:123"), "urn:li:activity:123")

    def test_feed_update_url(self):
        url = "https://www.linkedin.com/feed/update/urn:li:ugcPost:7447000000000000000"
        self.assertEqual(parse(url), "urn:li:ugcPost:7447000000000000000")

    def test_unrecognized_url_returns_none(self):
        self.assertIsNone(parse("https://lnkd.in/p/g5zZZDnE"))
        self.assertIsNone(parse("https://www.linkedin.com/in/someone/"))


if __name__ == "__main__":
    unittest.main()
