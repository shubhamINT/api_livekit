# Tasks — 2026-10-25-init-pack-onboarding

**Status:** approved (2026-10-25, by Shubham Halder)

## Goal

Bring the repo to a clean `doctor` (except the edit-guard line) and record the project brief.

## Success criteria

- `sh core-be-workflow/scripts/sdd-check.sh doctor` reports only the edit-guard line.
- `specs/project.md` approved with no `[NEEDS CLARIFICATION]` left.
- No source file touched.

## Skills applied

- `core-be-init`, `core-be-workflow` (Register the pack)

## Steps

- [x] 1. `edit` `AGENTS.md`: replace the text between `<!-- core-be:start -->` and `<!-- core-be:end -->` with the template's current block (190 → 235 lines; diff in research).
- [x] 2. `edit` `AGENTS.md`: apply the consolidation decisions the user approves (rows 3, 6, 8, 10, 13 of the table in `research/2026-10-25-init-pack-onboarding.md`). Each is one line.
- [x] 3. `edit` `.gitignore`: append the pack block (`# core-be:start` … `agent-tracking/board/` … `# core-be:end`). Nothing outside the markers changes.
- [x] 4. `create` `specs/project.md` from the template, filled at stop 3 with the user's answers only.
- [x] 5. Run `doctor` again; fix every finding except the edit-guard line.
- [x] 6. `create` `agent-tracking/reports/2026-10-25-init-pack-onboarding.md`; update the `INDEX.md` row.

Not changed: `CLAUDE.md` (already `@AGENTS.md`), `specs/constitution.md`, `agent-tracking/INDEX.md` template, `README.md`, `opencode.json`, `## Project structure`, any source.

## Files expected to change

| Path | Change |
|------|--------|
| `AGENTS.md` | edit: pack block refreshed; approved one-line fixes outside it |
| `.gitignore` | edit: pack block appended |
| `specs/project.md` | create |
| `agent-tracking/reports/2026-10-25-init-pack-onboarding.md` | create |
