# Tooling — What Enforces the Standard

Automate everything a machine can check, so review time goes to design and
correctness. Before adding a tool to a repo, check whether it already has one
that covers the job — extend the existing config instead of adding a second tool.
Verify every version/flag below against the tool's docs when you apply it;
tool CLIs change.

## Order of gates

```
format → lint → types → tests + coverage → security scan → secret scan → dependency audit
```

Run cheap gates first; a failing gate stops the pipeline. Locally via
`pre-commit`; in CI on every PR.

---

## Python

| Job | Tool | Command |
|-----|------|---------|
| Format | Ruff | `uv run ruff format .` (`--check` in CI) |
| Lint (incl. security `S`, complexity `C90`) | Ruff | `uv run ruff check .` |
| Types | mypy or pyright | `uv run mypy src` / `uv run pyright` |
| Tests + coverage | pytest + pytest-cov | `uv run pytest` (80% floor in config) |
| SAST | Semgrep | `semgrep scan --config p/python --config p/owasp-top-ten src/` |
| Dependencies | pip-audit | `uv run --with pip-audit pip-audit` |
| Secrets | gitleaks | `gitleaks git .` (history) / `gitleaks dir .` (working tree) |

Minimal `pyproject.toml` keys (extend the repo's existing blocks, do not duplicate):

```toml
[tool.ruff]
target-version = "py312"
# line-length: keep the default 88 unless the repo already sets one

[tool.ruff.lint]
select = [
  "E", "W", "F",   # pycodestyle, pyflakes
  "I",             # isort
  "B",             # bugbear
  "UP",            # pyupgrade
  "SIM",           # simplify
  "ASYNC",         # blocking calls in async
  "S",             # flake8-bandit security
  "BLE",           # blind except
  "C90",           # mccabe complexity
  "D",             # docstrings
  "G",             # logging format
  "FAST",          # FastAPI
]
[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "D"]      # assert and docstrings are fine in tests
[tool.ruff.lint.mccabe]
max-complexity = 10
[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.mypy]
strict = true
```

Adopting on a legacy repo: turn rules on, then baseline existing violations
per-file in `per-file-ignores` with a ticket, so **new** code is clean
immediately and the backlog shrinks over time. Never silence a rule globally to
get a green build.

## Node.js / TypeScript

| Job | Tool | Command |
|-----|------|---------|
| Format | Prettier | `npx prettier --check .` |
| Lint (incl. security, complexity) | ESLint 9 + typescript-eslint | `npx eslint .` |
| Types | tsc | `npx tsc --noEmit` |
| Tests + coverage | vitest + @vitest/coverage-v8 | `npx vitest run --coverage` |
| SAST | Semgrep | `semgrep scan --config p/typescript --config p/nodejs --config p/owasp-top-ten src/` |
| Dependencies | npm / pnpm | `npm audit --audit-level=high` / `pnpm audit` |
| Secrets | gitleaks | `gitleaks git .` / `gitleaks dir .` |

Minimal `eslint.config.js` (flat config):

```js
import js from '@eslint/js';
import { defineConfig } from 'eslint/config';
import tseslint from 'typescript-eslint';
import pluginSecurity from 'eslint-plugin-security';

export default defineConfig(
  js.configs.recommended,
  tseslint.configs.strictTypeChecked,
  pluginSecurity.configs.recommended,
  {
    languageOptions: { parserOptions: { projectService: true } },
    rules: {
      complexity: ['error', 10],
      'max-depth': ['error', 3],
      'max-params': ['error', 4],
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-explicit-any': 'error',
      // Google JS/TS style guide rules (see javascript-style.md / typescript-style.md indexes)
      'no-var': 'error',
      'prefer-const': 'error',
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      curly: ['error', 'multi-line'],
      'one-var': ['error', 'never'],
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-new-func': 'error',
      'no-multi-str': 'error',
      'no-array-constructor': 'error',
      'no-object-constructor': 'error',
      'no-new-wrappers': 'error',
      'no-throw-literal': 'error',
      'prefer-promise-reject-errors': 'error',
      'prefer-spread': 'error',
      'default-case-last': 'error',
      'default-case': 'error',
      'prefer-rest-params': 'error',
      'no-extend-native': 'error',
    },
  },
);
```

Minimal `.prettierrc` — single quotes match the Google guides:

```json
{ "singleQuote": true }
```

`eslint-plugin-security` is noisy (e.g. `detect-object-injection`); triage its
hits, disable a rule per line with a reason, never globally without agreement.

Biome is an acceptable single-tool alternative to ESLint + Prettier **only** if
the repo already uses it; do not mix both.

## Pre-commit (both stacks)

`.pre-commit-config.yaml` hooks, in order: formatter, linter, `gitleaks`
(`repo: https://github.com/gitleaks/gitleaks`, `id: gitleaks`), and for Python
`pip-audit`. Pin every hook to a released tag (`rev:`), never a branch.

## CI

The same commands as pre-commit, plus tests with coverage, Semgrep, and the
dependency audit.
