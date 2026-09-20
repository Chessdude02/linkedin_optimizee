# Runbook

Operational guide: setup, day-to-day use, troubleshooting, and incident
response. Every troubleshooting entry below came from a real failure
during the first live setup of this project (on Windows/PowerShell) —
none of it is speculative.

## Setup

```bash
git clone https://github.com/Chessdude02/linkedin_optimizee.git
cd linkedin_optimizee
pip install -r requirements.txt
cp .env.example .env
```

Generate the dashboard's two secrets:

```bash
python3 scripts/hash_password.py       # prompts for a password, writes
                                        # DASHBOARD_PASSWORD_HASH into .env
                                        # directly -- nothing to copy/paste
python3 -c "import secrets; print(secrets.token_hex(32))"   # DASHBOARD_SECRET_KEY
```

Put the secret-key output and a `DASHBOARD_USERNAME` of your choice into
`.env` (there's no signup flow — you invent the username yourself).
Verify everything loaded before going further:

```bash
python3 scripts/verify_env.py
```

Fix anything it flags before continuing. Leave `WRITE_ENABLED=false` and
`MOCK_EXECUTION=true` for now.

## Starting the two processes

**Dashboard** (human review/approval — cannot execute anything):
```bash
python3 -m dashboard.app
```
**Not** `python3 dashboard/app.py` — see Troubleshooting below for why
that fails.

**Execution service** (separate terminal, separate process — the only
thing that can actually publish):
```bash
python3 run_executor.py --once     # one pass over APPROVED actions, then exit
python3 run_executor.py            # polls forever
```

## Day-to-day operation

1. Create an action request (`scripts/request_action.py` for manual
   testing; an agent calls `control_center.actions.request_action()`
   directly in a real deployment).
2. Open the dashboard, review it under **Pending**, click into it, read
   the *exact* content, **Approve** or **Decline**.
3. Run the execution service (`--once` for a manual test, or leave it
   polling).
4. Check **Audit Log** for the full trail, or the actual LinkedIn post
   for real executions — see "Don't trust EXECUTED blindly" below.

### The kill switch

**System Controls** in the dashboard. Toggle it off whenever you're not
actively testing or running for real — there's no reason to leave real
writes armed. It overrides everything: existing approvals, in-flight
requests, all of it. If the kill-switch state is ever unreadable/corrupt,
the system fails closed (writes blocked) — verified in
`tests/test_kill_switch.py`.

### Registering a LinkedIn account for real execution

```bash
python3 scripts/register_account.py
```
You need the account's Publora `platform_id` (format `linkedin-XXXXXXX`),
found in Publora's dashboard under **Channels → your LinkedIn account**.
This is a deliberate manual step — no agent or dashboard flow can do it.

### Getting a post's URN

LinkedIn post URLs come in three shapes (`activity`, `share`, `ugcPost`).
A shortened `lnkd.in` link is **not** one of these — it's a redirect.

```bash
python3 scripts/parse_post_url.py
```
Open the `lnkd.in` link in a browser first, let it redirect, and paste
the **full** resulting `linkedin.com/...` URL. Pasting the short link
directly will fail to parse (and, before this was fixed, an earlier
version of this script also failed silently on legitimate `ugcPost`-shaped
URLs — fixed in `scripts/parse_post_url.py`, covered by
`tests/test_url_parser.py`).

## Troubleshooting

### `ModuleNotFoundError: No module named 'control_center'`

You ran `python3 dashboard/app.py` directly. Running a script by path only
puts its own directory on Python's import path, not the repo root where
`control_center/` lives as a sibling package. Run it as a module instead,
from the repo root:
```bash
python3 -m dashboard.app
```

### `RuntimeError: DASHBOARD_SECRET_KEY is not set`

The variable is either missing or **empty** in `.env` (e.g. the line
reads `DASHBOARD_SECRET_KEY=` with nothing after the `=` — this happens
when you generate the value but forget to actually paste it in). Run
`python3 scripts/verify_env.py` to confirm; it reports presence and shape
without exposing the value.

### `.env` changes don't seem to take effect

The most common causes, in order of likelihood:

1. **The value was generated but never actually written to the file.**
   This happened repeatedly during the first live setup — a script prints
   a value, and the step of pasting it into `.env` gets silently skipped.
   Prefer scripts that write directly (`scripts/hash_password.py` does
   this now) over copy-paste. To update any other value without manual
   editing:
   ```python
   import re
   from pathlib import Path
   env_path = Path(".env")
   text = env_path.read_text(encoding="utf-8")
   text = re.sub(r"^KEY_NAME=.*$", "KEY_NAME=new_value", text, flags=re.MULTILINE)
   env_path.write_text(text, encoding="utf-8")
   ```
2. **The file is actually named `.env.txt`**, not `.env` — a classic
   Notepad "Save As" default on Windows (it appends `.txt` unless you
   explicitly choose "All Files"). Check with:
   ```powershell
   Get-ChildItem -Force | Where-Object { $_.Name -like ".env*" }
   ```
3. Verify with `python3 scripts/verify_env.py` after any fix, before
   assuming it worked.

### Login fails with "Invalid username or password" even though you're sure it's right

Verify independently of the web form:
```python
from dotenv import load_dotenv; load_dotenv()
import os
from dashboard.security import verify_password
print(verify_password("the password you're typing", os.environ.get("DASHBOARD_PASSWORD_HASH") or ""))
```
If this prints `False`, the stored hash doesn't match — regenerate it with
`scripts/hash_password.py` (which now writes directly, avoiding the
copy-paste gap above) rather than debugging further. `getpass`-based
password prompts have been observed to behave inconsistently in some
Windows terminal/IDE-embedded shells (silent truncation, inconsistent
echo suppression) — if it keeps happening, use a plain `input()`-based
script instead and accept the password briefly appearing in your
terminal/history for a local dev setup.

### "Too many failed attempts" (429) on login

Rate limiter locked you out after 5 failures in 5 minutes (per username,
in-memory, resets when the dashboard process restarts). Wait 5 minutes or
restart the dashboard process.

### `DuplicateActionError` when creating an action

An active (`PENDING`/`APPROVED`/`EXECUTING`/`EXECUTED`) action with
identical `account_id` + `action_type` + `target_id` + `payload` already
exists. Find out what happened to it:
```python
from control_center import actions, db
conn = db.get_connection("control_center.db")
print(actions.get_action(conn, "the-action-id-from-the-error-message"))
```
If it's still `PENDING` or `APPROVED`, go act on that one instead of
creating a new one. If it's `FAILED`, `DECLINED`, or `EXPIRED`, the
duplicate check doesn't apply to it — the "duplicate" error message
itself will be about a *different*, currently-active action; check which
one the error names.

### An action is stuck in `FAILED` and I want to retry it

You can't retry a `FAILED` action in place — it's a terminal state (see
`ARCHITECTURE.md`'s state machine). Create a fresh action with
`scripts/request_action.py`; it'll get a new id and (since the content is
presumably now correct) a different hash, so it won't collide with the
old failed one.

### `run_executor.py` says "Processed 0 approved action(s)"

The action isn't `APPROVED` yet. Either it's still `PENDING` (go approve
it in the dashboard) or it already reached a terminal state (`EXECUTED`,
`FAILED`, `DECLINED`, `EXPIRED`) and there's nothing left to do — check
its status with the snippet above.

### An execution says `BLOCKED` with `reason: writes_disabled`

The kill switch is off. This is correct behavior, not a bug — go to
**System Controls** and enable writes if you actually intend to execute
for real.

### Don't trust `EXECUTED` blindly

**The only visible sign of whether a run was real or mock is the startup
line** `run_executor.py` prints: `MOCK_EXECUTION=True` or
`MOCK_EXECUTION=False`. During the first live setup, an entire "real"
test was actually still running in mock mode (because `MOCK_EXECUTION=false`
had been written to `.env` in a copy-paste step that silently didn't
take), producing a convincing-looking `EXECUTED` result for an action
that never touched a real API. Always read that startup line before
trusting a result. For anything that matters, also verify the real-world
effect directly (check the actual LinkedIn post), not just the reported
status — see `THREAT_MODEL.md`'s "Data leakage" entry on `CREATE_REACTION`
response handling for a related, separate finding.

### `HTTP 401: {'error': 'Invalid API key'}`

The real backend correctly failed closed — this is the system working as
designed, not a crash. The `PUBLORA_API_KEY` in the execution service's
`.env` is wrong, stale, or was rotated/revoked in Publora's dashboard
since it was issued. Get a current key from Publora (Settings → API) and
update `.env` (verify with `scripts/verify_env.py`, which checks the
key's shape — `sk_...` prefix — without printing it). The action that
failed is now `FAILED` (terminal) — create a fresh one to retry.

## Stricter credential isolation

For a deployment beyond a single trusted personal machine, split the
environment:

```bash
# .env.dashboard -- everything EXCEPT PUBLORA_API_KEY
# .env.executor  -- everything, INCLUDING PUBLORA_API_KEY
```

Run each process pointed at its own file (e.g. via
`python-dotenv`'s `load_dotenv(dotenv_path=...)`, or your process
manager's env-file support) so the dashboard's process environment never
contains the credential at all, closing the gap noted in
`SECURITY.md`'s "Known deviation from ideal isolation."

## Incident response

If you suspect a credential leak, an unexpected write, or unauthorized
dashboard access:

1. **Kill switch first** — System Controls → Disable All Writes. This is
   the single fastest way to stop further real-world effects.
2. **Rotate `PUBLORA_API_KEY`** in Publora's dashboard immediately.
3. **Check the Audit Log** for the affected window — every state
   transition is recorded with actor role/id and a timestamp; it's
   append-only.
4. **Do not delete the database or audit log** — you need it to
   understand what happened before deciding what to do next.
5. Once the immediate exposure is closed, review what let it happen
   before re-enabling writes.
