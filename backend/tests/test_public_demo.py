"""Direct HTTP adversarial regression checks; UI hiding is not authorization."""
import asyncio
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastapi.routing import iter_route_contexts
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app import demo
from app.config import Settings
from app.main import create_app
from app.public_policy import PUBLIC_ROUTES, LOCAL_ONLY_ROUTES
from app.security import PublicLimiter, SecurityMiddleware


@pytest.fixture(scope="session")
def prepared(tmp_path_factory):
    original = demo.DEMO_DIR
    demo.DEMO_DIR = tmp_path_factory.mktemp("isolated-public")
    try:
        demo.prepare_demo()
        yield demo.DEMO_DIR
    finally:
        demo.DEMO_DIR = original


@pytest.fixture
def frontend_stub(tmp_path, monkeypatch):
    # Backend routing tests do not require npm/build artifacts. Real compiled
    # React is separately exercised by production HTTP and browser checks.
    from app import main
    root = tmp_path / "static-routing-fixture"
    dist = root / "frontend/dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<div id="root"></div><script src="/assets/index-test.js"></script>')
    (dist / "assets/index-test.js").write_text("// Static routing test fixture only\n")
    (dist / "favicon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    (dist / "template.csv").write_text("plate_waste_kg,kitchen_serving_waste_kg,diners\n")
    monkeypatch.setattr(main, "ROOT", root)
    return root


@pytest.fixture
def public_env(tmp_path, monkeypatch, prepared, frontend_stub):
    destination = tmp_path / "public"
    shutil.copytree(prepared, destination)
    monkeypatch.setattr(demo, "DEMO_DIR", destination)
    monkeypatch.setenv("MEALLOOP_MODE", "PUBLIC_DEMO")
    monkeypatch.setenv("MEALLOOP_PUBLIC_HOSTS", "testserver,127.0.0.1")
    monkeypatch.delenv("MEALLOOP_DATABASE_URL", raising=False)
    return destination


@pytest.fixture
def public(public_env):
    with TestClient(create_app()) as client:
        yield client


def api_inventory(app):
    return {(method, route.path) for route in iter_route_contexts(app.routes)
            if (getattr(route, "path", "") or "").startswith("/api/")
            for method in route.methods}


def test_all_registered_api_routes_classified(client):
    assert not PUBLIC_ROUTES & LOCAL_ONLY_ROUTES
    assert api_inventory(client.app) == PUBLIC_ROUTES | LOCAL_ONLY_ROUTES


@pytest.mark.parametrize("method,path", sorted(LOCAL_ONLY_ROUTES))
def test_every_persistence_and_export_endpoint_denied(public, method, path):
    path = path.replace("{plan_id}", "1").replace("{service_id}", "1")
    before = demo.sha(demo.DEMO_DIR / "demo.db")
    r = public.request(method, path, json={})
    assert r.status_code == 403
    assert demo.sha(demo.DEMO_DIR / "demo.db") == before


@pytest.mark.parametrize("method,path", [("GET", "/api/unreviewed"), ("PUT", "/api/overview"),
    ("DELETE", "/api/impact/records/1"), ("PATCH", "/api/decisions/plans/1"),
    ("POST", "/api/decisions/preview/"), ("OPTIONS", "/api/overview")])
def test_default_deny(public, method, path):
    assert public.request(method, path).status_code == 403


def test_new_registered_route_cannot_inherit_permission(public_env):
    app = create_app()
    @app.get("/api/new-feature")
    def unreviewed():
        raise AssertionError("Must never execute")
    assert ("GET", "/api/new-feature") not in PUBLIC_ROUTES
    assert api_inventory(app) - PUBLIC_ROUTES - LOCAL_ONLY_ROUTES == {("GET", "/api/new-feature")}
    with TestClient(app) as c:
        assert c.get("/api/new-feature").status_code == 403


def test_added_route_overlapping_reviewed_template_is_denied(public_env):
    app = create_app()
    @app.get("/api/impact/records/secret/export")
    def secret():
        return {"secret": True}
    with TestClient(app) as c:
        assert c.get("/api/impact/records/secret/export").status_code == 403


@pytest.mark.parametrize("path", ["/api/overview?batch_id=2", "/api/charts?batch_id=999",
    "/api/dataset/status?batch_id=1&batch_id=2", "/api/impact/records?source_category=user_reported",
    "/api/impact/summary?source_category=user_reported_documented", "/api/impact/records?source_category=synthetic&source_category=user_reported"])
def test_private_cohort_and_batch_reference_denied(public, path):
    assert public.get(path).status_code == 403


@pytest.mark.parametrize("path", ["/api/impact/records/3", "/api/impact/records/999/history",
    "/api/impact/records/03/quality", "/api/decisions/plans/2", "/api/decisions/plans/01"])
def test_identifiers_are_bounded(public, path):
    assert public.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/.env", "/data/mealloop.db",
    "/backend/app/main.py", "/.public-demo/demo.db", "/assets/%2e%2e/%2e%2e/.env", "/template.csv", "/unknown/spa", "/api/unknown"])
