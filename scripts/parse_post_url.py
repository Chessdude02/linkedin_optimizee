#!/usr/bin/env python3
"""Extract a LinkedIn post URN from a pasted URL.

LinkedIn posts show up in three different URN shapes depending on how
they were shared:

    /posts/slug-activity-7448...-XX   -> urn:li:activity:7448...
    /posts/slug-share-7449...-XX      -> urn:li:share:7449...
    /posts/slug-ugcPost-7450...-XX    -> urn:li:ugcPost:7450...
    /feed/update/urn:li:ugcPost:7447...  (already a URN, passed straight through)

A shortened lnkd.in link is NOT one of these -- it's a redirect. Open it
in a browser first, copy the URL it redirects to, and paste THAT here.

Usage: python3 scripts/parse_post_url.py
"""
from __future__ import annotations

import re

_PATTERNS = [
    ("activity", re.compile(r"activity-(\d+)")),
    ("share", re.compile(r"share-(\d+)")),
    ("ugcPost", re.compile(r"ugcPost-(\d+)")),
]

_ALREADY_URN = re.compile(r"urn:li:(activity|share|ugcPost):(\d+)")


def parse(url: str) -> str | None:
    already = _ALREADY_URN.search(url)
    if already:
        return f"urn:li:{already.group(1)}:{already.group(2)}"
    for urn_type, pattern in _PATTERNS:
        m = pattern.search(url)
        if m:
            return f"urn:li:{urn_type}:{m.group(1)}"
    return None


def main() -> None:
    url = input("Paste the full LinkedIn post URL (not a lnkd.in short link): ").strip()
    if "lnkd.in" in url:
        print(
            "That's a shortened link. Open it in a browser, let it redirect, "
            "then paste the full linkedin.com URL from the address bar."
        )
        raise SystemExit(1)
    urn = parse(url)
    if urn:
        print(urn)
    else:
        print(
            "Could not find an activity/share/ugcPost id in that URL. "
            "Make sure you pasted the full linkedin.com/posts/... URL, "
            "not a shortened or partial one."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
