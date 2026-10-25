# Research — 2026-10-25-init-pack-onboarding

## `doctor` before

```
MEDIUM  AGENTS.md  managed block differs from the pack's current template; refresh it (references/REGISTER-PACK.md)
MEDIUM  .gitignore  pack block missing (board and screenshot scratch would be committed); see references/REGISTER-PACK.md
MEDIUM  specs/project.md  missing; the project brief from the init skill
MEDIUM  .claude/settings.json  edit guard not registered for any agent (ignore if the pack is a Claude plugin); the user runs install-hook.sh --agent <name> for each agent the team uses
```

## Survey

- Mode `existing`: 168 tracked Python files, long git history, `tests/` with stdlib `unittest`.
- `CLAUDE.md` is already the single line `@AGENTS.md`. Nothing to consolidate there.
- `specs/constitution.md` exists (v1.0.0, ratified 2026-10-22). Not touched.
- `agent-tracking/INDEX.md` exists. Not recreated.
- `## Project structure` is recorded in `AGENTS.md` (after the pack block). Structure detection is not re-run.
- `README.md` exists; its gaps were audited on 2026-10-20 (`reports/2026-10-20-audit-readme.html`) and fixed by `2026-10-20-refactor-docs-split`. Left as it is.
- Other agent files: `opencode.json` only. No `.cursorrules`, `.github/copilot-instructions.md` or `.specify/`. Left as it is.
- Originals saved to `research/2026-10-25-init-pack-onboarding-originals/` (`AGENTS.md`, `CLAUDE.md`, `.gitignore`).

## Pack block diff (current → template)

The template adds: the `Change`, `Assess`, `Explain`, `Init` and `Constitution` rows to the task
table and the full spec chain on the `Feature` row; a `### Specs` and a `### Guard` subsection;
the reviewer note for hosts without subagents; twelve new rows in the skill index. It renames
`plan.md` to `tasks.md` in §3 step 3. 190 → 235 lines. Nothing outside the markers changes.

## Paths checked

Every path named in `AGENTS.md` outside the pack block exists, except
`Dockerfile.control` and `Dockerfile.agent` (`AGENTS.md:252-253`): they live at
`docker/Dockerfile.control` and `docker/Dockerfile.agent`.

## Consolidation table

| # | Block | File | Action | Reason |
|---|-------|------|--------|--------|
| 1 | Intro ("The one instruction file…") | `AGENTS.md:1-9` | keep | Repo rule; says `CLAUDE.md` only imports this file, which is true. |
| 2 | Working agreement, steps 1-5 | `AGENTS.md:11-30` | keep | Repo rule. Overlaps pack §1 and §3 (ask first, plan first) but adds the repo's trivial threshold ("2+ files or 3+ steps") and the `livekit-docs` MCP rule. No contradiction. |
| 3 | Agent working files: `plans/<slug>/` holds `plan.md` | `AGENTS.md:46` | **ask** (conflict) | The pack now names the checklist `tasks.md`, not `plan.md`. Proposed: change the line to "`scope.md`, `tasks.md`, `progress.md`; older tasks keep `plan.md`". |
| 4 | Agent working files: rest of section | `AGENTS.md:32-62` | keep | Repo rule (docs vs dev-docs vs agent-tracking split). |
| 5 | Definition of done | `AGENTS.md:63-88` | keep | Repo rule. |
| 6 | "Never `git commit` unless explicitly asked" | `AGENTS.md:89` | **ask** (duplicate) | Same rule as pack §4 rule 11 and the user's global instructions. Proposed: drop; the pack's rule 11 survives with the same meaning. Alternative: keep (cheap, and survives if the pack block is ever removed). |
| 7 | Commands | `AGENTS.md:91-124` | keep | README material in principle, but agents need the exact commands; README already carries the human quickstart. |
| 8 | Commands: `mkdocs build --strict` vs DoD `uv run mkdocs build --strict` | `AGENTS.md:120,123`, `AGENTS.md:84` | **ask** (inconsistent) | Proposed: change line 120 to `uv run mkdocs build --strict` (and `uv run mkdocs serve`), matching the DoD. |
| 9 | Architecture, key source table, modes, env vars | `AGENTS.md:126-268` | keep | Repo rule; all paths checked except row 10. |
| 10 | Deployment modes: `Dockerfile.control`, `Dockerfile.agent` | `AGENTS.md:252-253` | **ask** (stale) | Files are under `docker/`. Proposed: fix to `docker/Dockerfile.control`, `docker/Dockerfile.agent`. |
| 11 | Runtime behaviors, scripts, webhook contracts, where truth lives, guardrails | `AGENTS.md:269-338` | keep | Repo rules. |
| 12 | Pack block | `AGENTS.md:340-529` | refresh from template | Managed block; stale per `doctor`. |
| 13 | Pack §5 says tests use pytest | pack block | **ask** (conflict) | Repo uses stdlib `unittest` (user confirmed at stop 1). The block cannot be edited. Proposed: add one line outside the markers, under Commands: "Tests use stdlib `unittest`, not pytest; this overrides the pack's language baseline." |
| 14 | `## Project structure` | `AGENTS.md:531-` | keep | Belongs to the repo. |
| 15 | `@AGENTS.md` | `CLAUDE.md:1` | keep | Already the target shape. |

## Radar (outside scope, not fixed)

- `.gitignore:21` has `*sripts/`, which looks like a typo for `scripts/`. As written it matches
  nothing in the repo; if it was meant to be `*scripts/` it would hide `scripts/` from git.
  Left untouched; a one-line follow-up if you want it removed or corrected.
