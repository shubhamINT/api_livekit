# JavaScript Style — Essentials

TypeScript services follow `typescript-style.md`; for `.ts`
files the TypeScript guide supersedes this one. This file applies to plain
`.js`, `.mjs` and `.cjs` files: config files (`eslint.config.js`, scripts) and
legacy JS services. Full text: `google/jsguide.md`. Each row has one status:
`tool` means Prettier or ESLint enforces it (the named rules are in the
Prettier and ESLint config in this pack's `tooling.md`);
`rule` means follow it by hand, as written; `override` means this standard
deliberately differs; `n/a` means Google-internal or Closure-only.

## Deviations from Google

- ES modules (`import` / `export`) replace `goog.module`, `goog.provide`,
  `goog.require` and all Closure interop. Legacy CommonJS services keep
  `require` in existing files; new files are ESM.
- Prettier decides layout (`singleQuote: true` matches Google quotes). Where
  Prettier differs from the guide (`{ a }` bracket spacing, +2 continuation
  indent, wrapping of long imports), Prettier wins.
- No Closure Compiler. Closure type syntax (`!Foo`, `?Foo`, `function(): T`),
  `@enum` / `@record` / `@interface` / `@template` checking and visibility tags
  are not required; types belong in TypeScript. JSDoc stays for documentation.
- Named exports only. Exception: config files whose tool requires a default
  export (`eslint.config.js`, `vitest.config.js`).
- Class privacy uses `#private` or module-local scope, not `@private` or
  trailing underscores.
- New files: follow the repo's existing licence-header convention if it has one.
- Enforcement: Prettier, ESLint 9 and `tsc` replace Closure Compiler,
  clang-format and the Closure linter (see `tooling.md`).

## Complete index of the Google JavaScript Style Guide

| § | Section | Status | Rule |
|---|---------|--------|---------------|
| 1 | Introduction | rule | See subsections. The guide defines style for JavaScript files. |
| 1.1 | Terminology notes | rule | Read *must* / *should* / *may* as RFC 2119; *prefer* means should, *avoid* means should not. |
| 1.2 | Guide notes | rule | Examples are non-normative; do not enforce optional formatting choices seen in examples. |
| 2 | Source file basics | rule | See subsections. |
| 2.1 | File name | override | Lowercase `kebab-case` (or the repo's existing convention); extension `.js`, `.mjs` or `.cjs`. |
| 2.2 | File encoding: UTF-8 | rule | Save every source file as UTF-8. |
| 2.3 | Special characters | rule | See subsections. |
| 2.3.1 | Whitespace characters | tool | Prettier indents with spaces, never tabs; `no-irregular-whitespace` flags other whitespace. Escape non-space whitespace inside strings. |
| 2.3.2 | Special escape sequences | rule | Use `\n`, `\t`, `\'` etc. rather than numeric escapes; never legacy octal escapes (`no-octal-escape`). |
| 2.3.3 | Non-ASCII characters | rule | Use the actual character or a `\u` escape, whichever reads better; comment non-printable escapes. |
| 3 | Source file structure | override | Order: licence header, optional `@fileoverview`, `import` statements, implementation. One blank line between sections. |
| 3.1 | License or copyright information, if present | rule | If the repo uses a licence header, it goes first in every new file. |
| 3.2 | @fileoverview JSDoc, if present | rule | Optional `@fileoverview` JSDoc goes directly after the licence header; format per §7.5. |
| 3.3 | goog.module statement | override | Not used. Every file is an ES module; the file path is its identity. |
| 3.3.1 | Hierarchy | override | No `goog.module` namespaces; directory structure follows the recorded project structure. |
| 3.3.2 | goog.module.declareLegacyNamespace | override | Not used; no Closure namespaces exist. |
| 3.3.3 | goog.module Exports | override | Use ESM `export` on declarations or `export { name }`; no `exports` object, no default export. |
| 3.4 | ES modules | rule | See subsections. All new files use `import` / `export`. |
| 3.4.1 | Imports | override | See subsections. Prettier may wrap long imports; the guide forbids wrapping them. |
| 3.4.1.1 | Import paths | rule | Import ES modules with `import`, never `goog.require`. |
| 3.4.1.1.1 | File extensions in import paths | rule | Always include the `.js` extension in relative import paths; Node ESM requires it. |
| 3.4.1.2 | Importing the same file multiple times | rule | Import each file once per module (ESLint `no-duplicate-imports` can check). |
| 3.4.1.3 | Naming imports | rule | See subsections. |
| 3.4.1.3.1 | Naming module imports | rule | `import * as name` uses a `lowerCamelCase` name derived from the file name (`fileOne` for `file-one.js`). |
| 3.4.1.3.2 | Naming default imports | rule | Default imports only for non-conforming modules; name them from the file name per §6.2 rules. |
| 3.4.1.3.3 | Naming named imports | rule | Keep imported names; avoid aliasing. If needed, alias with parts of the source file name (`BigCat`). |
| 3.4.2 | Exports | rule | See subsections. Export only what other modules use; module-locals are not marked `@private`. |
| 3.4.2.1 | Named vs default exports | rule | Use named exports only; never `export default` (`no-restricted-exports`). Config-file exception in deviations. |
| 3.4.2.2 | Mutability of exports | rule | Never mutate exported bindings after module initialization; export a getter or a constant object instead. |
| 3.4.2.3 | export from | override | Prettier may wrap long `export … from` lines; accept its output. |
| 3.4.3 | Circular Dependencies in ES modules | rule | Do not create import or `export from` cycles between modules. |
| 3.4.4 | Interoperating with Closure | n/a | Closure `goog.js`, `goog.require` and `goog.declareModuleId` are not used. |
| 3.4.4.1 | Referencing goog | n/a | Closure `goog.js` is not used. |
| 3.4.4.2 | goog.require in ES modules | n/a | No Closure namespaces to require; use `import`. |
| 3.4.4.3 | Declaring Closure Module IDs in ES modules | n/a | `goog.declareModuleId` is Closure-only. |
| 3.5 | goog.setTestOnly | n/a | Closure-only; test files are separated by vitest file naming instead. |
| 3.6 | goog.require and goog.requireType statements | override | Use ESM `import` statements; destructure named imports, keep names matching the export. |
| 3.7 | The file’s implementation | rule | Implementation follows imports after at least one blank line; module-local declarations and exports mixed as needed. |
| 4 | Formatting | tool | Prettier formats every file; see subsections for where it differs. |
| 4.1 | Braces | rule | See subsections. |
| 4.1.1 | Braces are used for all control structures | tool | ESLint `curly`: brace every `if`/`for`/`while` body; guide allows only a one-line `if` without `else` to omit them. |
| 4.1.2 | Nonempty blocks: K&R style | tool | Prettier prints K&R braces. |
| 4.1.3 | Empty blocks: may be concise | tool | Prettier prints `{}`; `no-empty` flags empty `if`/`catch` blocks in multi-block statements. |
| 4.2 | Block indentation: +2 spaces | tool | Prettier, `tabWidth: 2` (default). |
| 4.2.1 | Array literals: optionally block-like | tool | Prettier decides array layout. |
| 4.2.2 | Object literals: optionally block-like | tool | Prettier decides object layout (keeps it expanded if the source breaks after `{`). |
| 4.2.3 | Class literals | tool | Prettier indents classes and omits semicolons after methods; use `extends` for inheritance. |
| 4.2.4 | Function expressions | tool | Prettier indents callback bodies. |
| 4.2.5 | Switch statements | tool | Prettier indents `case` labels and bodies +2. |
| 4.3 | Statements | tool | See subsections. |
| 4.3.1 | One statement per line | tool | Prettier puts each statement on its own line. |
| 4.3.2 | Semicolons are required | tool | Prettier `semi: true` (default) terminates every statement. |
| 4.4 | Column limit: 80 | tool | Prettier `printWidth: 80` (default); long URLs and strings may exceed it. |
| 4.5 | Line-wrapping | tool | Prettier wraps lines; extract a variable when wrapping hurts readability. |
| 4.5.1 | Where to break | tool | Prettier breaks at higher syntactic levels and after operators. |
| 4.5.2 | Indent continuation lines at least +4 spaces | override | Prettier indents continuation lines +2; accept its output. |
| 4.6 | Whitespace | tool | See subsections. |
| 4.6.1 | Vertical whitespace | tool | Prettier collapses repeated blank lines and strips blank lines at block edges; add blank lines only for logical grouping. |
| 4.6.2 | Horizontal whitespace | override | Prettier sets spacing, including `{ a: 1 }` bracket spacing, which the guide writes as `{a: 1}`. No trailing whitespace. |
| 4.6.3 | Horizontal alignment: discouraged | tool | Prettier removes alignment padding. |
| 4.6.4 | Function arguments | override | Prettier puts arguments on one line or one per line, indented +2, not +4. |
| 4.7 | Grouping parentheses: recommended | override | Prettier removes redundant parens and adds some for clarity; extract a named variable when precedence is unclear. |
| 4.8 | Comments | rule | See subsections. |
| 4.8.1 | Block comment style | rule | Indent comments with the code; use `//` or `/* */` with aligned `*`; no boxes; no `/** */` for implementation comments. |
| 4.8.2 | Parameter Name Comments | rule | When a literal argument is unclear, add `/* name= */ value`, or better, refactor to an options object. |
| 5 | Language features | rule | See subsections. Features the guide does not mention may be used. |
| 5.1 | Local variable declarations | rule | See subsections. |
| 5.1.1 | Use const and let | tool | ESLint `no-var` and `prefer-const`: `const` by default, `let` only when reassigned. |
| 5.1.2 | One variable per declaration | tool | ESLint `one-var` set to `never`. |
| 5.1.3 | Declared when needed, initialized as soon as possible | rule | Declare locals near first use, not at block top, and initialize immediately. |
| 5.1.4 | Declare types as needed | override | JSDoc type annotations are optional in plain JS; add `@type` only where it helps the editor. Never mix inline and block JSDoc. |
| 5.2 | Array literals | rule | See subsections. |
| 5.2.1 | Use trailing commas | tool | Prettier `trailingComma: "all"` (Prettier 3 default). |
| 5.2.2 | Do not use the variadic Array constructor | tool | ESLint `no-array-constructor`; use literals. `new Array(length)` stays allowed. |
| 5.2.3 | Non-numeric properties | rule | Never put non-numeric properties on arrays; use a `Map` or object. |
| 5.2.4 | Destructuring | rule | Omit unused elements; optional destructured array parameter defaults to `[]` with defaults on the left; prefer object destructuring. |
| 5.2.5 | Spread operator | rule | Use `[...a, ...b]` instead of `Array.prototype.slice.call` or `concat`; no space after `...`. |
| 5.3 | Object literals | rule | See subsections. |
| 5.3.1 | Use trailing commas | tool | Prettier `trailingComma: "all"`. |
| 5.3.2 | Do not use the Object constructor | tool | ESLint `no-object-constructor`; use `{}`. |
| 5.3.3 | Do not mix quoted and unquoted keys | rule | Structs use unquoted keys, dicts use quoted or computed keys; never mix in one literal (Prettier `quoteProps: "consistent"` helps). |
| 5.3.4 | Computed property names | rule | Computed keys count as dict-style unless they are symbols; do not mix enum keys with other keys. |
| 5.3.5 | Method shorthand | rule | Method shorthand is allowed; remember arrow-function `this` refers to the outer scope. |
| 5.3.6 | Shorthand properties | rule | Shorthand properties (`{foo, bar}`) are allowed. |
| 5.3.7 | Destructuring | rule | Parameter destructuring: one level, unquoted shorthand, defaults on the left, optional objects default to `{}`. |
| 5.3.8 | Enums | override | Use a never-mutated module-level `const` object with `CONSTANT_CASE` keys and literal string/number values; `@enum` optional. |
| 5.4 | Classes | rule | See subsections. |
| 5.4.1 | Constructors | tool | ESLint `constructor-super` and `no-this-before-super`: call `super()` before touching `this`. |
| 5.4.2 | Fields | override | Declare every field in the constructor or as a class field; never add fields later or on the prototype. Use `#private`, not `@private`. |
| 5.4.3 | Computed properties | rule | Computed class members only for symbols; define `[Symbol.iterator]` on iterable classes; use other symbols sparingly. |
| 5.4.4 | Static methods | rule | Prefer module-local functions over private statics; call statics on the defining class only; no `this` in statics. |
| 5.4.5 | Old-style class declarations | override | Always use `class`; `goog.defineClass` and `goog.inherits` are unavailable. |
| 5.4.6 | Do not manipulate prototype s directly | rule | Never touch `prototype` in ordinary code; no mixins; never modify builtin prototypes. |
| 5.4.7 | Getters and Setters | rule | Avoid `get`/`set` properties; use ordinary methods. If unavoidable, getters must not change observable state. |
| 5.4.8 | Overriding toString | rule | An overridden `toString` must always succeed and have no side effects. |
| 5.4.9 | Interfaces | override | Closure `@interface` / `@record` are not used; declare interfaces in TypeScript. |
| 5.4.10 | Abstract Classes | override | Closure `@abstract` is unchecked without the compiler; use TypeScript `abstract` for abstract classes. |
| 5.4.11 | Do not create static container classes | rule | Export individual functions and constants, not a class of statics used as a namespace. |
| 5.4.12 | Do not define nested namespaces | rule | Do not hang classes, enums or typedefs off another name (`Foo.Bar`); make them top-level exports. |
| 5.5 | Functions | rule | See subsections. |
| 5.5.1 | Top-level functions | override | Declare top-level functions locally and export with ESM `export`; no `exports` object. |
| 5.5.2 | Nested functions and closures | rule | Nested functions are fine; name one by assigning it to a local `const`. |
| 5.5.3 | Arrow functions | rule | Prefer arrows for nested functions and callbacks over `bind` or `self = this`; expression bodies only when returning a value (or `void`). |
| 5.5.4 | Generators | tool | Prettier prints `function* name()` and `yield*`. |
| 5.5.5 | Parameter and return types | rule | Document params and returns with JSDoc; see subsections. |
| 5.5.5.1 | Default parameters | rule | Optional params use `=` defaults with spaces, come after required ones, no `opt_` prefix, no side-effecting initializers; prefer destructured options for many. |
| 5.5.5.2 | Rest parameters | tool | ESLint `prefer-rest-params`: use `...rest`, never `arguments`; rest param last, not named `var_args`. |
| 5.5.6 | Generics | override | Closure `@template` is not required in plain JS; express generics in TypeScript. |
| 5.5.7 | Spread operator | tool | ESLint `prefer-spread`: use `fn(...args)` instead of `fn.apply`. |
| 5.6 | String literals | rule | See subsections. |
| 5.6.1 | Use single quotes | tool | Prettier `singleQuote: true`; ordinary string literals never span lines. |
| 5.6.2 | Template literals | rule | Use template literals instead of complex string concatenation; they may span lines. |
| 5.6.3 | No line continuations | tool | ESLint `no-multi-str`: no backslash line continuations; concatenate or use a template literal. |
| 5.7 | Number literals | tool | Prettier lowercases `0x`/`0o`/`0b` prefixes; ESLint `no-octal` bans leading-zero octals. |
| 5.8 | Control structures | rule | See subsections. |
| 5.8.1 | For loops | rule | Prefer `for`-`of` and `Object.keys`; `for`-`in` only on dict objects, never arrays, guarded (`guard-for-in`). |
| 5.8.2 | Exceptions | tool | ESLint `no-throw-literal` and `prefer-promise-reject-errors`: throw `new Error` or subclasses; prefer exceptions over error-return objects. |
| 5.8.2.1 | Empty catch blocks | tool | ESLint `no-empty`: an intentionally empty `catch` needs a comment explaining why. |
| 5.8.3 | Switch statements | tool | See subsections: commented fall-through, `default` case last. |
| 5.8.3.1 | Fall-through: commented | tool | ESLint `no-fallthrough`: end each case with `break`/`return`/`throw`, or mark `// fall through`. |
| 5.8.3.2 | The `default` case is present | tool | ESLint `default-case` and `default-case-last`: every switch has a `default` group, placed last, even if empty. |
| 5.9 | this | rule | Use `this` only in constructors, methods and arrows inside them; never for the global object or event target. |
| 5.10 | Equality Checks | tool | ESLint `eqeqeq`: use `===` / `!==`. |
| 5.10.1 | Exceptions Where Coercion is Desirable | tool | `== null` to catch both `null` and `undefined` is allowed (`eqeqeq` with `{ null: "ignore" }`). |
| 5.11 | Disallowed features | tool | See subsections. |
| 5.11.1 | with | tool | ESLint `no-with`; also a syntax error in ES modules. |
| 5.11.2 | Dynamic code evaluation | tool | ESLint `no-eval`, `no-implied-eval`, `no-new-func`; `eslint-plugin-security` `detect-eval-with-expression`. |
| 5.11.3 | Automatic semicolon insertion | tool | Prettier `semi: true` inserts every semicolon. |
| 5.11.4 | Non-standard features | rule | Use only ECMA-262 / WHATWG features and Node APIs; no proposals or transpiler-only syntax. |
| 5.11.5 | Wrapper objects for primitive types | tool | ESLint `no-new-wrappers`; call `Boolean(x)`, `Number(x)`, `String(x)` for coercion. |
| 5.11.6 | Modifying builtin objects | tool | ESLint `no-extend-native` and `no-global-assign`; add globals only when a third-party API requires it. |
| 5.11.7 | Omitting () when invoking a constructor | tool | Prettier prints `new Foo()`. |
| 6 | Naming | rule | See subsections. |
| 6.1 | Rules common to all identifiers | rule | ASCII letters and digits; descriptive names; no ambiguous abbreviations or Hungarian notation; short names only in scopes of 10 lines or fewer. |
| 6.2 | Rules by identifier type | rule | See subsections. |
| 6.2.1 | Package names | n/a | Closure dotted namespaces do not exist; npm package names follow npm rules. |
| 6.2.2 | Class names | rule | Classes and typedefs in `UpperCamelCase`, usually nouns; unexported classes are just locals. |
| 6.2.3 | Method names | override | `lowerCamelCase` verb phrases; `getFoo`/`isFoo`/`setFoo` for accessors; privacy via `#private`, not trailing underscore. |
| 6.2.4 | Enum names | rule | Enum object in `UpperCamelCase`, singular noun; members in `CONSTANT_CASE`. |
| 6.2.5 | Constant names | rule | `CONSTANT_CASE` (uppercase, underscores, no trailing underscore) for constants; see subsections. |
| 6.2.5.1 | Definition of “constant” | rule | `CONSTANT_CASE` only for deeply immutable values; mutable collections, loggers and instances are not constants. |
| 6.2.5.2 | Local aliases | rule | Alias with `const` only when it improves readability, keeping the last part of the aliased name. |
| 6.2.6 | Non-constant field names | override | `lowerCamelCase` nouns; use `#private` instead of a trailing underscore. |
| 6.2.7 | Parameter names | rule | `lowerCamelCase`; no one-letter names in public methods; `$` prefix only when a framework requires it. |
| 6.2.8 | Local variable names | rule | `lowerCamelCase`, including function-scoped constants and variables holding constructors. |
| 6.2.9 | Template parameter names | override | Closure all-caps names (`TYPE`) are not used; TypeScript uses `T` or `UpperCamelCase`. |
| 6.2.10 | Module-local names | rule | Unexported names are implicitly private; do not mark them `@private`. |
| 6.3 | Camel case: defined | rule | Treat acronyms as words: `xmlHttpRequest`, `newCustomerId`, `supportsIpv6OnIos`. |
| 7 | JSDoc | rule | See subsections. JSDoc documents exported classes, functions and fields. |
| 7.1 | General form | rule | Use `/** … */`; single-line form only if it fits; otherwise `/**` and `*/` on their own lines. Keep it well-formed. |
| 7.2 | Markdown | rule | Write JSDoc in Markdown; use real Markdown lists, not indented plain text. |
| 7.3 | JSDoc tags | rule | Block tags start their own line; simple tags (`@const`, `@final`) may share one. Be consistent. |
| 7.4 | Line wrapping | rule | Indent wrapped block-tag text four spaces; do not indent wrapped `@fileoverview` text. |
| 7.5 | Top/file-level comments | rule | Add a `@fileoverview` when a file holds more than one class; describe contents and dependencies. |
| 7.6 | Class comments | rule | Document every class with a description of when and how to use it; `extends` needs no `@extends`. |
| 7.7 | Enum and typedef comments | rule | Tag enums and typedefs (`@enum`, `@typedef`); public ones need a description. |
| 7.8 | Method and function comments | rule | Document params and return; description is a third-person verb phrase ("Returns …"); omit obvious descriptions; mark overrides `@override`. |
| 7.9 | Property comments | rule | Document public properties and exported constants; private ones may skip the description. |
| 7.10 | Type annotations | override | Closure type syntax is not required; if typing JS, use TypeScript-compatible JSDoc types in braces. |
| 7.10.1 | Nullability | override | Closure `!` / `?` modifiers are not used; null safety comes from TypeScript `strict`. |
| 7.10.2 | Type Casts | rule | Cast only when inference fails: `/** @type {X} */ (expr)`, parentheses required. |
| 7.10.3 | Template Parameter Types | rule | Always give type parameters: `Array<string>`, not bare `Array`. |
| 7.10.4 | Function type expressions | override | Closure `function(string): number` syntax is not used; write TypeScript-style `(s: string) => number`. |
| 7.10.5 | Whitespace | override | Closure annotation spacing does not apply; format types as TypeScript does. |
| 7.11 | Visibility annotations | override | Closure `@private` / `@package` / `@protected` are unchecked; use module scope and `#private`. |
| 8 | Policies | rule | See subsections. |
| 8.1 | Issues unspecified by Google Style: Be Consistent! | rule | For anything unsettled, match the rest of the file, then the rest of the package. |
| 8.2 | Compiler warnings | override | Closure warnings are replaced by ESLint and `tsc` diagnostics; see subsections. |
| 8.2.1 | Use a standard warning set | override | Use the repo's shared `eslint.config.js` (see `tooling.md`) instead of `--warning_level=VERBOSE`. |
| 8.2.2 | How to handle a warning | rule | Understand it, then fix it; else prove a false alarm and suppress with a comment; else leave a TODO and do not suppress. |
| 8.2.3 | Suppress a warning at the narrowest reasonable scope | rule | Suppress per line: `// eslint-disable-next-line <rule> -- reason`; never per file or globally. |
| 8.3 | Deprecation | rule | Mark deprecated APIs `@deprecated` with clear directions for fixing call sites. |
| 8.4 | Code not in Google Style | rule | See subsections. |
| 8.4.1 | Reformatting existing code | rule | Do not restyle code you are not otherwise changing; keep style fixes out of focused changes. |
| 8.4.2 | Newly added code: use Google Style | rule | New files follow this guide; new code in old files matches them but must not break this guide. |
| 8.5 | Local style rules | rule | Extra team rules must not block cleanup changes; avoid rules without purpose. |
| 8.6 | Generated code: mostly exempt | rule | Generated code is exempt, but identifiers referenced from hand-written code follow naming rules. |
| 9 | Appendices | rule | See subsections. |
| 9.1 | JSDoc tag reference | rule | See subsections. |
| 9.1.1 | Type annotations and other Closure Compiler annotations | n/a | Closure Compiler annotation reference; no Closure Compiler here. |
| 9.1.2 | Documentation annotations | rule | See subsections for documentation-only tags. |
| 9.1.2.1 | `@author` or `@owner` - *Not recommended.* | rule | Not recommended: omit `@author` and `@owner`. |
| 9.1.2.2 | `@bug` | rule | In regression tests, cite each bug on its own `@bug` line. |
| 9.1.2.3 | `@code` - *Deprecated. Do not use.* | rule | Never use `{@code}`; use Markdown backticks. |
| 9.1.2.4 | `@desc` | n/a | Describes Closure `goog.getMsg` messages; not used. |
| 9.1.2.5 | `@link` | rule | Use `{@link Name}` for internal cross-references; Markdown link syntax for external links. |
| 9.1.2.6 | `@see` | rule | Use `@see` to reference another class, function or method. |
| 9.1.2.7 | `@supported` | n/a | Lists supported browsers; server-side Node code has none. |
| 9.1.3 | Framework specific annotations | n/a | `@ngInject` (Angular 1) and `@polymerBehavior` (Polymer) are not used. |
| 9.1.3.1 | `@ngInject` for Angular 1 | n/a | Angular 1 is not used. |
| 9.1.3.2 | `@polymerBehavior` for Polymer | n/a | Polymer is not used. |
| 9.1.4 | Notes about standard Closure Compiler annotations | rule | Never use deprecated `@expose` or `@inheritDoc`; use `@override`. |
| 9.1.4.1 | `@expose` - *Deprecated. Do not use.* | rule | Never use `@expose`. |
| 9.1.4.2 | `@inheritDoc` - *Deprecated. Do not use.* | rule | Never use `@inheritDoc`; use `@override`. |
| 9.2 | Commonly misunderstood style rules | rule | No fixed class member order; `{}` for empty blocks; break at higher syntactic level; readable non-ASCII is fine. |
| 9.3 | Style-related tools | override | Tools are Prettier, ESLint 9, `tsc` and Semgrep; see `tooling.md`. |
| 9.3.1 | Closure Compiler | override | Not used; `tsc --noEmit` does type checking. |
| 9.3.2 | clang-format | override | Not used; Prettier formats. |
| 9.3.3 | Closure compiler linter | override | Not used; ESLint lints. |
| 9.3.4 | Conformance framework | override | Not used; ESLint rules, `eslint-plugin-security` and Semgrep enforce banned patterns. |
| 9.4 | Exceptions for legacy platforms | n/a | Node 24 supports modern ECMAScript; legacy-platform exceptions never apply. |
| 9.4.1 | Overview | n/a | `var`, `arguments` and default-less optional params stay banned on Node 24. |
| 9.4.2 | Use var | n/a | `var` is never needed; use `const` / `let` (`no-var`). |
| 9.4.2.1 | `var` declarations are NOT block-scoped | n/a | `var` is banned (`no-var`); function scoping never arises. |
| 9.4.2.2 | Declare variables as close as possible to first use | n/a | Legacy `var` guidance; §5.1.3 covers `const`/`let`. |
| 9.4.2.3 | Use @const for constants variables | n/a | `const` is available on Node 24. |
| 9.4.3 | Do not use block scoped functions declarations | n/a | ES2015+ block-scoped functions are standard on Node 24. |
| 9.4.4 | Dependency management with goog.provide / goog.require | override | `goog.provide`, `goog.scope`, `goog.forwardDeclare` and `goog.module.get` are not used; ESM only. |
| 9.4.4.1 | Summary | override | `goog.provide` files do not exist; ESM only. |
| 9.4.4.2 | Aliasing with `goog.scope` | override | `goog.scope` is not used; ESM imports give short names. |
| 9.4.4.3 | `goog.forwardDeclare` | override | Not used; restructure modules to avoid cycles (§3.4.3). |
| 9.4.4.4 | `goog.module.get(name)` | override | Not used; import the module directly. |
| 9.4.4.5 | `goog.module.declareLegacyNamespace()` | override | Not used; no legacy Closure namespaces exist. |
