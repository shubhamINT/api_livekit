# TypeScript / Node.js Style — Essentials

Baseline: [Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html)
(and the [JavaScript guide](https://google.github.io/styleguide/jsguide.html) for
plain JS). Google has no Node-specific guide; Node runtime practice comes from
[Node.js Best Practices](https://github.com/goldbergyoni/nodebestpractices).
Layout is decided by Prettier; the rules here are the ones a formatter cannot
enforce. The Airbnb config is **not** used — it does not support ESLint 9 flat
config.

## Contents
1. Source files and modules
2. Language features
3. Naming
4. Type system
5. Comments and docs
6. Node runtime practice
7. Anti-patterns table
8. Complete index

---

## 1. Source files and modules

- ES modules (`"type": "module"` in `package.json`, or TS `module: "NodeNext"`). No `require` in TS source.
- **Named exports only; no default exports.** Names stay consistent across importers and refactors.
- Import types with `import type { X }`.
- No mutable exports (`export let`). Export functions or `const`.
- No namespaces (`namespace Foo {}`) — use modules.
- One concept per file; filename in `kebab-case.ts` or the repo's existing convention.
- Licence header first if the repo uses one, then imports.

## 2. Language features

- `const` by default, `let` when reassigned, never `var`.
- `===` / `!==` only (`== null` is the one accepted exception, to cover `undefined` too — only if the repo already uses it).
- Use `for…of` for arrays, `Object.entries()` for objects. Never `for…in` over arrays.
- Spread / destructuring over `Object.assign` and manual copying.
- Classes: `readonly` fields when never reassigned; parameter properties OK; no `#private` mixed with `private` in one codebase — pick the repo's convention.
- No `this` outside classes; arrow functions for callbacks.
- Throw only `Error` (or subclasses). Never throw strings or objects. Attach cause: `new Error("msg", { cause: err })`.
- `try`/`catch` binds `unknown`; narrow before use (`if (err instanceof Error)`).
- No `eval`, `new Function`, `with`, or modifying built-in prototypes.
- No decorators unless the framework requires them (NestJS).
- Always `await` or explicitly handle every promise — no floating promises (`@typescript-eslint/no-floating-promises`).

## 3. Naming

| Kind | Style |
|------|-------|
| Classes, interfaces, types, enums | `UpperCamelCase` |
| Variables, functions, methods, properties | `lowerCamelCase` |
| Module-level constants, enum members | `CONSTANT_CASE` |
| Type parameters | `T`, or `UpperCamelCase` (`TItem`) |

- No `I` prefix on interfaces. No Hungarian notation. No trailing/leading underscores for privacy — use `private`.
- Acronyms as words: `loadHttpUrl`, not `loadHTTPURL`.

## 4. Type system

- `tsconfig` has `"strict": true` plus `noUncheckedIndexedAccess`, `noImplicitOverride`, `exactOptionalPropertyTypes` on new services.
- **No `any`.** Use `unknown` and narrow, or a precise type. A necessary `any` carries an `eslint-disable-next-line` with a reason.
- Rely on inference for locals; annotate exported function parameters and return types.
- Prefer `interface` for object shapes; `type` for unions, mapped and conditional types.
- `undefined` for absent values in new code; do not mix `null` and `undefined` meaning the same thing.
- Optional (`?:`) instead of `| undefined` in parameters and fields.
- No non-null assertions (`x!`) except with a comment proving it.
- Validate external data with **zod** at the boundary, and derive the type from the schema (`z.infer<typeof Schema>`), so type and runtime check cannot drift.
- Avoid `enum`; prefer string-literal unions or `as const` objects.
- No wrapper types (`String`, `Number`, `Boolean`, `Object`).

## 5. Comments and docs

- JSDoc (`/** … */`) on every exported function, class, and type: purpose, `@param` only when it adds information, `@returns`, `@throws`.
- Do not repeat types in JSDoc — TypeScript has them.
- Line comments (`//`) explain *why*.
- `// TODO(PROJ-123): reason`.

## 6. Node runtime practice

From Node.js Best Practices (§ numbers are that guide's sections):

- **Architecture (§1)** — layer by concern: routes → domain → services/data. Keep Express/Fastify objects (`req`, `res`) out of domain code. Config in one module, validated at startup (fail fast on missing env).
- **Errors (§2)**
  - One `AppError` hierarchy with `statusCode` and `isOperational`.
  - One central error middleware / `setErrorHandler` emits the response envelope; routes do not hand-roll error bodies.
  - Handle `unhandledRejection` and `uncaughtException`: log, then exit — do not keep running in an unknown state; the process manager restarts it.
  - Distinguish operational errors (bad input, upstream down) from programmer errors (bugs).
- **Code patterns (§3)** — `async`/`await` over callbacks; no sync I/O (`fs.readFileSync`) on request paths; no CPU-heavy loops on the event loop (use worker threads or a queue).
- **Going to production (§5)**
  - Structured JSON logging (pino) with request ids; never `console.log` in service code.
  - Graceful shutdown on `SIGTERM`: stop accepting, drain, close DB / clients, then exit.
  - `NODE_ENV=production`.
  - Lock dependencies (`package-lock.json` / `pnpm-lock.yaml` committed; `npm ci` in CI).
- **Security (§6)** — see `core-be-audit-security/references/node-checks.md`.
- **Outbound HTTP** — built-in `fetch` (undici) with `AbortSignal.timeout(ms)` on every call, or a shared client with a timeout.

## 7. Anti-patterns

| Don't | Do |
|-------|----|
| `export default router` | `export const ordersRouter = …` |
| `catch (e: any)` | `catch (err: unknown)` + narrow |
| `throw "not found"` | `throw new NotFoundError("order", id)` |
| `process.env.X` scattered | one `config.ts` parsed by zod at startup |
| `JSON.parse(body) as Order` | `OrderSchema.parse(JSON.parse(body))` |
| `` db.query(`… WHERE id = ${id}`) `` | parameterised query / query builder |
| `promise.then()` without catch, or un-awaited call | `await`, or `void` with explicit `.catch` |
| `console.log(user)` | `logger.info({ userId }, "user loaded")` |
| `fetch(url)` with no timeout | `fetch(url, { signal: AbortSignal.timeout(3000) })` |
| `enum Status { … }` | `type Status = "open" \| "closed"` |

## 8. Complete index of the Google TypeScript Style Guide

Every numbered section of the Google guide, in order. The full text lives in
`google/tsguide.md`; read the section there for detail and examples. Status:
`tool` = enforced automatically by the named tool or rule; `rule` = follow by
hand in review; `override` = this standard deliberately differs (reason given);
`n/a` = Google-internal or not relevant to backend Node.

| § | Section | Status | Rule |
|---|---------|--------|---------------|
| 1 | Introduction | rule | See subsections. |
| 1.1 | Terminology notes | rule | Read must/should/may as RFC 2119; "prefer" means should, "avoid" means should not. |
| 1.2 | Guide notes | rule | Examples are non-normative; do not enforce formatting choices seen only in examples. |
| 2 | Source file basics | rule | See subsections. |
| 2.1 | File encoding: UTF-8 | rule | Save source files as UTF-8. |
| 2.1.1 | Whitespace characters | rule | Only ASCII space (0x20) as whitespace outside line endings; escape tabs and other whitespace inside strings. |
| 2.1.2 | Special escape sequences | rule | Use `\n`, `\t`, `\'` and similar instead of numeric escapes; never legacy octal escapes. |
| 2.1.3 | Non-ASCII characters | rule | Write printable Unicode characters directly; escape non-printable ones and add an explanatory comment. |
| 3 | Source file structure | rule | Order: licence header, optional `@fileoverview`, imports, implementation; one blank line between sections. |
| 3.1 | Copyright information | rule | If the repo uses a licence header, it goes first in every file, copied from existing files. |
| 3.2 | @fileoverview JSDoc | rule | Optional file-level `@fileoverview` JSDoc describing content and use; wrapped lines not indented. |
| 3.3 | Imports | rule | Use named or namespace imports; default imports only when external code requires; side-effect imports only for side effects. |
| 3.3.1 | Import paths | override | Relative paths with the `.js` extension, because ESM with `NodeNext` requires it; keep `../` chains short. |
| 3.3.2 | Namespace versus named imports | rule | Named imports for frequently used, clearly named symbols; namespace imports for many symbols from large APIs. |
| 3.3.3 | Renaming imports | rule | Rename imports (`as`) only to avoid collisions, fix generated names, or clarify unclear names. |
| 3.4 | Exports | rule | Named exports only; never `export default`. |
| 3.4.1 | Export visibility | rule | Export only symbols used outside the module; keep the exported surface minimal. |
| 3.4.2 | Mutable exports | rule | No `export let`; expose mutable state through a getter function; exports final after module body runs. |
| 3.4.3 | Container classes | tool | `@typescript-eslint/no-extraneous-class`: export individual functions and constants, not classes of static members. |
| 3.5 | Import and export type | rule | See subsections. |
| 3.5.1 | Import type | override | Google permits `import type`; this standard requires it for type-only imports so type and value imports stay explicit. |
| 3.5.2 | Export type | rule | Use `export type { X }` when re-exporting a type. |
| 3.5.3 | Use modules not namespaces | tool | `@typescript-eslint/no-namespace`, `@typescript-eslint/no-require-imports`, `@typescript-eslint/triple-slash-reference`; ES module syntax only. |
| 4 | Language features | rule | Features not covered by the guide may be used; see subsections. |
| 4.1 | Local variable declarations | rule | See subsections. |
| 4.1.1 | Use const and let | tool | ESLint `no-var` and `prefer-const`; tsc rejects use of `let`/`const` before declaration. |
| 4.1.2 | One variable per declaration | rule | Declare one variable per statement; no `let a = 1, b = 2;`. |
| 4.2 | Array literals | rule | See subsections. |
| 4.2.1 | Do not use the Array constructor | tool | `@typescript-eslint/no-array-constructor`; use `[]` literals or `Array.from({length: n})`. |
| 4.2.2 | Do not define properties on arrays | rule | No non-numeric properties on arrays other than `length`; use a `Map` or object. |
| 4.2.3 | Using spread syntax | rule | Spread only iterables into arrays; never spread primitives, `null` or `undefined` (use `cond ? arr : []`). |
| 4.2.4 | Array destructuring | rule | Omit unused elements; optional destructured array parameters default to `[]` with defaults on the left. Prefer object destructuring. |
| 4.3 | Object literals | rule | See subsections. |
| 4.3.1 | Do not use the Object constructor | rule | Use object literals (`{}`), never `new Object()`. |
| 4.3.2 | Iterating objects | rule | No unfiltered `for…in`; use `for…of` over `Object.keys`/`values`/`entries`. |
| 4.3.3 | Using spread syntax | rule | Spread only plain objects into objects; never arrays, primitives, class instances or `null`/`undefined`. |
| 4.3.4 | Computed property names | rule | Computed keys count as quoted dict-style keys (unless symbols); do not mix with unquoted keys. |
| 4.3.5 | Object destructuring | rule | Parameter destructuring: one level, shorthand only; defaults on the left; optional destructured object defaults to `{}`. |
| 4.4 | Classes | rule | See subsections. |
| 4.4.1 | Class declarations | tool | Prettier drops semicolons after class declarations and keeps them after class-expression statements. |
| 4.4.2 | Class method declarations | rule | No semicolons between methods; one blank line between methods; `toString` overrides must always succeed with no side effects. |
| 4.4.3 | Static methods | rule | Prefer module functions to private static methods; no `this` in static context; call statics only on the defining class. |
| 4.4.4 | Constructors | tool | Prettier adds `new Foo()` parentheses; `@typescript-eslint/no-useless-constructor` flags empty or pass-through constructors. |
| 4.4.5 | Class members | override | Google bans `#private`; this standard allows it where the repo already uses it (native in Node 24), never mixed with `private`. |
| 4.4.6 | Visibility | rule | Limit visibility; never write `public` except on non-readonly parameter properties. |
| 4.4.7 | Disallowed class patterns | rule | Do not manipulate `prototype` directly; no mixins. |
| 4.5 | Functions | rule | See subsections. |
| 4.5.1 | Terminology | rule | Definitions only: function declaration, function expression, arrow function, block body, concise body. |
| 4.5.2 | Prefer function declarations for named functions | rule | Use `function foo()` for named top-level functions; arrow functions only when a type annotation is needed. |
| 4.5.3 | Nested functions | rule | Nested functions may be declarations or arrows; prefer arrows inside methods to keep outer `this`. |
| 4.5.4 | Do not use function expressions | rule | Use arrow functions instead of `function` expressions, except generators or deliberate `this` rebinding. |
| 4.5.5 | Arrow function bodies | rule | Use a concise body only when the return value is used; otherwise a block body or `void`. |
| 4.5.6 | Rebinding this | rule | No `this` in function declarations or expressions; use arrows, not `bind` or `const self = this`. |
| 4.5.7 | Prefer passing arrow functions as callbacks | rule | Wrap named callbacks in arrows that forward arguments explicitly (`.map((s) => parseInt(s))`, not `.map(parseInt)`). |
| 4.5.8 | Arrow functions as properties | rule | Avoid arrow-function class properties; call methods through arrows at the call site instead of passing method references. |
| 4.5.9 | Event handlers | rule | Arrow-function properties only for listeners that must be removed later; never `bind` when registering a listener. |
| 4.5.10 | Parameter initializers | rule | Default parameter values must be simple and side-effect free; use a destructured options object for many optionals. |
| 4.5.11 | Prefer rest and spread when appropriate | tool | ESLint `prefer-rest-params` and `prefer-spread`; never name anything `arguments`. |
| 4.5.12 | Formatting functions | tool | Prettier handles blank lines, generator `*` placement, arrow parentheses and spread spacing. |
| 4.6 | this | tool | tsc `noImplicitThis` (part of `strict`); use `this` only in classes, typed-`this` functions, or arrows inside them. |
| 4.7 | Interfaces | n/a | Heading has no content in the source guide; see 6.3 and 6.4. |
| 4.8 | Primitive literals | rule | See subsections. |
| 4.8.1 | String literals | tool | Prettier `singleQuote: true` enforces single quotes. By hand: no line continuations; template literals over complex concatenation. |
| 4.8.2 | Number literals | rule | Use lowercase `0x`, `0o`, `0b` prefixes; no leading zero otherwise. |
| 4.8.3 | Type coercion | rule | Coerce with `String()`, `Boolean()`, `!!` or templates; parse with `Number()` and check `NaN`; no unary `+`, no radix-10 `parseInt`. |
| 4.9 | Control structures | rule | See subsections. |
| 4.9.1 | Control flow statements and blocks | rule | Always brace blocks (one-line `if` excepted); avoid assignment in conditions, else double parentheses; `for…of` for arrays. |
| 4.9.2 | Grouping parentheses | rule | Keep clarifying parentheses; do not wrap whole expressions after `return`, `throw`, `typeof`, `delete` and similar. |
| 4.9.3 | Exception handling | rule | Use `new Error()` or subclasses; throw and reject only `Error`s (`@typescript-eslint/only-throw-error`); comment every empty `catch`. |
| 4.9.4 | Switch statements | rule | Every `switch` has a final `default`; no fall-through from non-empty cases (ESLint `no-fallthrough`). |
| 4.9.5 | Equality checks | override | Google always allows `== null`; this standard allows it only where the repo already uses it. Otherwise `===` / `!==` only. |
| 4.9.6 | Type and non-nullability assertions | override | Stricter: every `!` or `as` needs a justifying comment; `@typescript-eslint/no-non-null-assertion` flags `!`; parse external data with zod. |
| 4.9.7 | Keep try blocks focused | rule | Keep only throwing calls inside `try`; widening to cover a whole loop is fine. |
| 4.10 | Decorators | rule | Do not define decorators; use only framework-provided ones (e.g. NestJS); no blank line after a decorator. |
| 4.11 | Disallowed features | rule | See subsections. |
| 4.11.1 | Wrapper objects for primitive types | rule | Never `new String`, `new Boolean` or `new Number`; calling them as functions to coerce is fine. |
| 4.11.2 | Automatic Semicolon Insertion | tool | Prettier (`semi: true`, the default) ends every statement with a semicolon. |
| 4.11.3 | Const enums | override | Google bans `const enum` but allows plain `enum`; this standard avoids both, using string-literal unions or `as const` objects. |
| 4.11.4 | Debugger statements | tool | ESLint `no-debugger`. |
| 4.11.5 | with | tool | ESLint `no-with`; tsc rejects `with` in strict-mode modules. |
| 4.11.6 | Dynamic code evaluation | tool | `@typescript-eslint/no-implied-eval`, eslint-plugin-security `detect-eval-with-expression`; never `eval` or `new Function`. |
| 4.11.7 | Non-standard features | rule | Only standardized ECMAScript; no TC39 proposals or transpiler extensions. Node APIs are fine. |
| 4.11.8 | Modifying builtin objects | rule | Never modify builtin prototypes or constructors; add globals only when a third-party API requires it. |
| 5 | Naming | rule | See subsections. |
| 5.1 | Identifiers | rule | Identifiers use ASCII letters, digits, underscores only in constants, rarely `$`. |
| 5.1.1 | Naming style | rule | Do not encode type information in names: no `_` privacy markers, `opt_` prefixes, or `I` interface prefixes. |
| 5.1.2 | Descriptive names | rule | Descriptive names; no ambiguous abbreviations or deleted letters; short names only in scopes of 10 lines or fewer. |
| 5.1.3 | Camel case | rule | Treat acronyms as words: `loadHttpUrl`, `customerId`. |
| 5.1.4 | Dollar sign | rule | Avoid `$` in identifiers unless a framework convention requires it. |
| 5.2 | Rules by identifier type | rule | `UpperCamelCase` types and classes, `lowerCamelCase` values and functions, `CONSTANT_CASE` global constants; see section 3. |
| 5.2.1 | Type parameters | rule | Single capital letter (`T`) or `UpperCamelCase`. |
| 5.2.2 | Test names | n/a | Covers xUnit method names; vitest names tests with strings in `describe`/`it`. |
| 5.2.3 | _ prefix/suffix | rule | No leading or trailing `_` on any identifier, and no bare `_` for unused values; skip destructured elements with commas. |
| 5.2.4 | Imports | override | Files are `kebab-case.ts` (or repo convention), not Google's `snake_case`; namespace import aliases stay `lowerCamelCase`. |
| 5.2.5 | Constants | rule | `CONSTANT_CASE` only for module-level constants, static readonly fields and enum values; per-call values use `lowerCamelCase`. |
| 5.2.6 | Aliases | rule | Local aliases keep the source name and format; use `const` or `readonly`. |
| 6 | Type system | rule | See subsections. |
| 6.1 | Type inference | rule | Rely on inference; omit annotations on trivially inferred initializers; annotate empty generic containers and complex expressions. |
| 6.1.1 | Return types | override | Google leaves return types optional; this standard (allowed local policy) annotates parameters and return types on exported functions. |
| 6.2 | Undefined and null | override | Google has no preference; this standard uses `undefined` for absence in new code, never mixing both for one meaning. |
| 6.2.1 | Nullable/undefined type aliases | rule | Type aliases must not include `\|null` or `\|undefined`; add them at the use site. |
| 6.2.2 | Prefer optional over \|undefined | rule | Use optional `?` fields and parameters instead of `\|undefined`; initialize class fields where possible. |
| 6.3 | Use structural types | rule | Annotate the declared type on object literals; define structural types with interfaces, not classes. |
| 6.4 | Prefer interfaces over type literal aliases | rule | Use `interface` for object shapes, not `type X = {…}`; `z.infer` aliases for schema types are fine. |
| 6.5 | Array<T> Type | rule | `T[]` / `readonly T[]` for simple element types; `Array<T>` for complex ones. |
| 6.6 | Indexable types / index signatures ( {[key: string]: T} ) | rule | Give index-signature keys meaningful labels; prefer `Map` and `Set` over objects used as dictionaries. |
| 6.7 | Mapped and conditional types | rule | Use the simplest type construct; prefer interface extension to `Pick`-style operators when readable. |
| 6.8 | any Type | tool | `@typescript-eslint/no-explicit-any`. |
| 6.8.1 | Providing a more specific type | override | For external JSON, derive the type from a zod schema (`z.infer`) instead of hand-declaring an interface. |
| 6.8.2 | Using unknown over any | rule | Use `unknown` for opaque values and narrow with type guards before use. |
| 6.8.3 | Suppressing any lint warnings | rule | A legitimate `any` (for example a test mock) gets `eslint-disable-next-line` plus a comment explaining why. |
| 6.9 | {} Type | tool | `@typescript-eslint/no-empty-object-type`; use `unknown`, `Record<string, T>` or `object` instead. |
| 6.10 | Tuple types | rule | Use a tuple instead of a `Pair` interface, but prefer named properties when clearer. |
| 6.11 | Wrapper types | tool | `@typescript-eslint/no-wrapper-object-types`; use `string`, `number`, `boolean`, `object`. |
| 6.12 | Return type only generics | rule | Do not create APIs whose generic appears only in the return type; specify such generics explicitly when calling. |
| 7 | Toolchain requirements | rule | See subsections and `tooling.md`. |
| 7.1 | TypeScript compiler | tool | `tsc --noEmit` with `strict` must pass on every file. |
| 7.1.1 | @ts-ignore | rule | No `@ts-ignore` or `@ts-nocheck` (`@typescript-eslint/ban-ts-comment`); `@ts-expect-error` only rarely, in tests. |
| 7.2 | Conformance | n/a | tsetse and tsec are Google-internal; this standard uses ESLint, eslint-plugin-security and Semgrep (`tooling.md`). |
| 8 | Comments and documentation | rule | See subsections and section 5. |
| 8.0.1 | JSDoc versus comments | rule | `/** */` JSDoc for API users; `//` comments for implementation notes. |
| 8.0.2 | Multi-line comments | rule | Multi-line implementation comments use repeated `//`, not `/* */`; no boxed comments. |
| 8.1 | JSDoc general form | rule | Well-formed JSDoc; a comment that overflows one line uses `/**` and `*/` on their own lines. |
| 8.2 | Markdown | rule | Write JSDoc in Markdown (real lists, not indented text). |
| 8.3 | JSDoc tags | rule | Each block tag on its own line at line start; never combine tags. |
| 8.4 | Line wrapping | rule | Indent wrapped block-tag lines four spaces; do not align wrapped descriptions. |
| 8.5 | Document all top-level exports of modules | rule | JSDoc every export, plus non-obvious members; do not merely restate names. |
| 8.6 | Class comments | rule | Class JSDoc explains how and when to use the class. |
| 8.7 | Method and function comments | rule | Descriptions start with a third-person verb phrase; omit obvious parameter and return descriptions. |
| 8.8 | Parameter property comments | rule | Document parameter properties with `@param` on the constructor. |
| 8.9 | JSDoc type annotations | rule | No types in JSDoc and no tags duplicating keywords (`@private`, `@enum`, `@override`, `@implements`). |
| 8.10 | Make comments that actually add information | rule | Skip comments that restate name and type; write `@param`/`@returns` only when they add information. |
| 8.10.1 | Comments when calling a function | rule | Use `/* name= */ value` comments for unclear arguments, or refactor to an options object. |
| 8.11 | Place documentation prior to decorators | rule | Put JSDoc before decorators, never between decorator and declaration. |
| 9 | Policies | rule | See subsections. |
| 9.1 | Consistency | override | Match surrounding code where unsettled; new files follow this guide. Do not restyle untouched code in the same change (AGENTS.md rule 11). |
| 9.1.1 | Reformatting existing code | rule | Restyling all old code is not required; put style-only fixes in a separate change. |
| 9.2 | Deprecation | rule | Mark deprecated APIs with `@deprecated` and clear migration directions. |
| 9.3 | Generated code: mostly exempt | rule | Generated code is exempt, but generated identifiers used by hand-written code follow naming rules (underscores allowed). |
| 9.3.1 | Style guide goals | rule | Rules exist to avoid known pitfalls, keep consistency, aid maintenance, and prefer automated checks. Otherwise decide locally. |
