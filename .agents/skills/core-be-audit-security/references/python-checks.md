# Python / FastAPI — Vulnerable Patterns

Grep for these, then read each hit in context. A match is a lead, not a finding,
until you confirm untrusted data reaches it.

| # | Pattern (grep hint) | Risk | IDs | Safe replacement |
|---|---------------------|------|-----|------------------|
| 1 | `f"SELECT`, `.format(` / `%` inside SQL, `text(f"` | SQL injection | A05, CWE-89 | Bound parameters: `text("… WHERE id = :id")`, ORM filters |
| 2 | Mongo filter built from raw request dict; `$where`, `$regex` from input | NoSQL injection | A05, CWE-943 | Validate with pydantic, build filters from typed fields only |
| 3 | `subprocess.*(…, shell=True)`, `os.system`, `os.popen` | Command injection | A05, CWE-78 | `subprocess.run([bin, arg], check=True, timeout=…)`, allow-list |
| 4 | `eval(`, `exec(`, `compile(` on input | Code injection | A05, CWE-94 | Parse data explicitly (`json`, `ast.literal_eval` for literals) |
| 5 | `pickle.load`, `pickle.loads`, `marshal`, `shelve`, `dill` on external data | RCE via deserialization | A08, CWE-502 | JSON + pydantic |
| 6 | `yaml.load(` without `SafeLoader` | RCE | A08, CWE-502 | `yaml.safe_load` |
| 7 | `requests.`/`httpx.` call without `timeout=` | DoS / hung workers | A06, CWE-400 | Explicit timeout; shared client with default timeout |
| 8 | `verify=False` | MITM | A04, CWE-295 | Keep verification; custom CA bundle if needed |
| 9 | `random.` for tokens/ids/OTP | Predictable secrets | A04, CWE-330 | `secrets.token_urlsafe`, `secrets.randbelow` |
| 10 | `hashlib.md5`/`sha1`/`sha256` for passwords | Weak password storage | A04/A07, CWE-916 | `argon2-cffi` / `bcrypt` / `passlib` with argon2 |
| 11 | Literal keys: `sk_`, `AKIA`, `-----BEGIN`, `password = "` | Hardcoded secret | A04, CWE-798 | `Settings` from env / secret manager |
| 12 | `open(os.path.join(base, user_input))` | Path traversal | A01, CWE-22 | `resolved = (base / name).resolve(); resolved.is_relative_to(base)` |
| 13 | `UploadFile` saved with client filename, no size/type check | Dangerous upload | CWE-434 | Random name, size limit, content sniffing, outside static dirs |
| 14 | pydantic model without `extra="forbid"`; ORM model used as request body | Mass assignment | API3, CWE-915 | Separate request model with `ConfigDict(extra="forbid")` and only writable fields |
| 15 | Route returns ORM object / dict without `response_model` | Data over-exposure | API3, CWE-200 | `response_model=PublicModel` |
| 16 | `Model.get(id)` / `find_one({"_id": id})` without owner / tenant filter | BOLA | A01, API1, CWE-639 | Always filter by owner from the authenticated principal; 404 on miss |
| 17 | `jwt.decode(…, options={"verify_signature": False})`, `algorithms` missing or from header | Token forgery | A07, CWE-347 | `jwt.decode(token, key, algorithms=["RS256"], audience=…, issuer=…)` |
| 18 | `httpx.get(user_url)` / webhooks to user-supplied hosts | SSRF | A01, API7, CWE-918 | Resolve host, block private/loopback/link-local/metadata IPs, disable or re-check redirects |
| 19 | `except Exception: pass` around auth/permission logic | Fail open | A10, CWE-636 | Narrow catch; deny on error |
| 20 | `app = FastAPI(debug=True)`; returning `str(exc)` / traceback to client | Info leak | A02, CWE-209 | Central handler returns generic envelope; details only in logs |
| 21 | `CORSMiddleware(allow_origins=["*"], allow_credentials=True)` | Credentialed cross-origin access | A02, CWE-942 | Explicit origin list |
| 22 | `logger.*(… token / password / authorization …)`, logging full request bodies | Secret leak in logs | A09, CWE-532 | Log ids, redact sensitive fields |
| 23 | `re.compile` of user-supplied patterns, nested quantifiers on input | ReDoS | CWE-1333 | Avoid user regex; use `re2`/timeouts; simplify patterns |
| 24 | Blocking calls in `async def` (`requests`, `time.sleep`, sync DB) | Event-loop stall → DoS | A06, CWE-400 | Async clients, `asyncio.to_thread` |
| 25 | `hmac` / token comparison with `==` | Timing attack | CWE-208 | `hmac.compare_digest` |
| 26 | `jinja2.Environment(autoescape=False)`, `Markup(user)` | XSS / SSTI | A05, CWE-79/1336 | `autoescape=True`; never render user templates |
| 27 | `xml.etree` / `lxml` parsing untrusted XML | XXE / billion laughs | CWE-611 | `defusedxml` |
| 28 | `tempfile.mktemp` | Race | CWE-377 | `tempfile.NamedTemporaryFile` / `mkstemp` |
| 29 | `assert` used for auth/validation | Stripped with `-O` | CWE-617 | Explicit `if … raise` |
| 30 | `/docs`, `/redoc`, `/openapi.json` public in production | Recon / API9 | API9 | `docs_url=None` in prod or protect |

Useful greps:

```bash
rg -n 'shell=True|os\.system|os\.popen|eval\(|exec\(|pickle\.|yaml\.load\(|verify=False|md5|sha1\(' src
rg -n 'f"(SELECT|INSERT|UPDATE|DELETE)|text\(f"' src
rg -n 'requests\.(get|post|put|delete)\(|httpx\.(get|post)\(' src   # then check for timeout=
rg -n 'allow_origins=\["\*"\]|debug=True' src
```
