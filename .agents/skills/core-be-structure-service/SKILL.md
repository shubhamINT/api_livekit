---
name: core-be-structure-service
description: >
  Detect, choose, record, and apply the project structure (architecture +
  folder layout) of a Python (FastAPI) or Node.js (TypeScript) backend service.
  Use before placing new code or moving existing code when the repo's AGENTS.md
  has no "Project structure" section; whenever the user asks to "structure this
  repo", "fix the folder structure", "where should this file go", "organise the
  code", "set up a new service", or asks which architecture to use (layered,
  feature-based, hexagonal, clean, MVC); and as the first step of every
  core-be-refactor-code and core-be-build-feature task. Never imposes a structure silently: it
  detects what exists, asks the user, and writes the decision into AGENTS.md so
  every later task follows it.
---

# Structure Service

Teams structure services differently, and all of the common patterns can work.
What fails is **mixing** them, or an agent quietly moving code into the layout
*it* prefers. This skill makes structure an explicit, recorded decision:
detect → confirm with the user → record → apply.

References:

| File | Contents |
|------|----------|
| `references/architectures.md` | Architecture patterns, when each fits, how to recognise each in a repo |
| `references/python-layouts.md` | Concrete FastAPI trees: layered-by-feature (default), layered-by-layer, hexagonal |
| `references/node-layouts.md` | Concrete TypeScript trees: the same three for Express / Fastify |
| `references/readme-standard.md` | README sections every service keeps current |

<gate>
**Gate — when this is the task itself** (not a step inside another task):
load `core-be-workflow` and run its phases 1–3 before anything else. Invoking this
skill directly (a slash command, a one-line request) is not an exemption,
and harness plan mode does not replace `tasks.md`.
</gate>

**Always, even inside another task:** make sure the repo is registered — the
core-be block in `AGENTS.md` and the `@AGENTS.md` import in `CLAUDE.md`
(`core-be-workflow`, Phase 2, "Register the pack") — and, when code or config
changed, finish with the docs sync (`core-be-workflow`, Phase 7) so the README
matches the code.

---

## Step 1 — Look for a recorded decision

Read the repo root `AGENTS.md`. If it has a `## Project structure` section,
**that is the structure**. Follow it and stop here — do not re-litigate it
unless the user asks. If the code contradicts the recorded section, report the
contradictions as findings; do not "fix" them outside an approved task.

## Step 2 — Detect what exists

No recorded section? Inspect the tree (`src/`, top-level packages, entry
points, imports between folders) and classify it using the detection signals in
`references/architectures.md`:

| Classification | Typical evidence |
|----------------|------------------|
| Layered by layer | top-level `api/`/`routes/`, `services/`, `repositories/`, `domain/`/`models/` folders |
| Layered by feature | top-level folders named after business areas (`orders/`, `users/`), each with its own router/service/repository |
| Hexagonal / clean | `domain/` or `core/` with no framework imports, `ports`/`adapters` or `application`/`infrastructure` folders |
| Unstructured / mixed | logic in route handlers, SQL next to HTTP code, one big module, or two patterns side by side |

Collect evidence as paths (e.g. "`src/api/invoices.py:30` runs SQL inside a
route handler"). Check the dependency direction too: do domain/business modules
import the web framework or the DB driver?

## Step 3 — Confirm or choose, with the user

Always ask; never decide alone. Present what you found and a recommendation:

- **Clear, consistent structure found** → "This repo is *layered by feature*
  (evidence: …). I'll follow it. OK?"
- **Unstructured or mixed** (any size) → recommend **layered, grouped by
  feature**, and list the alternatives with a one-sentence trade-off each:
  1. **Layered, grouped by feature** — *default recommendation.* Each business
     area owns its router, schemas, service, and repository; shared
     infrastructure lives in `core/`. Scales well, keeps a change inside one
     folder.
  2. **Layered by technical layer** — `api/`, `services/`, `repositories/`,
     `domain/`. An alternative if the team prefers technical folders.
  3. **Hexagonal (ports & adapters)** — when domain logic is heavy and must be
     tested without infrastructure, and there are genuinely several adapters.
- **User names a pattern not listed** (clean architecture, modular monolith,
  CQRS…) → use `references/architectures.md` to agree on concrete folders
  before recording it.

For a large existing repo, also ask whether to migrate everything or only code
touched by current and future tasks (incremental, usually the right answer).

When the recommendation moves code (anything except "follow what exists"),
show it as a structure proposal before asking: a `core-be-workflow` report of type
`structure`, saved to `agent-tracking/reports/<slug>.html`, per `core-be-workflow/references/VISUAL-REPORT.md`, with a Current → Target
tree diff (added paths green, moved amber, removed grey) and a
dependency-direction graph with rule violations red. The user decides on the
picture, not on a paragraph.

## Step 4 — Record the decision in `AGENTS.md`

Fewer than about five source files: record Pattern, Layout, and the
"where does X go" row only; skip the rest.

<template>
Write (or update) a `## Project structure` section at the end of the repo root
`AGENTS.md`. Keep it short and concrete — it is read at the start of every task:

```markdown
## Project structure

**Pattern:** Layered, grouped by feature (decided YYYY-MM-DD with <name>).

**Layout**
<tree with one-line comment per folder>

**Dependency rules**
- routers → services → repositories; nothing imports a router
- `core/` is imported by everyone and imports no feature
- business logic never imports FastAPI / Express or the DB driver directly

**Where does X go**
| It … | Put it in |
|------|-----------|

**Terms:** "service" = use-case logic for one feature (not an external client;
external clients live in `core/clients/<upstream>.py`).

**Migration:** incremental — code moves into this layout when a task touches it.
```
</template>

Take the tree and rules from the matching layout reference; adapt names to what
the repo already uses rather than renaming for its own sake. Log the decision in
the current task's `progress.md`.

## Step 5 — Apply

- **New code** (`core-be-build-feature`): goes exactly where the recorded structure says.
- **Refactors** (`core-be-refactor-code`): moving misplaced code into the recorded
  structure is a planned step (`Move Function` / `Move File`, `git mv` to keep
  history), approved through `core-be-workflow` like any other step. Behaviour must not
  change; update every import in the same step.
- **Audits** (`core-be-audit-code`): code that breaks the recorded dependency rules is a
  finding (layer leak).
- **README**: the project-structure tree in the README changes in the same
  change as the code (`references/readme-standard.md`).

## Rules that hold in every structure

<hard-rules>
- HTTP handlers validate, delegate, and shape the response — no SQL, no
  external calls, no business branching.
- One config module reads the environment; nothing else does.
- One response envelope and one central error handler.
- External responses are validated and condensed at the boundary.
- Tests mirror the source layout.
- No `utils` dumping ground; a helper lives beside the concept it serves.
- Do not scaffold folders nothing uses yet.
</hard-rules>
