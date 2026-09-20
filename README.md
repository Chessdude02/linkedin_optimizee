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

## Current status: Phase 1+2+3+4/5

Built and tested. Important caveat up front: Phase 4/5 (below) has never
been run against the real Publora API or a real LinkedIn account —
everything is unit-tested with the network mocked. Treat it as reviewed,
not as proven in production, until you've run it yourself against a real
(ideally low-stakes) account.

### Real execution backend (Phase 4/5)

- **`control_center/backends/publora.py`** — implements the Publora
  endpoints for every action type that has one: `CREATE_POST`/
  `SCHEDULE_POST`, `CREATE_COMMENT`/`CREATE_REPLY`, `CREATE_REACTION`,
  `RESHARE_POST`, `DELETE_POST`, `DELETE_COMMENT`. `SEND_MESSAGE` and
  `MODIFY_PROFILE` still have no backend (see below) and raise rather than
  silently succeeding.
- **Credential isolation, enforced by import structure, not just intent**
  — `PUBLORA_API_KEY` is read only inside `backends/publora.py`, which is
  imported *lazily*, only from `executor._run_backend`, only when
  `MOCK_EXECUTION=false`. Importing `control_center.actions` (what agents
  use) or anything under `dashboard/` never reaches this module. A test
  (`test_dashboard_process_never_touches_the_publora_credential`) asserts
  no module under `dashboard/` references `executor` or `publora` in its
  namespace at all.
- **Account registry** (`control_center/accounts.py`) — maps a
  control-center `account_id` to the real Publora `platformId`. Connecting
  an account is a deliberate, separate operator step (see `.env.example`),
  not something an agent or the dashboard's approve/decline flow can do.
- **Fail-closed on ambiguity, distinctly from a definite failure** — an
  HTTP 4xx/5xx from Publora raises and the action is marked `FAILED`; a
  timeout or connection error returns `UNKNOWN` instead, and the action is
  left `EXECUTING` for a human to investigate rather than being retried or
  guessed into either outcome.
- **19 additional passing tests** (106 total): every action type's request
  shape, the reaction-type alias table, HTTP-error vs. timeout/connection-
  error handling, the missing-credential and missing-account-registration
  fail-closed paths, and a full mocked-network integration test through
  `executor.execute_approved_action` end to end. No test ever makes a real
  network call.

Connect an account and go live (only in the execution service's own
environment):

```bash
python3 -c "
from control_center import accounts, db
conn = db.get_connection('control_center.db')
accounts.register_account(conn, 'my-account', 'Display name', 'linkedin-XXXXXXX')
"
# in run_executor.py's .env only: PUBLORA_API_KEY=sk_..., MOCK_EXECUTION=false
python3 run_executor.py
```

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
- **11 additional passing tests** covering auth, lockout, CSRF
  enforcement, approve/decline with correct and tampered hashes, the kill
  switch's login+CSRF requirements, and the two structural
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
- **31 tests** covering authorization, integrity/tamper detection,
  expiration, duplicate detection, concurrent-execution safety, the kill
  switch, prompt-injection isolation, and fail-closed failure handling
  (`tests/`); plus a further **25 tests** added in a later hardening pass
  directly covering `hashing.py`, `risk.py`, `audit.py` query behaviour,
  schema creation, and `run_executor.py`'s loop body — everything above
  had only indirect coverage until then. **106 tests total, all passing.**

**Not built yet** (see the phasing this project follows):

- `SEND_MESSAGE` and `MODIFY_PROFILE` action types are defined (for the
  schema to have a home for them later) but have no execution path —
  `linkedin-skills` itself has no LinkedIn DM API access and no automated
  profile-write path, so there is nothing to route yet. `executor.py`
  refuses both with `BLOCKED: action_type_not_implemented`.
- Full documentation set (SECURITY.md, ARCHITECTURE.md, THREAT_MODEL.md,
  RUNBOOK.md) — deferred to Phase 7, once there's real production usage
  to document accurately rather than a speculative one written before
  anyone has run this against a live account.

## Quickstart

```bash
pip install -r requirements.txt   # python-dotenv (optional), flask, requests
cp .env.example .env              # safe defaults: no real writes, mock mode
python3 demo.py                   # library-only flow, no dashboard needed
python3 -m unittest discover -s tests -v   # all 106 tests
```

To try the dashboard + separate executor, see the Phase 3 section above.
To go from mock to real execution, see the Phase 4/5 section above — and
read its caveat first.

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
