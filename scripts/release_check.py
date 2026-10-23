"""Offline release gate. Writes deterministic evidence; critical failures exit nonzero."""
import argparse
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

REQUIRED_DOCS = ["README.md", "LICENSE", "data/README.md", "docs/DATA_DICTIONARY.md",
    "docs/ARCHITECTURE.md", "docs/FORECAST_METHODOLOGY.md", "docs/MODEL_EVALUATION.md",
    "docs/DECISION_METHODOLOGY.md", "docs/IMPACT_MEASUREMENT_PROTOCOL.md",
    "docs/IMPACT_EVIDENCE_LIMITATIONS.md", "docs/PUBLIC_DEMO_SECURITY.md",
    "docs/DEPLOYMENT_GUIDE.md", "docs/REPRODUCIBILITY.md", "docs/THIRD_PARTY_LICENSES.md"]


def run_release_checks():
    from app import demo
    from app.config import Settings
    from app.public_policy import PUBLIC_ROUTES, LOCAL_ONLY_ROUTES
    results = {}
    def check(name, operation):
        try:
            value = operation()
            results[name] = {"passed": True, "evidence": value}
        except Exception as exc:
            results[name] = {"passed": False, "error": str(exc)}
    def require(condition, message):
        if not condition:
            raise ValueError(message)
        return True
    check("required_documentation", lambda: require(all((ROOT / p).is_file() and (ROOT / p).stat().st_size > 100 for p in REQUIRED_DOCS), "Required documentation is missing or empty."))
    check("source_and_evidence_fingerprints", demo.verify_files)
    def dependencies():
        locked = {}
        for line in (ROOT / "backend/requirements-lock.txt").read_text().splitlines():
            name, expected = line.strip().split("==")
            installed = importlib.metadata.version(name)
            require(installed == expected, f"Dependency mismatch: {name} expected {expected}, got {installed}.")
            locked[name] = installed
        subprocess.run([sys.executable, "-m", "pip", "check"], check=True, capture_output=True, text=True, cwd=ROOT)
        package = json.loads((ROOT / "frontend/package.json").read_text())
        lock = json.loads((ROOT / "frontend/package-lock.json").read_text())
        for key in ("version", "dependencies", "devDependencies"):
            require(package[key] == lock["packages"][""][key], f"Frontend lock mismatch: {key}")
        require(all(p.get("integrity") for p in lock["packages"].values() if p.get("resolved", "").startswith("https://")), "A resolved npm dependency has no integrity digest.")
        require((ROOT / "frontend/dist/index.html").is_file(), "Compile the production frontend first.")
        return {"python_packages": locked, "npm_lock_sha256": demo.sha(ROOT / "frontend/package-lock.json"), "frontend_version": package["version"]}
    check("dependency_integrity", dependencies)
    saved_env = {key: os.environ.get(key) for key in ("MEALLOOP_MODE", "MEALLOOP_PUBLIC_HOSTS", "MEALLOOP_DATABASE_URL")}
    original_dir = demo.DEMO_DIR
    try:
        # Test artifacts never share the developer's normal operational state.
        with tempfile.TemporaryDirectory(prefix="mealloop-release-") as directory:
            demo.DEMO_DIR = Path(directory) / "public"
            os.environ["MEALLOOP_MODE"] = "PUBLIC_DEMO"
            os.environ["MEALLOOP_PUBLIC_HOSTS"] = "testserver"
            os.environ.pop("MEALLOOP_DATABASE_URL", None)
            def safety():
                os.environ["MEALLOOP_DATABASE_URL"] = "sqlite:///DO-NOT-OPEN.db"
                try:
                    try:
                        Settings.from_env()
                    except ValueError:
                        return True
                    raise ValueError("Public mode accepted a database override.")
                finally:
                    os.environ.pop("MEALLOOP_DATABASE_URL", None)
            check("fail_closed_configuration", safety)
            def smoke():
                manifest = demo.prepare_demo()
                require(demo.prepare_demo() == manifest, "Demo initialization is not idempotent.")
                from app.main import create_app
                from fastapi.routing import iter_route_contexts
                from fastapi.testclient import TestClient
                from sqlalchemy import text
                from sqlalchemy.exc import OperationalError
                app = create_app()
                inventory = {(method, route.path) for route in iter_route_contexts(app.routes)
                    if (getattr(route, "path", "") or "").startswith("/api/") for method in route.methods}
                require(inventory == PUBLIC_ROUTES | LOCAL_ONLY_ROUTES, "Unreviewed API routes detected.")
                denied = []
                with TestClient(app) as client:
                    for method, path in sorted(LOCAL_ONLY_ROUTES):
                        actual = path.replace("{service_id}", "1").replace("{plan_id}", "1")
                        require(client.request(method, actual, json={}).status_code == 403, f"Forbidden endpoint reachable: {method} {path}")
                        denied.append(f"{method} {path}")
                    require(client.get("/").status_code == 200, "SPA missing.")
                    require(client.get("/api/unknown").status_code == 403, "Default-deny failed.")
                    require(client.get("/api/impact/records?source_category=user_reported").status_code == 403, "Private cohort reachable.")
                    require(client.get("/api/impact/records/999").status_code == 404, "Identifier bound failed.")
                    require(client.get("/.env").status_code == 404 and client.get("/docs").status_code == 404, "Private files/debug reachable.")
                    status = client.get("/api/dataset/status").json()
                    require(len(status["batches"]) == 1 and status["batches"][0]["sha256"] == demo.FINGERPRINTS[demo.RAW], "Official source isolation failed.")
                    require(len(client.get("/api/charts").json()["daily"]) == 155, "Measured rows changed.")
                    evaluation = client.get("/api/models/evaluation").json()
                    require(evaluation == json.loads((ROOT / "docs/evaluation/build_02_evaluation.json").read_text()), "Forecast evidence changed.")
                    request = client.get("/api/decisions/demo").json()
                    optimized = client.post("/api/decisions/preview", json=request).json()
                    require(optimized["recommended"]["quantity"] == 440 and optimized["comparison"]["potential_surplus_reduction_kg"] == 16, "Synthetic decision acceptance failed.")
                    fixture = client.get("/api/impact/demo").json()["complete"]
                    assessment = client.post("/api/impact/preview", json=fixture).json()
                    require(assessment["accounting"]["estimated_discarded_kg"] == 8 and assessment["combined_weighed_kg"] == 9.7, "Synthetic accounting separation failed.")
                    records = client.get("/api/impact/records").json()
                    require(len(records) == 2 and all(r["record"]["source_category"] == "synthetic" for r in records), "Private reports entered demo.")
                    forecast = client.post("/api/forecasts/preview", json={"batch_id": 1, "service_date": "2026-10-24", "planned_diners": 400, "menu": 1})
                    require(forecast.status_code == 200 and "id" not in forecast.json(), "Stateless forecast failed.")
                    with app.state.engine.connect() as connection:
                        require(connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0004", "Migration head mismatch.")
                        try:
                            connection.execute(text("DELETE FROM daily_records"))
                        except OperationalError:
                            pass
                        else:
                            raise ValueError("Demo database permits writes.")
                require(demo.sha(demo.DEMO_DIR / "demo.db") == manifest["database_sha256"], "Anonymous preview changed persisted data.")
                with TestClient(create_app()) as client:
                    require(client.get("/api/impact/records").json() == records, "Restart changed immutable demo state.")
                # Simulate a fresh ephemeral filesystem using a second new directory.
                demo.DEMO_DIR = Path(directory) / "reseed"
                require(demo.prepare_demo() == manifest, "Fresh reseed differs from the first build.")
                return {"registered_routes": sorted(f"{m} {p}" for m, p in inventory), "blocked_routes": denied,
                        "migration_head": "0004", "restart_identical": True, "ephemeral_reseed_identical": True,
                        "database_readonly": True, "stateless_previews": True, "measured_rows": 155,
                        "synthetic_recommended_portions": 440, "synthetic_modeled_difference_kg": 16,
                        "synthetic_portion_estimate_kg": 8, "synthetic_scale_inventory_kg": 9.7}
            check("public_http_reproducibility_and_isolation", smoke)
    finally:
        demo.DEMO_DIR = original_dir
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return {"release": "0.5.0", "decision": "READY" if all(v["passed"] for v in results.values()) else "NOT READY",
            "scope": "Local release checks only; cloud deployment, organizer eligibility and independent security certification are outside this check's scope.", "checks": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".run/release-check.json")
    args = parser.parse_args()
    report = run_release_checks()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"decision": report["decision"], "checks": {k: v["passed"] for k, v in report["checks"].items()}}))
    return 0 if report["decision"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