def test_no_files_or_debug_fallback(public, path):
    assert public.get(path).status_code in (403, 404)


def test_real_source_and_synthetic_cohort_only(public):
    status = public.get("/api/dataset/status").json()
    assert len(status["batches"]) == 1
    assert status["batches"][0]["sha256"] == demo.FINGERPRINTS[demo.RAW]
    assert status["batches"][0]["source"]["kind"] == "measured"
    assert status["batches"][0]["source"]["license"] == "CC BY 4.0"
    assert len(public.get("/api/charts").json()["daily"]) == 155
    records = public.get("/api/impact/records").json()
    assert len(records) == 2
    assert all(r["record"]["source_category"] == "synthetic" for r in records)
    assert public.get("/api/impact/records/1").json()["assessment"]["combined_weighed_kg"] == 9.7
    assert public.get("/api/impact/records/1").json()["assessment"]["accounting"]["estimated_discarded_kg"] == 8
    assert not public.get("/api/impact/records/2").json()["assessment"]["can_finalize"]


def test_stateless_previews_reproduce_without_saving(public):
    before = demo.sha(demo.DEMO_DIR / "demo.db")
    data = public.get("/api/decisions/demo").json()
    result = public.post("/api/decisions/preview", json=data).json()
    assert result["recommended"]["quantity"] == 440
    assert result["comparison"]["potential_surplus_reduction_kg"] == 16
    data["reliability_target"] = 0.7
    altered = public.post("/api/decisions/preview", json=data)
    assert altered.status_code == 200
    assert altered.json()["recommended"]["quantity"] == 400
    fixture = public.get("/api/impact/demo").json()["complete"]
    assessment = public.post("/api/impact/preview", json=fixture)
    assert assessment.status_code == 200
    assert assessment.json()["accounting"]["remaining_portions"] == 40
    forecast = public.post("/api/forecasts/preview", json={"batch_id": 1, "service_date": "2026-10-24", "planned_diners": 400, "menu": 1})
    assert forecast.status_code == 200
    assert forecast.json()["label"] == "Forecast / Model estimate"
    assert "id" not in forecast.json()
    assert demo.sha(demo.DEMO_DIR / "demo.db") == before


def test_private_inputs_cannot_supply_demo_references(public):
    fixture = public.get("/api/impact/demo").json()["complete"]
    assert public.post("/api/impact/preview", json={**fixture, "source_category": "user_reported"}).status_code == 403
    assert public.post("/api/impact/preview", json={**fixture, "decision_plan_id": 99}).status_code == 403
    assert public.post("/api/impact/comparison", json={"source_category": "user_reported"}).status_code == 403


def test_readonly_database_is_a_second_barrier(public):
    with public.app.state.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA query_only").scalar() == 1
        with pytest.raises(OperationalError):
            connection.execute(text("DELETE FROM daily_records"))


def test_mode_is_only_server_controlled(public, monkeypatch):
    assert public.get("/api/config?mode=LOCAL", headers={"X-MealLoop-Mode": "LOCAL"}).json()["mode"] == "PUBLIC_DEMO"
    monkeypatch.setenv("MEALLOOP_MODE", "LOCAL")
    with TestClient(create_app("sqlite:///:memory:")) as local:
        assert local.get("/api/config?mode=PUBLIC_DEMO").json()["mode"] == "LOCAL"


@pytest.mark.parametrize("mode", ["public_demo", "", "PRODUCTION", "LOCAL "])
def test_invalid_modes_fail_closed(monkeypatch, mode):
    monkeypatch.setenv("MEALLOOP_MODE", mode)
    with pytest.raises(ValueError):
        Settings.from_env()


@pytest.mark.parametrize("hosts", ["", "*", "*.example.com", "https://example.com", "example.com:443", "a,,b", "../local"])
def test_public_hosts_must_be_explicit(monkeypatch, hosts):
    monkeypatch.setenv("MEALLOOP_MODE", "PUBLIC_DEMO")
    monkeypatch.setenv("MEALLOOP_PUBLIC_HOSTS", hosts)
    with pytest.raises(ValueError):
        Settings.from_env()


def test_public_forbids_any_database_override(public_env, monkeypatch, tmp_path):
    local = tmp_path / "private.db"
    local.write_bytes(b"private sentinel")
    monkeypatch.setenv("MEALLOOP_DATABASE_URL", f"sqlite:///{local.as_posix()}")
    with pytest.raises(ValueError):
        create_app()
    monkeypatch.delenv("MEALLOOP_DATABASE_URL")
    with pytest.raises(ValueError):
        create_app(f"sqlite:///{local.as_posix()}")
    assert local.read_bytes() == b"private sentinel"


