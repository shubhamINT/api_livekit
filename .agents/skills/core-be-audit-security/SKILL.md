---
name: core-be-audit-security
description: >
  Security audit of Python (FastAPI) and Node.js (TypeScript) backend code
  against OWASP Top 10:2025, OWASP API Security Top 10:2023, OWASP ASVS 5.0,
  CWE Top 25 (2025), and OWASP Top 10 for LLM Applications 2025, using Semgrep,
  Ruff/Bandit, eslint-plugin-security, gitleaks, pip-audit and npm audit plus
  manual review. Use whenever the user asks for a security audit, security
  review, vulnerability scan, pentest-style code review, "is this secure",
  "check for vulnerabilities", "OWASP check", secrets scan, or a review of code
  touching auth, input handling, file uploads, external calls or LLM calls —
  starting with core-be-workflow scoping (phases 1–3). Produces a traceable findings report;
  fixes only when remediation is explicitly in scope.
---

# Security Audit

AI-written and human-written backend code fail in the same places: access
control, injection, secrets, unsafe defaults, and unvalidated input. Studies of
LLM-generated code keep finding security flaws in roughly 40–45% of samples
(Pearce et al. 2022; Veracode 2025), and assistants confidently suggest
packages that do not exist. So an audit is systematic: tools first to catch the
cheap things, then a human-style review against published standards, every
finding traceable to a standard ID and a `file:line`.

<gate>
**Gate — before anything else:** load `core-be-workflow`. If
`agent-tracking/plans/<slug>/scope.md` for this task is missing, or its
"Agreed scope" rows are not all filled, run `core-be-workflow` phases 1–3 now and
end your turn at the scope questions. Invoking this skill directly (a slash command, a one-line
request) is not an exemption, and harness plan mode does not replace
`tasks.md`. Scope must include ASVS level (L2 default) and whether the
service calls an LLM. This skill supplies phases 4–7.
</gate>

**Always, even inside another task:** make sure the repo is registered — the
core-be block in `AGENTS.md` and the `@AGENTS.md` import in `CLAUDE.md`
(`core-be-workflow`, Phase 2, "Register the pack") — and, when code or config
changed, finish with the docs sync (`core-be-workflow`, Phase 7) so the README
matches the code.

**Default is report-only.** Do not modify source code during an audit unless the
user scoped remediation. Remediation is a separate, planned task built from the
report.

References (read as needed):

| File | Contents |
|------|----------|
| `references/standards.md` | OWASP Top 10:2025, API Top 10:2023, ASVS 5.0 chapters, CWE Top 25 2025, LLM Top 10 2025 — lists and backend focus |
| `references/python-checks.md` | Python / FastAPI vulnerable patterns and safe replacements |
| `references/node-checks.md` | Node / Express / Fastify vulnerable patterns and safe replacements |
| `references/scanners.md` | Exact scanner commands, what each catches, triage rules |

---

## Phase 4 — Automated pass

Run the scanners in `references/scanners.md` that fit the stack. Tools that are
not installed: run them ephemerally (`uvx`, `npx`, `uv run --with`) if allowed,
otherwise record "not run" and ask. Save summarised output in
`research/<slug>.md` (never paste discovered secret values — record file, line,
rule, and a redacted prefix).

Triage every hit: **confirmed**, **false positive** (with reason), or **needs
manual check**. False positives stay in the report, marked, so the next auditor
does not re-triage them.

## Phase 5 — Review plan

In `tasks.md` list: files/endpoints in review order (trust boundaries first),
checklists to apply, ASVS level, and which scanner hits need manual
confirmation. Get approval.

## Phase 6 — Manual review

**Fan out at `standard` / `deep` depth.** With more than a handful of files,
split them into groups (by module or trust boundary) and give each group to a
read-only `investigator` subagent with the checklists below, after you map the attack surface
(`core-be-workflow/references/SUBAGENTS.md`). You own the report: open
every returned `file:line` and confirm the finding before it goes in.

Map the attack surface first:

1. **Entry points**: every route (method + path), queue consumer, cron job, CLI, webhook.
2. **For each entry point**: authentication required? which authorization check? which input schema? what does it touch (DB, files, subprocess, outbound HTTP, LLM)?
3. **Trust boundaries**: where untrusted data enters, and every sink it can reach (SQL, shell, filesystem path, template, redirect URL, outbound URL, deserializer, LLM prompt, logs).

Then walk this checklist. Each item maps to the standards in `references/standards.md`.

**Access control** (A01, API1/3/5, CWE-862/863/639)
- Every resource read/write checks the caller owns or may access it — object-level (BOLA), property-level (mass assignment / over-exposed fields), function-level (admin routes).
- Deny by default; routes without auth are an explicit allow-list (e.g. `/health`).
- IDs from the client are never trusted to scope data without an ownership filter.

**Authentication and sessions** (A07, API2, ASVS V6/V7/V9/V10)
- Passwords hashed with argon2id / bcrypt / scrypt; never MD5/SHA-1/plain SHA-256.
- JWT: algorithm pinned (no `none`, no `alg` from header), signature, `exp`, `aud`, `iss` verified; secrets/keys from config.
- Rate limiting / lockout on login, OTP, password reset.
- Tokens and session ids never logged or put in URLs.

**Injection** (A05, CWE-89/78/77/94/79)
- SQL / NoSQL: parameterised queries only; no string-built queries, no user-controlled operators (`$where`, `$regex`, raw filters).
- OS commands: no shell; argument lists; allow-listed binaries.
- No `eval`/`exec`/`new Function`/template rendering of user input.
- Output encoding where the backend renders HTML or emails.

