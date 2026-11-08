# Architecture Patterns

"Structure" covers two things: the **architectural pattern** (how concerns are
separated and which way dependencies point) and the **folder layout** (how that
maps onto files). Pick the pattern first; the layout follows. Most production
backends are *layered, with business logic isolated from HTTP and the database*,
organised either by technical layer or by feature.

## Contents
1. Pattern catalogue
2. Detection signals
3. The dependency rule
4. Choosing

---

## 1. Pattern catalogue

| Pattern | Core idea | Fits | Watch out for |
|---------|-----------|------|---------------|
| **Layered (N-tier)** | Presentation → application/service → data access; each layer calls only the one below | Most backend APIs — the default | Anaemic "pass-through" layers that add nothing |
| **Layered, grouped by feature** (vertical slice) | Same layers, but folders per business area (`orders/`, `users/`), each with its own router/service/repository | Services with several business areas; teams that change one feature at a time | Features reaching into each other's internals — share via a feature's public module only |
| **Hexagonal (ports & adapters)** | Domain core in the centre; HTTP, DB, queues are adapters plugged into ports the core defines | Heavy domain logic that must be tested without infrastructure; several real adapters per port | Ports with one adapter (a hypothetical seam — see `core-be-coding-standards` module design) |
| **Clean / Onion** | Concentric rings: entities → use cases → interface adapters → frameworks; dependencies point inward only | Large, long-lived codebases whose rules must outlive framework choices | Ceremony: many files per use case in a small service |
| **Modular monolith** | One deployable, internally split into strongly bounded modules with explicit public interfaces | Growing products that want module boundaries without network calls | Modules sharing tables or importing each other's internals |
| **Domain-Driven Design** | Organise around bounded contexts and a shared domain language | Complex business domains; usually combined with hexagonal or feature layout | Applying tactical patterns (aggregates, repositories everywhere) to simple CRUD |
| **CQRS** | Separate write (command) and read (query) models/paths | Very read-heavy or event-sourced systems | Two models where one would do |
| **Event-driven** | Components communicate through events/queues rather than direct calls | Async workflows, decoupled integrations | Hidden control flow; needs idempotency, retries, dead-letter handling |
| **Microservices** | Independently deployable services, each owning its data | Large organisations needing independent deploy/scale | Distributed-systems cost; do not split what a module boundary would solve |
| **MVC / MVP / MVVM** | UI-layer patterns: model, view, controller/presenter/view-model | Server-rendered web apps (MVC); frontends | For a JSON API, "controller" = the HTTP handler layer inside one of the patterns above |

## 2. Detection signals

| You see | Likely pattern |
|---------|----------------|
| Top-level `controllers/`/`routes/`/`api/`, `services/`, `repositories/`/`dal/`, `models/` | Layered by layer |
| Top-level business nouns (`billing/`, `orders/`), each containing router + service + repository files | Layered by feature |
| `domain/` with no framework or driver imports; `ports/` + `adapters/`, or `application/` + `infrastructure/` | Hexagonal / clean |
| `modules/<name>/` each with an `index`/`__init__` exposing a small public surface, cross-module imports only via it | Modular monolith |
| `commands/` and `queries/` (or `handlers/` split that way) | CQRS |
| `events/`, `consumers/`, `publishers/`, queue clients central to flow | Event-driven |
| `views/`/`templates/` + `controllers/` | MVC |
| SQL or HTTP calls inside route handlers; one large module; two of the above side by side | Unstructured / mixed |

Confirm with imports, not only folder names: a folder called `domain/` that
imports FastAPI is not a hexagonal core.

## 3. The dependency rule

Whatever the pattern, dependencies point **toward business logic**, never away
from it:

- Business logic (domain / services / use cases) does not import the web
  framework, the HTTP request object, or the database driver.
- HTTP handlers and repositories/clients are the edges; they depend on the
  business logic, not the other way round.
- Configuration and logging are infrastructure everyone may import; they import
  no business code.

Check it: `rg -n "from fastapi|import express|from sqlalchemy|require\\('pg'\\)" src/<business-folder>`.

## 4. Choosing

Decide in this order and stop at the first match:

1. **The repo already follows one pattern consistently**, whatever it is →
   recommend **keeping it**, and record it in `## Project structure`.
2. **Anything else — new service, unstructured, or mixed code, however small** →
   recommend **layered, grouped by feature**. A service with one business area
   is simply one feature folder today; it grows without a later migration.
3. Offer the others as alternatives only, with their trade-off in one line:
   layered-by-layer (if the user prefers technical folders), hexagonal (heavy
   domain logic with several real adapters).

Always confirm with the user and record the result (see `SKILL.md` Step 4).
