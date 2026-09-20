"""Unit tests for the Research & Discovery Agent. ApifyClient and
drafting.analyze are both mocked -- no real network call, no real Claude
call. Exercises the real control_center.research/watchlist logic
underneath.

Core invariant under test throughout: research_one()/run_research() only
ever create research_items. They never call control_center.actions
directly and never leave a row in the `actions` table -- that only
happens via the separate, explicit research.convert_to_action() call.
"""
import unittest
from unittest.mock import MagicMock, patch

from agents.research_agent import research_one, run_research
from control_center import actions, research, watchlist
from control_center.exceptions import AlreadyConvertedError, ResearchItemNotFoundError
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


class TestResearchAgent(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()
        self.target_id = watchlist.add_target(
            self.conn, "https://linkedin.com/posts/x", "vedant-linkedin", "test target"
        )
        self.target = watchlist.list_targets(self.conn)[0]
        self.run_id = research.start_run(self.conn, "research-agent")

    def _mock_apify(self):
        apify = MagicMock()
        apify.fetch_post.return_value = SAMPLE_POST
        apify.fetch_post_comments.return_value = [{"text": "a comment"}]
        return apify

    def test_full_proposal_surfaces_four_research_items_not_actions(self):
        apify = self._mock_apify()
        with patch("agents.research_agent.drafting.analyze", return_value=FULL_PROPOSAL):
            surfaced, errors = research_one(self.conn, self.run_id, self.target, apify)

        self.assertEqual(errors, [])
        self.assertEqual(len(surfaced), 4)
        types = {s["opportunity_type"] for s in surfaced}
        self.assertEqual(
            types,
            {"ENGAGEMENT_OPPORTUNITY", "COMMENT_OPPORTUNITY", "RESHARE_OPPORTUNITY", "CONTENT_IDEA"},
        )

        items = research.list_items(self.conn, status="SURFACED")
        self.assertEqual(len(items), 4)

        # The core invariant: discovering never touches the actions table.
        self.assertEqual(actions.list_actions(self.conn), [])

    def test_nothing_worth_proposing_surfaces_nothing(self):
        apify = self._mock_apify()
        with patch("agents.research_agent.drafting.analyze", return_value=NOTHING_PROPOSAL):
            surfaced, errors = research_one(self.conn, self.run_id, self.target, apify)
        self.assertEqual(surfaced, [])
        self.assertEqual(errors, [])
        self.assertEqual(research.list_items(self.conn), [])

    def test_running_twice_does_not_duplicate_findings(self):
        apify = self._mock_apify()
        with patch("agents.research_agent.drafting.analyze", return_value=FULL_PROPOSAL):
            first, _ = research_one(self.conn, self.run_id, self.target, apify)
            second, _ = research_one(self.conn, self.run_id, self.target, apify)

        self.assertEqual(len(first), 4)
        self.assertEqual(len(second), 0)  # already surfaced -- last_seen/times_seen bumped instead
        items = research.list_items(self.conn)
        self.assertEqual(len(items), 4)
        for item in items:
            self.assertEqual(item["times_seen"], 2)

    def test_reshare_targets_share_urn_not_activity_urn(self):
        apify = self._mock_apify()
        with patch("agents.research_agent.drafting.analyze", return_value=FULL_PROPOSAL):
            research_one(self.conn, self.run_id, self.target, apify)

        items = research.list_items(self.conn)
        reshare = [i for i in items if i["opportunity_type"] == "RESHARE_OPPORTUNITY"][0]
        self.assertEqual(reshare["suggested_target_id"], "urn:li:ugcPost:456")

        reaction = [i for i in items if i["opportunity_type"] == "ENGAGEMENT_OPPORTUNITY"][0]
        self.assertEqual(reaction["suggested_target_id"], "urn:li:activity:123")

    def test_record_check_updates_watchlist_state(self):
        apify = self._mock_apify()
        with patch("agents.research_agent.drafting.analyze", return_value=NOTHING_PROPOSAL):
            research_one(self.conn, self.run_id, self.target, apify)
        updated = watchlist.list_targets(self.conn)[0]
        self.assertEqual(updated["last_comment_count"], 1)
        self.assertIsNotNone(updated["last_checked_at"])

    def test_run_research_iterates_every_target(self):
        watchlist.add_target(self.conn, "https://linkedin.com/posts/y", "vedant-linkedin")
        with patch("agents.research_agent.ApifyClient") as mock_client_cls:
            mock_client = self._mock_apify()
            mock_client_cls.return_value = mock_client
            with patch("agents.research_agent.drafting.analyze", return_value=NOTHING_PROPOSAL):
                summary = run_research(self.conn)
        self.assertEqual(mock_client.fetch_post.call_count, 2)
        self.assertEqual(summary["surfaced"], [])
        self.assertEqual(summary["errors"], [])
        run = research.get_run(self.conn, summary["run_id"])
        self.assertEqual(run["status"], "COMPLETED")

    def test_apify_error_on_one_target_does_not_stop_the_run(self):
        watchlist.add_target(self.conn, "https://linkedin.com/posts/y", "vedant-linkedin")
        from control_center.read_sources.apify import ApifyError

        with patch("agents.research_agent.ApifyClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.fetch_post.side_effect = [ApifyError("boom"), SAMPLE_POST]
            mock_client.fetch_post_comments.return_value = []
            mock_client_cls.return_value = mock_client
            with patch("agents.research_agent.drafting.analyze", return_value=NOTHING_PROPOSAL):
                summary = run_research(self.conn)

        self.assertEqual(len(summary["errors"]), 1)
        run = research.get_run(self.conn, summary["run_id"])
        self.assertEqual(run["status"], "COMPLETED_WITH_ERRORS")


class TestConvertToAction(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()
        self.target_id = watchlist.add_target(
            self.conn, "https://linkedin.com/posts/x", "vedant-linkedin"
        )
        self.target = watchlist.list_targets(self.conn)[0]
        self.run_id = research.start_run(self.conn, "research-agent")
        apify = MagicMock()
        apify.fetch_post.return_value = SAMPLE_POST
        apify.fetch_post_comments.return_value = [{"text": "a comment"}]
        with patch("agents.research_agent.drafting.analyze", return_value=FULL_PROPOSAL):
            surfaced, _ = research_one(self.conn, self.run_id, self.target, apify)
        self.item_id = surfaced[0]["item_id"]

    def test_convert_creates_pending_action_never_approved_or_executed(self):
        result = research.convert_to_action(self.conn, self.item_id, created_by="vedant")
        self.assertEqual(result["status"], "PENDING")

        action = actions.get_action(self.conn, result["action_id"])
        self.assertIsNotNone(action)
        self.assertEqual(action["status"], "PENDING")

        item = research.get_item(self.conn, self.item_id)
        self.assertEqual(item["status"], "CONVERTED_TO_ACTION")
        self.assertEqual(item["converted_action_id"], result["action_id"])

    def test_converting_twice_raises_and_does_not_create_a_second_action(self):
        research.convert_to_action(self.conn, self.item_id, created_by="vedant")
        with self.assertRaises(AlreadyConvertedError):
            research.convert_to_action(self.conn, self.item_id, created_by="vedant")
        self.assertEqual(len(actions.list_actions(self.conn)), 1)

    def test_converting_unknown_item_raises(self):
        with self.assertRaises(ResearchItemNotFoundError):
            research.convert_to_action(self.conn, "does-not-exist", created_by="vedant")


if __name__ == "__main__":
    unittest.main()
