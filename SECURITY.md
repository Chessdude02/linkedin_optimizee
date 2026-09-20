# Security

This project is a human-in-the-loop authorization layer for LinkedIn
automation, built on
[sergebulaev/linkedin-skills](https://github.com/sergebulaev/linkedin-skills).
It is risk-reduced, fail-closed, and auditable. It is not, and does not
claim to be, risk-free.

For the full breakdown of what's mitigated and what residual risk
remains, see `THREAT_MODEL.md`. For how the pieces fit together, see
`ARCHITECTURE.md`. For day-to-day operation and troubleshooting, see
`RUNBOOK.md`.

## Reporting a vulnerability

This is currently a personal project with a single owner/operator. If you
find a security issue, open a private issue on the repository or contact
the repository owner directly. There is no formal disclosure SLA at this
stage — this is not yet software other people run in production.

## Credential handling

| Credential | Lives in | Read by |
|---|---|---|
| `DASHBOARD_SECRET_KEY` | dashboard's environment | `dashboard/app.py` only, to sign session cookies |
| `DASHBOARD_PASSWORD_HASH` | dashboard's environment | `dashboard/auth.py` only, for login verification |
| `PUBLORA_API_KEY` | **execution service's environment only** | `control_center/backends/publora.py`, imported lazily, only when `MOCK_EXECUTION=false` |

**Never** commit `.env`, `.env.local`, or any file containing the above.
`.gitignore` covers `.env*`; `scripts/check_no_secrets.py`-style scanning
is worth running before any push if this project's scope grows.

**Rotation:** if `PUBLORA_API_KEY` is ever exposed (committed, pasted
somewhere public, logged), rotate it immediately in Publora's dashboard
(Settings → API → Create Key, then revoke the old one) and update the
execution service's `.env`. Nothing in this codebase caches or persists
the key outside the environment variable itself.

**Verification without exposure:** `scripts/verify_env.py` checks that
every required credential is present and shaped correctly (right prefix,
right length) without ever printing the full value — use it instead of
`echo`-ing or `cat`-ing `.env` when debugging.

## Known deviation from ideal isolation

The design this project follows (see the original build brief, section
50) calls for the write credential to exist *only* in the execution
service's process. The code enforces this at the import graph level —
`dashboard/` cannot reach `PUBLORA_API_KEY` through any function call, and
a test (`test_dashboard_process_never_touches_the_publora_credential`)
asserts this.

In an actual single-operator deployment (the one that ran the real,
verified test against a live LinkedIn account), both the dashboard and
the execution service were run off *one* `.env` file on one machine,
which means the key is present in the dashboard process's raw
environment even though no code path reads it. A stricter deployment
should use two separate environment files — see `RUNBOOK.md`'s
"Stricter credential isolation" section.

## Dashboard security posture

- **Authentication:** single operator account, credentials from
  environment variables (never hardcoded). Password hashed with
  `hashlib.scrypt` (memory-hard, appropriate for password storage —
  chosen over a fast hash like plain SHA-256).
- **Session cookies:** HttpOnly, SameSite=Strict, Secure by default
  (`DASHBOARD_COOKIE_SECURE=false` exists only for local plain-HTTP
  development and should never be set in any deployment reachable over a
  network).
- **CSRF:** every state-changing POST (approve, decline, kill-switch
  toggle, logout) requires a per-session token generated server-side and
  validated before the request does anything.
- **Rate limiting:** login attempts are locked out after 5 failures in 5
  minutes, per username. This is in-memory and per-process — see
  `dashboard/security.py`'s docstring for the multi-worker limitation.
- **No 2FA.** Anyone with the operator's password gets full
  approve/decline/kill-switch access. Appropriate for a personal
  single-user tool; not appropriate to expose to untrusted users without
  adding it.
- **Never run this dashboard exposed to the public internet** without at
  minimum putting it behind a real TLS-terminating reverse proxy (so
  `Secure` cookies actually mean something) and adding a second factor.
  It was designed and tested for `127.0.0.1` / a private network only.

## What "tested" means here

Phase 1 through 5 include 112 automated tests, all passing, covering
authorization boundaries, content-hash tamper detection, expiration,
duplicate/concurrent execution safety, the kill switch, prompt-injection
isolation, and the real backend's request-building and error handling —
all with the network mocked.

Separately, one full manual run went end-to-end against the real Publora
API and a real LinkedIn account: an agent-style request, a human approval
in the dashboard, and a real `CREATE_REACTION` execution, verified by
checking the actual LinkedIn post for the resulting like. That single run
is not a comprehensive production validation — it proves the pipeline
*can* work end to end, not that every action type, every failure mode, or
every edge case has been exercised for real. Treat Phase 4/5 as reviewed
and unit-tested, with one real data point, not as battle-tested.

## Scope notes

- No secrets are ever printed to logs, the audit trail, or error
  responses — see `audit.py`'s key-based scrubbing and
  `THREAT_MODEL.md`'s "Data leakage" section for the one real gap found
  (response-body validation on `CREATE_REACTION`).
- The DIY/arbitrary-command-execution tier that exists in
  `linkedin-skills` (`LINKEDIN_SKILLS_CUSTOM_POSTER`) is not used by, or
  reachable from, this project at all. Nothing here ever shells out to an
  operator-configured command.
- This project has no read layer (no Apify integration, no content
  fetching). If you pair it with `linkedin-skills` or any other system
  that reads LinkedIn content, treat that content as untrusted data per
  `linkedin-skills`' own `references/untrusted-content.md` rule — nothing
  fetched should ever be treated as an instruction or as approval.
