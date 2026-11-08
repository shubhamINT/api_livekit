# Node.js (TypeScript) Layouts

Three concrete layouts for Express or Fastify. Adapt names to what the repo
already uses; do not scaffold folders nothing uses yet.

## Contents
1. Layered, grouped by feature (default)
2. Layered by technical layer
3. Hexagonal (ports & adapters)
4. Shared files in every layout

---

## 1. Layered, grouped by feature (default)

"Structure by components" from Node.js Best Practices (§1.1): each business area
is a self-contained module.

```
repo/
├── src/
│   ├── server.ts                # entry: build app, listen, graceful shutdown
│   ├── app.ts                   # app factory: middleware, module routers, error handler
│   ├── core/                    # cross-cutting infrastructure only
│   │   ├── config.ts            # one zod-validated config object from process.env
│   │   ├── db.ts                # connection lifecycle
│   │   ├── errors.ts            # AppError hierarchy + central error handler → envelope
│   │   ├── logger.ts            # pino
│   │   ├── auth.ts              # shared auth middleware
│   │   └── clients/             # shared external clients, one per upstream
│   └── modules/
│       ├── orders/
│       │   ├── orders.routes.ts      # HTTP only: validate, call service, shape response
│       │   ├── orders.schema.ts      # zod request/response schemas + inferred types
│       │   ├── orders.service.ts     # use-case / business logic
│       │   ├── orders.repository.ts  # data access
│       │   └── index.ts              # the module's public surface (router + service exports)
│       └── users/
│           └── …
├── tests/
│   └── modules/orders/orders.service.test.ts   # mirrors src/
├── package.json  tsconfig.json  eslint.config.js  vitest.config.ts
├── .env.example  Dockerfile  README.md  AGENTS.md
```

Rules:
- `routes → service → repository`; routes never touch the repository or DB.
- Other modules import only from a module's `index.ts`, never its internals.
- `*.service.ts` does not import `express`/`fastify` types or `req`/`res`; it receives plain typed values and throws `AppError` subclasses.

## 2. Layered by technical layer

Good for small services with one or two business areas.

```
repo/
├── src/
│   ├── server.ts                # entrypoint
│   ├── app.ts                   # express/fastify assembly
│   ├── api/                     # routers/controllers — HTTP in/out only
│   │   └── v1/
│   ├── validators/              # zod schemas for requests/responses
│   ├── services/                # business / use-case logic
│   ├── domain/                  # entities, types, pure business rules
│   ├── repositories/            # data access (Prisma / Drizzle / Knex / raw SQL adapters)
│   ├── middlewares/             # auth, error handling, rate limiting
│   └── config/                  # env parsing, constants
├── tests/
│   ├── unit/
│   └── integration/
├── dist/                        # build output (gitignored)
├── package.json  tsconfig.json  .env.example  Dockerfile  README.md  AGENTS.md
```

Rules: `api → services → (domain, repositories)`; `domain/` and `services/`
stay framework-agnostic. No `utils/` or `types/` dumping ground — types live
beside the schema or module that owns them.

## 3. Hexagonal (ports & adapters)

Only when domain logic is heavy and ports have more than one real adapter.

```
src/
├── main.ts                      # composition root: build adapters, inject into use cases
├── domain/                      # entities, value objects, domain errors — no imports from node_modules
├── application/
│   ├── ports.ts                 # interfaces: OrderRepository, PaymentGateway
│   └── place-order.ts           # use case, depends on ports only
└── adapters/
    ├── http/                    # express/fastify routes → call use cases
    ├── persistence/             # database implementations of repository ports
    └── payments/                # stripe-gateway.ts, fake-gateway.ts
```

## 4. Shared files in every layout

- `package.json`: `"type": "module"`, `"license"` set to the repo's licence identifier, `"engines": { "node": ">=24" }`; lockfile committed.
- `tsconfig.json` strict; ESLint flat config + Prettier (see `core-be-coding-standards/references/tooling.md`).
- `.env.example` listing every variable parsed by `config.ts`.
- `README.md` per `readme-standard.md`.
- `LICENSE` at the root.
- Tests per `core-be-write-tests`.
