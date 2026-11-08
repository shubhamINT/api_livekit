# Code Smells → Named Refactorings

Source: Martin Fowler, *Refactoring* (2nd ed., 2018), chapter 3 smells and the
[online catalog](https://refactoring.com/catalog/). Cite smells and refactorings
**by these exact names** in findings and plans, so any reader can look them up.

A smell is a hint, not a verdict. Before recommending a refactoring, confirm the
smell actually slows change or hides bugs in this code.

## Smell table

| Smell | How it shows up in a backend service | Refactorings to reach for |
|-------|--------------------------------------|---------------------------|
| **Mysterious Name** | `process()`, `data`, `handle2` | Change Function Declaration, Rename Variable, Rename Field |
| **Duplicated Code** | Same validation / query / mapping in several routes | Extract Function, Slide Statements, Pull Up Method |
| **Long Function** | Route handler doing parse + auth + query + mapping + response | Extract Function, Replace Temp with Query, Decompose Conditional, Split Phase |
| **Long Parameter List** | `create_order(a, b, c, d, e, f)` | Introduce Parameter Object, Preserve Whole Object, Remove Flag Argument |
| **Global Data** | Module-level mutable dicts, singletons mutated at runtime | Encapsulate Variable |
| **Mutable Data** | Shared objects mutated by several functions | Encapsulate Variable, Split Variable, Separate Query from Modifier, Change Reference to Value |
| **Divergent Change** | One module edited for unrelated reasons (DB schema *and* pricing rules) | Split Phase, Move Function, Extract Class |
| **Shotgun Surgery** | One change needs edits in many files | Move Function, Move Field, Combine Functions into Class, Inline Class |
| **Feature Envy** | A function mostly reads another module's data | Move Function, Extract Function |
| **Data Clumps** | `(host, port, user, password)` travel together everywhere | Extract Class, Introduce Parameter Object |
| **Primitive Obsession** | Money as `float`, ids and emails as bare `str` | Replace Primitive with Object, Replace Type Code with Subclasses |
| **Repeated Switches** | Same `if kind == …` ladder in several places | Replace Conditional with Polymorphism (or a dispatch dict) |
| **Loops** | Manual accumulate/filter loops | Replace Loop with Pipeline (comprehension / `map`/`filter`) |
| **Lazy Element** | A class or function that adds nothing | Inline Function, Inline Class, Collapse Hierarchy |
| **Speculative Generality** | Hooks, params, base classes "for later" | Collapse Hierarchy, Inline Function, Inline Class, Change Function Declaration, Remove Dead Code |
| **Temporary Field** | Attribute set only in some code paths | Extract Class, Move Function, Introduce Special Case |
| **Message Chains** | `order.customer().account().plan().limit` | Hide Delegate, Extract Function, Move Function |
| **Middle Man** | Class whose methods only forward | Remove Middle Man, Inline Function |
| **Insider Trading** | Modules reaching into each other's internals | Move Function, Move Field, Hide Delegate |
| **Large Class** | `UserService` with 40 methods | Extract Class, Extract Superclass, Replace Type Code with Subclasses |
| **Alternative Classes with Different Interfaces** | Two clients for the same thing with different method names | Change Function Declaration, Move Function, Extract Superclass |
| **Data Class** | Class with fields only, logic elsewhere | Encapsulate Record, Move Function (only if behaviour really belongs there — DTOs are fine) |
| **Refused Bequest** | Subclass ignores most of the parent | Push Down Method, Replace Subclass with Delegate, Replace Superclass with Delegate |
| **Comments** | Comment explaining what a block does | Extract Function, Change Function Declaration, Introduce Assertion |

Backend additions (not in Fowler's list, common in services):

| Smell | Fix |
|-------|-----|
| **Layer leak** — SQL/HTTP calls inside route handlers | Move Function into `services/` or `core/db/`; route delegates |
| **Config sprawl** — `os.getenv` / `process.env` everywhere | Move to the single settings module (Encapsulate Variable) |
| **Envelope drift** — routes build their own error bodies | Central exception handler; delete per-route bodies |
| **Swallowed errors** — `except: pass`, `catch {}` | Narrow the catch; handle or re-raise with context |
| **Dead code** — unreachable branches, unused exports | Remove Dead Code |

## Most-used refactorings (quick definitions)

| Refactoring | One line |
|-------------|----------|
| Extract Function | Move a fragment into a named function |
| Inline Function | Replace a call with the body when the name adds nothing |
| Extract Variable | Name a sub-expression |
| Inline Variable | Remove a variable that only restates its expression |
| Change Function Declaration | Rename a function / add or remove parameters |
| Rename Variable | Give a variable an intention-revealing name |
| Encapsulate Variable | Route access to shared data through functions |
| Introduce Parameter Object | Group parameters that travel together |
| Combine Functions into Class | Group functions that operate on the same data |
| Split Phase | Separate code that does two sequential things (parse, then compute) |
| Extract Class / Inline Class | Split a class doing two jobs / merge one doing none |
| Hide Delegate / Remove Middle Man | Add or remove a forwarding layer |
| Move Function / Move Field | Put behaviour and data where they are used |
| Slide Statements | Move related lines together |
| Split Loop | One loop, one job |
| Replace Loop with Pipeline | Loop becomes comprehension / collection pipeline |
| Remove Dead Code | Delete what nothing calls |
| Decompose Conditional | Extract condition and branches into named functions |
| Consolidate Conditional Expression | Merge checks with the same result |
| Replace Nested Conditional with Guard Clauses | Return early for special cases |
| Replace Conditional with Polymorphism | Type-specific classes replace a switch |
| Introduce Special Case | Null object / special-case object replaces repeated checks |
| Separate Query from Modifier | A function either returns data or changes state, not both |
| Parameterize Function | Merge near-identical functions via a parameter |
| Remove Flag Argument | Replace a boolean switch parameter with explicit functions |
| Preserve Whole Object | Pass the object, not several of its fields |
| Replace Primitive with Object | Wrap a primitive that has behaviour (Money, Email) |
| Replace Temp with Query | Replace a temp variable with a function call |
| Replace Magic Literal | Name a meaningful constant |
| Introduce Assertion | State an assumption explicitly (in Python: a check that raises, not `assert`, outside tests) |
