from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import ROOT
from app.main import create_app
from app.models import DailyRecord, ForecastArtifact
from sqlalchemy.orm import Session


@pytest.fixture
def measured(client):
    content = (ROOT / "data/raw/Food waste data school Finland 2024-2025.xlsx").read_bytes()
    response = client.post("/api/dataset/import", files={"file": ("official.xlsx", content)})
    assert response.status_code == 201
    return client, response.json()["id"]


@pytest.fixture
def ready(measured):
    client, batch_id = measured
    result = client.post("/api/models/train", json={"batch_id": batch_id})
    assert result.status_code == 200, result.text
    return client, batch_id, result.json()


def test_status_empty_missing_and_unprepared(client, measured):
    client, batch_id = measured
    assert client.get(f"/api/models/status?batch_id={batch_id}").json()["status"] == "not_prepared"
    assert client.get("/api/models/status?batch_id=999").status_code == 404
    assert client.get("/api/models/status?batch_id=0").status_code == 422
    assert client.get(f"/api/models/evaluation?batch_id={batch_id}").status_code == 409
    assert client.post("/api/forecasts", json={"batch_id": batch_id, "service_date": "2025-04-14", "planned_diners": 400}).status_code == 409


def test_empty_model_status(client):
    assert client.get("/api/models/status").json()["status"] == "empty"
    assert client.post("/api/models/train", json={"batch_id": 1}).status_code == 404


def test_ready_evidence_and_cached_training(ready):
    client, batch_id, metadata = ready
    assert metadata["production_training"]["eligible"] == 152
    assert metadata["evaluation_fit_cutoff"]["eligible"] == 134
    assert client.get(f"/api/models/status?batch_id={batch_id}").json()["status"] == "ready"
    evaluation = client.get(f"/api/models/evaluation?batch_id={batch_id}")
    assert evaluation.status_code == 200, evaluation.text
    assert evaluation.json()["selected_method"] == "recent_mean_10"
    with patch("app.forecast_service.evaluate", side_effect=AssertionError("cached model must not fit")):
        assert client.post("/api/models/train", json={"batch_id": batch_id}).json()["model_id"] == metadata["model_id"]
        for planned in (200, 400):
            response = client.post("/api/forecasts", json={"batch_id": batch_id, "service_date": "2025-04-14", "planned_diners": planned, "menu": 1})
            assert response.status_code == 201, response.text
    runs = client.get(f"/api/forecasts/runs?batch_id={batch_id}").json()
    assert len(runs) == 2
    assert runs[0]["result"]["rates_g_per_diner"] == runs[1]["result"]["rates_g_per_diner"]
    assert runs[0]["result"]["estimated_mass_kg"]["combined"] == 2 * runs[1]["result"]["estimated_mass_kg"]["combined"]
    assert "pickle" in metadata["serialization"]


@pytest.mark.parametrize("value", [0, -1, 1.5, "400", True, 1_000_001, None])
def test_invalid_planned_diners_rejected_without_training(measured, value):
    client, batch_id = measured
    response = client.post("/api/forecasts", json={"batch_id": batch_id, "service_date": "2025-04-14", "planned_diners": value})
    assert response.status_code == 422


@pytest.mark.parametrize("payload", [{"service_date": "bad"}, {"menu": 0}, {"menu": 1.5}, {"menu": 10001}, {"actual_diners": 400}])
def test_request_validation(measured, payload):
    client, batch_id = measured
    request = {"batch_id": batch_id, "service_date": "2025-04-14", "planned_diners": 400, **payload}
    assert client.post("/api/forecasts", json=request).status_code == 422


def test_forecasts_arithmetic_fallback_dates_and_warnings(ready):
    client, batch_id, _ = ready
    for menu in (None, 999):
        response = client.post("/api/forecasts", json={"batch_id": batch_id, "service_date": "2026-10-24", "planned_diners": 400, "menu": menu})
        assert response.status_code == 201
        result = response.json()["result"]
        assert result["label"] == "Forecast / Model estimate"
        r, kg = result["rates_g_per_diner"], result["estimated_mass_kg"]
        assert r["combined"] == r["plate"] + r["kitchen"]
        assert kg["combined"] == kg["plate"] + kg["kitchen"]
        assert kg["plate"] == pytest.approx(r["plate"] * .4)
        assert any("fallback" in w for w in result["warnings"])
        assert any("Long-gap" in w for w in result["warnings"])
    assert client.post("/api/forecasts", json={"batch_id": batch_id, "service_date": "2025-04-11", "planned_diners": 400}).status_code == 422


