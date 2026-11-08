# Security Standards — Reference Lists

Current editions as of 2026. Cite IDs exactly as written here (e.g.
`A01:2025`, `API1:2023`, `CWE-639`, `ASVS V8.2.2`, `LLM01:2025`). Check the
source URLs for newer editions when starting an audit; if one exists, note it
in the report's Method section.

## Contents
1. OWASP Top 10:2025
2. OWASP API Security Top 10:2023
3. OWASP ASVS 5.0.0
4. CWE Top 25 (2025)
5. OWASP Top 10 for LLM Applications 2025
6. Quick mapping: bug → IDs

---

## 1. OWASP Top 10:2025
Source: https://top10.owasp.org/2025

| ID | Category | Backend focus |
|----|----------|---------------|
| A01:2025 | Broken Access Control | Missing ownership checks, IDOR, privilege escalation, **SSRF (now folded in)**, CORS misconfig |
| A02:2025 | Security Misconfiguration | Debug on, default creds, verbose errors, open docs/admin routes, permissive CORS, missing headers |
| A03:2025 | Software Supply Chain Failures | Vulnerable / malicious / hallucinated dependencies, unpinned versions, untrusted registries, CI integrity |
| A04:2025 | Cryptographic Failures | Weak hashing, disabled TLS verification, hardcoded keys, weak randomness |
| A05:2025 | Injection | SQL/NoSQL, OS command, code (`eval`), template, LDAP, log injection |
| A06:2025 | Insecure Design | Missing rate limits on business flows, trust in client, no threat model |
| A07:2025 | Authentication Failures | Weak password storage, JWT mistakes, no brute-force protection, session fixation |
| A08:2025 | Software or Data Integrity Failures | Unsafe deserialization, unsigned webhooks/updates |
| A09:2025 | Security Logging and Alerting Failures | No audit log of security events, secrets in logs, no alerting |
| A10:2025 | Mishandling of Exceptional Conditions | Fail-open error paths, swallowed exceptions, inconsistent state after errors, leaking internals in errors |

## 2. OWASP API Security Top 10:2023
Source: https://api-security.owasp.org/editions/2023/en/0x11-t10 — latest edition.

| ID | Category |
|----|----------|
| API1:2023 | Broken Object Level Authorization (BOLA) |
| API2:2023 | Broken Authentication |
| API3:2023 | Broken Object Property Level Authorization (mass assignment, excessive data exposure) |
| API4:2023 | Unrestricted Resource Consumption |
| API5:2023 | Broken Function Level Authorization |
| API6:2023 | Unrestricted Access to Sensitive Business Flows |
| API7:2023 | Server Side Request Forgery |
| API8:2023 | Security Misconfiguration |
| API9:2023 | Improper Inventory Management (undocumented / old API versions, forgotten endpoints) |
| API10:2023 | Unsafe Consumption of APIs (trusting upstream responses) |

## 3. OWASP ASVS 5.0.0 (May 2025)
Source: https://github.com/OWASP/ASVS/tree/master/5.0/en — ~345 requirements, 17 chapters.

Levels: **L1** first layer of defence (minimum for any service) · **L2** what most
applications should reach — **Default** · **L3** high assurance
(payments, PII-heavy, regulated).

| Chapter | Backend API relevance |
|---------|-----------------------|
| V1 Encoding and Sanitization | Yes — injection prevention |
| V2 Validation and Business Logic | Yes — input schemas, business-flow limits |
| V3 Web Frontend Security | Only if the service serves browser UI |
| V4 API and Web Service | Yes — core chapter |
| V5 File Handling | Yes if uploads/downloads/paths |
| V6 Authentication | Yes |
| V7 Session Management | Yes if sessions/cookies |
| V8 Authorization | Yes — core chapter |
| V9 Self-contained Tokens | Yes if JWT |
| V10 OAuth and OIDC | Yes if OAuth/OIDC |
| V11 Cryptography | Yes |
| V12 Secure Communication | Yes — TLS in/out |
| V13 Configuration | Yes — secrets, debug, dependencies |
| V14 Data Protection | Yes — PII, caching, retention |
| V15 Secure Coding and Architecture | Yes — dependencies, dangerous functions, concurrency |
| V16 Security Logging and Error Handling | Yes |
| V17 WebRTC | Rarely |

Cite requirement IDs from the ASVS source (e.g. `V8.2.2`) when you have
confirmed the exact requirement text; otherwise cite the chapter (`ASVS V8`).
Do not invent requirement numbers.

## 4. CWE Top 25 (2025)
Source: https://cwe.mitre.org/top25/archive/2025/2025_cwe_top25.html

