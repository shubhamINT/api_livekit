# <Report title> — <slug>

- **Type:** feature | change | refactor | audit | security | test
- **Date:** YYYY-MM-DD
- **Status:** done
- **Trace:** [scope](../plans/<slug>/scope.md) · [research](../research/<slug>.md) · [plan](../plans/<slug>/tasks.md) · [progress](../plans/<slug>/progress.md)

## 1. Summary

<what was asked, what was done, headline result in 3–5 lines>

<!-- audit / security only: keep this table; delete it for every other type -->
| Critical | High | Medium | Low | Info |
|----------|------|--------|-----|------|
| 0 | 0 | 0 | 0 | 0 |

## 2. Scope

- **In:** 
- **Out:** 
- **Depth:** 
- **Constraints:** 

## 3. Method

- Tools: 
- Checklists / standards: 

## 4. Current → Target

<!-- refactor / feature / structure / test: required. audit / security: delete this section. -->
<!-- Patterns and colours: ../references/VISUAL-REPORT.md -->

### Current

```mermaid
flowchart LR
  H[OrderRouter] --> S[OrderService]
  H -. leak .-> DB[(raw SQL in route)]
  classDef leak stroke:#dc2626,stroke-width:2px,color:#dc2626
  class DB leak
```

### Target

```mermaid
flowchart LR
  H[OrderRouter] --> S[OrderService] --> R[OrderRepository]
  classDef added fill:#d1fae5,stroke:#059669,color:#064e3b
  class R added
```

**Problem:** <one sentence>
**Change:** <one sentence>

<!-- structure: replace the diagrams with two tree blocks, prefix lines + added, ~ moved, - removed -->

| Metric | Before | After | Δ |
|--------|--------|-------|---|
|        |        |       |   |

## 5. Findings

<!-- audit / security -->
| ID | Severity | Category | Standard | Location | Evidence | Impact | Recommendation | Status |
|----|----------|----------|----------|----------|----------|--------|----------------|--------|

<!-- refactor: replace the table above with -->
<!-- | Change | Named refactoring | Files | Reason | -->
<!-- feature: replace with what was built, interface, tests added -->

<!-- audit / security only: delete everything from here to the next ## heading otherwise -->
### Finding details

#### <ID> — <title>

- **Severity:** 
- **Standard:** OWASP A0x:2025 · CWE-nnn · ASVS Vn.n.n
- **Location:** `path/to/file.py:42`
- **Evidence:** 

```text
<minimal code excerpt>
```

- **Impact:** 
- **Recommendation:** 

## 5b. Spec vs code (part of Findings or Changes)

<!-- feature / change only: converge table (core-be-converge). Else delete. -->
| AC | Test | Code | Status |
|----|------|------|--------|
|    |      |      | met / partial / missing |

## 6. Verification

| Check | Before | After |
|-------|--------|-------|

## 7. Docs updated

<!-- omit for audit / security -->
| File | Section | Change |
|------|---------|--------|
| README.md | | |
| AGENTS.md | | |

## 8. Out-of-scope observations and next tasks

- 