def test_init_restart_and_ephemeral_reset(public_env):
    first = demo.validate_demo()
    assert demo.prepare_demo() == first
    with TestClient(create_app()) as c:
        original = c.get("/api/impact/records/1").json()
    with TestClient(create_app()) as c:
        assert c.get("/api/impact/records/1").json() == original
    # Only our known disposable fixture directory is reset in this test.
    (public_env / "demo.db").unlink()
    (public_env / "manifest.json").unlink()
    assert demo.prepare_demo() == first


def test_missing_or_corrupt_demo_never_falls_back(public_env):
    db = public_env / "demo.db"
    db.write_bytes(db.read_bytes() + b"corruption")
    with pytest.raises(ValueError):
        create_app()
    with pytest.raises(ValueError):
        demo.prepare_demo()


def test_all_source_evidence_fingerprints():
    assert demo.verify_files() == demo.FINGERPRINTS
    bundle = json.loads((demo.ROOT / demo.ARTIFACT).read_text(encoding="utf-8"))
    assert bundle["evaluation"] == json.loads((demo.ROOT / "docs/evaluation/build_02_evaluation.json").read_text(encoding="utf-8"))


def test_fixture_checksum_failure(tmp_path, monkeypatch):
    relative = "data/fixtures/synthetic_impact_demo.json"
    fixture = tmp_path / relative
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes((demo.ROOT / relative).read_bytes() + b" ")
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    monkeypatch.setattr(demo, "FINGERPRINTS", {relative: demo.FINGERPRINTS[relative]})
    with pytest.raises(ValueError, match="fingerprint"):
        demo.verify_files()


