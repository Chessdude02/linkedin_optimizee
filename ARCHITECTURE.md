# Architecture

This document describes the system as it actually exists after Phase
1 through 5, including one real end-to-end run against a live LinkedIn
account. It is not a design proposal — everything described here has run.

## The one property that matters

```
AGENT ≠ AUTHORIZER ≠ EXECUTOR
```

No single process can both decide an action is a good idea and make it
happen. Concretely:

- **Agents** (or a human using the CLI scripts the same way an agent
  would) can only call `control_center.actions.request_action()`. That
  function's only effect is inserting a `PENDING` row. There is no
  `publish_post()`, `approve_action()`, or `execute_action()` reachable
  with `caller_role="agent"`.
- **Humans** approve or decline through the dashboard (`dashboard/`), a
  Flask process. Approving calls `approvals.approve_action()` with
  `caller_role="human"` hardcoded server-side — never taken from the
  request. This process never imports `control_center.executor` at all.
- **The execution service** (`run_executor.py`) is a separate OS process.
  It is the only thing that ever imports `control_center.backends.publora`,
  and therefore the only thing that ever needs `PUBLORA_API_KEY` in its
  environment.

This is enforced by which module imports which, not by convention. Two
tests (`tests/test_dashboard.py`) assert the dashboard's route map has no
route containing "execute" and that no module under `dashboard/`
references `executor` or `publora` in its namespace.

## Component diagram

```
  ┌─────────────┐   request_action()   ┌──────────────────┐
  │   Agent /    │ ────────────────────▶│   control_center  │
  │  manual CLI  │                       │   .actions        │  (agent-facing)
  └─────────────┘                       └─────────┬────────┘
                                                    │ INSERT (status=PENDING)
                                                    ▼
                                          ┌───────────────────┐
                                          │  SQLite database   │
                                          │  (control_center.  │
                                          │       db)           │
                                          └─────────┬──────────┘
                                                    │
                     approve_action() /             │             execute_approved_action()
                     decline_action()                │             (caller_role="executor")
                              │                      │                        │
                              ▼                      │                        ▼
                    ┌──────────────────┐             │              ┌──────────────────┐
                    │    dashboard/      │◀───────────┘              │  run_executor.py  │
                    │  (Flask, human-    │                            │  (separate        │
                    │   facing, browser) │                            │   process)         │
                    └──────────────────┘                            └─────────┬─────────┘
                                                                                 │ lazy import,
                                                                                 │ only if
                                                                                 │ MOCK_EXECUTION=false
                                                                                 ▼
                                                                     ┌────────────────────┐
                                                                     │ control_center.      │
                                                                     │ backends.publora      │
                                                                     │ (reads PUBLORA_API_   │
                                                                     │  KEY, calls the real  │
                                                                     │  Publora API)         │
                                                                     └────────────────────┘
```

The dashboard and the execution service both read the same SQLite file
but are separate processes with separate import graphs and (in a proper
deployment) separate environments — see **Known deviation from ideal
isolation** below.

## Data flow through one action

1. `actions.request_action()` computes `payload_hash = SHA256(action_type,
   account_id, target_id, payload, schedule)` and inserts a row:
   `status=PENDING`, `expires_at = now + PENDING_TTL_MINUTES` (default 24h).
2. A human opens the action in the dashboard, sees the exact stored
   content, and clicks Approve. The form submits the `payload_hash` that
   was rendered on the page as a hidden field.
3. `approvals.approve_action()` re-reads the action's *current*
   `payload_hash` from the database and compares it to what the form
   submitted. Mismatch → `ContentHashMismatchError`, nothing changes.
   Match → an `approvals` row is inserted with `approved_hash` frozen at
   that value and `expires_at = now + APPROVAL_TTL_MINUTES` (default 15
   min), and the action's status flips to `APPROVED`.
4. `run_executor.py`, running as its own process, polls for `APPROVED`
   actions (or is run with `--once` for a single pass). For each one it
   calls `executor.execute_approved_action()`.
5. That function runs the full pre-flight checklist (see
   `control_center/executor.py`'s docstring) before doing anything:
   kill switch → action exists → known type → not already executed →
   status is APPROVED → an approval record exists and hasn't expired →
   the *current* payload hash (recomputed from the action's stored
   fields right now) still matches the hash frozen at approval time →
   atomic `UPDATE ... WHERE status='APPROVED'` claim (so two concurrent
   workers can't both execute it).
6. Only after all of that does `_run_backend()` run — mock by default,
   or (lazily importing `backends/publora.py`) a real Publora API call
   when `MOCK_EXECUTION=false`.
7. The result updates `actions.status` to `EXECUTED` or `FAILED`, or
   leaves it `EXECUTING` with an `executions.result='UNKNOWN'` row if the
   network call timed out or reset — genuinely ambiguous outcomes are
   never guessed into either terminal state.
8. Every step along the way writes an `audit_logs` row.

## State machine

```
PENDING ──┬─▶ APPROVED ──┬─▶ EXECUTING ──┬─▶ EXECUTED
          │              │               └─▶ FAILED
          ├─▶ DECLINED   ├─▶ BLOCKED
          └─▶ EXPIRED    └─▶ EXPIRED
```

All terminal states (`DECLINED`, `EXPIRED`, `EXECUTED`, `FAILED`,
`BLOCKED`) have no outgoing transitions — `control_center/state_machine.py`
enforces this and every transition anywhere in the codebase goes through
it. Notably: an action stuck in `FAILED` (e.g. from a bad credential)
cannot be retried in place. A fresh `request_action()` call with a new
`payload_hash` is required — this came up during real testing when a
`CREATE_REACTION` action failed on an invalid API key.

## Database

SQLite, 8 tables: `users`, `agents`, `accounts`, `actions`, `approvals`,
`executions`, `audit_logs`, `system_settings`. WAL mode is enabled so the
dashboard (reader/writer) and the execution service (writer) can operate
against the same file concurrently without blocking each other for reads.
The atomic-claim pattern (`UPDATE ... WHERE status = 'APPROVED'`, checking
`rowcount`) relies on SQLite's single-writer lock — verified under real
concurrent access in `tests/test_duplicate_and_concurrency.py`, which runs
two threads with two separate connections racing to execute the same
action and asserts exactly one wins.

## Known deviation from ideal isolation

Section 50 of the design this project follows calls for the write
credential (`PUBLORA_API_KEY`) to live *only* in the execution service's
environment — never the dashboard's, never an agent's. The code enforces
this at the import level (see above). In the actual first real deployment,
however, the operator ran both the dashboard and the execution service on
the same machine reading the same `.env` file, meaning the dashboard
process's `os.environ` technically contains `PUBLORA_API_KEY` even though
no code path in `dashboard/` ever reads it.

This is a documented, accepted gap for a single-operator personal
deployment, not a silent one. True isolation requires two separate `.env`
files (or environments) — one for the dashboard, one for
`run_executor.py` — with the dashboard's simply never containing
`PUBLORA_API_KEY` at all. See `RUNBOOK.md` for how to split them if a
stricter deployment is warranted.

## Read side (not built)

This project only implements the write path. Reading LinkedIn content
(post bodies, comment threads, engagement data) is out of scope here and
is the job of `sergebulaev/linkedin-skills`' Apify-backed layer, a
separate codebase. Nothing here fetches or analyzes LinkedIn content.
