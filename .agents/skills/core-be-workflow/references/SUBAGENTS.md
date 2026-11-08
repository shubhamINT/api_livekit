# Subagents

A subagent is a second agent with a fresh context, a narrow brief, and its own
tools. Used well, it gives you three things you cannot get alone:

- **Parallelism** — several independent searches or hypothesis checks at once.
- **Independence** — a reviewer or test writer that has not seen your
  reasoning, so it does not share your blind spots.
- **Clean context** — large file reads stay in the subagent; you get the
  conclusion with `file:line` evidence.

Used badly, it costs tokens and returns confident nonsense. The rules below keep
it on the useful side.

## When to delegate

| Delegate | Do it yourself |
|----------|----------------|
| Sweeping many files to locate or map code (audit fan-out, "where is X used") | A single file you already know |
| Checking 2+ independent debugging hypotheses | One obvious hypothesis |
| Writing black-box tests from acceptance criteria | A one-line test next to a one-line fix |
| Reviewing your own diff before calling it done | Trivial tasks (no workflow) |
| Designing alternative interfaces (`DESIGN-IT-TWICE.md`) | Anything that needs the conversation with the user |

Never delegate: talking to the user, approving a plan, deciding scope, or
editing files another agent is editing.

## Roles

Three roles cover backend work. No dedicated agent type ships for them —
spawn a general-purpose subagent and paste the matching role section below
into its brief, on any host.

### investigator — read-only

Locates code, traces a data flow, or tests one hypothesis. Reads and runs
read-only commands (`rg`, `git log`, `git blame`, the test suite, a repro
script). Edits nothing. Returns: the answer, `file:line` evidence for every
claim, and what it could not confirm.

Use for: audit fan-out (one investigator per group of files), debugging
hypotheses (one per hypothesis), mapping the neighbourhood of a feature.

### test-writer — edits test files only

Writes tests from the **contract** (acceptance criteria, API schema, the
service contract list in `core-be-write-tests`) before reading the
implementation body. Knowing only the contract is the point: tests written
from the implementation tend to assert what the code does, not what it should
do. It may read signatures, existing test helpers, and fixtures. It edits only
paths under the test tree. Returns: tests added, which criterion each covers,
and the run result (red is expected before the implementation exists).

Use for: tests-first on a feature, characterization tests before a refactor,
the regression test for a bug.

### reviewer — read-only, fresh eyes

Reviews a finished diff against `tasks.md`, `scope.md`, and
`core-be-coding-standards` (including the AI-generated-code self-review),
plus the `core-be-audit-security` items for the trust boundaries touched.
It also asks of each new test: *what plausible bug would make this fail?* — a
test with no answer is test theater. Edits nothing. Returns findings as
`file:line — problem — fix`, and scope creep (changes not in the plan).

Use for: Phase 6b of every feature, the end of every refactor, the fix of every
non-trivial bug.

## Writing the brief

The subagent knows nothing you have not written down. Every brief contains:

1. **Role** and what it may touch (read-only, or the exact paths it may edit).
2. **Task slug** and paths to `scope.md` / `tasks.md` / `research/<slug>.md`.
3. **The question** or deliverable, specific enough to finish:
   "Does `list_orders` filter by `owner_id` on every code path? Evidence per path."
4. **Files or directories** in scope.
5. **Output shape**: what to return, and whether to append to
   `research/<slug>.md` (give it a heading to write under).

Parallel agents that edit files must own disjoint paths; give each one the
board loop from `PARALLEL-AGENTS.md` in its brief. When in doubt, only
one agent edits at a time.

## Output — compressed, technical only

<output>
Subagent output costs the caller's context window, not just its own. Every
role returns findings as `file:line — claim — evidence`, one line each. No
narrative, no restating the brief, no hedging, no "I also checked...". Full
sentences only where a claim is genuinely ambiguous without one. Names, paths,
commands, and error text stay exact; everything else is cut.
</output>

## Trust, but verify

A subagent's report is a lead, not a fact. Before acting on a claim, open the
cited `file:line` and confirm it. Before reporting a reviewer finding to the
user, check it is real. Record what was delegated and what came back in
`progress.md`.

## Hosts without subagents

Play the role yourself, in sequence, and protect the independence that made the
role useful: write tests from the acceptance criteria *before* reopening the
implementation; review the diff as a separate pass, reading `tasks.md` first and
the diff second, as if someone else wrote it.
