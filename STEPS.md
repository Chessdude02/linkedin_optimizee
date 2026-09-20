# Steps to run this project

A linear walkthrough from a fresh clone to a real LinkedIn write, done the
safe way: mock mode first, real mode only once you've seen the whole
pipeline work. For deeper explanations of *why* things are built this way,
see `README.md` and `ARCHITECTURE.md`. For troubleshooting when something
here doesn't behave as described, see `RUNBOOK.md` — this file only covers
the happy path.

Three separate things run in this project, and they're supposed to stay
separate:
- **the dashboard** — where you review and approve/decline
- **the execution service** (`run_executor.py`) — the only thing that can
  actually publish to LinkedIn
- **agents** (manual scripts, or `run_research_agent.py`) — can only ever
  *propose*, never publish

## 1. Install

```bash
git clone https://github.com/Chessdude02/linkedin_optimizee.git
cd linkedin_optimizee
pip install -r requirements.txt
cp .env.example .env
```

## 2. Configure the dashboard's login

```bash
python3 scripts/hash_password.py
```
This prompts for a password and writes `DASHBOARD_PASSWORD_HASH` straight
into `.env` for you — no copy/paste needed.

Then open `.env` and set:
- `DASHBOARD_USERNAME` — pick anything, there's no signup flow.
- `DASHBOARD_SECRET_KEY` — generate one and paste it in:
  ```bash
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```

Leave everything else in `.env` at its default for now
(`WRITE_ENABLED=false`, `MOCK_EXECUTION=true`) — you want mock mode for
your first run.

## 3. Verify the config

```bash
python3 scripts/verify_env.py
```
Fix anything it flags before moving on.

## 4. Start the dashboard

```bash
python3 -m dashboard.app
```
Not `python3 dashboard/app.py` — that fails with a `ModuleNotFoundError`
(see `RUNBOOK.md` if you hit it anyway). Leave this running and open
`http://127.0.0.1:5000` in a browser; log in with the username/password
from step 2.

## 5. Create a test action

In a **second terminal**, from the repo root:
```bash
python3 scripts/request_action.py
```
Walk through the prompts (e.g. action type `CREATE_POST`, any account id,
some content, any reason). This is standing in for what a real agent would
do by calling `control_center.actions.request_action()` directly — the
result is identical either way: one new row in the queue, status
`PENDING`.

## 6. Review and approve it

Back in the dashboard, go to **Pending**, click into the action, read the
exact content that would be published, and click **Approve** (or
**Decline** — try both, nothing is real yet).

## 7. Run the execution service

Still in the second terminal:
```bash
python3 run_executor.py --once
```
This is the only process in the whole system that can call out to
LinkedIn. With `MOCK_EXECUTION=true` (the default), it simulates the call
and marks the action `EXECUTED` without any network request. Check
**Audit Log** in the dashboard — you should see the full trail:
`ACTION_CREATED` → `ACTION_APPROVED` → `ACTION_EXECUTED`.

You now have the full loop working end to end, safely, with nothing real
happening. Everything past this point is optional and moves toward real
publishing.

## 8. (Optional) Go real: register a LinkedIn account

You need a [Publora](https://publora.com) account connected to LinkedIn,
and its `platform_id` (Publora dashboard → **Channels** → your LinkedIn
account → looks like `linkedin-XXXXXXX`).

```bash
python3 scripts/register_account.py
```

Then in `.env`, set `PUBLORA_API_KEY` (from Publora → **Settings → API**)
and flip:
```
MOCK_EXECUTION=false
```
**Only** set these two in the terminal/environment that runs
`run_executor.py` — never in the dashboard's. See `RUNBOOK.md`'s
"Stricter credential isolation" section if you want to enforce this at
the process level instead of just by convention.

## 9. (Optional) Go real: flip the kill switch

In the dashboard, go to **System Controls** and enable writes. This is a
second, independent gate on top of approval — even an approved action
won't execute for real until this is on. Turn it back off when you're not
actively testing.

## 10. (Optional) Do one real write, carefully

Repeat steps 5–7 with a real `account_id` (matching what you registered)
and a real `target_id` (a post URN — see `scripts/parse_post_url.py` if
you only have a LinkedIn URL). Before trusting the result, read
`run_executor.py`'s startup line — it prints `MOCK_EXECUTION=True` or
`MOCK_EXECUTION=False` — and then go check the actual LinkedIn post. Don't
trust a status of `EXECUTED` on its own; see `RUNBOOK.md`'s "Don't trust
EXECUTED blindly" for why.

## 11. (Optional) Use the Research Agent

This agent only ever produces *recommendations* you review — it can never
publish anything itself, and discovering something never creates a
pending action by itself.

```bash
python3 scripts/manage_watchlist.py add     # tell it which post(s) to watch
```
You'll also need, in `.env`:
```
APIFY_TOKEN=...        # https://console.apify.com/settings/integrations
ANTHROPIC_API_KEY=...  # https://console.anthropic.com
```
Then:
```bash
python3 run_research_agent.py --once
```
Open the dashboard's **Research** tab to review what it found. Nothing
there is actionable until you explicitly click **Create Action Proposal**
on a finding — which only creates a normal `PENDING` action, still needing
the same Approve step (step 6) and the same execution service (step 7)
as anything else.

## Where things run in a real, ongoing setup

- Dashboard: wherever you'll actually check in and approve things.
- `run_executor.py`: a machine that stays on, polling
  (`python3 run_executor.py`, no `--once`) — this is the only place
  `PUBLORA_API_KEY` should ever be set.
- `run_research_agent.py`: can run anywhere with `APIFY_TOKEN` /
  `ANTHROPIC_API_KEY`, on a schedule (it defaults to polling once an hour
  since each pass costs real Apify credits).

Something not behaving as described here? Check `RUNBOOK.md` first — it's
built entirely from real failures hit setting this up, not guesses.
