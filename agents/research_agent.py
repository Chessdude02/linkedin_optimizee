"""The Research & Discovery Agent: watches specific posts, surfaces
research findings. READ-ONLY with respect to the Action Queue.

RESEARCH ≠ AUTHORIZE ≠ EXECUTE. This agent's only capabilities are read
calls (Apify) and one write capability scoped entirely to its own,
separate research_items table (control_center.research). It never calls
control_center.actions.request_action() -- discovering, analyzing, and
drafting content never by itself creates anything in the `actions`
table. A human must explicitly convert a finding
(research.convert_to_action, triggered from the dashboard) before
anything becomes a PENDING action -- and even then, that PENDING action
still needs separate approval and execution exactly like any other.

It cannot approve, execute, touch the kill switch, register accounts, or
manage its own watchlist. A compromised or malfunctioning run can, at
worst, fill the research dashboard with findings a human has to read and
explicitly act on one by one -- it cannot make anything happen on
LinkedIn by itself, at any stage.

Opportunity-type mapping (this project's extension of the four
LinkedIn-write-shaped action types onto the broader opportunity taxonomy
the design calls for -- COMMENT_OPPORTUNITY is a direct match; the other
three don't have exact equivalents in that taxonomy, since it does not
enumerate a reaction/reshare opportunity type):
    CREATE_REACTION -> ENGAGEMENT_OPPORTUNITY
    CREATE_COMMENT  -> COMMENT_OPPORTUNITY
    RESHARE_POST    -> RESHARE_OPPORTUNITY
    CREATE_POST     -> CONTENT_IDEA

Deferred by design, not by oversight: relevance/recency/discussion/
novelty SCORES are not computed here. With only a single point-in-time
check of each watched post (no history of how it's grown, no comparison
across many posts), any number put in those fields would be invented,
not measured -- exactly what this project's content-integrity rules
forbid. They stay NULL until there's a real signal to back them.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from control_center import drafting, research, watchlist
from control_center.read_sources.apify import ApifyClient, ApifyError

AGENT_ID = "research-agent"

_OPPORTUNITY_FOR_ACTION_TYPE = {
    "CREATE_REACTION": "ENGAGEMENT_OPPORTUNITY",
    "CREATE_COMMENT": "COMMENT_OPPORTUNITY",
    "RESHARE_POST": "RESHARE_OPPORTUNITY",
    "CREATE_POST": "CONTENT_IDEA",
}


def _surface(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    post: dict[str, Any],
    source_url: str,
    account_id: str,
    action_type: str,
    target_id: str | None,
    payload: dict[str, Any],
    reason: str,
) -> dict[str, Any] | None:
    opportunity_type = _OPPORTUNITY_FOR_ACTION_TYPE[action_type]
    item_id, created = research.create_or_touch_item(
        conn,
        run_id=run_id,
        source="apify:linkedin-post-detail",
        source_url=source_url,
        account_id=account_id,
        opportunity_type=opportunity_type,
        external_id=post.get("urn"),
        author=post.get("authorName"),
        published_at=post.get("postedAtISO"),
        content=post.get("text"),
        reason_surfaced=reason,
        draft_content=payload.get("message") or payload.get("content") or payload.get("commentary"),
        suggested_action_type=action_type,
        suggested_target_id=target_id,
        suggested_payload=payload,
        quality_signals={
            "numLikes": post.get("numLikes"),
            "numComments": post.get("numComments"),
            "numShares": post.get("numShares"),
        },
    )
    if not created:
        return None  # already surfaced before; last_seen/times_seen bumped, nothing new to show
    return {"item_id": item_id, "opportunity_type": opportunity_type}


def research_one(
    conn: sqlite3.Connection, run_id: str, target: dict[str, Any], apify: ApifyClient
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Check one watchlist target. Returns (surfaced_items, errors).
    Fails closed per-target: a fetch or drafting error here is recorded
    and this target is skipped, but does not stop the rest of the run."""
    errors: list[dict[str, str]] = []
    try:
        post = apify.fetch_post(target["post_url"])
        comments = apify.fetch_post_comments(post_id=post["urn"] or target["post_url"])
    except ApifyError as exc:
        errors.append({"target": target["post_url"], "error": str(exc)})
        return [], errors

    watchlist.record_check(conn, target["id"], len(comments))

    try:
        analysis = drafting.analyze(post, comments)
    except Exception as exc:  # noqa: BLE001 -- a bad/unparseable model response must not crash the run
        errors.append({"target": target["post_url"], "error": f"drafting failed: {exc}"})
        return [], errors

    account_id = target["account_id"]
    surfaced: list[dict[str, Any]] = []
    post_target = post.get("urn") or target["post_url"]
    reshare_target = post.get("shareUrn") or post_target

    reaction = analysis.get("reaction", {})
    if reaction.get("propose"):
        item = _surface(
            conn, run_id, post=post, source_url=target["post_url"], account_id=account_id,
            action_type="CREATE_REACTION", target_id=post_target,
            payload={"reaction_type": reaction.get("reaction_type", "LIKE")},
            reason=reaction.get("reason", ""),
        )
        if item:
            surfaced.append(item)

    comment = analysis.get("comment", {})
    if comment.get("propose") and comment.get("draft"):
        item = _surface(
            conn, run_id, post=post, source_url=target["post_url"], account_id=account_id,
            action_type="CREATE_COMMENT", target_id=post_target,
            payload={"message": comment["draft"]}, reason=comment.get("reason", ""),
        )
        if item:
            surfaced.append(item)

    reshare = analysis.get("reshare", {})
    if reshare.get("propose"):
        item = _surface(
            conn, run_id, post=post, source_url=target["post_url"], account_id=account_id,
            action_type="RESHARE_POST", target_id=reshare_target,
            payload={"commentary": reshare.get("commentary", "")}, reason=reshare.get("reason", ""),
        )
        if item:
            surfaced.append(item)

    new_post = analysis.get("new_post", {})
    if new_post.get("propose") and new_post.get("draft"):
        item = _surface(
            conn, run_id, post=post, source_url=f"inspired-by:{target['post_url']}", account_id=account_id,
            action_type="CREATE_POST", target_id=None,
            payload={"content": new_post["draft"]}, reason=new_post.get("reason", ""),
        )
        if item:
            surfaced.append(item)

    return surfaced, errors


def run_research(conn: sqlite3.Connection) -> dict[str, Any]:
    """Run one research pass over the whole watchlist. Never touches the
    actions table. Returns a summary: {run_id, surfaced: [...], errors: [...]}."""
    run_id = research.start_run(conn, AGENT_ID)
    apify = ApifyClient()
    all_surfaced: list[dict[str, Any]] = []
    all_errors: list[dict[str, str]] = []
    targets = watchlist.list_targets(conn)

    for target in targets:
        surfaced, errors = research_one(conn, run_id, target, apify)
        all_surfaced += surfaced
        all_errors += errors

    research.finish_run(
        conn,
        run_id,
        sources_accessed=[t["post_url"] for t in targets],
        result_count=len(all_surfaced),
        errors=all_errors,
    )
    return {"run_id": run_id, "surfaced": all_surfaced, "errors": all_errors}
