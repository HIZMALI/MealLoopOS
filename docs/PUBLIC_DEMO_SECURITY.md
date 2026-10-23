# Public demo security boundaries

This is an application hardening review and executed regression evidence, not a certified security audit. The demo is for anonymous demonstration, not private operational work.

## Server-controlled modes

| Boundary | LOCAL (default) | PUBLIC_DEMO (explicit) |
| --- | --- | --- |
| Launch | `scripts/start.ps1` loopback 8080 / Vite 15173 | `MEALLOOP_MODE=PUBLIC_DEMO`, exact public host allowlist, `scripts/serve.py` |
| Data | Existing `data/mealloop.db`, or explicit local DB URL | Only server-fixed `.public-demo/demo.db`; any database override rejects startup |
| Storage | Existing migrations and write workflows | SQLite URI `mode=ro` and every connection `PRAGMA query_only=ON`; no startup migration |
| Data contents | User imports, plans and self-reports | One official measured batch, one prepared forecast artifact, one synthetic plan, two synthetic services / three revisions, zero saved forecast runs |
| API | Existing local workflows plus stateless forecast preview | Exact route/method allowlist, default deny, bounded resource IDs and synthetic cohort only |
| Browser | Imports, training, save/finalize/correct and exports | Previews and read-only inspection; every write and export route blocked server-side |
| Docs | `/docs`, `/redoc`, `/openapi.json` | Disabled and inaccessible |
| Origins | Existing localhost development CORS origins plus server-side foreign-Origin POST rejection | Single origin; no CORS grants, cross-origin POST rejected |
| Network | Peer must be loopback; normal launcher explicitly selects LOCAL | Explicit host allowlist; 0.0.0.0 and hosting `PORT`; TLS terminates at host |

Neither query parameters nor headers change mode. Frontend configuration comes from `/api/config`; a failed fetch displays a retry state and does not assume LOCAL. Public config/health omit database paths, host configuration and operational details. LOCAL POSTs from browsers require their own origin or trusted loopback Vite development/preview origins; origin-less local CLI requests remain supported. This also rejects cross-site simple multipart uploads before parsing. LOCAL is not an authenticated shared LAN service and must not be put behind a public reverse proxy. The public runner ignores proxy headers; LOCAL rejects remote peers even with a localhost Host header.

## Complete reviewed API inventory

The authoritative machine sets are `backend/app/public_policy.py`; tests enumerate every registered API method/template and require complete classification. Newly registered routes receive no public permission. Security uses FastAPI's effective route contexts (including wrapped routers) and the route actually selected in registration order, avoiding permission inheritance by an overlapping new route.

| Methods and paths | Public classification |
| --- | --- |
| GET `/api/config`, `/api/health` | Safe capability/health reads |
| GET `/api/dataset/status`, `/api/overview`, `/api/charts` | Official isolated batch only; `batch_id` absent or exactly 1 |
| POST `/api/dataset/import` | Denied before upload parsing |
| GET `/api/models/status`, `/api/models/metadata`, `/api/models/evaluation` | Prepared official artifact/evidence only |
| POST `/api/models/train` | Denied |
| POST `/api/forecasts` and GET `/api/forecasts/runs` | Denied |
| POST `/api/forecasts/preview` | Stateless prediction from prepared JSON; no fit or save |
| GET `/api/decisions/metadata`, `/api/decisions/demo` | Bounded engine information and synthetic input fixture |
| POST `/api/decisions/preview` | Stateless assumption calculation |
| POST `/api/decisions/plans` | Denied |
| GET `/api/decisions/plans` and `/api/decisions/plans/{plan_id}` | Only prepared synthetic plan; detail ID exactly 1 |
| GET `/api/decisions/plans/{plan_id}/export` | Denied |
| GET `/api/impact/metadata`, `/api/impact/demo` | Accounting information and explicit synthetic fixtures |
| POST `/api/impact/demo` | Denied; runtime visitors cannot seed |
| POST `/api/impact/preview`, `/api/impact/comparison` | Nonpersistent; source must be synthetic; plan reference null or 1 |
| POST `/api/impact/records` | Denied |
| GET `/api/impact/records`, `/api/impact/summary` | Synthetic cohort only, including default selection |
| GET `/api/impact/records/{service_id}` and suffixes `/history`, `/quality`, `/plan` | IDs exactly 1 or 2, synthetic immutable snapshots |
| POST `/api/impact/records/{service_id}/revisions`, `/finalize` | Denied |
| GET `/api/impact/records/{service_id}/export` | Denied |

