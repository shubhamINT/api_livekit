"""Check every Mermaid diagram in the docs and fail if any of them is broken.

Read-only. Touches no database and makes no network calls, beyond letting npm fetch the
Mermaid parser into a cache directory on first run.

Why this exists: `mkdocs build --strict` cannot catch a broken diagram. The
`pymdownx.superfences` custom fence hands the block straight through as
`<pre class="mermaid">`, and MkDocs never looks inside it — all Mermaid parsing happens in the
reader's browser. So a malformed diagram builds clean, deploys clean, and then renders as a red
"Syntax error in text" box on the live site.

There are two ways a diagram can be wrong, and they need different checks:

1. **It does not parse.** The reader gets a red error box. Caught by running Mermaid's own
   parser (`mermaid.parse`) under jsdom — no browser needed, unlike `mermaid-cli`, which wants
   a headless Chrome.

2. **It parses but renders wrong.** No error box, just a wrong-looking picture, so this is the
   sneakier class. The known case is a literal `\\n` in a node label: Mermaid accepts it and
   then draws the characters `\\n` on the diagram instead of a line break. That is exactly how
   the documentation home page shipped `API[API Server\\nFastAPI]`. `mermaid.parse()` returns
   *success* for it, so the parser alone would not have caught the one real bug we had — hence
   the lint rules below.

Run it alongside the docs build:

    uv run python scripts/check_mermaid.py

Exit code is 1 when a diagram fails, so it works as a pre-deploy gate. `--json` prints the same
result as one JSON object. `--lint-only` skips the Node parser and runs just the render checks.

Requires `node` and `npm` on PATH for the parse stage. If they are missing the script exits 2
and says so rather than reporting success — a checker that cannot check must not look like a
checker that found nothing wrong. Use `--lint-only` to run the pure-Python half anywhere.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Where to look. README is included because GitHub renders Mermaid too.
SEARCH_ROOTS = [REPO_ROOT / "docs", REPO_ROOT / "README.md"]

FENCE_RE = re.compile(r"^([ \t]*)```mermaid[ \t]*$", re.MULTILINE)

# Node deps are cached here rather than added to the repo, so this stays a Python project.
NODE_CACHE = Path(
    os.getenv("MERMAID_CHECK_CACHE", Path.home() / ".cache" / "api_livekit_mermaid_check")
)
NODE_DEPS = ["mermaid@11", "jsdom"]

# Loads Mermaid under jsdom and parses each diagram fed to it as JSON on stdin.
PARSER_JS = """
import { JSDOM } from 'jsdom';

// Mermaid needs a DOM to initialise. Note we deliberately do NOT assign global.navigator:
// on modern Node it is a getter-only property and assigning to it throws.
const dom = new JSDOM('<!DOCTYPE html><body></body>', { pretendToBeVisual: true });
global.window = dom.window;
global.document = dom.window.document;
global.HTMLElement = dom.window.HTMLElement;
global.SVGElement = dom.window.SVGElement;

const mermaid = (await import('mermaid')).default;
mermaid.initialize({ startOnLoad: false });

let raw = '';
for await (const chunk of process.stdin) raw += chunk;
const diagrams = JSON.parse(raw);

const results = [];
for (const d of diagrams) {
  try {
    await mermaid.parse(d.source);
    results.push({ where: d.where, ok: true });
  } catch (e) {
    const msg = String((e && e.message) || e).split('\\n').slice(0, 3).join(' ').trim();
    results.push({ where: d.where, ok: false, error: msg });
  }
}
process.stdout.write(JSON.stringify(results));
"""


@dataclass
class Diagram:
    path: Path
    line: int  # 1-indexed line of the opening fence
    source: str
    problems: list[str] = field(default_factory=list)

    @property
    def where(self) -> str:
        return f"{self.path.relative_to(REPO_ROOT)}:{self.line}"


# ── Extraction ──────────────────────────────────────────────────────────────────────────────


def _iter_markdown_files() -> list[Path]:
    files: list[Path] = []
    for root in SEARCH_ROOTS:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(sorted(root.rglob("*.md")))
    return files


def extract_diagrams(path: Path) -> list[Diagram]:
    """Pull every ```mermaid block out of one Markdown file.

    Indentation-aware: a fence nested in a list item is closed by ``` at the same indent, so a
    differently indented closing fence does not end the block early.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    diagrams: list[Diagram] = []

    i = 0
    while i < len(lines):
        match = FENCE_RE.match(lines[i])
        if not match:
            i += 1
            continue
        indent = match.group(1)
        closing = f"{indent}```".rstrip()
        body: list[str] = []
        j = i + 1
        while j < len(lines) and lines[j].rstrip() != closing:
            # Strip the fence's indentation so Mermaid sees a flush-left diagram.
            body.append(lines[j][len(indent):] if lines[j].startswith(indent) else lines[j])
            j += 1
        diagrams.append(Diagram(path=path, line=i + 1, source="\n".join(body)))
        i = j + 1

    return diagrams


