#!/usr/bin/env python3
"""Run the Research & Discovery Agent: check the watchlist, surface
research findings.

This process never calls control_center.actions.request_action() and has
no import of control_center.executor or control_center.backends anywhere
-- it cannot publish anything itself, at any stage. It needs APIFY_TOKEN
(read layer) and, optionally, ANTHROPIC_API_KEY (drafting -- without it,
nothing gets surfaced, since a template stub isn't worth a human's review
time). Findings land in the research dashboard for review; converting one
into an action proposal is a separate, explicit, human step.

Usage:
  python3 run_research_agent.py --once      # one pass, then exit
  python3 run_research_agent.py             # polls forever
"""
from __future__ import annotations

import argparse
import time

from agents.research_agent import run_research
from control_center import db, settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=3600.0,
                         help="seconds between passes in loop mode (default 1h -- "
                              "Apify calls cost money per run, don't poll aggressively)")
    args = parser.parse_args()

    conn = db.get_connection(settings.DB_PATH)
    db.init_db(conn)

    def run_pass() -> None:
        summary = run_research(conn)
        if not summary["surfaced"]:
            print("Nothing new worth surfacing this pass.")
        for item in summary["surfaced"]:
            print(f"Surfaced {item['opportunity_type']}: research item {item['item_id']}")
        for err in summary["errors"]:
            print(f"ERROR on {err['target']}: {err['error']}")
        print(f"Run {summary['run_id']} complete. Review findings in the dashboard's Research tab.")

    if args.once:
        run_pass()
        return

    try:
        while True:
            run_pass()
            time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
