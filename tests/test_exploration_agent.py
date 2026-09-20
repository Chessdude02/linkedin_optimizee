"""Unit tests for the Exploration Agent. ApifyClient and drafting.analyze
are both mocked -- no real network call, no real Claude call. Exercises
the real control_center.actions/watchlist logic underneath."""
import unittest
from unittest.mock import MagicMock, patch

from agents.exploration_agent import explore_all, explore_one
from control_center import actions, watchlist
from tests.helpers import fresh_conn

SAMPLE_POST = {
    "text": "a viral post",
    "urn": "urn:li:activity:123",
    "shareUrn": "urn:li:ugcPost:456",
    "authorName": "Someone",
    "numLikes": 500,
    "numComments": 40,
}

FULL_PROPOSAL = {
    "reaction": {"propose": True, "reaction_type": "LIKE", "reason": "worth a like"},
    "comment": {"propose": True, "draft": "Great point about X.", "reason": "worth engaging"},
    "reshare": {"propose": True, "commentary": "Worth your feed too.", "reason": "amplify"},
    "new_post": {"propose": True, "draft": "My own take on this topic.", "reason": "inspired"},
    "drafted": True,
}

NOTHING_PROPOSAL = {
    "reaction": {"propose": False, "reaction_type": "LIKE", "reason": "meh"},
    "comment": {"propose": False, "draft": "", "reason": "meh"},
    "reshare": {"propose": False, "commentary": "", "reason": "meh"},
    "new_post": {"propose": False, "draft": "", "reason": "meh"},
    "drafted": True,
}


class TestExplorationAgent(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()
        self.target_id = watchlist.add_target(
            self.conn, "https://linkedin.com/posts/x", "vedant-linkedin", "test target"
        )
        self.target = watchlist.list_targets(self.conn)[0]

    def _mock_apify(self):
        apify = MagicMock()
        apify.fetch_post.return_value = SAMPLE_POST
        apify.fetch_post_comments.return_value = [{"text": "a comment"}]
        return apify

    def test_full_proposal_creates_four_actions(self):
        apify = self._mock_apify()
        with patch("agents.exploration_agent.drafting.analyze", return_value=FULL_PROPOSAL):
            proposed = explore_one(self.conn, self.target, apify)

        self.assertEqual(len(proposed), 4)
        types = {p["action_type"] for p in proposed}
        self.assertEqual(types, {"CREATE_REACTION", "CREATE_COMMENT", "RESHARE_POST", "CREATE_POST"})

        pending = actions.list_actions(self.conn, status="PENDING")
        self.assertEqual(len(pending), 4)
        for action in pending:
            self.assertEqual(action["agent_id"], "exploration-agent")

    def test_nothing_worth_proposing_creates_no_actions(self):
        apify = self._mock_apify()
        with patch("agents.exploration_agent.drafting.analyze", return_value=NOTHING_PROPOSAL):
            proposed = explore_one(self.conn, self.target, apify)
        self.assertEqual(proposed, [])
        self.assertEqual(actions.list_actions(self.conn, status="PENDING"), [])

    def test_running_twice_does_not_duplicate_proposals(self):
        apify = self._mock_apify()
        with patch("agents.exploration_agent.drafting.analyze", return_value=FULL_PROPOSAL):
            first = explore_one(self.conn, self.target, apify)
            second = explore_one(self.conn, self.target, apify)

        self.assertEqual(len(first), 4)
        self.assertEqual(len(second), 0)  # every target already has an open action
        self.assertEqual(len(actions.list_actions(self.conn, status="PENDING")), 4)

    def test_reshare_targets_share_urn_not_activity_urn(self):
        apify = self._mock_apify()
        with patch("agents.exploration_agent.drafting.analyze", return_value=FULL_PROPOSAL):
            explore_one(self.conn, self.target, apify)

        reshare = [a for a in actions.list_actions(self.conn, status="PENDING")
                   if a["action_type"] == "RESHARE_POST"][0]
        self.assertEqual(reshare["target_id"], "urn:li:ugcPost:456")

        reaction = [a for a in actions.list_actions(self.conn, status="PENDING")
                    if a["action_type"] == "CREATE_REACTION"][0]
        self.assertEqual(reaction["target_id"], "urn:li:activity:123")

    def test_record_check_updates_watchlist_state(self):
        apify = self._mock_apify()
        with patch("agents.exploration_agent.drafting.analyze", return_value=NOTHING_PROPOSAL):
            explore_one(self.conn, self.target, apify)
        updated = watchlist.list_targets(self.conn)[0]
        self.assertEqual(updated["last_comment_count"], 1)
        self.assertIsNotNone(updated["last_checked_at"])

    def test_explore_all_iterates_every_target(self):
        watchlist.add_target(self.conn, "https://linkedin.com/posts/y", "vedant-linkedin")
        with patch("agents.exploration_agent.ApifyClient") as mock_client_cls:
            mock_client = self._mock_apify()
            mock_client_cls.return_value = mock_client
            with patch("agents.exploration_agent.drafting.analyze", return_value=NOTHING_PROPOSAL):
                explore_all(self.conn)
        self.assertEqual(mock_client.fetch_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
