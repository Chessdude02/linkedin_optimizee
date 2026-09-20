"""Unit tests for control_center.drafting. No real Anthropic API call --
anthropic.Anthropic is mocked."""
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from control_center import drafting


class TestDraftingFallback(unittest.TestCase):
    def test_no_api_key_proposes_nothing(self):
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            result = drafting.analyze({"text": "a post"}, [])
        self.assertFalse(result["drafted"])
        self.assertFalse(result["reaction"]["propose"])
        self.assertFalse(result["comment"]["propose"])
        self.assertFalse(result["reshare"]["propose"])
        self.assertFalse(result["new_post"]["propose"])


class TestDraftingWithMockedClaude(unittest.TestCase):
    def _mock_response(self, payload: dict):
        block = MagicMock()
        block.text = json.dumps(payload)
        response = MagicMock()
        response.content = [block]
        return response

    def test_parses_claude_response(self):
        payload = {
            "reaction": {"propose": True, "reaction_type": "PRAISE", "reason": "great insight"},
            "comment": {"propose": True, "draft": "Sharp take on this.", "reason": "worth engaging"},
            "reshare": {"propose": False, "commentary": "", "reason": "not a fit for my audience"},
            "new_post": {"propose": False, "draft": "", "reason": "nothing new to add"},
        }
        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = self._mock_response(payload)
            mock_anthropic_cls.return_value = mock_client

            result = drafting.analyze(
                {"text": "a post", "authorName": "Someone", "numLikes": 100},
                [{"text": "a comment"}],
                api_key="sk-ant-test-not-real",
            )

        self.assertTrue(result["drafted"])
        self.assertTrue(result["reaction"]["propose"])
        self.assertEqual(result["reaction"]["reaction_type"], "PRAISE")
        self.assertTrue(result["comment"]["propose"])
        self.assertEqual(result["comment"]["draft"], "Sharp take on this.")
        self.assertFalse(result["reshare"]["propose"])
        self.assertFalse(result["new_post"]["propose"])

    def test_uses_env_key_when_not_passed_explicitly(self):
        payload = {
            "reaction": {"propose": False, "reaction_type": "LIKE", "reason": ""},
            "comment": {"propose": False, "draft": "", "reason": ""},
            "reshare": {"propose": False, "commentary": "", "reason": ""},
            "new_post": {"propose": False, "draft": "", "reason": ""},
        }
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-env-not-real"}):
            with patch("anthropic.Anthropic") as mock_anthropic_cls:
                mock_client = MagicMock()
                mock_client.messages.create.return_value = self._mock_response(payload)
                mock_anthropic_cls.return_value = mock_client

                drafting.analyze({"text": "a post"}, [])

                mock_anthropic_cls.assert_called_once_with(api_key="sk-ant-env-not-real")


if __name__ == "__main__":
    unittest.main()
