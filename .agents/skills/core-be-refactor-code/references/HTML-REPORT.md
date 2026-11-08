# HTML Report Format

The architectural review is rendered as a single HTML file at `agent-tracking/reports/<slug>.html` (or as Markdown with Mermaid code blocks if the user chose MD). Never write it to the OS temp directory. Build it on the standard template `core-be-workflow/templates/report.html`: white page, report header on top, plain numbered sections. The look, legend, script policy, and diagram snippets are in `core-be-workflow/references/VISUAL-REPORT.md`. This file adds only what is specific to an architecture review. The report loads Mermaid from a CDN, so it must contain no secrets or security findings.

## Layout

Keep the template's header, Summary, and Scope and method sections. Replace sections 3–5 with one section of candidate cards, then a Top recommendation section. Keep Out-of-scope observations and next tasks last.

## Header

The template header: repo name in the title, date, trace links, and the one-line legend. The headline names how many candidates were found and which one is recommended. No introduction paragraph.

## Candidate card

The diagrams carry the weight. Prose is sparse, plain, and uses the glossary terms (from the module-design vocabulary (`core-be-coding-standards/references/module-design.md`)) without ceremony.

Each candidate is one `<article class="card">`:

- **Title**: short, names the deepening (e.g. "Collapse the Order intake pipeline").
- **Meta line** (`<p class="meta">`): recommendation strength as bold text (`Strong` in `.pass` green, `Worth exploring` in `.sev.med` amber, `Speculative` in grey), then the dependency category (`in-process`, `local-substitutable`, `ports & adapters`, `mock`) as plain text.
- **Files**: `<code>` list.
- **Before / After diagram**: the centrepiece. The template's `.ct` Current → Target panels. See patterns below.
- **Problem**: one sentence. What hurts.
- **Solution**: one sentence. What changes.
- **Wins**: bullets, ≤6 words each. e.g. "Tests hit one interface", "Pricing logic stops leaking", "Delete 4 shallow wrappers".
- **ADR note** (if applicable): one line in the template's `.adr` element.

Problem, Solution, and Wins go in one `<dl>`, as in the template.

No paragraphs of explanation. If the diagram needs a paragraph to be understood, redraw the diagram.

## Diagram patterns

Pick the simplest pattern that shows the candidate's problem. Snippets for each are in `core-be-workflow/references/VISUAL-REPORT.md`.

### Mermaid graph (the workhorse for dependencies / call flow)

Use a Mermaid `flowchart` when the point is "X calls Y calls Z, and look at the mess." Put it inside a template `.panel`. Colour with the legend `classDef`s (`bad`, `add`, `chg`, `del`, `deep`). Sequence diagrams work well for "before: 6 round-trips; after: 1."

```html
<figure class="panel"><figcaption>Current</figcaption>
  <pre class="mermaid">
flowchart LR
  A[OrderHandler] --> B[OrderValidator] --> C[OrderRepo]
  C -. leak .-> D[PricingClient]
  classDef bad fill:#fef2f2,stroke:#dc2626,color:#991b1b
  class C,D bad
  </pre>
</figure>
```

### Hand-built boxes-and-arrows (when Mermaid's layout fights you)

Modules as template `.box` elements in a `.row`, joined by `→`. Reach for this when the "after" diagram is one thick-bordered deep module (`.box.deep`) with its internal parts listed inside, since Mermaid won't render that with the right weight.

### Cross-section (good for layered shallowness)

A vertical list of `.box` items, one per layer a call passes through. Before: 6 thin layers each doing nothing. After: 1 thick band labelled with the consolidated responsibility.

### Mass diagram (good for "interface as wide as implementation")

A small table per side: module, public functions (interface), lines of implementation. Before: the numbers are close (shallow). After: few public functions, many lines behind them (deep).

### Call-graph collapse

Before: a tree of function calls rendered as nested boxes. After: the same tree collapsed into one `.box.deep`, with the now-internal calls listed inside it.

## Style guidance

- Follow the "Standard look" in `core-be-workflow/references/VISUAL-REPORT.md`: white page, colour only for the legend states and recommendation strength.
- Keep diagrams short enough that before/after sits side by side without scrolling.
- The only script is the template's Mermaid loader. The report is otherwise static: no app code, no interactivity beyond Mermaid's own rendering.

## Top recommendation section

One card with a 3px accent left border. Candidate name, one sentence on why, anchor link to its card. That's it.

## Tone

Plain English, concise, but the architectural nouns and verbs come straight from the module-design vocabulary (`core-be-coding-standards/references/module-design.md`). Concision is not an excuse to drift.

<hard-rules>
**Use exactly:** module, interface, implementation, depth, deep, shallow, seam, adapter, leverage, locality.

**Never substitute:** component, service, unit (for module) · API, signature (for interface) · boundary (for seam) · layer, wrapper (for module, when you mean module).
</hard-rules>

**Phrasings that fit the style:**

- "Order intake module is shallow: interface nearly matches the implementation."
- "Pricing leaks across the seam."
- "Deepen: one interface, one place to test."
- "Two adapters justify the seam: HTTP in prod, in-memory in tests."

**Wins bullets** name the gain in glossary terms: *"locality: bugs concentrate in one module"*, *"leverage: one interface, N call sites"*, *"interface shrinks; implementation absorbs the wrappers"*. Don't write *"easier to maintain"* or *"cleaner code"*, because those terms aren't in the glossary and don't earn their place.

No hedging, no throat-clearing, no "it's worth noting that…". If a sentence could be a bullet, make it a bullet. If a bullet could be cut, cut it. If a term isn't in the module-design glossary, reach for one that is before inventing a new one.