Other methods, unregistered APIs and trailing-slash variants default to 403. Unknown API paths never receive HTML. Public static routing serves only `/`, `/index.html`, `/favicon.svg` and compiled `/assets/`; there is no whole-repository static mount or generic filesystem/SPA fallback. Hash routes need no arbitrary server path fallback. StaticFiles rejects traversal and does not follow links outside its directory.

## Input, runtime and abuse bounds

Public POST bodies are JSON only, at most **64 KiB**, including chunked bodies, with a **10-second total body deadline**. URLs are at most 4,096 characters/bytes as checked by the gate. The existing strict schemas reject nonfinite numbers, extra fields and invalid scenarios; UI validation is secondary. Public decisions allow **10 scenarios and 201 candidate quantities** (three solves including sensitivity), within the unchanged local engine's limits. No external model, solver, subprocess or user code runs per request. Prepared forecasts never fit.

One worker accepts at most 12 concurrent connections/tasks, backlog 64, 5-second keep-alive and bounded incomplete HTTP events. Public computation has **60 POST requests/minute per socket peer**, plus **120/minute globally**, with `429` / `Retry-After: 60`. Forwarded IP headers are ignored. Browser Origins must use HTTP/HTTPS and match the validated Host exactly, allowing TLS termination at the edge without trusting forwarded scheme headers. Hosting proxies therefore share the peer budget; this conservative limit may affect simultaneous judges. Limiter state is bounded and process-local, resets on restart, and is not a distributed WAF or volumetric DDoS defense. No automatic retries loop on 429.

Responses passing through the security gate carry nosniff, frame denial, no-referrer, disabled camera/microphone/geolocation and no-store headers. The public CSP allows same-origin scripts/connections, same-origin/data images and inline styles needed by React/Recharts; it denies objects, external embedding, base changes and cross-origin forms. TLS/HSTS belong to the hosting edge and are not claimed from a localhost test. The runner disables access logging and proxy-header trust. Validation errors omit raw submitted input; unexpected errors use a generic message and log exception class. Do not enter personal data into demonstration forms. No third-party analytics is installed.

## Reproducible isolation

`prepare_public_demo.py` imports only committed, SHA-256 checked public source/evidence/fixtures. It does not read the normal database or download replacements. The prepared forecast JSON matches the published evaluation exactly; mismatched library configuration fails closed, with no startup retraining. Seed capture/import timestamps are fixed **synthetic demonstration metadata**, not proof of service occurrence. Assessment/plan engines and all applied migrations remain unchanged.

Startup validates input hashes, manifest/database digest, migration, counts, source/category identity and normalized forecasting identity. The manifest is a trusted local integrity check, not a cryptographic signature against a compromised operator/host. Demo files/directory must not redirect via symlinks/junctions. Missing state is recreated offline by the public runner. Existing modified/partial state is refused; move the generated `.public-demo` directory aside while the server is stopped before a deliberate rebuild. The command never deletes unknown files or falls back to the local DB.

## Executed checks and remaining limits

See `backend/tests/test_public_demo.py` and the commands/results described in `REPRODUCIBILITY.md`. Direct HTTP tests cover every denied endpoint, unknown/new routes, malformed/oversized/chunked input, rate exhaustion, hostile origins/hosts, ID/cohort enumeration, filesystem paths, DB write rejection, private-local sentinel isolation, idempotency, repeated restart and fresh reseed. The full pre-existing suite is retained. Dependency scans found no known advisories at execution time; locks are not signed supply-chain attestations (Python lock pins versions without wheel hashes).

No authentication, write-capable public account, external penetration test, Linux deployment test, distributed load test or formal accessibility certification was performed. Private operational hosting needs a separate authenticated design, authorization and backup work. Public demonstration safety does not establish real-world waste prevention or independent measurement assurance.

The dependency notice text is served under the reviewed `/assets/` mount and linked from the footer. Render's documented server-side hostname self-reference supplies the same strictly validated environment key; there is no request-derived host configuration. Release evidence is in `evaluation/release_verification.json`. These local checks establish no cloud security certification.
