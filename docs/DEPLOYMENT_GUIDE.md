# Running and deployment

The public demonstration is available at [mealloop-os-demo.onrender.com](https://mealloop-os-demo.onrender.com/#demo). Windows local execution and Render's native Linux build/runtime are verified with Python 3.14.0 and Node 24.13.1. The hosted service is read-only; LOCAL remains a private workstation mode.

## Local development

Follow README setup, then run `scripts/start.ps1`. It selects LOCAL and serves the backend on loopback 8080 and Vite on 15173. Existing listeners are not killed. LOCAL is an unauthenticated private workspace; never place it behind a public proxy.

The setup script installs `backend/requirements-lock.txt` and uses `npm ci`. The broader `requirements.txt` records development ranges; the exact lock is required for the prepared public predictor's configuration identity. Do not bypass that check or retrain on startup.

## Compiled isolated demonstration

Build the frontend and prepare the demo, then select an unused port:

```powershell
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe scripts\prepare_public_demo.py
.\.venv\Scripts\python.exe scripts\release_check.py
$env:MEALLOOP_MODE = 'PUBLIC_DEMO'
$env:MEALLOOP_PUBLIC_HOSTS = '127.0.0.1'
$env:PORT = '18085'
Remove-Item Env:MEALLOOP_DATABASE_URL -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe scripts\serve.py
```

Open `http://127.0.0.1:18085/#demo`. The compiled frontend/API share one origin. PUBLIC_DEMO binds 0.0.0.0 but accepts only configured exact Host names. It uses a server-fixed generated read-only DB and never the normal `data/mealloop.db`. Missing demo state is recreated offline; modified/partial state fails closed. To rebuild deliberately, stop the server and move only its generated `.public-demo` directory aside. Never substitute a local operational backup.

`MEALLOOP_DATABASE_URL` is forbidden in public mode, even if empty. `PORT` must be an ASCII integer from 1024 to 65535. The runner uses one worker, ignores proxy headers and disables access logging. `GET /api/health` returns safe readiness/capability information after startup validates the demo. Private filesystem paths and configuration are not exposed.

For a compiled LOCAL application, set `MEALLOOP_MODE=LOCAL` and run `python scripts/serve.py`; it uses loopback 8080 and local write workflows. Production uses built files, not Vite dev/preview.

## Render configuration

`render.yaml` defines one native Python **Free** web service, branch `main`, automatic deploys off, no permanent disk or separate database, exact Python/Node versions and PUBLIC_DEMO only. The authenticated Dashboard confirmed these settings on 23 October 2026. Blueprint automatic synchronization is also paused. No paid resource, upgrade or payment information was used.

[Render's Blueprint reference](https://render.com/docs/blueprint-spec#self-referencing-environment-variables) documents mapping a service's default variable to another key. [Default variables](https://render.com/docs/environment-variables#render_external_hostname) define the assigned public hostname. The configuration uses:

```yaml
- key: MEALLOOP_PUBLIC_HOSTS
  fromService:
    name: mealloop-os-demo
    type: web
    envVarKey: RENDER_EXTERNAL_HOSTNAME
```

Keep the reference name equal to the service name. This uses the assigned public hostname, not private-network `property: host`. Do not invent a hostname, allow wildcards, trust request headers for configuration or disable validation. Blueprint references refresh on sync. The deployed value was inspected and equals `mealloop-os-demo.onrender.com`.

Build command:

```sh
python -m pip install -r backend/requirements-lock.txt && npm --prefix frontend ci && npm --prefix frontend run build && python scripts/prepare_public_demo.py && python scripts/release_check.py
```

Start command: `python scripts/serve.py`. Health check: `/api/health`. Runtime pins use [Python version selection](https://render.com/docs/python-version) and [Node version selection](https://render.com/docs/node-version); binding follows [FastAPI deployment guidance](https://render.com/docs/deploy-fastapi).

To reproduce the Blueprint deployment: connect the public repository, select `main` and root `render.yaml`; review exactly one Free web service and no database/disk before creating it. Never import private environment groups, `.env` or backups. Abort on a paid upgrade or payment requirement. Check exact runtime versions, installed locks, all release gates, assigned hostname, TLS/health, all four tools, blocked writes and restart/idle wake behavior. Do not weaken security to make health pass.

Manual Dashboard fallback: New Web Service, repository root, Python 3 runtime, Free instance, auto-deploy Off, health `/api/health`, the same Build command; set `PYTHON_VERSION=3.14.0`, `NODE_VERSION=24.13.1`, `MEALLOOP_MODE=PUBLIC_DEMO`, `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`. Without a Blueprint reference, the POSIX Start command can use the server-provided hostname:

```sh
test -n "$RENDER_EXTERNAL_HOSTNAME" && MEALLOOP_PUBLIC_HOSTS="$RENDER_EXTERNAL_HOSTNAME" python scripts/serve.py
```

Alternatively copy the actual assigned hostname into `MEALLOOP_PUBLIC_HOSTS` and use the ordinary Start command. An environment value containing a literal `$RENDER_EXTERNAL_HOSTNAME` is not shell interpolation. The Blueprint Build and Start commands were executed on Render; the manual fallback above was not exercised.

[Free-service documentation](https://render.com/docs/free) describes idle sleep, wake latency, ephemeral storage and quotas. Reseeding avoids durable demo storage, but does not guarantee availability. Recheck current terms/account requirements before deploying. Opening the demo before a presentation is a preparation step, not an uptime guarantee.

## Executed cloud verification and remaining limits

Run `scripts/release_check.py`, `scripts/smoke_release.py` and the commands in `REPRODUCIBILITY.md`. Critical gate failure means NOT READY. HTTP smoke records three actual local production processes: fresh seed, prepared restart and fresh reseed. Windows startup/memory samples are not Linux container, Render cold-start or sustained-load measurements.

On 23 October 2026, the native Linux build installed the exact Python lock, ran `npm ci` (zero reported vulnerabilities), compiled the production frontend, prepared the isolated demo and passed every `release_check.py` gate. Logs confirmed successful application startup and the assigned HTTPS URL. The first bootstrap attempt failed closed while `MEALLOOP_PUBLIC_HOSTS` was unavailable; a second deployment of the same application commit succeeded after the Blueprint reference resolved. No Host protection was relaxed.

External HTTPS checks used ordinary certificate validation. Health returned 200, configuration reported PUBLIC_DEMO/read-only, the official workbook hash and 155 days matched, and the forecast evaluation matched the frozen JSON. Desktop and 390px browser checks opened all four modules without critical console errors. Live previews reproduced 440 portions at 95%, 400 at 70% with 12 expected unserved portions, and the separate synthetic 8 kg estimate, 7.6 kg surplus reading and 9.7 kg disjoint total. No synthetic example is an operational pilot.

Eight write-route probes, private/debug/file paths, unknown API routes and private-cohort requests were denied. Same-origin previews succeeded, foreign Origin was rejected, and saved examples were unchanged after previews. An invalid Host received 403 at the public endpoint; this may be Render's edge rejection, while direct application Host rejection is covered locally. No database override, secret files or linked private environment group was configured.

The Dashboard accepted a service restart and the external checks passed again afterward. Fresh seed, prepared restart and explicit ephemeral reseed were also exercised in three local production processes. Cloud idle wake and deliberate loss of the generated cloud state remain unverified. The Dashboard shows a 512 MB memory limit and 0.15 CPU; actual memory/CPU charts require paid compute, so no cloud memory measurement is claimed. Windows RSS samples do not substitute for one.

Free-plan limits and availability can change; observed deployment does not guarantee future quota capacity or uptime. Optional Linux binary notices have not received the same filesystem-level inspection as the retained Windows dependency inventory. No external penetration/load test, cloud shell inspection, formal accessibility certification or security certification is claimed. Full executed check details and preserved scientific hashes are in `evaluation/release_verification.json`.
