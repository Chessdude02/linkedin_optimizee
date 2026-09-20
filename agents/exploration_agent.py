"""The Exploration Agent: watches specific posts, proposes actions.

This is an "agent" only in the sense the whole project's design uses that
word -- it has exactly one capability, calling
control_center.actions.request_action(caller_role="agent", ...). It
cannot approve, cannot execute, cannot touch the kill switch, cannot
register accounts or add itself to the watchlist. A compromised or
malfunctioning run of this agent can, at worst, fill the PENDING queue
with proposals a human still has to read and click through one by one.

For each watched post it: fetches the post + its comments via Apify,
asks Claude what's worth proposing (control_center.drafting.analyze),
and for anything worth proposing that doesn't already have an open or
executed action against that target, calls request_action().
"""
from __future__ import annotations

import sqlite3
from typing import Any

from control_center import actions, drafting, watchlist
from control_center.exceptions import DuplicateActionError
from control_center.read_sources.apify import ApifyClient

AGENT_ID = "exploration-agent"


def _propose(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    action_type: str,
    target_id: str,
    payload: dict[str, Any],
    reason: str,
) -> dict[str, Any] | None:
    if actions.has_open_or_executed(conn, target_id=target_id, action_type=action_type):
        return None
    try:
        return actions.request_action(
            conn,
            caller_role="agent",
            agent_id=AGENT_ID,
            account_id=account_id,
            action_type=action_type,
            target_id=target_id,
            payload=payload,
            reason=reason,
        )
    except DuplicateActionError:
        # Edge case: content happened to hash-match an existing active
        # action despite the has_open_or_executed check above (e.g. a
        # race with another run). Skip rather than crash the whole pass.
        return None


def explore_one(conn: sqlite3.Connection, target: dict[str, Any], apify: ApifyClient) -> list[dict[str, Any]]:
    """Check one watchlist target, propose whatever's worth proposing.
    Returns the list of {"action_type": ..., "result": ...} for anything
    actually proposed (skips are not included)."""
    post = apify.fetch_post(target["post_url"])
    comments = apify.fetch_post_comments(post_id=post["urn"] or target["post_url"])
    watchlist.record_check(conn, target["id"], len(comments))

    analysis = drafting.analyze(post, comments)
    account_id = target["account_id"]
    proposed: list[dict[str, Any]] = []

    post_target = post.get("urn") or target["post_url"]
    reshare_target = post.get("shareUrn") or post_target

    reaction = analysis.get("reaction", {})
    if reaction.get("propose"):
        result = _propose(
            conn, account_id=account_id, action_type="CREATE_REACTION", target_id=post_target,
            payload={"reaction_type": reaction.get("reaction_type", "LIKE")},
            reason=reaction.get("reason", ""),
        )
        if result:
            proposed.append({"action_type": "CREATE_REACTION", "result": result})

    comment = analysis.get("comment", {})
    if comment.get("propose") and comment.get("draft"):
        result = _propose(
            conn, account_id=account_id, action_type="CREATE_COMMENT", target_id=post_target,
            payload={"message": comment["draft"]}, reason=comment.get("reason", ""),
        )
        if result:
            proposed.append({"action_type": "CREATE_COMMENT", "result": result})

    reshare = analysis.get("reshare", {})
    if reshare.get("propose"):
        result = _propose(
            conn, account_id=account_id, action_type="RESHARE_POST", target_id=reshare_target,
            payload={"commentary": reshare.get("commentary", "")}, reason=reshare.get("reason", ""),
        )
        if result:
            proposed.append({"action_type": "RESHARE_POST", "result": result})

    new_post = analysis.get("new_post", {})
    if new_post.get("propose") and new_post.get("draft"):
        # A brand-new post isn't tied to the watched post, so it can't
        # collide with has_open_or_executed on a shared target_id --
        # give it a synthetic per-source target so re-running the agent
        # on the same watched post doesn't spam duplicate post ideas.
        synthetic_target = f"inspired-by:{post_target}"
        result = _propose(
            conn, account_id=account_id, action_type="CREATE_POST", target_id=synthetic_target,
            payload={"content": new_post["draft"]}, reason=new_post.get("reason", ""),
        )
        if result:
            proposed.append({"action_type": "CREATE_POST", "result": result})

    return proposed


def explore_all(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Run one pass over the whole watchlist. Returns everything proposed
    across all targets."""
    apify = ApifyClient()
    proposed: list[dict[str, Any]] = []
    for target in watchlist.list_targets(conn):
        proposed += explore_one(conn, target, apify)
    return proposed
