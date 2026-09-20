"""Unit tests for the read-only Apify client. No real network call --
requests.Session.post is mocked, matching the same pattern used for
control_center/backends/publora.py's tests."""
import os
import unittest
from unittest.mock import MagicMock, patch

from control_center.read_sources.apify import ApifyClient, ApifyError


def _fake_response(status_code: int, json_body):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.text = str(json_body)
    return resp


class TestApifyClient(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {"APIFY_TOKEN": "apify_api_test_not_real"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_token_raises(self):
        env = dict(os.environ)
        env.pop("APIFY_TOKEN", None)
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ApifyError):
                ApifyClient()

    def test_fetch_post_normalizes_response(self):
        client = ApifyClient()
        raw_item = {
            "post": {
                "text": "hello world",
                "url": "https://linkedin.com/posts/x",
                "urn": {"activity_urn": "123", "share_urn": None, "ugcPost_urn": "456"},
                "created_at": "2026-01-01T00:00:00Z",
            },
            "author": {"name": "Someone", "headline": "Engineer"},
            "stats": {"total_reactions": 10, "comments": 2, "shares": 1},
        }
        with patch.object(client, "_session") as session:
            session.post.return_value = _fake_response(200, [raw_item])
            post = client.fetch_post("https://linkedin.com/posts/x")
        self.assertEqual(post["text"], "hello world")
        self.assertEqual(post["urn"], "urn:li:activity:123")
        self.assertEqual(post["shareUrn"], "urn:li:ugcPost:456")
        self.assertEqual(post["numLikes"], 10)
        _, kwargs = session.post.call_args
        self.assertEqual(kwargs["json"], {"post_urls": ["https://linkedin.com/posts/x"]})
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer apify_api_test_not_real")

    def test_fetch_post_empty_result_raises(self):
        client = ApifyClient()
        with patch.object(client, "_session") as session:
            session.post.return_value = _fake_response(200, [])
            with self.assertRaises(ApifyError):
                client.fetch_post("https://linkedin.com/posts/x")

    def test_fetch_post_comments_filters_summary_row(self):
        client = ApifyClient()
        with patch.object(client, "_session") as session:
            session.post.return_value = _fake_response(
                200, [{"text": "a real comment"}, {"summary": {"total": 1}}]
            )
            comments = client.fetch_post_comments(post_id="urn:li:activity:123")
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["text"], "a real comment")

    def test_fetch_post_engagers_splits_across_types(self):
        client = ApifyClient()
        with patch.object(client, "_session") as session:
            session.post.side_effect = [
                _fake_response(200, [{"name": "liker1"}]),
                _fake_response(200, [{"name": "commenter1"}]),
            ]
            engagers = client.fetch_post_engagers(
                post_url="https://linkedin.com/posts/x", types=("likers", "commenters")
            )
        self.assertEqual(len(engagers), 2)
        self.assertEqual(session.post.call_count, 2)

    def test_http_error_raises(self):
        client = ApifyClient()
        with patch.object(client, "_session") as session:
            session.post.return_value = _fake_response(401, {"error": "invalid token"})
            with self.assertRaises(ApifyError):
                client.fetch_post("https://linkedin.com/posts/x")


if __name__ == "__main__":
    unittest.main()
