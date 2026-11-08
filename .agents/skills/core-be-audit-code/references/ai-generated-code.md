# AI-Generated Code — Failure Patterns

LLM-written code looks finished. It compiles, it reads fluently, and its
comments sound sure of themselves — which is exactly why its failures slip past
review. The failures are not random; they cluster in the eight categories below.
Review against each category with a **concrete verification action**, not by
eye. "Looks right" is the failure mode.

Used by `core-be-audit-code` (review of any code), `core-be-refactor-code` (smell inventory),
and as the self-review in `core-be-coding-standards` before handing back your own code.
General quality is in `core-be-coding-standards`; vulnerabilities in `core-be-audit-security`.

## The eight checks

### 1. Hallucinated APIs and packages
Plausible-sounding functions, methods, parameters, config keys, and whole
packages that do not exist — or exist with different behaviour. ~20% of package
names suggested by LLMs in one large study did not exist, and many of the fake
names recur predictably, which attackers exploit by registering them
("slopsquatting"; Spracklen et al., USENIX Security 2025).

Verify:
- Every new dependency: exists on PyPI / npm under that exact name, is the
  intended project (repo link, maintainers, age, downloads), and is in the lockfile.
- Every imported symbol exists in the **installed** version: open the package
  source in `.venv/lib/.../site-packages/` or `node_modules/`, or the versioned
  official docs. Check signature and return type, not just the name.
- Every config key / env var / CLI flag used is real for that tool version.
- Run it: type checker (`mypy`/`pyright`/`tsc`) and the tests exercising the call.

### 2. Silent edge-case gaps
Generated code handles the happy path. Look for what it skipped:
- empty / `None` / `undefined` / missing keys / empty collections
- off-by-one in pagination, slicing, ranges, date boundaries, time zones
- concurrent requests (race on read-modify-write, duplicate submissions, idempotency)
- error paths: upstream timeout, 4xx/5xx, malformed response, DB constraint violation, partial failure mid-loop
- large inputs: unbounded lists, huge payloads, deep recursion

Verify: list the inputs each function can receive; confirm a branch or a test
for each class. Missing → finding.

### 3. Over-engineering
Abstraction layers, factories, strategy classes, config flags, retries, caches,
and defensive checks nobody asked for. They add surface to test and maintain.

Verify: apply the deletion test (`core-be-coding-standards/references/module-design.md`) to each abstraction. One
implementation behind an interface, a parameter only ever passed one value, a
wrapper that only forwards — recommend inlining. Compare the size of the change
to the size of the requirement.

### 4. Inconsistent style
Code generated across sessions mixes patterns: sync and async clients, two HTTP
libraries, `snake_case` and `camelCase`, different error styles, different
logging, a second config loader.

Verify: for each new pattern, find the existing one in the repo
(`rg` for the equivalent). Two ways of doing the same thing → finding; the
repo's established way wins.

### 5. Licence risk from verbatim chunks
Models sometimes reproduce recognisable code from specific projects, including
GPL-licensed code.

Verify: unusually specific, polished, or oddly-commented blocks (distinctive
variable names, embedded copyright lines, a different style from the rest) —
search a distinctive line on the web / GitHub code search. Any match with an
licence incompatible with the repo's own `LICENSE` is a blocker.

### 6. Outdated practices
Training-data lag: deprecated APIs and insecure defaults that used to be normal.

Common in Python: `datetime.utcnow()` (deprecated 3.12), pydantic v1 APIs
(`.dict()`, `@validator`, `class Config`) in a v2 codebase, `asyncio.get_event_loop()`
in new code, `requests` in async services, `typing.List`/`Optional`, FastAPI
`@app.on_event` instead of lifespan.

Common in Node: CommonJS `require` in an ESM TypeScript repo, callback-style
`fs`, `request` / `node-fetch` where built-in `fetch` exists, `body-parser`
separately with modern Express, ESLint `.eslintrc` in an ESLint 9 repo,
`new Buffer()`, old `crypto.createCipher`.

Both: MD5/SHA-1 for passwords, JWT without algorithm pinning, pinned-to-old
dependency versions with known CVEs.

Verify: check each API against the version in the lockfile; run `ruff check
--select UP` / typescript-eslint `deprecation` rules; run the dependency audit.

### 7. Test coverage theater
Tests that pass but prove nothing:
- assert only that something is truthy / not `None` / was called
- mirror the implementation (recompute the expected value with the same logic)
- mock the function under test, or mock so much that no real code runs
- snapshot everything without asserting meaning
- no failure-path tests; parametrised cases that are all the same class
- tests named `test_1`, `test_function_works`

Verify: for each test, ask "what bug would make this fail?" If none, it is
theater. Mutate the code mentally (flip a condition, drop a line) — would a test
go red? High coverage with weak assertions is a finding.

### 8. Comments and docs that lie
Comments and docstrings describing intended behaviour that the code does not
implement ("validates the email", "retries three times", "thread-safe"), README
claims about features that do not exist, TODOs claiming work is done.

Verify: for each comment that asserts behaviour, find the line that implements
it. No such line → finding (fix the code or delete the comment).

## Finding format

<output>
```
AI-004 | High | Hallucinated API | src/services/rates/rates_service.py:57
  `await client.get_json(url)` — `httpx.AsyncClient` has no `get_json` method
  (checked in .venv/lib/python3.12/site-packages/httpx/_client.py); this line
  raises AttributeError on every call. No test covers it.
  Fix: `response = await client.get(url, timeout=...)`, `response.raise_for_status()`,
  `response.json()`; add a MockTransport test for this path.
```

Severity follows impact: a hallucinated call on a hot path is High (it crashes
at runtime); a lying comment is usually Low unless it misleads about security.
</output>

## Self-review before handing back your own code

Run all eight checks on your own diff. In particular:

- [ ] I opened the source or docs for every library call I used that I have not already seen in this repo.
- [ ] Every new dependency exists, is intended, is licence-compatible, and is in the lockfile.
- [ ] I handled empty, error, and concurrent cases, or documented why not.
- [ ] Nothing I added fails the deletion test.
- [ ] My code uses the repo's existing patterns, not new ones.
- [ ] Each test I wrote would fail if the behaviour broke.
- [ ] Every comment I wrote is true of the code as it stands.
