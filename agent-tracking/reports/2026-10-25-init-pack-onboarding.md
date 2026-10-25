# Report — 2026-10-25-init-pack-onboarding

- **Type:** init (mode `existing`)
- **Date:** 2026-10-25
- **Requested and approved by:** Shubham Halder

## `doctor` before

```
MEDIUM  AGENTS.md  managed block differs from the pack's current template; refresh it
MEDIUM  .gitignore  pack block missing (board and screenshot scratch would be committed)
MEDIUM  specs/project.md  missing; the project brief from the init skill
MEDIUM  .claude/settings.json  edit guard not registered for any agent
```

## `doctor` after

```
MEDIUM  .claude/settings.json  edit guard not registered for any agent
```

The user declined the edit guard ("no need for an edit guard"), so this line stays by decision.

## Files created and edited

| Path | Change |
|------|--------|
| `AGENTS.md` | Pack block (between `<!-- core-be:start -->` and `<!-- core-be:end -->`) refreshed from the template, 190 → 235 lines. Four one-line fixes outside it (below). |
| `.gitignore` | Pack block appended (`agent-tracking/board/`). Existing lines untouched. |
| `specs/project.md` | Created; approved 2026-10-25. |
| `agent-tracking/INDEX.md` | One row added. |
| `agent-tracking/plans/2026-10-25-init-pack-onboarding/` | `scope.md`, `tasks.md`, `progress.md`. |
| `agent-tracking/research/2026-10-25-init-pack-onboarding.md` | Survey, block diff, consolidation table. |
| `agent-tracking/research/2026-10-25-init-pack-onboarding-originals/` | Copies of `AGENTS.md`, `CLAUDE.md`, `.gitignore` before any edit. |

Not touched: `CLAUDE.md` (already only `@AGENTS.md`), `specs/constitution.md`, `README.md`,
`opencode.json`, the `## Project structure` section, and all source.

## Consolidation decisions

The user accepted every proposed action ("proposed").

| # | Block | Decision | Result |
|---|-------|----------|--------|
| 3 | `AGENTS.md:46` names `plan.md` as the task checklist | Rename to `tasks.md` | Line now lists `scope.md`, `tasks.md`, `progress.md`; older tasks keep `plan.md`. |
| 6 | `AGENTS.md:89` "Never `git commit`…" duplicates pack rule 11 | Keep | Unchanged. |
| 8 | `AGENTS.md:120,123` `mkdocs` without `uv run` | Align with the Definition of done | `uv run mkdocs build --strict`, `uv run mkdocs serve`. |
| 10 | `AGENTS.md:252-253` stale Dockerfile paths | Fix | `docker/Dockerfile.control`, `docker/Dockerfile.agent`. |
| 13 | Pack baseline says pytest; repo uses `unittest` | Record the override outside the markers | `AGENTS.md:126`. |
| 12 | Pack block | Refresh | Done. |
| others | Repo rules | Keep | Unchanged. |

## Project brief summary

A self-hosted LiveKit core platform. Developers use its APIs to build their own voice products
(HR or sales automation, any voice product): they manage assistants and run calls over Exotel,
web calls and Google Meet. Fourteen built feature groups (F-1 to F-14) are listed from
`docs/features.md`. Success means first measuring response latency (end of caller speech to first
agent audio, p50/p95 per mode), then setting the target from that baseline. Until then, no
change may raise p95 latency or break recording or the webhooks. The platform stays
self-hosted and follows new LiveKit releases. Nothing is out of scope.

## Findings outside scope (not fixed)

- `.gitignore:21` `*sripts/` looks like a typo. It currently matches nothing.
- `docs/features.md` §25 says the worker stops accepting jobs at about 65% CPU. The code now
  counts the worker's own sessions instead (`agent_run.py:24`, `agent_run.py:60-65`).
- The pack template reads "read the the Project structure section" (`AGENTS.md:399-400`). It is
  inside the markers, so the fix belongs in the pack.

## Next step

No new feature is planned. The first candidate is the latency baseline from the success
measures. When a feature is chosen, it runs through `core-be-specify`.