| Rank | CWE | Name | Relevant to Python/Node backends |
|------|-----|------|----------------------------------|
| 1 | CWE-79 | Cross-site Scripting | If HTML/email rendered |
| 2 | CWE-89 | SQL Injection | Yes |
| 3 | CWE-352 | Cross-Site Request Forgery | If cookie auth |
| 4 | CWE-862 | Missing Authorization | Yes |
| 5 | CWE-787 | Out-of-bounds Write | Native extensions only |
| 6 | CWE-22 | Path Traversal | Yes |
| 7 | CWE-416 | Use After Free | Native only |
| 8 | CWE-125 | Out-of-bounds Read | Native only |
| 9 | CWE-78 | OS Command Injection | Yes |
| 10 | CWE-94 | Code Injection | Yes |
| 11 | CWE-120 | Classic Buffer Overflow | Native only |
| 12 | CWE-434 | Unrestricted Upload of Dangerous File Type | Yes |
| 13 | CWE-476 | NULL Pointer Dereference | `None`/`undefined` crashes → DoS |
| 14 | CWE-121 | Stack-based Buffer Overflow | Native only |
| 15 | CWE-502 | Deserialization of Untrusted Data | Yes |
| 16 | CWE-122 | Heap-based Buffer Overflow | Native only |
| 17 | CWE-863 | Incorrect Authorization | Yes |
| 18 | CWE-20 | Improper Input Validation | Yes |
| 19 | CWE-284 | Improper Access Control | Yes |
| 20 | CWE-200 | Exposure of Sensitive Information | Yes |
| 21 | CWE-306 | Missing Authentication for Critical Function | Yes |
| 22 | CWE-918 | Server-Side Request Forgery | Yes |
| 23 | CWE-77 | Command Injection | Yes |
| 24 | CWE-639 | Authorization Bypass Through User-Controlled Key | Yes (BOLA) |
| 25 | CWE-770 | Allocation of Resources Without Limits or Throttling | Yes |

Common CWEs outside the Top 25 worth citing: CWE-798 hardcoded credentials,
CWE-117 log injection, CWE-327 broken crypto, CWE-330 weak randomness, CWE-295
improper certificate validation, CWE-1333 ReDoS, CWE-1321 prototype pollution,
CWE-915 mass assignment, CWE-209 error message information exposure, CWE-400
uncontrolled resource consumption, CWE-601 open redirect.

## 5. OWASP Top 10 for LLM Applications 2025
Source: https://genai.owasp.org/llm-top-10/ — apply when the service calls an LLM.

| ID | Category |
|----|----------|
| LLM01:2025 | Prompt Injection |
| LLM02:2025 | Sensitive Information Disclosure |
| LLM03:2025 | Supply Chain |
| LLM04:2025 | Data and Model Poisoning |
| LLM05:2025 | Improper Output Handling |
| LLM06:2025 | Excessive Agency |
| LLM07:2025 | System Prompt Leakage |
| LLM08:2025 | Vector and Embedding Weaknesses |
| LLM09:2025 | Misinformation |
| LLM10:2025 | Unbounded Consumption |

## 6. Quick mapping: bug → IDs

| Bug | OWASP | API | CWE |
|-----|-------|-----|-----|
| No owner filter on `GET /x/{id}` | A01:2025 | API1:2023 | CWE-639, CWE-862 |
| Admin route without role check | A01:2025 | API5:2023 | CWE-285, CWE-863 |
| Model accepts `is_admin` from client | A01:2025 | API3:2023 | CWE-915 |
| Response returns password hash / internal fields | A01:2025 | API3:2023 | CWE-200 |
| f-string / template-literal SQL | A05:2025 | — | CWE-89 |
| `subprocess(..., shell=True)` / `exec()` with input | A05:2025 | — | CWE-78 |
| `eval` / `new Function` on input | A05:2025 | — | CWE-94 |
| Hardcoded API key | A04:2025 | — | CWE-798 |
| `verify=False` / `rejectUnauthorized:false` | A04:2025 | — | CWE-295 |
| `pickle.loads` / `yaml.load` on input | A08:2025 | — | CWE-502 |
| Fetch arbitrary user URL | A01:2025 | API7:2023 | CWE-918 |
| No request timeout / no page-size cap | A06:2025 | API4:2023 | CWE-770, CWE-400 |
| No login rate limit | A07:2025 | API2:2023 / API6:2023 | CWE-307 |
| Stack trace in response | A02:2025 / A10:2025 | API8:2023 | CWE-209 |
| `except: pass` around auth check (fail open) | A10:2025 | — | CWE-636 |
| Secrets / tokens in logs | A09:2025 | — | CWE-532 |
| Vulnerable / nonexistent dependency | A03:2025 | — | CWE-1395, CWE-1357 |
| Path join with user filename | A01:2025 | — | CWE-22 |
| Weak password hash | A04:2025 / A07:2025 | API2:2023 | CWE-916 |
| LLM output executed / put into SQL | A05:2025 | — | CWE-94 · LLM05:2025 |
