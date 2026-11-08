# Python Style — Essentials

Baseline: [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
(section numbers below refer to it) plus PEP 8 where Google is silent. Layout is
decided by `ruff format`; the rules here are the ones a formatter cannot enforce.

## Contents
1. Resolved conflicts
2. Language rules
3. Style rules
4. Typing
5. Async / FastAPI specifics
6. Anti-patterns table
7. Complete index

---

## 1. Resolved conflicts

| Topic | Google says | Rule |
|-------|-------------|---------------|
| Line length | 80 | Ruff default **88** (or the repo's existing `line-length`). The formatter decides; do not hand-wrap. |
| Formatter | Black or Pyink | **Ruff format** (Black-compatible, one tool with the linter). |
| Imports | Import modules, not names | Follow Google for internal packages (`from src.core import config`). Importing names is fine for `typing`, `collections.abc`, pydantic, FastAPI, and when the repo already does it consistently. |
| Docstrings | Google style | **Google style** (`Args:`, `Returns:`, `Raises:`). Ruff `D` with `convention = "google"`. |

## 2. Language rules

- **Lint (§2.1)** — code passes `ruff check`. Suppress a single line with the specific code and a reason: `# noqa: S603 - args are a fixed list`. Never blanket `# noqa`.
- **Imports (§2.2)** — absolute imports only. No `from x import *`. Import order: stdlib, third party, first party (Ruff `I` sorts).
- **Packages (§2.3)** — import every module by its full package path (`from src.core import config`, never a bare `import config`); do not assume the script's directory is on `sys.path`.
- **Exceptions (§2.4)**
  - Use built-in exceptions when they fit (`ValueError`, `KeyError`); define a small app hierarchy (`AppError` → `NotFoundError`, `ConflictError` …) in `src/core/exceptions.py`.
  - Never `except:` or `except Exception:` unless re-raising, or at a top-level boundary that logs and converts (health probes, job runners). Ruff `BLE`, `E722`.
  - Do not use `assert` for validation or control flow — it is stripped under `-O`. Assertions belong in tests.
  - Keep `try` bodies minimal; use `finally` or context managers for cleanup.
  - Chain: `raise NotFoundError(...) from err`.
- **Mutable global state (§2.5)** — avoid. Module-level constants are `UPPER_SNAKE`. Singletons (settings, logger, client pool) are created once and injected or imported read-only.
- **Nested functions (§2.6)** — fine for closures/decorators; not to hide helpers that deserve a name and a test.
- **Comprehensions (§2.7)** — one `for` and one optional `if`. Anything more becomes a loop or a function.
- **Default iterators (§2.8)** — `for key in mapping`, `if x in seq`; not `.keys()` / `.has_key()`.
- **Generators (§2.9)** — use them where they help; document with `Yields:`, not `Returns:`. A generator that holds an expensive resource must guarantee cleanup (wrap it in a context manager).
- **Lambdas (§2.10)** — one-liners only; otherwise `def`. Prefer `operator.itemgetter` etc.
- **Conditional expressions (§2.11)** — only for simple one-liners.
- **Default arguments (§2.12)** — never mutable (`def f(items: list[str] | None = None)`). Ruff `B006`.
- **Properties (§2.13)** — only for cheap, obvious computed attributes; no I/O inside a property.
- **True/False (§2.14)** — `if not items:` for sequences; `if x is None:` for None. Never `== None`, never `if x == True`.
- **Lexical scoping (§2.16)** — closures are fine; beware that a name rebound later in the enclosing function is what the inner function sees.
- **Decorators (§2.17)** — use judiciously; `@staticmethod` rarely (a module function is usually better).
- **Threading (§2.18)** — do not rely on atomicity of built-in types; use `queue.Queue` / locks, or better, async.
- **Power features (§2.19)** — no metaclasses, `__getattr__` magic, bytecode tricks, or dynamic `import` hacks in service code.
- **`from __future__` (§2.20)** — `from __future__ import annotations` where the codebase uses it; target Python 3.12+ syntax (`X | None`, `list[str]`). Ruff `UP` modernises.

## 3. Style rules

- **Naming (§3.16)** — `module_name`, `package_name`, `ClassName`, `ExceptionName` (ends in `Error`), `function_name`, `CONSTANT_NAME`, `_internal`. No single-letter names except loop indices and `e` in short handlers. No type in the name (`id_to_name_dict` → `name_by_id`).
- **Shebang (§3.7)** — only files executed directly start with `#!/usr/bin/env python3`; importable modules have none.
- **Docstrings (§3.8)** — every public module, class, and function. First line is a summary sentence ending in a period. Sections:

  ```python
  def fetch_invoice(invoice_id: str, *, owner_id: str) -> Invoice:
      """Fetch one invoice owned by the caller.

      Args:
          invoice_id: The invoice's public id.
          owner_id: The authenticated owner; rows of other owners are invisible.

      Returns:
          The invoice.

      Raises:
          NotFoundError: No invoice with this id belongs to the owner.
      """
  ```

- **Comments (§3.8.5)** — explain tricky logic and *why*; never restate code.
- **Strings (§3.10)** — f-strings for formatting. **Logging uses `%`-style lazy args**, not f-strings: `logger.info("sent invoice %s", invoice_id)` (Ruff `G004`). Error messages state what failed and the offending value (without secrets).
- **Resources (§3.11)** — always `with` for files, sockets, locks, DB sessions, `httpx.AsyncClient`.
- **TODO (§3.12)** — `# TODO: PROJ-123 - reason` (a ticket link, never a person).
- **Imports formatting (§3.13)** — one module per `import` line, all imports at the top after the module docstring, grouped `__future__`, stdlib, third party, first party (Ruff `I`, `E401`, `E402`).
- **Statements (§3.14)** — one statement per line; Ruff format splits `if x: y` onto two lines.
- **Getters and setters (§3.15)** — only when access is costly or has side effects (`get_foo()` / `set_foo()`); a getter/setter pair that just reads and writes an attribute should be a public attribute instead.
- **Main (§3.17)** — executable modules guard with `if __name__ == "__main__":`; service code has none (entry is `server.py`).
- **Function length (§3.18)** — prefer small; ~40 lines is the review trigger.

## 4. Typing (§2.21, §3.19)

- Annotate every public function signature and every class attribute. New code passes `mypy --strict` or `pyright` strict.
- `X | None`, not `Optional[X]`. Built-in generics (`list[str]`, `dict[str, int]`).
- Use `collections.abc` (`Sequence`, `Mapping`, `Iterable`) for parameters; concrete types for returns.
- `Any` needs a comment explaining why. Prefer `object` or a `Protocol`.
- `TypedDict` / pydantic models for structured dicts crossing boundaries; never pass raw `dict[str, Any]` through the domain.
- `typing.Protocol` for injected dependencies (only when two implementations exist — production + fake).

## 5. Async / FastAPI specifics

- **Never block the event loop.** No `requests`, `time.sleep`, sync DB drivers, or heavy CPU in `async def`. Use `httpx.AsyncClient`, `asyncio.sleep`, async drivers, or `await asyncio.to_thread(...)` / `run_in_threadpool`. Ruff `ASYNC`.
- One shared `httpx.AsyncClient` per upstream, created in lifespan, closed on shutdown; explicit `timeout=`.
- Fan-out with `asyncio.gather(..., return_exceptions=True)` or `asyncio.TaskGroup`; bound concurrency with `asyncio.Semaphore`.
- Keep a reference to background tasks (`asyncio.create_task`) or they can be garbage-collected mid-flight.
- Pydantic v2: request models use `model_config = ConfigDict(extra="forbid")`; response models declared via `response_model=` so internal fields never leak.
- Dependencies (`Depends`) for auth, tenant, DB session — not repeated inline in every route.
- Routes are `async def` only when everything inside is awaitable; otherwise plain `def` (FastAPI runs it in a thread pool).

## 6. Anti-patterns

| Don't | Do |
|-------|----|
| `def f(x=[])` | `def f(x: list[str] | None = None)` |
| `except Exception: pass` | catch the specific error, handle or re-raise with context |
| `assert user.is_admin` in service code | `if not user.is_admin: raise ForbiddenError(...)` |
| `f"SELECT * FROM t WHERE id = {id}"` | parameterised query / ORM filter |
| `logger.info(f"user {u}")` | `logger.info("user %s", u)` |
| `os.getenv("X")` scattered | one `Settings` in `src/core/config.py` |
| `requests.get(url)` in async code | `await client.get(url, timeout=...)` |
| `from module import *` | explicit imports |
| `type(x) == Foo` | `isinstance(x, Foo)` |
| `utils.py` with 40 unrelated helpers | functions live beside the concept they serve |

## 7. Complete index of the Google Python Style Guide

Every numbered section of the Google guide has one row below, in guide order, so no rule is lost. The full text lives in [`google/pyguide.md`](google/pyguide.md); read that section when you need the detail or the examples.
Status: `tool` = enforced automatically by the named tool; `rule` = follow it by hand (one-line summary); `override` = this standard deliberately differs (reason given); `n/a` = not applicable.

| § | Section | Status | Rule |
|---|---------|--------|---------------|
| 1 | Background | override | Ruff format replaces Black/Pyink; Google's Vim settings file is not used. |
| 2 | Python Language Rules | n/a | Chapter heading only; rules are in 2.1–2.21. |
| 2.1 | Lint | override | `ruff check` replaces pylint. Suppress one line with the specific code and a reason: `# noqa: S603 - fixed args`. |
| 2.2 | Imports | override | Import modules for internal packages; importing names is allowed for `typing`, `collections.abc`, pydantic and FastAPI. No relative imports. |
| 2.2.4.1 | Exemptions | rule | Import symbols directly from `typing`, `collections.abc` and `typing_extensions`. |
| 2.3 | Packages | rule | Import each module by its full package path; never assume the main script's directory is on `sys.path`. |
| 2.4 | Exceptions | rule | Built-in exceptions where they fit; custom ones end in `Error`; no catch-alls; no `assert` for logic; minimal `try`. Ruff `BLE`, `E722`, `S101` help. |
| 2.5 | Mutable Global State | rule | Avoid it. If unavoidable, prefix with `_`, expose via functions, and comment why. Not auto-enforced. |
| 2.6 | Nested/Local/Inner Classes and Functions | rule | Nest only to close over a local value (not `self`/`cls`); to hide a helper, use a `_name` at module level. |
| 2.7 | Comprehensions & Generator Expressions | rule | Simple cases only: one `for`, at most one `if`; otherwise write a loop. |
| 2.8 | Default Iterators and Operators | rule | Use `for k in d`, `x in seq`, `for line in f`; never mutate a container while iterating it. Ruff `SIM118` flags `.keys()`. |
| 2.9 | Generators | rule | Use when useful; document with `Yields:` not `Returns:`; force cleanup of expensive resources with a context manager. |
| 2.10 | Lambda Functions | rule | One-liners only; prefer generator expressions to `map`/`filter` with lambda, and `operator` functions. Ruff `E731` flags assigned lambdas. |
| 2.11 | Conditional Expressions | rule | Simple cases only; each of the three parts must fit on one line, otherwise use an `if` statement. |
| 2.12 | Default Argument Values | tool | Never mutable or call-evaluated defaults; use `None` and set inside. Ruff `B006`, `B008`. |
| 2.13 | Properties | rule | `@property` only for cheap, unsurprising, trivially derived values; no plain get/set wrappers, nothing a subclass may override. |
| 2.14 | True/False Evaluations | rule | Use implicit false (`if not seq:`); `is None` for None; never `== False`; compare known ints to `0`. Ruff `E711`, `E712`. |
| 2.16 | Lexical Scoping | rule | Closures are fine; beware names rebound later in the enclosing scope (the inner function sees the final binding). |
| 2.17 | Function and Method Decorators | rule | Use judiciously, document and test them; no I/O at decoration time; never `staticmethod`; `classmethod` only for named constructors. |
| 2.18 | Threading | rule | Do not rely on atomicity of built-ins; use `queue.Queue` or `threading` primitives, or async instead of threads. |
| 2.19 | Power Features | rule | No metaclasses, bytecode access, import hacks, reflection tricks or `__del__` cleanup; stdlib users like `dataclasses`, `enum` are fine. |
| 2.20 | Modern Python: from \_\_future\_\_ imports | override | Target Python 3.12+ syntax; `from __future__ import annotations` only where the codebase already uses it; Ruff `UP` modernises. |
| 2.21 | Type Annotated Code | override | mypy `--strict` or pyright strict replaces pytype; all new code is annotated, not just public APIs. |
| 3 | Python Style Rules | n/a | Chapter heading only; rules are in 3.1–3.19. |
| 3.1 | Semicolons | tool | No trailing semicolons or two statements on one line. Ruff format, Ruff `E702`, `E703`. |
| 3.2 | Line length | override | 88 (Ruff default) or the repo's `line-length`, not 80; Ruff format wraps, Ruff `E501` flags the rest. No backslash continuation. |
| 3.3 | Parentheses | tool | Ruff format removes redundant parentheses after `if`, `while`, `return`; keep them only for tuples or line continuation. |
| 3.4 | Indentation | tool | Four spaces, never tabs, hanging indents. Ruff format, Ruff `W191`. |
| 3.4.1 | Trailing commas in sequences of items? | tool | Ruff format honours the magic trailing comma: trailing comma means one item per line. |
| 3.5 | Blank Lines | tool | Two blank lines between top-level definitions, one between methods. Ruff format. |
| 3.6 | Whitespace | tool | Standard spacing, no trailing whitespace, no vertical alignment. Ruff format, Ruff `W291`, `W293`. |
| 3.7 | Shebang Line | rule | Only files executed directly start with `#!/usr/bin/env python3`; importable modules have none. |
| 3.8 | Comments and Docstrings | rule | Use the right style for module, class and function docstrings and for comments; details in 3.8.1–3.8.6. |
| 3.8.1 | Docstrings | tool | `"""` docstrings, one-line summary ending in punctuation, blank line, then body. Ruff `D` (`convention = "google"`). |
| 3.8.2 | Modules | tool | Every file carries a module docstring (Ruff `D100`), after the repo's licence header if it uses one. |
| 3.8.2.1 | Test modules | rule | Tests need no module, class or `test_` docstrings (Ruff `D` is off for `tests/**`); add one only if it adds information. |
| 3.8.3 | Functions and Methods | tool | Docstrings on public, large or non-obvious functions with `Args:`, `Returns:`/`Yields:`, `Raises:`. Ruff `D`; content accuracy is yours. |
| 3.8.3.1 | Overridden Methods | rule | Mark overrides with `@typing.override`; they then need a docstring only if they refine the base contract or add side effects. |
| 3.8.4 | Classes | rule | Summary says what an instance represents; public attributes in `Attributes:`; exceptions describe what they represent, not when raised. |
| 3.8.5 | Block and Inline Comments | rule | Comment tricky code and explain why; two spaces before `#`, one after; never restate the code. |
| 3.8.6 | Punctuation, Spelling, and Grammar | rule | Write comments as readable prose with proper capitalisation, punctuation and spelling. |
| 3.10 | Strings | rule | Prefer f-strings; never format with `+`; build strings in loops with `"".join`; `"""` for multi-line. Ruff format normalises quotes to `"`. |
| 3.10.1 | Logging | tool | Pass a literal `%`-pattern plus arguments, never an f-string: `logger.info("sent %s", invoice_id)`. Ruff `G004`. |
| 3.10.2 | Error Messages | rule | Messages match the real condition precisely, mark interpolated values clearly (`{p=}`, `%r`), and stay greppable. |
| 3.11 | Files, Sockets, and similar Stateful Resources | rule | Close resources with `with`/`async with` or `contextlib.closing`; never rely on `__del__`. Ruff `SIM115` flags bare `open()`. |
| 3.12 | TODO Comments | rule | `# TODO: PROJ-123 - reason` — a ticket link, a hyphen, then the reason; never a person's name. |
| 3.13 | Imports formatting | tool | One import per line, at the top, grouped `__future__`, stdlib, third party, first party. Ruff `I` (its default order), `E401`, `E402`. |
| 3.14 | Statements | override | One statement per line, always: Ruff format splits even `if x: y`, which Google allows. Ruff `E701`, `E702`. |
| 3.15 | Getters and Setters | rule | Use `get_foo()`/`set_foo()` only when access is costly or has side effects; otherwise make the attribute public. |
| 3.16 | Naming | rule | Descriptive names, no ambiguous abbreviations, `.py` files without dashes. pep8-naming (`N`) is not selected, so not auto-enforced. |
| 3.16.1 | Names to Avoid | rule | No single letters except counters, `e`, `f`, private unconstrained type variables; no dashes, no dunder names, no type in the name. |
| 3.16.2 | Naming Conventions | rule | Follow PEP 8; single `_` for internal, avoid `__` name mangling; CapWords classes, acronyms fully capitalised; `test_<method>_<state>`. |
| 3.16.2.1 | Exemptions | rule | Code tightly coupled to an external or non-Python codebase may follow that codebase's naming. |
| 3.16.3 | File Naming | rule | Filenames end in `.py` and contain no dashes; wrap executables with a symlink or shell script. |
| 3.16.4 | Guidelines derived from Guido's Recommendations | rule | `lower_with_under` for packages, modules, functions, variables; `CapWords` classes; `CAPS_WITH_UNDER` constants; leading `_` when internal. |
| 3.16.5 | Mathematical Notation | rule | Short notation-matching names are allowed in maths-heavy code if the source is cited; public APIs keep descriptive names. |
| 3.17 | Main | rule | Executables put logic in `main()` behind `if __name__ == "__main__":`; no side effects at import; services have none. |
| 3.18 | Function length | rule | Prefer small, focused functions; about 40 lines triggers a review. Ruff `C901` caps complexity at 10. |
| 3.19 | Type Annotations | rule | Heading for 3.19.1–3.19.15; annotations are checked by mypy `--strict` or pyright strict. |
| 3.19.1 | General Rules | override | Annotate every function, not only public APIs (strict mode requires it); skip `self`/`cls`; use `Self` when needed; justify `Any`. |
| 3.19.2 | Line Breaking | tool | One parameter per line with a trailing comma, return type on the closing line. Ruff format. |
| 3.19.3 | Forward Declarations | rule | For a class not yet defined, use `from __future__ import annotations` or a string annotation. |
| 3.19.4 | Default Values | tool | Spaces around `=` only when the parameter has an annotation: `a: int = 0`. Ruff format. |
| 3.19.5 | NoneType | tool | Declare `X \| None` explicitly, never implicit `a: str = None`. mypy rejects implicit Optional; Ruff `UP` rewrites `Optional`/`Union`. |
| 3.19.6 | Type Aliases | override | Python 3.12+: use the `type` statement (`type Pair = tuple[int, int]`), CapWords, `_Private` if module-local. Ruff `UP040` rewrites `TypeAlias`. |
| 3.19.7 | Ignoring Types | override | Use `# type: ignore[code]` with a reason (mypy/pyright); pytype disable comments do not apply. |
| 3.19.8 | Typing Variables | rule | Annotate a variable only when its type cannot be inferred; never add `# type:` comments. |
| 3.19.9 | Tuples vs Lists | rule | `list[T]` for homogeneous items; `tuple[T, ...]` or fixed `tuple[A, B]` for set-size mixed types. |
| 3.19.10 | Type variables | override | Python 3.12+: prefer PEP 695 syntax `def first[T](items: list[T]) -> T`; module-level `TypeVar`s follow Google naming (`_T` private, descriptive otherwise). |
| 3.19.11 | String types | tool | `str` for text, `bytes` for binary, `AnyStr` when they must match; never `typing.Text`. Ruff `UP019`. |
| 3.19.12 | Imports For Typing | rule | Import `typing`/`collections.abc` symbols directly, never shadow them; abstract containers for parameters; built-in generics (Ruff `UP006`). |
| 3.19.13 | Conditional Imports | rule | `if TYPE_CHECKING:` only when a runtime import must be avoided; block after normal imports, sorted. Not for types pydantic/FastAPI resolve at runtime. |
| 3.19.14 | Circular Dependencies | rule | Typing-caused import cycles are a smell: refactor. Last resort is Google's alias-the-module-to-`Any` pattern. |
| 3.19.15 | Generics | tool | Always give type parameters (`Sequence[int]`, not bare `Sequence`); prefer a type variable to explicit `Any`. mypy `--strict` (`disallow_any_generics`). |
| 4 | Parting Words | rule | Be consistent with the surrounding code, but do not use consistency to justify keeping an outdated style. |