def test_request_bounds_and_origin(public):
    assert public.post("/api/decisions/preview", content=b"x" * 65537, headers={"Content-Type": "application/json"}).status_code == 413
    assert public.post("/api/decisions/preview", content="{}", headers={"Content-Type": "text/plain"}).status_code == 415
    assert public.post("/api/decisions/preview", json={}, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert public.post("/api/decisions/preview", json={}, headers={"Origin": "https://[invalid"}).status_code == 403
    assert public.get("/api/overview?x=" + "x" * 4100).status_code == 414
    assert public.get("/api/decisions/plans?offset=" + "9" * 1000).status_code == 422
    assert public.get("/api/health", headers={"Host": "attacker.example"}).status_code == 400
    data = public.get("/api/decisions/demo").json()
    data["maximum_capacity"] = 10000
    data["batch_increment"] = 1
    assert public.post("/api/decisions/preview", json=data).status_code == 422
    assert public.post("/api/decisions/preview", content="[" * 2000, headers={"Content-Type": "application/json"}).status_code == 422
    data["maximum_capacity"] = 10**1000
    assert public.post("/api/decisions/preview", json=data).status_code == 422
    data = public.get("/api/decisions/demo").json()
    data["demand_scenarios"] = [{"name": f"Scenario {i}", "demand_portions": 400, "probability": 1/11} for i in range(11)]
    assert public.post("/api/decisions/preview", json=data).status_code == 422


def test_tls_termination_origin_without_trusting_forwarded_headers(public):
    data = public.get("/api/decisions/demo").json()
    assert public.post("/api/decisions/preview", json=data, headers={"Origin": "https://testserver"}).status_code == 200
    assert public.post("/api/decisions/preview", json=data, headers={"Origin": "https://attacker.example", "X-Forwarded-Host": "attacker.example"}).status_code == 403


def test_public_rate_limit_direct_requests(public):
    for _ in range(60):
        assert public.post("/api/decisions/preview", json={}).status_code == 422
    blocked = public.post("/api/decisions/preview", json={}, headers={"X-Forwarded-For": "8.8.8.8"})
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "60"
    assert public.get("/api/health").status_code == 200


def test_limiter_global_budget_and_window():
    limiter = PublicLimiter()
    assert all(limiter.allow(str(i), now=100) for i in range(120))
    assert not limiter.allow("new", now=100)
    assert limiter.allow("new", now=161)
    assert len(limiter.clients) == 1


def test_security_headers_and_same_origin(public):
    response = public.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert "access-control-allow-origin" not in public.get("/api/health", headers={"Origin": "https://attacker.example"}).headers
    assert "database" not in public.get("/api/health").json()
    assert "path" not in public.get("/api/config").text.lower()


def test_spa_routes_use_hash_and_static_assets(public, monkeypatch):
    response = public.get("/#demo")
    assert response.status_code == 200 and '<div id="root">' in response.text
    import re
    script = re.search(r'src="(/assets/[^\"]+\.js)"', response.text)[1]
    assert public.get(script).status_code == 200
    assert public.get("/api/missing").headers["content-type"].startswith("application/json")
    assert public.get("/template.csv").status_code == 404
    monkeypatch.setenv("MEALLOOP_MODE", "LOCAL")
    with TestClient(create_app("sqlite:///:memory:")) as local:
        template = local.get("/template.csv")
        assert template.status_code == 200 and "diners" in template.text


def test_local_preserved_and_remote_peers_blocked(client):
    assert client.get("/docs").status_code == 200
    fixture = json.loads((demo.ROOT / "data/fixtures/synthetic_decision_demo.json").read_text())
    saved = client.post("/api/decisions/plans", json=fixture, headers={"Origin": "http://127.0.0.1:15173"})
    assert saved.status_code == 201
    assert client.get(f"/api/decisions/plans/{saved.json()['id']}/export?format=csv").status_code == 200
    assert client.post("/api/dataset/import", headers={"Origin": "https://attacker.example"}).status_code == 403
    with TestClient(client.app, client=("203.0.113.12", 1234)) as remote:
        assert remote.get("/api/health").status_code == 403


def test_public_cannot_read_or_modify_local_reports(tmp_path, monkeypatch, prepared, frontend_stub):
    monkeypatch.setenv("MEALLOOP_MODE", "LOCAL")
    local_db = tmp_path / "private-local.db"
    with TestClient(create_app(f"sqlite:///{local_db.as_posix()}")) as local:
        record = local.get("/api/impact/demo").json()["incomplete"]
        record.update(source_category="user_reported", operator_notes="PRIVATE-SENTINEL-917")
        assert local.post("/api/impact/records", json=record).status_code == 201
    before = demo.sha(local_db)
    monkeypatch.setenv("MEALLOOP_MODE", "PUBLIC_DEMO")
    monkeypatch.setenv("MEALLOOP_PUBLIC_HOSTS", "testserver")
    monkeypatch.setattr(demo, "DEMO_DIR", prepared)
    with TestClient(create_app()) as public:
        for path in ("/api/impact/records", "/api/impact/summary", "/api/impact/records/1/history"):
            assert "PRIVATE-SENTINEL" not in public.get(path).text
        assert public.post("/api/impact/records/1/finalize", json={"expected_version": 1}).status_code == 403
    assert demo.sha(local_db) == before


def test_chunked_request_is_bounded_before_handler(public_env):
    from app.config import Settings
    called = []
    async def endpoint(scope, receive, send):
        called.append(True)
    middleware = SecurityMiddleware(endpoint, Settings("PUBLIC_DEMO", ("testserver",)), create_app().routes)
    chunks = iter([{"type": "http.request", "body": b"x" * 40000, "more_body": True},
                   {"type": "http.request", "body": b"x" * 40000, "more_body": False}])
    async def receive():
        return next(chunks)
    messages = []
    async def send(message):
        messages.append(message)
    asyncio.run(middleware({"type": "http", "path": "/api/decisions/preview", "method": "POST", "root_path": "",
                           "headers": [(b"content-type", b"application/json")], "query_string": b"", "scheme": "http", "client": ("127.0.0.1", 1)}, receive, send))
    assert not called and messages[0]["status"] == 413


def test_unexpected_error_message_does_not_disclose_private_details(client, caplog):
    @client.app.get("/api/test-error")
    def error():
        raise RuntimeError("PRIVATE-SECRET-SENTINEL")
    with TestClient(client.app, raise_server_exceptions=False) as safe_client:
        response = safe_client.get("/api/test-error")
    assert response.status_code == 500
    assert "PRIVATE-SECRET" not in response.text
    assert "PRIVATE-SECRET" not in caplog.text


def test_release_gate_reports_not_ready_on_missing_document(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("mealloop_release_check", demo.ROOT / "scripts/release_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "REQUIRED_DOCS", ["docs/THIS-FILE-MUST-NOT-EXIST.md"])
    report = module.run_release_checks()
    assert report["decision"] == "NOT READY"
    assert report["checks"]["required_documentation"]["passed"] is False


def test_public_unexpected_error_is_generic_and_has_security_headers(public_env, monkeypatch, caplog):
    from app import security
    app = create_app()
    @app.get("/api/test-error")
    def failure():
        raise RuntimeError("PRIVATE-PREVIEW-INPUT")
    monkeypatch.setattr(security, "PUBLIC_ROUTES", security.PUBLIC_ROUTES | {("GET", "/api/test-error")})
    with TestClient(app) as c:
        response = c.get("/api/test-error")
    assert response.status_code == 500
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "PRIVATE-PREVIEW-INPUT" not in response.text + caplog.text
