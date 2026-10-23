# Running and deployment

Windows local execution is verified with Python 3.14.0 and Node 24.13.1. Linux installation, Render execution, managed TLS/edge behavior and hosting quotas remain unverified. No Render resource or live hosted URL is claimed.

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

`render.yaml` defines one native Python **free** web service, branch `main`, automatic deploys off, no disk/database, exact Python/Node versions and PUBLIC_DEMO only. It is configuration, not evidence of deployment. Creating a host is a separate action; repository publication does not create one.

[Render's Blueprint reference](https://render.com/docs/blueprint-spec#self-referencing-environment-variables) documents mapping a service's default variable to another key. [Default variables](https://render.com/docs/environment-variables#render_external_hostname) define the assigned public hostname. The configuration uses:

```yaml
- key: MEALLOOP_PUBLIC_HOSTS
  fromService:
    name: mealloop-os-demo
    type: web
    envVarKey: RENDER_EXTERNAL_HOSTNAME
```

Keep the reference name equal to the service name. This uses the assigned public hostname, not private-network `property: host`. Do not invent a hostname, allow wildcards, trust request headers for configuration or disable validation. Blueprint references refresh on sync. Their actual cloud resolution remains unverified here.

Build command:

```sh
python -m pip install -r backend/requirements-lock.txt && npm --prefix frontend ci && npm --prefix frontend run build && python scripts/prepare_public_demo.py && python scripts/release_check.py
```

Start command: `python scripts/serve.py`. Health check: `/api/health`. Runtime pins use [Python version selection](https://render.com/docs/python-version) and [Node version selection](https://render.com/docs/node-version); binding follows [FastAPI deployment guidance](https://render.com/docs/deploy-fastapi).

For a later authorized Blueprint deployment: connect the actual public repository, select `main` and root `render.yaml`; review exactly one Free web service and no database/disk before creating it. Never import private environment groups, `.env` or backups. Abort on a paid upgrade or payment requirement. Check exact runtime versions, installed locks, all release gates, assigned hostname, TLS/health, all four tools, blocked writes and restart/idle wake behavior. Do not weaken security to make health pass.

Manual Dashboard fallback: New Web Service, repository root, Python 3 runtime, Free instance, auto-deploy Off, health `/api/health`, the same Build command; set `PYTHON_VERSION=3.14.0`, `NODE_VERSION=24.13.1`, `MEALLOOP_MODE=PUBLIC_DEMO`, `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`. Without a Blueprint reference, the POSIX Start command can use the server-provided hostname:

```sh
test -n "$RENDER_EXTERNAL_HOSTNAME" && MEALLOOP_PUBLIC_HOSTS="$RENDER_EXTERNAL_HOSTNAME" python scripts/serve.py
```

Alternatively copy the actual assigned hostname into `MEALLOOP_PUBLIC_HOSTS` and use the ordinary Start command. An environment value containing a literal `$RENDER_EXTERNAL_HOSTNAME` is not shell interpolation. No Linux/Render shell command above was executed in this release.

[Free-service documentation](https://render.com/docs/free) describes idle sleep, wake latency, ephemeral storage and quotas. Reseeding avoids durable demo storage, but does not guarantee availability. Recheck current terms/account requirements before deploying. Opening the demo before a presentation is a preparation step, not an uptime guarantee.

## Verification and remaining gates

Run `scripts/release_check.py`, `scripts/smoke_release.py` and the commands in `REPRODUCIBILITY.md`. Critical gate failure means NOT READY. HTTP smoke records three actual local production processes: fresh seed, prepared restart and fresh reseed. Windows startup/memory samples are not Linux container, Render cold-start or sustained-load measurements.

Before claiming a deployed release, execute Linux dependency installation and binary-notice review, provider configuration validation, exact edge Host/Origin/TLS checks, free quota/account checks, resource/concurrency measurements and remote cold-start/restart tests. No provider validator, cloud deployment, external penetration/load test or security certification is claimed.
