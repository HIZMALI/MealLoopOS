import csv
import hashlib
import io
import json
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.database import ROOT, make_engine, migrate
from app.decision_schemas import DecisionPreview, SavedPlan
from app.decision_service import demo_request
from app.main import create_app


def demo():
    return demo_request().model_dump(mode="json")


def test_empty_database_preview_and_save_are_independent_from_forecasting(client):
    with patch("app.forecast_service.evaluate", side_effect=AssertionError("Decision Studio cannot fit a waste model")), \
         patch("app.forecast_service.predict_production", side_effect=AssertionError("Cannot infer demand from waste")):
        assert client.get("/api/models/status").json()["status"] == "empty"
        assert client.get("/api/dataset/status").json()["status"] == "empty"
        fixture = client.get("/api/decisions/demo")
        assert fixture.status_code == 200 and fixture.json() == demo()
        assert fixture.json()["scenario_kind"] == "synthetic_demo"
        meta = client.get("/api/decisions/metadata").json()
        assert meta["evidence_type"] == "assumption_based"
        result = client.post("/api/decisions/preview", json=demo())
        assert result.status_code == 200, result.text
        DecisionPreview.model_validate(result.json())
        assert result.json()["recommended"]["quantity"] == 440
        assert client.get("/api/decisions/plans").json() == []
        saved = client.post("/api/decisions/plans", json=demo())
        assert saved.status_code == 201, saved.text
        SavedPlan.model_validate(saved.json())
        assert saved.json()["context_reference"] is None
        assert saved.json()["result"] == result.json()
        assert client.get("/api/dataset/status").json()["status"] == "empty"
        assert client.get("/api/models/status").json()["status"] == "empty"


def test_immutable_snapshots_listing_export_and_restart(tmp_path):
    url = f"sqlite:///{(tmp_path / 'plans.db').as_posix()}"
    with TestClient(create_app(url)) as client:
        first = client.post("/api/decisions/plans", json=demo()).json()
        altered = {**demo(), "reliability_target": 0.7, "scenario_kind": "user_assumptions", "title": '=HYPERLINK("malicious")'}
        altered["demand_scenarios"][0]["name"] = "+SUM(1,1)"
        second = client.post("/api/decisions/plans", json=altered).json()
        assert first["id"] != second["id"]
        assert second["result"]["recommended"]["quantity"] == 400
        assert client.get(f'/api/decisions/plans/{first["id"]}').json() == first
        assert client.put(f'/api/decisions/plans/{first["id"]}', json=altered).status_code == 405
        assert client.delete(f'/api/decisions/plans/{first["id"]}').status_code == 405
        items = client.get("/api/decisions/plans?limit=1&offset=0").json()
        assert [p["id"] for p in items] == [second["id"]]
        assert client.get("/api/decisions/plans?limit=1&offset=1").json()[0]["id"] == first["id"]
        assert first["created_at"].endswith("Z")
        exported = client.get(f'/api/decisions/plans/{second["id"]}/export?format=json')
        assert exported.json() == second
        assert exported.headers["content-disposition"] == f'attachment; filename="mealloop-assumption-plan-{second["id"]}.json"'
        exported_csv = client.get(f'/api/decisions/plans/{second["id"]}/export?format=csv')
        assert "HYPERLINK" not in exported_csv.text and "+SUM" not in exported_csv.text
        rows = list(csv.DictReader(io.StringIO(exported_csv.text)))
        assert len(rows) == 51
        assert {r["evidence_type"] for r in rows} == {"assumption_based"}
        assert float(next(r for r in rows if r["quantity"] == "400")["expected_unmet_portions"]) == 12
    with patch("app.decision_service.preview", side_effect=AssertionError("Saved retrieval must not recalculate")):
        with TestClient(create_app(url)) as client:
            assert client.get(f'/api/decisions/plans/{first["id"]}').json() == first
            assert client.get(f'/api/decisions/plans/{second["id"]}/export').json() == second


