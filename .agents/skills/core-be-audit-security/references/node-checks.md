# Node.js / TypeScript (Express, Fastify) — Vulnerable Patterns

Grep for these, then read each hit in context. A match is a lead, not a finding,
until you confirm untrusted data reaches it.

| # | Pattern (grep hint) | Risk | IDs | Safe replacement |
|---|---------------------|------|-----|------------------|
| 1 | `` query(`…${ `` , string concat into SQL, `knex.raw(` / `sequelize.query(` with interpolation, Prisma `$queryRawUnsafe` | SQL injection | A05, CWE-89 | Placeholders (`$1`, `?`), query builder, Prisma tagged `$queryRaw` |
| 2 | Mongo query from `req.body` / `req.query` directly (`{ user: req.body.user }` can be `{ "$ne": null }`) | NoSQL operator injection | A05, CWE-943 | zod-validate to primitives; `mongo-sanitize` / strict schemas |
| 3 | `child_process.exec(`, `execSync(`, `spawn(…, { shell: true })` | Command injection | A05, CWE-78 | `execFile` / `spawn(bin, [args])` without shell, allow-list |
| 4 | `eval(`, `new Function(`, `vm.runInContext` on input, `setTimeout(string)` | Code injection | A05, CWE-94 | Parse data; never execute input |
| 5 | Deep merge / `Object.assign` / lodash `merge`/`set` with request objects; `obj[key] = value` with user `key` | Prototype pollution | CWE-1321 | `Object.create(null)`, `Map`, reject `__proto__`/`constructor`/`prototype`, zod `.strict()` |
| 6 | `node-serialize`, `serialize-javascript` decode, `js-yaml` `load` with unsafe schema | Deserialization RCE | A08, CWE-502 | `JSON.parse` + zod; `yaml` safe defaults |
| 7 | `fetch(` / `axios` without timeout / `AbortSignal` | DoS / hung requests | A06, CWE-400 | `AbortSignal.timeout(ms)`; axios `timeout` |
| 8 | `rejectUnauthorized: false`, `NODE_TLS_REJECT_UNAUTHORIZED=0` | MITM | A04, CWE-295 | Keep verification; provide CA |
| 9 | `Math.random()` for tokens/ids | Predictable secrets | A04, CWE-330 | `crypto.randomBytes`, `crypto.randomUUID()` |
| 10 | `createHash('md5'|'sha1'|'sha256')` for passwords | Weak password storage | A04/A07, CWE-916 | `argon2` / `bcrypt` |
| 11 | Literal keys / tokens / connection strings in source or `.env` committed | Hardcoded secret | A04, CWE-798 | env via validated `config.ts`, secret manager |
| 12 | `path.join(base, req.params.file)`, `res.sendFile(userPath)` | Path traversal | A01, CWE-22 | `path.resolve` then check `startsWith(base + path.sep)`; `sendFile(name, { root })` |
| 13 | `multer` without `limits` / `fileFilter`; client filename kept | Dangerous upload / DoS | CWE-434, CWE-770 | Limits, type sniffing, random names |
| 14 | `Model.create(req.body)`, `update(req.body)` | Mass assignment | API3, CWE-915 | zod schema with allowed fields only |
| 15 | Returning DB document directly (`res.json(user)`) | Data over-exposure | API3, CWE-200 | Map to a response DTO |
| 16 | `findById(req.params.id)` without owner / tenant filter | BOLA | A01, API1, CWE-639 | `findOne({ _id: id, ownerId: req.user.id })`; 404 on miss |
| 17 | `jwt.verify(token, key)` without `algorithms`; `jwt.decode` used for auth; secret literal | Token forgery | A07, CWE-347 | `jwt.verify(token, key, { algorithms: ["RS256"], audience, issuer })` |
| 18 | `fetch(req.body.url)` / webhook to user host | SSRF | A01, API7, CWE-918 | DNS-resolve + block private/loopback/link-local/metadata ranges; `redirect: "manual"` |
| 19 | `catch {}` / `catch (e) { next() }` around auth checks | Fail open | A10, CWE-636 | Deny on error |
| 20 | Express default error handler in prod; `res.status(500).send(err.stack)` | Info leak | A02, CWE-209 | Central error handler → generic envelope |
| 21 | `cors({ origin: "*", credentials: true })`, `origin: true` reflecting any origin with credentials | Credentialed cross-origin | A02, CWE-942 | Explicit origin allow-list |
| 22 | No `helmet()` (Express) / `@fastify/helmet` when serving browsers | Missing headers | A02 | Add helmet |
| 23 | `express.json()` without `limit`; Fastify `bodyLimit` raised; no pagination cap | Resource exhaustion | API4, CWE-770 | Body limits, max page size, rate limiting (`express-rate-limit`, `@fastify/rate-limit`) |
| 24 | Regex from input (`new RegExp(req.query.q)`), catastrophic patterns | ReDoS | CWE-1333 | Escape input, avoid nested quantifiers, `re2` |
| 25 | Sync / CPU-heavy work on request path (`fs.readFileSync`, `crypto.pbkdf2Sync`, big JSON) | Event-loop block → DoS | CWE-400 | Async APIs, worker threads |
| 26 | `===` on secrets / HMACs | Timing attack | CWE-208 | `crypto.timingSafeEqual` |
| 27 | `res.redirect(req.query.next)` | Open redirect | CWE-601 | Allow-list relative paths |
| 28 | `console.log(req.headers)` / logging tokens | Secret leak in logs | A09, CWE-532 | pino with `redact` paths |
| 29 | Template engines with unescaped output (`<%-`, `{{{ }}}`, `dangerouslySetInnerHTML` in SSR) | XSS | A05, CWE-79 | Escaped output |
| 30 | `npm install` without lockfile in CI, `^`/`*` ranges on critical deps, postinstall scripts from unknown packages | Supply chain | A03 | `npm ci`, lockfile committed, review new deps, `--ignore-scripts` where feasible |

Useful greps:

```bash
rg -n 'child_process|exec\(|execSync|shell:\s*true|eval\(|new Function|rejectUnauthorized|Math\.random' src
rg -n 'query\(`|\$queryRawUnsafe|knex\.raw\(|sequelize\.query\(' src
rg -n 'findById\(req\.|create\(req\.body|update\(req\.body' src
rg -n "origin:\s*['\"]\*['\"]|origin:\s*true" src
```
