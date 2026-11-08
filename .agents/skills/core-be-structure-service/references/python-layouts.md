# Python (FastAPI) Layouts

Three concrete layouts. Adapt names to what the repo already uses; do not
scaffold folders nothing uses yet.

## Contents
1. Layered, grouped by feature (default)
2. Layered by technical layer
3. Hexagonal (ports & adapters)
4. Shared files in every layout

---

## 1. Layered, grouped by feature (default)

Each business area is one package containing its own layers. Pattern popularised
by the widely used *FastAPI Best Practices* guide (zhanymkanov/fastapi-best-practices).

```
repo/
├── src/
│   ├── main.py                  # app factory: routers, middleware, lifespan, error handlers
│   ├── core/                    # cross-cutting infrastructure only
│   │   ├── config.py            # one Settings (pydantic-settings) singleton
│   │   ├── db.py                # engine/session or client lifecycle
│   │   ├── errors.py            # AppError hierarchy + central handlers → envelope
│   │   ├── logging.py
│   │   ├── security.py          # auth dependencies shared by features
│   │   └── clients/             # shared external clients, one module per upstream
│   ├── orders/                  # one package per business area
│   │   ├── router.py            # HTTP only: validate, call service, shape response
│   │   ├── schemas.py           # pydantic request/response models
│   │   ├── service.py           # use-case / business logic for orders
│   │   ├── repository.py        # data access for orders
│   │   ├── models.py            # ORM / document models
│   │   ├── dependencies.py      # FastAPI Depends() specific to orders
│   │   └── exceptions.py        # order-specific errors (subclass core AppError)
│   └── users/
│       └── …                    # same shape
├── tests/
│   ├── orders/test_service.py   # mirrors src/
│   ├── orders/test_router.py
│   └── conftest.py
├── migrations/                  # alembic, if SQL
├── pyproject.toml  uv.lock  .env.example  Dockerfile  README.md  AGENTS.md
```

Rules:
- `router → service → repository`; routers never touch the repository or DB.
- A feature uses another feature only through its `service.py` public functions — never its repository or models.
- `service.py` does not import `fastapi` (raise domain exceptions; the central handler maps them to HTTP).
- Files appear only when needed: a feature with no DB access has no `repository.py`.

## 2. Layered by technical layer

Good for small services with one or two business areas.

```
repo/
├── src/
│   └── app/
│       ├── main.py              # app factory
│       ├── api/                 # routers — HTTP in/out only
│       │   └── v1/
│       │       ├── orders.py
│       │       └── users.py
│       ├── schemas/             # pydantic DTOs, one file per area
│       ├── services/            # use-case logic, orchestrates domain + repositories
│       ├── domain/              # entities and pure business rules — no framework imports
│       ├── repositories/        # data access (the adapter side)
│       ├── db/                  # session, models, migrations config
│       └── core/                # config, security, logging, errors
├── tests/
│   ├── unit/                    # domain + services with fakes
│   └── integration/             # through API / repositories with stand-ins
├── pyproject.toml  .env.example  Dockerfile  README.md  AGENTS.md
```

Rules: `api → services → (domain, repositories)`; `domain/` and `services/`
never import from `api/` or `db/` driver code directly.

## 3. Hexagonal (ports & adapters)

Only when domain logic is heavy and ports have more than one real adapter.

```
src/
├── main.py                      # composition root: builds adapters, injects into use cases
├── domain/                      # entities, value objects, domain errors — pure Python
├── application/                 # use cases + ports (typing.Protocol) they depend on
│   ├── ports.py                 # e.g. OrderRepository, PaymentGateway protocols
│   └── place_order.py
└── adapters/
    ├── http/                    # FastAPI routers → call use cases
    ├── persistence/             # SQLAlchemy / Mongo implementations of repository ports
    └── payments/                # stripe_gateway.py, fake_gateway.py (two adapters = real seam)
```

Rules: `domain` imports nothing outside the stdlib; `application` imports
`domain` only; adapters import inward. Tests drive use cases with fake adapters.

## 4. Shared files in every layout

- `pyproject.toml` with `license` set to the repo's licence identifier, Ruff/mypy/pytest config (see `core-be-coding-standards/references/tooling.md`).
- `.env.example` listing every variable read by the single settings module.
- `README.md` per `readme-standard.md`.
- `LICENSE` at the root.
- Tests per `core-be-write-tests`.
