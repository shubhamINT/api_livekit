# Scanners — Commands and Triage

Run what fits the stack. Prefer the repo's existing tool configs. Record the
tool version (`<tool> --version`) in the report's Method section. Check each
tool's `--help` if a flag below fails; CLIs change.

Ephemeral runs avoid adding dev dependencies during an audit — ask before
installing anything permanently.

## Secrets (always)

```bash
gitleaks git . --redact --report-format json --report-path /tmp/gitleaks.json   # full git history
gitleaks dir . --redact                                                          # working tree (incl. untracked)
# alternative / second opinion, verified hits only:
trufflehog git file://. --results=verified
```

`gitleaks detect` / `protect` are deprecated names (v8.19+); use `git` / `dir`.
Always `--redact`. A secret in history is still leaked even if deleted from HEAD —
it must be rotated; removing it from history is optional hygiene, not a fix.

## Python

```bash
uvx ruff check --select S,BLE,ASYNC --output-format concise src      # bandit-equivalent rules
uvx bandit -r src -q                                                  # optional second opinion
uvx semgrep scan --config p/python --config p/owasp-top-ten --config p/secrets src
uv run --with pip-audit pip-audit                                     # installed env
uvx pip-audit -r requirements.txt                                     # requirements file
```

## Node.js / TypeScript

```bash
npx eslint .                          # security rules only if eslint-plugin-security is in eslint.config.js
uvx semgrep scan --config p/typescript --config p/nodejs --config p/owasp-top-ten --config p/secrets src
npm audit --audit-level=low --json    # or: pnpm audit --json / yarn npm audit
npx tsc --noEmit                      # type errors often hide unchecked input paths
```

(`semgrep` via `pipx run semgrep` / `uvx semgrep` if not on PATH.)

## Dependency existence check (hallucinated / typosquatted packages)

For every direct dependency, especially recently added ones:

```bash
# Python: confirm on PyPI, check age / maintainer / downloads
curl -s https://pypi.org/pypi/<name>/json | jq '.info.name, .info.home_page, (.releases|keys|length)'
# Node
npm view <name> name repository.url time.created maintainers --json
```

Red flags: package created very recently, near-identical name to a popular
package, no repository, single maintainer with no history, install scripts.

## Licences

List dependency licences and compare them with the repo's own `LICENSE`:

```bash
uvx pip-licenses --format=markdown          # Python
npx license-checker --production --summary  # Node
```

Flag GPL / AGPL / unknown for human review.

## Triage rules

| Result | Action |
|--------|--------|
| Confirmed | Finding with severity, standard IDs, `file:line` |
| False positive | Keep in the report's appendix with a one-line reason |
| Needs manual check | Resolve during Phase 6 before the report is final |
| Dependency vuln | Check reachability: is the vulnerable function used? Severity follows reachability, not the CVSS alone |
| Secret | Tell the user immediately; record redacted; recommend rotation |

Scanners miss logic flaws — BOLA, missing authorization, business-flow abuse,
SSRF through indirect paths. A clean scan never means a clean audit.
