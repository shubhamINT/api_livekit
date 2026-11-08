# Visual Report Guide

Every report shows **what exists now** and **what changes**, as pictures first
and prose second. A reviewer should understand the proposal from the diagrams
alone; the text only names things and records evidence.

Save every report to `agent-tracking/reports/<slug>.html` (or `.md`), the
same `<slug>` as the task's `agent-tracking/plans/<slug>/` folder. Never save
it to the OS temp directory or the repo root. Link it from the task's row in
`agent-tracking/INDEX.md`.

Every report, architecture review included, starts from
`templates/report.html` (or `templates/report.md`). It holds the header, the
legend, summary numbers, and two worked Current → Target examples (a Mermaid
flowchart and a tree diff). Other patterns below are snippets to add when they
fit. Do not add CSS frameworks (no Tailwind, no Bootstrap) or new colours.

## Standard look

Plain and readable beats decorated. The reader should see content, not design.

- White page, dark grey text, one sans-serif font, one monospace font.
- Report header on top: title, one meta line (type · date · slug), trace links,
  the legend, and a one- or two-sentence headline result.
- Numbered plain section headings with a thin accent rule. No badges, icons,
  gradients, shadows, tinted cards, or dark mode.
- Colour only where it carries meaning: severity, the legend states (problem,
  added, changed, removed), and pass/fail. Everything else is grey or black.
- Cards and panels: 1px light grey border, white inside.
- Numbers in tables right-aligned. A thin bar beside a number is fine; a chart
  is not needed when a table says it.

Two hard rules when filling the template:

- Never put a `{{placeholder}}` inside a `style=""` attribute or a Mermaid
  block. Linters read `{{0}}` as an empty CSS ruleset, and Mermaid fails to
  parse braces. Write real numbers and names there.
- Keep the template's Mermaid loader. It renders diagrams one by one with fixed
  ids; `startOnLoad: true` can give two diagrams the same id and draw one in
  the wrong panel.

## Script policy by report type

| Report type | Mermaid CDN | Why |
|-------------|-------------|-----|
| refactor, architecture review | allowed | Diagrams are the point; report holds code shape, not secrets |
| feature | allowed | Same |
| structure | allowed | Same |
| test | allowed | Same |
| core-be-audit-code, core-be-audit-security | **forbidden** | Findings are sensitive, opened offline, attached to tickets. Inline CSS, plain boxes and tables only |

A report that loads Mermaid must contain **no secrets, credentials, internal
hostnames, or security findings**. If a refactor or feature task turns up a
security hole, it goes in chat and in a separate audit report, not here.

For audit and security reports, delete the `<script type="module">` block from
the template before filling it. `grep -n '<script' agent-tracking/reports/<slug>.html` must
return nothing.

## Legend (same meaning in every report)

| Mark | Meaning |
|------|---------|
| Solid box | module |
| Thick box | deep module (small interface, large implementation) |
| Dashed line | seam |
| Red | problem: leak, violation, failing check, finding |
| Green | added |
| Amber | changed or moved |
| Grey, struck through | removed |

The legend is one line in the header (`.legend` in the template). Mermaid diagrams
use the same colours through `classDef` (see below).

## The centrepiece: Current → Target panel

An `h3` naming the change, then two bordered panels side by side labelled
"Current" and "Target" in small grey caps. Stacks to one column under 720px.
Below the panels, one card with Problem, Change, and Wins as a definition
list, plus an optional one-line ADR note.

```html
<h3>Collapse the order intake pipeline</h3>
<div class="ct">
  <figure class="panel"><figcaption>Current</figcaption><!-- diagram --></figure>
  <figure class="panel"><figcaption>Target</figcaption><!-- diagram --></figure>
</div>
<div class="card">
  <dl>
    <dt>Problem</dt><dd>one sentence</dd>
    <dt>Change</dt><dd>one sentence</dd>
    <dt>Wins</dt><dd>locality: SQL in one module · tests hit one interface</dd>
  </dl>
  <div class="adr">ADR: one line</div>
</div>
```

Every non-audit report has at least one Current → Target panel. Audit reports
show the current state only (they change nothing), so they use the severity bar
and per-finding cards instead.

## Diagram patterns

Pick the simplest pattern that makes the point. One clear diagram per change
is enough; add a second only when it shows something the first cannot.

### Mermaid flowchart (dependencies, call flow)

Use it when the point is "X calls Y calls Z, and look at the mess". Colour with
the legend classes:

```html
<pre class="mermaid">
flowchart LR
  H[OrderHandler] --> V[OrderValidator] --> R[OrderRepo]
  R -. leak .-> P[PricingClient]
  classDef bad fill:#fef2f2,stroke:#dc2626,color:#991b1b
  classDef add fill:#ecfdf5,stroke:#059669,color:#065f46
  classDef chg fill:#fffbeb,stroke:#d97706,color:#92400e
  classDef del fill:#fff,stroke:#6b7280,color:#6b7280,stroke-dasharray:4 4
  classDef deep fill:#fff,stroke:#1f2937,stroke-width:3px
  class R,P bad
</pre>
```