def test_synthetic_and_insufficient_are_blocked(client, csv_data):
    for kind in ("synthetic", "measured"):
        response = client.post("/api/dataset/import", files={"file": ("f.csv", csv_data + (b"\n" if kind == "measured" else b""))}, data={"source_kind": kind})
        batch_id = response.json()["id"]
        status = client.get(f"/api/models/status?batch_id={batch_id}").json()
        assert status["status"] == "blocked"
        assert client.post("/api/models/train", json={"batch_id": batch_id}).status_code == 422


def test_batch_and_normalized_data_changes_invalidate_artifacts(ready):
    client, batch_id, old = ready
    with Session(client.app.state.engine) as session:
        last = session.scalar(select(DailyRecord).where(DailyRecord.batch_id == batch_id).order_by(DailyRecord.day_index.desc()).limit(1))
        last.plate_waste_kg += 1
        session.commit()
    assert client.get(f"/api/models/status?batch_id={batch_id}").json()["status"] == "not_prepared"
    assert client.get(f"/api/models/metadata?batch_id={batch_id}").status_code == 409
    new = client.post("/api/models/train", json={"batch_id": batch_id}).json()
    assert new["model_id"] != old["model_id"]
    with Session(client.app.state.engine) as session:
        assert len(session.scalars(select(ForecastArtifact)).all()) == 2
    response = client.post("/api/dataset/import", files={"file": ("short.csv", b"PW kg,KSW kg,DINERS\n1,2,3\n")})
    other = response.json()["id"]
    assert client.get(f"/api/models/status?batch_id={other}").json()["status"] == "blocked"
    assert client.get(f"/api/models/status?batch_id={batch_id}").json()["metadata"]["model_id"] == new["model_id"]


def test_another_eligible_batch_needs_its_own_artifact(ready):
    client, original_id, original = ready
    # A valid XLSX container with trailing whitespace is a different file, with
    # unchanged cell measurements but explicitly unverified custom provenance.
    content = (ROOT / "data/raw/Food waste data school Finland 2024-2025.xlsx").read_bytes() + b"\n"
    imported = client.post("/api/dataset/import", files={"file": ("custom.xlsx", content)}, data={"baseline_days": "135"})
    assert imported.status_code == 201
    other_id = imported.json()["id"]
    assert not imported.json()["inspection"]["verified_official_file"]
    assert client.get(f"/api/models/status?batch_id={other_id}").json()["status"] == "not_prepared"
    trained = client.post("/api/models/train", json={"batch_id": other_id})
    assert trained.status_code == 200
    assert trained.json()["model_id"] != original["model_id"]
    assert trained.json()["source"]["doi"] is None
    assert client.get(f"/api/models/metadata?batch_id={original_id}").json()["model_id"] == original["model_id"]


def test_changed_configuration_cannot_use_old_artifact(ready):
    client, batch_id, _ = ready
    with patch("app.forecast_service.CONFIG_KEY", "new-configuration-key"):
        assert client.get(f"/api/models/status?batch_id={batch_id}").json()["status"] == "not_prepared"
        assert client.get(f"/api/models/evaluation?batch_id={batch_id}").status_code == 409
        assert client.post("/api/forecasts", json={"batch_id": batch_id, "service_date": "2025-04-14", "planned_diners": 400}).status_code == 409


def test_restart_uses_persisted_json_and_forecasts(tmp_path):
    url = f"sqlite:///{(tmp_path / 'forecast.db').as_posix()}"
    with TestClient(create_app(url)) as client:
        content = (ROOT / "data/raw/Food waste data school Finland 2024-2025.xlsx").read_bytes()
        batch_id = client.post("/api/dataset/import", files={"file": ("real.xlsx", content)}).json()["id"]
        model_id = client.post("/api/models/train", json={"batch_id": batch_id}).json()["model_id"]
        saved = client.post("/api/forecasts", json={"batch_id": batch_id, "service_date": "2025-04-14", "planned_diners": 400}).json()
    with patch("app.forecast_service.evaluate", side_effect=AssertionError("restart must not retrain")):
        with TestClient(create_app(url)) as client:
            assert client.get("/api/models/status").json()["metadata"]["model_id"] == model_id
            runs = client.get(f"/api/forecasts/runs?batch_id={batch_id}").json()
            assert runs[0] == saved
            assert client.post("/api/forecasts", json={"batch_id": batch_id, "service_date": "2025-04-15", "planned_diners": 500}).status_code == 201
