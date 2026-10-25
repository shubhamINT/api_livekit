# Scope — 2026-10-25-init-pack-onboarding

- **Type:** init
- **Requested by:** Shubham Halder, backend engineer
- **Date:** 2026-10-25

## Original request (verbatim)

> /core-be-init

## Agreed scope

| Question | Answer |
|----------|--------|
| Mode | `existing` (default) |
| Fix `AGENTS.md` / `CLAUDE.md` | Yes, with a preview first (default) |
| Fold other agent files into `AGENTS.md` | No (default); `opencode.json` is left as it is |
| Stack | Confirmed as detected: Python 3.12+, `uv`, FastAPI + Gunicorn, LiveKit Agents `~=1.8.8`, MongoDB (Beanie), stdlib `unittest`, Ruff via `uvx` |
| Test framework vs the pack's pytest baseline | Keep stdlib `unittest` (default) |
| Never touch | No extra restrictions beyond the init hard rules (default) |
| Report format | Markdown (`core-be-init` output contract) |

## Assumptions confirmed with the user

- The user answered "default" to every stop-1 question.

## Clarification log

| Question asked | User's answer |
|----------------|---------------|
| Mode `existing` or `new`? | default (`existing`) |
| Fix `AGENTS.md` / `CLAUDE.md` with preview? | default (yes) |
| Fold `opencode.json` into `AGENTS.md`? | default (no) |
| Stack as detected; keep `unittest` over pytest? | default (yes, keep `unittest`) |
| Anything the pack must never touch? | default (nothing extra) |
