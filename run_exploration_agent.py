#!/usr/bin/env python3
"""Run the Exploration Agent: check the watchlist, propose actions.

This process only ever calls control_center.actions.request_action() --
it has no import of control_center.executor or control_center.backends
anywhere, and cannot publish anything itself. It needs APIFY_TOKEN (read
layer) and, optionally, ANTHROPIC_API_KEY (drafting -- without it,
nothing gets proposed, since a template stub isn't worth a human's
review time).

Usage:
  python3 run_exploration_agent.py --once      # one pass, then exit
  python3 run_exploration_agent.py             # polls forever
"""
from __future__ import annotations

import argparse
import time

from agents.exploration_agent import explore_all
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
        proposed = explore_all(conn)
        if not proposed:
            print("Nothing new worth proposing this pass.")
        for item in proposed:
            print(f"Proposed {item['action_type']}: {item['result']}")

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
