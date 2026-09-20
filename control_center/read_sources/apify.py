"""Read-only LinkedIn data via Apify, for the Exploration Agent.

Mirrors the actor IDs and input schemas from sergebulaev/linkedin-skills'
lib/apify_client.py (verified against that file directly) rather than
guessing at Apify's actor input formats. Reimplemented here, not imported
from that project, so this repo stays self-contained and doesn't depend
on a sibling clone existing at some path on whatever machine runs it.

This is read-only: it cannot publish, comment, react, or modify anything.
Lower stakes than the Publora write credential, but APIFY_TOKEN is still
only read here, and this module is only ever imported by
agents/exploration_agent.py -- neither control_center.actions (agent API)
nor dashboard/ needs LinkedIn read access at all.
"""
from __future__ import annotations

import os
from typing import Any, Optional, Sequence

import requests


class ApifyError(RuntimeError):
    pass


class ApifyClient:
    BASE_URL = "https://api.apify.com/v2"

    POST_ACTOR = "apimaestro~linkedin-post-detail"
    POST_COMMENTS_ACTOR = "apimaestro~linkedin-post-comments-replies-engagements-scraper-no-cookies"
    POST_ENGAGERS_ACTOR = "scraping_solutions~linkedin-posts-engagers-likers-and-commenters-no-cookies"

    def __init__(self, token: Optional[str] = None, timeout: float = 180.0):
        self.token = token or os.environ.get("APIFY_TOKEN")
        if not self.token:
            raise ApifyError("APIFY_TOKEN not set. Export it or pass token= explicitly.")
        self.timeout = timeout
        self._session = requests.Session()

    def fetch_post(self, post_url: str) -> dict[str, Any]:
        """Post body, author, and engagement stats for one post."""
        items = self._run_sync(self.POST_ACTOR, {"post_urls": [post_url]})
        if not items:
            raise ApifyError(f"no post returned for {post_url}")
        return self._normalize_post(items[0])

    @staticmethod
    def _normalize_post(raw: dict[str, Any]) -> dict[str, Any]:
        post = raw.get("post") or {}
        author = raw.get("author") or {}
        stats = raw.get("stats") or {}
        urn = post.get("urn") or {}

        def _urn(prefix: str, value: Any) -> Optional[str]:
            return f"{prefix}{value}" if value else None

        share_urn = _urn("urn:li:share:", urn.get("share_urn")) or _urn(
            "urn:li:ugcPost:", urn.get("ugcPost_urn")
        )
        activity_urn = _urn("urn:li:activity:", urn.get("activity_urn"))
        return {
            "text": post.get("text"),
            "urn": activity_urn or share_urn,
            "shareUrn": share_urn,
            "url": post.get("url"),
            "authorName": author.get("name"),
            "authorHeadline": author.get("headline"),
            "numLikes": stats.get("total_reactions"),
            "numComments": stats.get("comments"),
            "numShares": stats.get("shares"),
            "postedAtISO": post.get("created_at"),
        }

    def fetch_post_comments(
        self, *, post_id: str, max_items: int = 20, sort_order: str = "most relevant"
    ) -> list[dict[str, Any]]:
        items = self._run_sync(
            self.POST_COMMENTS_ACTOR,
            {"postIds": [post_id], "limit": min(max_items, 100), "sortOrder": sort_order},
        )
        return [it for it in items if isinstance(it, dict) and "summary" not in it]

    ENGAGER_TYPES = ("likers", "commenters", "reshares")

    def fetch_post_engagers(
        self, *, post_url: str, max_items: int = 50, types: Sequence[str] = ("likers", "commenters")
    ) -> list[dict[str, Any]]:
        wanted = tuple(dict.fromkeys(types))
        per_type = max(1, min(max_items // max(len(wanted), 1), 3000))
        engagers: list[dict[str, Any]] = []
        for kind in wanted:
            rows = self._run_sync(
                self.POST_ENGAGERS_ACTOR, {"urls": [post_url], "resultsLimit": per_type, "type": kind}
            )
            engagers += [{**r, "type": r.get("type", kind)} for r in rows if isinstance(r, dict)]
        return engagers[:max_items]

    def _run_sync(self, actor_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        url = f"{self.BASE_URL}/acts/{actor_id}/run-sync-get-dataset-items"
        r = self._session.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            try:
                body = r.json()
            except ValueError:
                body = {"error": r.text[:500]}
            raise ApifyError(f"HTTP {r.status_code}: {body}")
        data = r.json()
        if isinstance(data, dict) and "error" in data:
            raise ApifyError(f"actor failed: {data['error']}")
        return data if isinstance(data, list) else []