def test_context_is_optional_provenance_and_historical_rows_are_unchanged(client):
    raw = (ROOT / "data/raw/Food waste data school Finland 2024-2025.xlsx").read_bytes()
    batch = client.post("/api/dataset/import", files={"file": ("official.xlsx", raw)}).json()
    before = client.get(f'/api/overview?batch_id={batch["id"]}').json()
    def database_snapshot():
        with client.app.state.engine.connect() as c:
            return {t: c.execute(text(f'SELECT * FROM {t} ORDER BY id')).fetchall() for t in
                    ("source_datasets", "import_batches", "daily_records", "forecast_artifacts", "forecast_runs")}
    old = database_snapshot()
    assert client.get(f'/api/models/status?batch_id={batch["id"]}').json()["status"] == "not_prepared"
    saved = client.post("/api/decisions/plans", json={**demo(), "context_batch_id": batch["id"]})
    assert saved.status_code == 201, saved.text
    reference = saved.json()["context_reference"]
    assert reference["source_kind"] == "measured"
    assert reference["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert "No historical measurement or forecast" in reference["role"]
    assert saved.json()["evidence_type"] == "assumption_based"
    assert database_snapshot() == old
    assert client.get(f'/api/overview?batch_id={batch["id"]}').json() == before
    assert client.post("/api/decisions/plans", json={**demo(), "context_batch_id": 999}).status_code == 404
    assert len(client.get("/api/decisions/plans").json()) == 1


@pytest.mark.parametrize("path", ["/plans/0", "/plans/no", "/plans?limit=101", "/plans?limit=0", "/plans?offset=-1", "/plans/1/export?format=../../bad"])
def test_invalid_routes_and_pagination(client, path):
    assert client.get("/api/decisions" + path).status_code == 422


def test_missing_plan_and_input_validation(client):
    assert client.get("/api/decisions/plans/999").status_code == 404
    assert client.get("/api/decisions/plans/999/export").status_code == 404
    for change in ({"evidence_type": "measured"}, {"result": {"recommended": 0}}, {"baseline_portions": "480"}, {"planning_date": "bad"}):
        response = client.post("/api/decisions/preview", json={**demo(), **change})
        assert response.status_code == 422, response.text
        assert all("input" not in e for e in response.json()["detail"])
    payload = demo()
    del payload["portion_mass_g"]
    assert client.post("/api/decisions/plans", json=payload).status_code == 422
    assert client.get("/api/decisions/plans").json() == []


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_returns_422_without_serialization_failure(client, value):
    body = json.dumps(demo()).replace('"portion_mass_g": 400.0', f'"portion_mass_g": {value}')
    assert value in body
    r = client.post("/api/decisions/preview", content=body, headers={"Content-Type": "application/json"})
    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["loc"] == ["body", "portion_mass_g"]


def test_oversize_bodies_content_length_and_chunked_are_bounded(client):
    for body in (b"x" * 65537, iter([b"x" * 32000, b"x" * 34000])):
        r = client.post("/api/decisions/preview", content=body, headers={"Content-Type": "application/json"})
        assert r.status_code == 413
        assert "64 KiB" in r.json()["detail"]["message"]
    assert client.post("/api/decisions/preview", content="{", headers={"Content-Type": "application/json"}).status_code == 422
    assert client.get("/api/health").status_code == 200


def test_infeasible_plan_can_be_saved_without_an_invented_recommendation(client):
    saved = client.post("/api/decisions/plans", json={**demo(), "maximum_capacity": 430})
    assert saved.status_code == 201, saved.text
    result = saved.json()["result"]
    assert result["status"] == "infeasible" and result["recommended"] is None
    assert client.get("/api/decisions/plans").json()[0]["recommended_portions"] is None


def test_migration_from_build02_preserves_measured_and_forecast_tables(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    config = Config()
    config.set_main_option("script_location", str(ROOT / "backend/migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0002")
    assert "decision_plans" not in inspect(engine).get_table_names()
    with engine.begin() as c:
        c.execute(text("INSERT INTO source_datasets(id,key,title,kind) VALUES(1,'preserve','Old measured source','measured')"))
        c.execute(text("INSERT INTO import_batches(id,source_id,filename,sha256,imported_at,row_count,inspection) VALUES(1,1,'old.csv',:hash,'2025-01-01',1,'{}')"), {"hash": "a" * 64})
        c.execute(text("INSERT INTO daily_records(id,batch_id,day_index,source_row,phase,diners,plate_waste_kg,issues) VALUES(1,1,1,2,'baseline',100,2.5,'[]')"))
        c.execute(text("INSERT INTO forecast_artifacts(id,batch_id,fingerprint,config_key,model_id,created_at,evaluation,predictor) VALUES(1,1,'old','config','recent_mean_10','2025-01-01','{}','{}')"))
        c.execute(text("INSERT INTO forecast_runs(id,artifact_id,batch_id,created_at,scenario,result) VALUES(1,1,1,'2025-01-01','{}','{}')"))
    old_tables = ["source_datasets", "import_batches", "daily_records", "forecast_artifacts", "forecast_runs"]
    with engine.connect() as c:
        old = {t: c.execute(text(f"SELECT * FROM {t}")).fetchall() for t in old_tables}
    migrate(engine)
    migrate(engine)  # startup retry is idempotent
    assert "decision_plans" in inspect(engine).get_table_names()
    with engine.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar() == ScriptDirectory.from_config(config).get_current_head()
        assert {t: c.execute(text(f"SELECT * FROM {t}")).fetchall() for t in old_tables} == old
    assert "ck_decision_evidence" in {x["name"] for x in inspect(engine).get_check_constraints("decision_plans")}
    engine.dispose()