# ── Render lints: things Mermaid parses happily but draws wrong ──────────────────────────────

# A literal backslash-n. Mermaid renders the two characters instead of a line break.
LITERAL_NEWLINE_RE = re.compile(r"\\n")


def lint(diagram: Diagram) -> list[str]:
    problems: list[str] = []
    for offset, line in enumerate(diagram.source.splitlines(), start=1):
        if LITERAL_NEWLINE_RE.search(line):
            problems.append(
                f"line {diagram.line + offset}: literal '\\n' renders as text, not a line "
                f"break — use '<br/>':  {line.strip()}"
            )
    return problems


# ── Parse stage (Node) ──────────────────────────────────────────────────────────────────────


def _node_available() -> bool:
    return shutil.which("node") is not None and shutil.which("npm") is not None


def _ensure_node_deps() -> bool:
    """Install mermaid + jsdom into the cache dir. Returns True when ready."""
    NODE_CACHE.mkdir(parents=True, exist_ok=True)
    if (NODE_CACHE / "node_modules" / "mermaid").is_dir():
        return True
    print(f"[check_mermaid] installing {' '.join(NODE_DEPS)} into {NODE_CACHE} (first run only)")
    result = subprocess.run(
        ["npm", "install", "--silent", "--no-fund", "--no-audit", *NODE_DEPS],
        cwd=NODE_CACHE,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        print(f"[check_mermaid] npm install failed: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def parse_all(diagrams: list[Diagram]) -> dict[str, str]:
    """Return {where: error} for diagrams Mermaid refuses to parse."""
    if not diagrams:
        return {}
    script = NODE_CACHE / "check_mermaid.mjs"
    script.write_text(PARSER_JS, encoding="utf-8")
    payload = json.dumps([{"where": d.where, "source": d.source} for d in diagrams])

    result = subprocess.run(
        ["node", str(script)],
        cwd=NODE_CACHE,
        input=payload,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"node exited {result.returncode}")

    return {
        row["where"]: row.get("error", "parse failed")
        for row in json.loads(result.stdout)
        if not row["ok"]
    }


# ── Entry point ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Mermaid diagrams in the docs.")
    parser.add_argument("--json", action="store_true", help="print one JSON object instead of text")
    parser.add_argument(
        "--lint-only",
        action="store_true",
        help="skip the Node parser; run only the pure-Python render checks",
    )
    args = parser.parse_args()

    diagrams: list[Diagram] = []
    for path in _iter_markdown_files():
        diagrams.extend(extract_diagrams(path))

    for diagram in diagrams:
        diagram.problems.extend(lint(diagram))

    if not args.lint_only:
        if not _node_available():
            message = (
                "node and npm are required for the parse stage. Install Node.js, or pass "
                "--lint-only to run just the render checks."
            )
            if args.json:
                print(json.dumps({"ok": False, "error": message, "checked": len(diagrams)}))
            else:
                print(f"[check_mermaid] {message}", file=sys.stderr)
            return 2
        if not _ensure_node_deps():
            return 2
        try:
            for where, error in parse_all(diagrams).items():
                for diagram in diagrams:
                    if diagram.where == where:
                        diagram.problems.append(f"does not parse: {error}")
        except Exception as e:
            if args.json:
                print(json.dumps({"ok": False, "error": str(e), "checked": len(diagrams)}))
            else:
                print(f"[check_mermaid] parse stage failed: {e}", file=sys.stderr)
            return 2

    broken = [d for d in diagrams if d.problems]

    if args.json:
        print(json.dumps({
            "ok": not broken,
            "checked": len(diagrams),
            "parsed": not args.lint_only,
            "failures": [{"where": d.where, "problems": d.problems} for d in broken],
        }, indent=2))
    else:
        mode = "lint only" if args.lint_only else "lint + parse"
        print(f"[check_mermaid] {len(diagrams)} diagram(s) checked ({mode}), {len(broken)} broken")
        for diagram in broken:
            print(f"\n  {diagram.where}")
            for problem in diagram.problems:
                print(f"    {problem}")

    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
