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

## Current status: Phase 1+2+3

Built and tested:

### Dashboard (Phase 3)

- **Flask app** (`dashboard/`) with server-rendered pages only — no
  frontend JavaScript, no secrets or tokens in the browser beyond the
  signed session cookie itself
- **Authentication** — single operator account, credentials from
  environment vars, password hashed with `hashlib.scrypt`
  (`dashboard/security.py`), login rate-limited with a lockout after 5
  failed attempts in 5 minutes
- **CSRF protection** on every state-changing POST (`dashboard/csrf.py`)
- **Secure session cookies** — HttpOnly, SameSite=Strict, Secure by
  default (opt out only for local plain-HTTP dev)
- **Backend-enforced authorization** — every route calls
  `approvals.approve_action(caller_role="human", approved_by=session["user"], ...)`;
  `caller_role` is never taken from the request
- **Structurally cannot execute** — `dashboard/` never imports
  `control_center.executor` at all; there is no route, button, or code
  path from the dashboard to a real write. Execution is a *separate
  process*, `run_executor.py`, that you run independently. Two tests
  (`tests/test_dashboard.py`) assert this structurally: no route
  contains "execute", and neither `dashboard.app` nor
  `dashboard.routes.pending` has `executor` in their namespace.
- **Required pages**: Dashboard (counts by status), Pending Actions
  (list), Action Detail (exact content, hash, agent's reason, risk,
  approve/decline), Audit Log (filterable), System Controls (kill switch
  + write status)
- **11 additional passing tests** (42 total) covering auth, lockout,
  CSRF enforcement, approve/decline with correct and tampered hashes, the
  kill switch's login+CSRF requirements, and the two structural
  execution-isolation checks above

Run it:

```bash
python3 scripts/hash_password.py         # generate DASHBOARD_PASSWORD_HASH
# put the values into .env, then:
python3 dashboard/app.py                 # dashboard on :5000 -- approve/decline only
python3 run_executor.py --once           # SEPARATE process -- actually executes APPROVED actions (mock)
```

### Phase 1+2 (security foundation + action queue)

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
pip install -r requirements.txt   # python-dotenv (optional) + flask (for the dashboard)
cp .env.example .env              # safe defaults: no real writes, mock mode
python3 demo.py                   # library-only flow, no dashboard needed
python3 -m unittest discover -s tests -v   # all 42 tests
```

To try the dashboard + separate executor, see the Phase 3 section above.

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
