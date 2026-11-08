---
name: core-be-init
description: >
  Set up or repair a repo for this pack. Surveys the repo, fixes a duplicated or
  messy `AGENTS.md` and `CLAUDE.md` (everything lives once in `AGENTS.md`;
  `CLAUDE.md` only imports it), creates what is missing (tracking folder,
  constitution, project brief), and talks through what the user wants built
  before any code. Use for "set up this repo", "onboard this project", "adopt
  the pack", "start a new project", or when `sdd-check.sh doctor` reports gaps.
  Changes no source.
---

# Init

One run leaves the repo ready: `sh core-be-workflow/scripts/sdd-check.sh doctor`
reports nothing but the edit-guard line, the user's wishes are written down and
approved, and every later change goes through the spec chain.

<gate>
`core-be-workflow` is loaded (do not re-read it) and you have run
`sh core-be-workflow/scripts/sdd-check.sh doctor`. Nothing is created or edited
before the user approves the onboarding plan (stop 2). Only tracking files are
written before that.
</gate>

## The three stops

1. **Scope questions**, then 2. **Onboarding plan approval**, then 3. **Project brief approval**.
Each stop ends your turn. Coding starts only after the brief and then a feature spec and plan are approved.

## Steps

1. **Survey, read-only.** Read the `doctor` output, the manifests and configs (stack), the folder tree, tests and CI, the README, and `AGENTS.md` and `CLAUDE.md` in full. Note other agent files (`.cursorrules`, `.github/copilot-instructions.md`, `.specify/`); do not touch them. Fewer than about five source files and no history? Mode `new`. Otherwise mode `existing`.
2. **Stop 1: ask**, in one message, each with a default:
   - Mode: `new` or `existing`.
   - Fix `AGENTS.md` and `CLAUDE.md`: yes (default), with a preview first.
   - Fold the other agent files you found into `AGENTS.md`: no (default, leave them).
   - Stack: confirm what you detected, or for a new project, name the language, framework, and database.
   - Anything the pack must never touch.
3. **Stop 2: plan.** Bootstrap tracking (`core-be-workflow` Phase 2, type `init`). Write the onboarding plan into `agent-tracking/plans/<slug>/tasks.md`: one line per file, `create`, `edit`, or `merge`, with what changes. Put the consolidation table (below) in `agent-tracking/research/<slug>.md`. Show both and wait for explicit approval.
4. **Apply** the approved lines, ticking each:
   - Consolidate `AGENTS.md` and `CLAUDE.md` (below).
   - Register the pack: `core-be-workflow/references/REGISTER-PACK.md` (managed block, `## Project structure` section, the `@AGENTS.md` import, the `.gitignore` block).
   - `agent-tracking/INDEX.md` from the template if absent.
   - `specs/constitution.md`: run `core-be-constitution` if missing (it has its own questions and approval).
   - Structure: existing repo, detect and record it with `core-be-structure-service`; new project, choose the layout with the user and record it. Creating folders or code is a later `structure` or `feature` task, never part of init.
   - README: missing, create it per `core-be-structure-service/references/readme-standard.md`; present, list its gaps in the report and leave it.
5. **Verify.** Run `doctor` again and fix every finding except the edit-guard line. That one is the user's step: ask which agents the team uses and tell them to run `sh <skills dir>/core-be-workflow/scripts/install-hook.sh --agent <name>` once per agent: `claude`, `codex`, `cursor`, `copilot`, `gemini`, or `windsurf` (never run it yourself).
6. **Stop 3: the project brief.** Ask in one message, with defaults:
   - What it is for and who uses it.
   - The features wanted: for each, what it does, for whom, and a priority (`must`, `should`, `could`).
   - Success measures, with numbers.
   - Stack and constraints: existing repo, confirm the detected ones; new project, propose options with reasons.
   - Out of scope.
   - What is still unknown.

   Write the answers, not your ideas, into `specs/project.md` from `templates/project.md`. An unanswered question stays as `[NEEDS CLARIFICATION: ...]` and you ask it again. Approval needs none left. On approval set `**Status:** approved (YYYY-MM-DD, by <name>)`.
7. **Hand over.** Ask which feature goes first. That feature runs through `core-be-specify` and the rest of the chain: its own questions, spec, plan, and approval, then code. An existing repo documents what the user wants next, not everything already built.

## Consolidate `AGENTS.md` and `CLAUDE.md`

Target: `AGENTS.md` holds everything, each fact once. `CLAUDE.md` holds the line `@AGENTS.md` and only what is true for Claude Code alone (hooks, permissions, slash commands, memory notes).

1. Save both originals to `agent-tracking/research/<slug>-originals/` before any edit.
2. Classify every block of both files: pack block (between the markers), repo rule, duplicate (the same idea twice, in either file), stale (names a file, command, or tool that no longer exists: check it), conflicting (two rules disagree), Claude-only, or README material (setup and run steps).
3. Write the table `block | file | action | reason`. Actions: `keep`, `merge`, `drop duplicate` (name the surviving copy), `move to README`, `move to CLAUDE.md`, or `ask`.
4. The user decides every `ask`, every stale item, and every conflict at stop 2. You decide none of them.
5. Apply: group the kept rules under clear headings in `AGENTS.md`, outside the pack markers, in the user's wording.

<hard-rules>
- Source is untouched. The only files you create or edit are `AGENTS.md`, `CLAUDE.md`, `.gitignore` (only between the pack markers), `README.md` (only if missing), `agent-tracking/`, and `specs/`.
- No file outside `agent-tracking/` is created or edited before stop 2 is approved.
- Never run `install-hook.sh` and never edit an agent's hook or settings file (`.claude/settings.json`, `.codex/hooks.json`, `.cursor/hooks.json`, and the like).
- Never delete a line the user did not approve. A dropped duplicate keeps its meaning in the surviving copy.
- Never merge two conflicting rules yourself, and never edit inside the pack markers except by refreshing the block from the template.
- Document what the user said. Do not invent features, users, numbers, or stack choices; an unknown stays a question.
</hard-rules>

<output>
`agent-tracking/reports/<slug>.md`: `doctor` before and after, files created and edited, the consolidation table with the decisions, a summary of the approved brief, and the next step (the first feature). Tell the user in at most six lines what changed, what the one manual step is, and which feature starts next.
</output>
