# Report

Paths are relative to the workflow skill folder.

Then the report. Delete every template comment and every section marked for
other task types; leave nothing to be ignored. Produce `agent-tracking/reports/<slug>.html` or
`agent-tracking/reports/<slug>.md` in the format the user chose. Always write
it there, never to the OS temp directory, the repo root, a hosted page (claude.ai
Artifact, gist, docs connector), or only to chat, so
the report sits next to its scope, plan, and progress. Build it from
`templates/report.html` or `templates/report.md`. Every report has:

1. **Summary** — what was asked, what was done, headline result
2. **Scope** — in / out, depth, constraints (link `scope.md`)
3. **Method** — tools run, checklists applied, standards referenced
4. **Current → Target** — diagrams of what exists and what changed
   (refactor, feature, structure, test; not audit/security, which change nothing)
5. **Findings** or **Changes** — per type:
   - audit/security: findings table (ID, severity, category, standard ref,
     `file:line`, evidence, impact, recommendation, status)
   - refactor: before/after metrics, each change with the named refactoring
   - feature: what was built, interface, tests added
   - feature / change: **Spec vs code** — the converge table from
     `core-be-converge`, one row per active `AC-n` (test, code, status). Done
     only on verdict `Converged`
6. **Verification** — commands run and results (before vs after)
7. **Out-of-scope observations** and **recommended next tasks**
8. **Trace** — links to scope, research, plan, progress
9. **Docs updated** — README and `AGENTS.md` sections changed (omit for audit
   and security)

Reports are visual first. Follow `references/VISUAL-REPORT.md` for the
diagram patterns, the colour legend, and the visuals each report type must
include. The reviewer should grasp the change from the diagrams alone.

Script policy for HTML reports:

- **Refactor, feature, structure, test:** inline CSS plus the one Mermaid
  import already in the template. Nothing else external. These reports must
  hold no secrets, credentials, or security findings.
- **Audit and security:** a single self-contained file. Delete the Mermaid
  block; inline CSS, plain boxes and tables only, no external scripts, fonts, or CDNs.
  Audit findings are sensitive and reports get opened offline and attached to
  tickets.