### Mermaid sequence diagram (round trips, request flow)

Good for "before: 6 round trips; after: 1" and for showing a new feature's
request path end to end. Use `rect rgb(236,253,245)` blocks to tint the added
steps green.

### Hand-built boxes (when Mermaid's layout fights you)

Modules as `<span class="box">` in a `.row`, joined by plain `→`. Modifiers:
`.add`, `.chg`, `.bad`, `.del`. `.box.deep` is the thick-bordered deep module;
put its interface on the first line and the internal parts as plain `.box`
items inside it. Use this for the "after" of a deepening, and in audit reports,
which cannot load Mermaid.

```html
<div class="row"><span class="box">PriceCalc</span> → <span class="box bad">DiscountUtil</span> → <span class="box del">PricingFacade</span></div>
<div class="box deep"><code>price(order) → Money</code>
  <div class="row"><span class="box">tax</span><span class="box">discount</span><span class="box">rounding</span></div></div>
```

### Cross-section (layered shallowness)

A vertical list of `.box` items, one per layer a call passes through.
Current: six boxes each doing nothing. Target: one `.box.deep` named after the
consolidated responsibility.

### Mass diagram (interface as wide as implementation)

A small table per side: module, public functions (interface), lines of
implementation. Current: the two numbers are close (shallow). Target: few
public functions, many lines behind them (deep).

### Call-graph collapse

Current: nested `.box` tree of function calls. Target: the same tree folded
into one `.box.deep`, the now-internal calls shown faded inside it.

### Tree diff (folder structure)

A `<pre class="tree">` per side. Wrap paths in `<span class="add">`,
`<span class="chg">`, `<span class="del">`, or `<span class="bad">`, and the
reason in `<span class="why">`.

```html
<pre class="tree">src/
├── <span class="del">routes.py</span>   <span class="why"># 900 lines, SQL in handlers</span>
└── <span class="add">orders/</span>
    ├── <span class="add">router.py</span>
    ├── <span class="add">service.py</span>
    └── <span class="add">repository.py</span></pre>
```

### Metrics table (before / after numbers)

A table with Metric, Before, After, and Δ columns. Numbers right-aligned
(`td.num`). Δ is `.better` (green) or `.worse` (red). An optional thin `.bar`
under the After value, width = After / larger value as a real percentage.

```html
<tr><td>Functions over complexity 10</td><td class="num">14</td>
  <td class="num">3<span class="bar" style="width:21%"></span></td><td class="num better">−11</td></tr>
```

### Severity bar (audit and security)

One horizontal stacked bar (`.sevbar`) with a segment per severity, width
proportional to count. Sits under the severity tiles.

### Source → sink sketch (security findings)

A `.row` of three to five `.box` elements: where untrusted input enters, what
it passes through, where it lands. Name the missing control in red text
(`.fail`) on the arrow and mark the sink `.box.bad`. No Mermaid.

## What each report type shows

| Type | Required visuals | Optional |
|------|------------------|----------|
| refactor | Current → Target module or call graph; metrics table (tests, coverage, complexity, lint/type errors, lines +/−) | cross-section, mass table, call-graph collapse |
| architecture review | per candidate: Current → Target diagram (see `core-be-refactor-code/references/HTML-REPORT.md`) | any pattern |
| feature | Current → Target component graph with added parts green; sequence diagram of the new request path | metrics table for coverage |
| structure | Current → Target tree diff; dependency-direction graph with rule violations red | table "where does X go" |
| test | metrics table for coverage and test count before/after; list of behaviours now pinned | — |
| core-be-audit-code | severity tiles + severity bar; per-finding cards; structure conformance as a tree with violations red | metrics table for current lint/type/complexity |
| core-be-audit-security | severity tiles + severity bar; per-finding cards; source → sink sketch for High and Critical | — |

## Markdown fallback

Same sections, same order. Mermaid goes in fenced ` ```mermaid ` blocks, which
GitHub, GitLab, and most IDE previews render. Put Current and Target as two
consecutive blocks under `### Current` and `### Target`. Metrics are the same
Before / After / Δ table. Tree diffs become two fenced text
blocks with `+`, `~`, `-` prefixes. Audit and security Markdown reports may use
Mermaid, because Markdown renders locally with no network fetch.

## Style

- Follow "Standard look" above. When in doubt, remove decoration, never content.
- Diagrams carry the weight. Problem and change are one sentence each. If a
  diagram needs a paragraph to be understood, redraw the diagram.
- Use the module-design vocabulary (`core-be-coding-standards/references/module-design.md`):
  module, interface, implementation, depth, seam, adapter, leverage, locality.
- The page must work at 375px width with no horizontal page scroll; wide
  diagrams and tables scroll inside their own container.
