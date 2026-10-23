from fastapi.testclient import TestClient
import pytest
from sqlalchemy import inspect
from app.main import create_app
from app.database import ROOT


def upload(client, content, name="test.csv", **data):
    return client.post("/api/dataset/import", files={"file": (name, content)}, data=data)


def test_health_empty_status_and_migration(client):
    assert client.get("/api/health").json()["database"] == "connected"
    assert client.get("/api/dataset/status").json()["status"] == "empty"
    assert client.get("/api/overview").status_code == 404
    assert client.get("/api/charts").status_code == 404
    tables = inspect(client.app.state.engine).get_table_names()
    assert {"source_datasets", "import_batches", "daily_records", "alembic_version"} <= set(tables)


def test_import_metrics_charts_and_idempotency(client, csv_data):
    response = upload(client, csv_data, baseline_days="2")
    assert response.status_code == 201, response.text
    batch = response.json()
    assert batch["baseline_days"] == 2
    assert not batch["inspection"]["verified_official_file"]
    assert batch["source"]["doi"] is None
    overview = client.get("/api/overview").json()
    assert overview["metrics"]["combined_recorded_waste_kg"] == 9
    assert len(overview["periods"]) == 2
    assert client.get("/api/charts").json()["daily"][1]["kitchen_serving_waste_kg"] is None
    assert upload(client, csv_data).status_code == 409
    assert len(client.get("/api/dataset/status").json()["batches"]) == 1


def test_atomic_rejection_and_informative_error(client):
    response = upload(client, b"PW kg,KSW kg,DINERS\n1,2,3\nabc,2,3\n")
    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["source_row"] == 3
    assert client.get("/api/dataset/status").json()["batches"] == []


def test_validation_and_no_client_paths(client, csv_data):
    assert upload(client, csv_data, source_kind="anything").status_code == 422
    assert upload(client, csv_data, baseline_days="-1").status_code == 422
    assert upload(client, csv_data, baseline_days="4").status_code == 422
    assert upload(client, csv_data, "bad.exe").status_code == 422
    assert client.get("/api/overview?batch_id=0").status_code == 422
    assert client.get("/api/overview?batch_id=99999").status_code == 404
    batch = upload(client, csv_data, "../../evil.csv").json()
    assert batch["filename"] == "evil.csv"


def test_large_content_length_rejected(client):
    result = client.post("/api/dataset/import", content=b"x", headers={"content-length": str(11 * 1024 * 1024)})
    assert result.status_code == 413


def test_chunked_oversized_body_bounded_before_file_parsing(client):
    result = client.post("/api/dataset/import", content=iter([b"x" * 1024 * 1024] * 11), headers={"content-type": "application/octet-stream"})
    assert result.status_code == 413


def test_synthetic_is_distinct_and_batch_selection(client, csv_data):
    b1 = upload(client, csv_data, source_kind="synthetic").json()
    b2 = upload(client, csv_data.replace(b",1,1,2,100", b",1,2,2,100")).json()
    assert b1["source"]["kind"] == "synthetic"
    assert b2["source"]["kind"] == "measured"
    assert client.get(f"/api/overview?batch_id={b1['id']}").json()["metrics"]["combined_recorded_waste_kg"] == 9
    assert client.get("/api/overview").json()["metrics"]["combined_recorded_waste_kg"] == 10


@pytest.mark.parametrize("line_ending", ["lf", "crlf"])
def test_bundled_fixture_cannot_be_mislabeled(client, line_ending):
    content = (ROOT / "data/fixtures/synthetic_test.csv").read_bytes().replace(b"\r\n", b"\n")
    if line_ending == "crlf":
        content = content.replace(b"\n", b"\r\n")
    response = upload(client, content, "renamed.csv")
    assert response.status_code == 422
    assert "synthetic test fixture" in response.json()["detail"]["message"]
    response = upload(client, content, "renamed.csv", source_kind="synthetic")
    assert response.status_code == 201
    assert response.json()["source"]["kind"] == "synthetic"


def test_persistence_after_app_restart(tmp_path, csv_data):
    url = f"sqlite:///{(tmp_path / 'persist.db').as_posix()}"
    with TestClient(create_app(url)) as client:
        assert upload(client, csv_data).status_code == 201
    with TestClient(create_app(url)) as client:
        assert client.get("/api/overview").json()["metrics"]["days"] == 3


def test_official_workbook_regression(client):
    content = (ROOT / "data/raw/Food waste data school Finland 2024-2025.xlsx").read_bytes()
    assert upload(client, content, "official.xlsx", source_kind="synthetic").status_code == 422
    assert upload(client, content, "official.xlsx", baseline_days="134").status_code == 422
    result = upload(client, content, "official.xlsx")
    assert result.status_code == 201, result.text
    batch = result.json()
    assert batch["row_count"] == 155 and batch["baseline_days"] == 135
    assert batch["inspection"]["verified_official_file"]
    assert batch["inspection"]["date_count"] == 155
    assert batch["inspection"]["flagged_rows"] == 3
    m = client.get("/api/overview").json()
    assert abs(m["metrics"]["plate_waste_kg"] - 1407.754) < 1e-8
    assert abs(m["metrics"]["kitchen_serving_waste_kg"] - 1243.88) < 1e-8
    assert m["metrics"]["coverage"]["complete_days"] == 154
    assert [p["days"] for p in m["periods"]] == [135, 20]
    rows = client.get("/api/charts").json()["daily"]
    assert rows[0]["date"] == "2024-08-08" and rows[-1]["date"] == "2025-04-11"
    assert rows[135]["phase"] == "intervention"
    assert rows[17]["kitchen_serving_waste_kg"] is None
    assert rows[150]["reported_plate_waste_g"] == 6751
