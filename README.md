# LinkedIn Optimizee — Control Center

A human-in-the-loop authorization layer for LinkedIn automation built on
[sergebulaev/linkedin-skills](https://github.com/sergebulaev/linkedin-skills).
The core property this project enforces:

```
AGENT ≠ AUTHORIZER ≠ EXECUTOR
```

An agent can read, analyze, and propose. Only a human can authorize. Only
a separate execution service can execute — and only an authorized,
unmodified, non-expired, non-duplicate action, with global writes turned
on.

This is a risk-reduced, fail-closed, auditable design. It is not, and
does not claim to be, risk-free — no software architecture can honestly
claim that.

## Current status: Phase 1+2 only

Built and tested:

- **Database** (SQLite, 8 tables: users, agents, accounts, actions,
  approvals, executions, audit_logs, system_settings)
- **Explicit state machine** — no transition outside the allowed table is
  possible (`control_center/state_machine.py`)
- **Action Queue** — `request_action()` is the *only* thing an agent can
  call; there is no `publish_post()`, `delete_post()`, `approve_action()`,
  or `execute_action()` reachable with `caller_role="agent"`
  (`control_center/actions.py`)
- **Content hashing** — SHA-256 over every execution-relevant field;
  approval is tied to an exact hash, and any change to the payload,
  target, or account after approval blocks execution with
  `CONTENT_HASH_MISMATCH` (`control_center/hashing.py`)
- **Human approval interface** — `approve_action()` / `decline_action()`,
  callable only with `caller_role="human"`, approvals expire (default 15
  min) (`control_center/approvals.py`)
- **Execution service** — `execute_approved_action()`, callable only with
  `caller_role="executor"`. Runs the full pre-flight checklist (kill
  switch → action exists → known type → not already executed → is
  APPROVED → approval exists and hasn't expired → hash matches → atomic
  claim) before doing anything (`control_center/executor.py`)
- **Global kill switch** — fails closed on missing or corrupt state
  (`control_center/kill_switch.py`)
- **Append-only audit log** with secret-key scrubbing
  (`control_center/audit.py`)
- **Deterministic risk classification** — metadata only, never a
  substitute for approval (`control_center/risk.py`)
- **31 passing tests** covering authorization, integrity/tamper
  detection, expiration, duplicate detection, concurrent-execution
  safety, the kill switch, prompt-injection isolation, and fail-closed
  failure handling (`tests/`)

**Not built yet** (see the phasing this project follows):

- **Phase 3 — Dashboard.** No web UI exists. Today the only way to
  approve/decline/execute is by calling the Python functions directly (see
  `demo.py`). A real dashboard needs its own auth, sessions, CSRF
  protection, and backend-enforced authorization before it should exist —
  building that without a review checkpoint first was the wrong call.
- **Phase 4/5 — Real execution backend.** `execute_approved_action()`
  today only runs a mock backend (`MOCK_EXECUTION=true`, the default). If
  you set `MOCK_EXECUTION=false` it refuses to execute with
  `NotImplementedError` rather than pretending to publish. Wiring this to
  the real `linkedin-skills` Publora client, with an isolated write
  credential the agent process and dashboard never see, is unbuilt.
- `SEND_MESSAGE` and `MODIFY_PROFILE` action types are defined (for the
  schema to have a home for them later) but have no execution path —
  `linkedin-skills` itself has no LinkedIn DM API access and no automated
  profile-write path, so there is nothing to route yet.
- Full documentation set (SECURITY.md, ARCHITECTURE.md, THREAT_MODEL.md,
  RUNBOOK.md) — deferred to Phase 7, once the dashboard and real executor
  exist and there's an actual deployed system to document accurately.

## Quickstart

```bash
pip install -r requirements.txt   # only python-dotenv, optional
cp .env.example .env              # safe defaults: no real writes, mock mode
python3 demo.py                   # see the full flow end-to-end
python3 -m unittest discover -s tests -v
```

## Why a human still has to look at every action

Even once a real executor exists, nothing in this design auto-approves
based on risk level, batches approvals by default, or infers approval
from conversational history. `approve_action()` requires the exact
current payload hash — approving the wrong or since-changed action raises
`ContentHashMismatchError` instead of silently approving whatever is
there now. An agent's output is a proposal, never an authorization,
however confident, well-formatted, or urgent it reads.

## License

Not yet decided — add one before treating this as anything other than a
personal project.
