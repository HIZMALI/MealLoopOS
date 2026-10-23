"""Production-equivalent HTTP/restart smoke in an allowlisted disposable checkout.

No local database, uploads, saved plans or runtime files are copied.
"""
import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".run/http-smoke.json")
    args = parser.parse_args()
    run_dir = ROOT / ".run"
    run_dir.mkdir(exist_ok=True)
    report = {"environment": "Windows local production-equivalent" if os.name == "nt" else sys.platform,
              "cloud_measured": False, "runs": []}
    with tempfile.TemporaryDirectory(prefix="release-http-", dir=run_dir) as folder:
        workspace = Path(folder)
        for directory in ("backend/app", "backend/migrations", "frontend/dist", "data/fixtures", "data/public_demo", "docs/evaluation"):
            shutil.copytree(ROOT / directory, workspace / directory, ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("scripts/serve.py", "data/raw/Food waste data school Finland 2024-2025.xlsx"):
            target = workspace / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        for index, label in enumerate(("fresh_seed", "prepared_restart", "ephemeral_reseed")):
            if index == 2:
                target = workspace / ".public-demo"
                assert target.resolve().parent == workspace.resolve()
                target.rename(workspace / ".public-demo-previous")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = {**os.environ, "MEALLOOP_MODE": "PUBLIC_DEMO", "MEALLOOP_PUBLIC_HOSTS": "127.0.0.1", "PORT": str(port),
                   "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
            env.pop("MEALLOOP_DATABASE_URL", None)
            with (workspace / f"{label}.log").open("w", encoding="utf-8") as log:
                start = time.perf_counter()
                process = subprocess.Popen([sys.executable, "scripts/serve.py"], cwd=workspace, env=env, stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                base = f"http://127.0.0.1:{port}"
                def request(path, data=None, headers=None):
                    req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                        headers={"Content-Type": "application/json", **(headers or {})})
                    try:
                        with urllib.request.urlopen(req, timeout=5) as response:
                            return response.status, response.read(), dict(response.headers)
                    except urllib.error.HTTPError as error:
                        return error.code, error.read(), dict(error.headers)
                try:
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError("Release server exited; inspect the smoke log.")
                        try:
                            status, body, _ = request("/api/health")
                            if status == 200:
                                break
                        except (OSError, urllib.error.URLError):
                            pass
                        if time.perf_counter() - start > 45:
                            raise RuntimeError("Release startup exceeded 45 seconds.")
                        time.sleep(0.1)
                    elapsed = time.perf_counter() - start
                    database = workspace / ".public-demo/demo.db"
                    database_before = hashlib.sha256(database.read_bytes()).hexdigest()
                    assert request("/")[0] == 200
                    assert request("/assets/third-party-notices.txt")[0] == 200
                    assert request("/api/config")[0] == 200
                    assert request("/api/health", headers={"Host": "attacker.invalid"})[0] == 400
                    assert request("/api/decisions/preview", {}, {"Origin": "https://attacker.invalid"})[0] == 403
                    assert request("/api/dataset/import", {})[0] == 403
                    assert request("/api/models/train", {})[0] == 403
                    assert request("/api/impact/records/1/finalize", {"expected_version": 2})[0] == 403
                    assert request("/api/forecasts", {})[0] == 403
                    assert request("/.env")[0] == 404
                    assert request("/api/unclassified")[0] == 403
                    assert request("/api/impact/records?source_category=user_reported")[0] == 403
                    assert request("/api/overview?batch_id=2")[0] == 403
                    _, body, _ = request("/api/decisions/demo")
                    _, optimized, _ = request("/api/decisions/preview", json.loads(body))
                    assert json.loads(optimized)["recommended"]["quantity"] == 440
                    assert json.loads(optimized)["comparison"]["potential_surplus_reduction_kg"] == 16
                    status, forecast, _ = request("/api/forecasts/preview", {"batch_id": 1, "service_date": "2026-10-24", "planned_diners": 400, "menu": 1})
                    assert status == 200 and "id" not in json.loads(forecast)
                    _, fixture, _ = request("/api/impact/demo")
                    status, preview, _ = request("/api/impact/preview", json.loads(fixture)["complete"])
                    assert status == 200 and json.loads(preview)["accounting"]["estimated_discarded_kg"] == 8
                    _, body, _ = request("/api/impact/records/1")
                    record = json.loads(body)
                    assert record["assessment"]["combined_weighed_kg"] == 9.7
                    _, before, _ = request("/api/overview")
                    if index == 0:
                        reference = before
                    assert before == reference
                    assert hashlib.sha256(database.read_bytes()).hexdigest() == database_before
                    run = {"kind": label, "startup_to_http_health_seconds": round(elapsed, 3), "http_checks_passed": True,
                           "invalid_host_rejected": True, "foreign_origin_rejected": True, "private_cohort_denied": True,
                           "all_three_previews_stateless": True, "database_hash_unchanged": True, "third_party_notices_served": True}
                    if os.name == "nt":
                        # Sample the launcher and its child, not unrelated Python processes.
                        command = f"$p=Get-CimInstance Win32_Process; $ids=@({process.pid}); do {{ $new=@($p | Where-Object {{ $_.ParentProcessId -in $ids -and $_.ProcessId -notin $ids }} | Select-Object -ExpandProperty ProcessId); $ids+=$new }} while($new.Count -gt 0); Get-Process -Id $ids | Select-Object WorkingSet64,PeakWorkingSet64 | ConvertTo-Json -Compress"
                        samples = json.loads(subprocess.check_output(["powershell", "-NoProfile", "-Command", command], text=True))
                        if isinstance(samples, dict):
                            samples = [samples]
                        run["sampled_process_tree_working_set_mib"] = round(sum(p["WorkingSet64"] for p in samples) / 1024**2, 2)
                        run["sampled_process_tree_peak_working_set_mib"] = round(sum(p["PeakWorkingSet64"] for p in samples) / 1024**2, 2)
                    report["runs"].append(run)
                finally:
                    if process.poll() is None:
                        if os.name == "nt":
                            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                        else:
                            process.terminate()
                        process.wait(timeout=10)
    report["passed"] = len(report["runs"]) == 3
    path = args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
