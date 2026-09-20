"""Content drafting for the Exploration Agent, via the Claude API.

Given a post's data (and its comments), asks Claude to decide what's
worth proposing and draft the actual content -- a real comment, a real
reshare caption, a real new-post idea -- rather than the Exploration
Agent just flagging "something happened" for a human to write from
scratch. The human still approves or declines every draft; this module
only ever produces PROPOSALS, never anything sent to `request_action()`
directly (that's `agents/exploration_agent.py`'s job).

Requires ANTHROPIC_API_KEY. Without it, `analyze` returns a template
stub per proposal type instead of a real draft, and marks the drafts as
low-quality via `"drafted": False` -- following the same manual-fallback
pattern used throughout this codebase (Publora/Apify/Pixfaro all degrade
gracefully rather than refusing to run without a credential).
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

MODEL = "claude-sonnet-5"

_SYSTEM_PROMPT = """You help decide what LinkedIn engagement is worth proposing to a human for review, and draft the actual content for each one.

You are given one post's data (author, text, engagement stats) and its top comments. Decide, independently, whether each of these is worth proposing:
- reacting to the post (a LIKE, or another reaction type if genuinely more fitting)
- leaving a top-level comment on the post
- resharing the post to the user's own feed with commentary
- writing the user's own new post, inspired by this one's topic or hook (not copying it)

Only propose something if it's genuinely worth a human's attention -- not every post deserves a reaction, not every post is reshare-worthy, not every post inspires a good new angle. Say no to things that aren't worth it.

For anything you propose, draft the ACTUAL content a human could approve as-is: a real comment (200-350 chars), a real reshare caption if any, a real post draft (900-1300 chars) if proposing one. Voice: direct, specific, no corporate hedging, no "leverage"/"unlock"/"delve"-style AI vocabulary, no more than ~1 em dash per 100 words.

Respond with ONLY a JSON object, no other text, matching this shape exactly:
{
  "reaction": {"propose": bool, "reaction_type": "LIKE"|"PRAISE"|"EMPATHY"|"INTEREST"|"APPRECIATION"|"ENTERTAINMENT", "reason": str},
  "comment": {"propose": bool, "draft": str, "reason": str},
  "reshare": {"propose": bool, "commentary": str, "reason": str},
  "new_post": {"propose": bool, "draft": str, "reason": str}
}"""


def _template_fallback(post: dict[str, Any]) -> dict[str, Any]:
    """No ANTHROPIC_API_KEY: propose nothing rather than draft something
    low-quality without a real model behind it."""
    return {
        "reaction": {"propose": False, "reaction_type": "LIKE", "reason": "ANTHROPIC_API_KEY not set"},
        "comment": {"propose": False, "draft": "", "reason": "ANTHROPIC_API_KEY not set"},
        "reshare": {"propose": False, "commentary": "", "reason": "ANTHROPIC_API_KEY not set"},
        "new_post": {"propose": False, "draft": "", "reason": "ANTHROPIC_API_KEY not set"},
        "drafted": False,
    }


def analyze(
    post: dict[str, Any],
    comments: list[dict[str, Any]],
    *,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """Ask Claude what's worth proposing for this post, with real drafts.

    Returns a dict with "reaction"/"comment"/"reshare"/"new_post" keys
    (each {"propose": bool, ...fields, "reason": str}) and "drafted": bool
    indicating whether a real model call happened.
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return _template_fallback(post)

    from anthropic import Anthropic

    client = Anthropic(api_key=key)
    user_content = json.dumps(
        {
            "post": {
                "author": post.get("authorName"),
                "text": post.get("text"),
                "numLikes": post.get("numLikes"),
                "numComments": post.get("numComments"),
                "numShares": post.get("numShares"),
            },
            "top_comments": [
                {"author": c.get("author", {}).get("name") if isinstance(c.get("author"), dict) else c.get("authorName"),
                 "text": c.get("text") or c.get("comment")}
                for c in comments[:10]
            ],
        },
        default=str,
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw_text = "".join(block.text for block in response.content if hasattr(block, "text"))
    parsed = json.loads(raw_text)
    parsed["drafted"] = True
    return parsed