**Input validation and resource limits** (API4, CWE-20/770/400)
- Every request body/query/header validated by pydantic (`extra="forbid"`) / zod (`.strict()`).
- Body size, pagination (max page size), upload size, and regex complexity bounded.
- Timeouts on every outbound call and DB query; concurrency limits on expensive work.

**SSRF and outbound calls** (A01:2025 includes SSRF, API7, API10, CWE-918)
- User-influenced URLs resolved and checked against private/loopback/link-local ranges after DNS resolution; redirects re-checked or disabled.
- Upstream responses validated like user input.

**Files and paths** (CWE-22/434, ASVS V5)
- Paths built from user input are normalised and confined to a base dir.
- Uploads: type checked by content, size limited, stored outside web root, random names.

**Deserialization and integrity** (A08, CWE-502)
- No `pickle`/`yaml.load`/`marshal`/`node-serialize` on untrusted data.
- Webhooks verify signatures (HMAC, constant-time compare) and timestamps.

**Secrets and crypto** (A04, CWE-798/200/327)
- No hardcoded secrets, keys, tokens, or connection strings in code, tests, Dockerfiles, or history.
- TLS verification never disabled (`verify=False`, `rejectUnauthorized: false`).
- Randomness for security uses `secrets` / `crypto.randomBytes`/`randomUUID`, never `random` / `Math.random`.
- Standard libraries for crypto; no home-made schemes.

**Configuration** (A02, API8, ASVS V13)
- Debug off in production; no stack traces or internal errors in responses.
- CORS: no `*` with credentials; explicit origins.
- Security headers (helmet for Express; equivalent middleware for FastAPI when serving browsers).
- Default credentials, sample admin users, open admin/docs routes (`/docs`, `/redoc`, `/swagger`) reviewed for production.

**Supply chain** (A03:2025, API9)
- Dependency audit clean of High/Critical or each one triaged.
- Lockfile committed; versions pinned; no packages from unexpected registries.
- Every dependency actually exists and is the intended package (typosquats, hallucinated names — see `core-be-audit-code/references/ai-generated-code.md`).
- Every dependency licence-compatible with the repo's own licence (read `LICENSE`); flag GPL/AGPL/unknown for human review.

**Logging and error handling** (A09, A10:2025, ASVS V16)
- Security events logged (auth failures, access denials, admin actions) with request id — without secrets or PII.
- User input in logs is sanitised (log injection, CWE-117).
- Exceptions never leave the system in an inconsistent state; failures fail closed (deny), not open.

**LLM-calling services** (LLM Top 10 2025 — only if in scope)
- Prompt injection: untrusted content is delimited and never granted authority; tool calls validated server-side.
- Model output treated as untrusted input before it reaches SQL, shell, HTML, URLs, or code execution (LLM05).
- Excessive agency: tools least-privilege, destructive actions need confirmation (LLM06).
- No secrets or other tenants' data in prompts or system prompts (LLM02, LLM07).
- Token / cost limits and timeouts (LLM10).

Log progress per checklist area in `progress.md`.

## Severity

Rate by impact × likelihood in *this* deployment. Explain the rating in one line.

| Severity | Typical examples |
|----------|------------------|
| **Critical** | Unauthenticated RCE, SQL injection on a public route, auth bypass, leaked production secret |
| **High** | BOLA exposing other tenants' data, SSRF to internal network, stored XSS in admin, missing auth on sensitive function |
| **Medium** | Missing rate limit on login, verbose errors leaking internals, weak hashing, missing timeouts enabling DoS |
| **Low** | Missing security headers, overly broad CORS without credentials, outdated dependency with no reachable vuln |
| **Info** | Hardening suggestion, defence in depth |

## Phase 7 — Report

Write the report to `agent-tracking/reports/<slug>.html` (or `.md`). Never the
repo root, the temp directory, or a hosted page (claude.ai Artifact, gist, docs
connector): audit findings stay local. If the user asks for another location,
state this rule first, then follow their answer.

`core-be-workflow` report template; HTML default. Visuals per
`core-be-workflow/references/VISUAL-REPORT.md`: severity tiles and severity bar, and a
source → sink row of plain boxes for each High or Critical finding.
**No Mermaid or any external script** — delete the template's script block.
Each finding:

```
S-003 | High | Broken Object Level Authorization
  Standard: A01:2025 · API1:2023 · CWE-639 · ASVS V8.2.2
  Location: src/api/routes/invoices.py:41
  Evidence: `invoice = await Invoice.get(invoice_id)` — no owner filter; route
            only checks the caller is authenticated.
  Impact:   Any authenticated user can read any tenant's invoice by id.
  Fix:      Query with owner scope: `Invoice.find_one(Invoice.id == invoice_id,
            Invoice.owner_id == caller.id)`; return 404 when absent.
  Status:   open
```

Rules for reports:

<hard-rules>
- Evidence is the minimal code excerpt. **Never include real secret values** —
  redact to a prefix (`sk_live_4f…`).
- Describe how the issue is reached (request shape, conditions). **Do not write
  working exploit code or weaponised payloads** — the report is shared widely.
- Every finding cites at least one standard ID and a `file:line`.
- Include the "Method" section (scanners + versions, checklists, ASVS level) and
  a coverage statement: what was reviewed and what was not.
- If a live secret is found, tell the user immediately in chat — it must be
  rotated regardless of the rest of the audit — then continue.
</hard-rules>
