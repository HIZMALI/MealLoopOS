from copy import deepcopy
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.database import ROOT, make_engine, migrate
from app.impact_schemas import RecordResult
from app.impact_service import demo_inputs
from app.main import create_app
from app.models import DecisionPlan, OperationalRevision, OperationalService


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr("app.impact_service.utc_now",lambda:datetime(2026,10,23,12,tzinfo=timezone.utc))


def fixture(**changes):
    return {**deepcopy(demo_inputs()["complete"]),**changes}


def create(client,payload=None):
    response=client.post("/api/impact/records",json=payload or fixture())
    assert response.status_code==201,response.text
    return response.json()


def finalize(client,record):
    response=client.post(f'/api/impact/records/{record["id"]}/finalize',json={"expected_version":record["version"]})
    assert response.status_code==201,response.text
    return response.json()


def test_seed_synthetic_demo_is_explicit_idempotent_and_scientifically_separate(client):
    assert client.get("/api/impact/records").json()==[]
    assert client.get("/api/impact/summary").json()["service_count"]==0
    assert "SYNTHETIC" in client.get("/api/impact/demo").json()["notice"]
    r=client.post("/api/impact/demo")
    assert r.status_code==201,r.text
    complete,incomplete=r.json()
    RecordResult.model_validate(complete)
    assert complete["status"]=="finalized" and incomplete["status"]=="draft"
    assert complete["plan_reference"]["recommended_portions"]==440
    assert complete["assessment"]["accounting"]["estimated_discarded_kg"]==8
    assert complete["assessment"]["combined_weighed_kg"]==9.7
    assert incomplete["assessment"]["accounting"]["unknown_portions"]==5
    assert not incomplete["assessment"]["can_finalize"]
    assert client.post("/api/impact/demo").json()==r.json()
    assert client.get("/api/impact/records").json()==[]
    assert client.get("/api/dataset/status").json()["status"]=="empty"
    assert client.get("/api/models/status").json()["status"]=="empty"
    summary=client.get("/api/impact/summary?source_category=synthetic").json()
    assert summary["service_count"]==2
    assert summary["combined_weighed_kg"]=={"total":9.7,"covered":1,"missing":1}
    assert summary["counts"]["unknown"]["total"]==5
    assert summary["evidence"]["unknown_disposition_services"]==1
    assert summary["estimated_discarded_kg"]["total"]==10  # separate count conversions 8 + 2
    assert client.get("/api/impact/summary?source_category=synthetic&status=finalized").json()["service_count"]==1


def test_full_draft_finalize_correction_history_and_latest_only_analytics(client):
    first=create(client)
    original=deepcopy(first)
    final=finalize(client,first)
    assert final["version"]==2 and final["previous_revision_id"]==first["revision_id"]
    change=fixture(dispositions={"donated":10,"retained":10,"repurposed":0,"discarded":15,"unknown":5})
    correction=client.post(f'/api/impact/records/{first["id"]}/revisions',json={"expected_version":2,"record":change,"correction_reason":"Five portions could not be traced."})
    assert correction.status_code==201,correction.text
    revised=correction.json()
    assert revised["status"]=="draft" and revised["version"]==3
    assert "dispositions.unknown" in revised["changed_fields"]
    assert client.post(f'/api/impact/records/{first["id"]}/finalize',json={"expected_version":3}).status_code==422
    history=client.get(f'/api/impact/records/{first["id"]}/history').json()
    assert len(history)==3 and history[0]==original and history[1]==final
    assert history[2]["correction_reason"]=="Five portions could not be traced."
    summary=client.get("/api/impact/summary?source_category=synthetic").json()
    assert summary["service_count"]==1 and summary["counts"]["discarded"]["total"]==15
    assert client.get("/api/impact/summary?source_category=synthetic&status=finalized").json()["service_count"]==0
    assert client.get(f'/api/impact/records/{first["id"]}/quality').json()==revised["assessment"]
    assert client.put(f'/api/impact/records/{first["id"]}',json=fixture()).status_code==405
    assert client.delete(f'/api/impact/records/{first["id"]}').status_code==405
    assert client.post(f'/api/impact/records/{first["id"]}/revisions',json={"expected_version":2,"record":fixture(),"correction_reason":"Stale update should fail."}).status_code==409


def test_provenance_locked_and_invalid_operations_leave_no_orphans(client):
    first=create(client)
    for cat in ("user_reported","user_reported_documented"):
        r=client.post(f'/api/impact/records/{first["id"]}/revisions',json={"expected_version":1,"record":fixture(source_category=cat,documents=[{"label":"Log","reference":"Page 2"}]),"correction_reason":"Cannot relabel synthetic records."})
        assert r.status_code==422
    assert client.post("/api/impact/records",json=fixture(decision_plan_id=999)).status_code==404
    with Session(client.app.state.engine) as session:
        assert len(session.scalars(select(OperationalService)).all())==1
        assert len(session.scalars(select(OperationalRevision)).all())==1


def test_plan_date_menu_link_and_frozen_original_outputs(client):
    plan=client.get("/api/decisions/demo").json()
    plan["planning_date"]="2026-10-22"
    saved=client.post("/api/decisions/plans",json=plan).json()
    assert client.post("/api/impact/records",json=fixture(decision_plan_id=saved["id"],service_date="2026-10-21")).status_code==422
    assert client.post("/api/impact/records",json=fixture(decision_plan_id=saved["id"],menu="2")).status_code==422
    assert client.post("/api/impact/records",json=fixture(decision_plan_id=saved["id"],source_category="user_reported")).status_code==422
    with Session(client.app.state.engine) as session:
        p=session.get(DecisionPlan,saved["id"])
        p.created_at=datetime(2026,10,20,12,tzinfo=timezone.utc)
        session.commit()
    with patch("app.decision_service.preview",side_effect=AssertionError("Cannot reoptimize an original plan")),patch("app.forecast_service.evaluate",side_effect=AssertionError("No forecast model required")):
        record=create(client,fixture(decision_plan_id=saved["id"]))
        assert record["assessment"]["planning_timing"]=="prospective_capture"
        assert record["assessment"]["actual_minus_recommended"]==0
        assert record["assessment"]["actual_minus_baseline"]==-40
        original=client.get(f'/api/impact/records/{record["id"]}/plan').json()
        assert original["result"]==saved["result"] and original["engine_version"]==saved["engine_version"]
    standalone=create(client)
    assert client.get(f'/api/impact/records/{standalone["id"]}/plan').status_code==404


@pytest.mark.parametrize("payload", [
    {"served":441},{"served":True},{"prepared":"440"},{"prepared":100001},
    {"created_at":"2000-01-01T00:00:00Z"},{"evidence_type":"independently_verified"},
    {"source_category":"historical"},{"decision_plan_id":-1},{"menu":""},
])
def test_validation_and_timestamp_forgery_rejected(client,payload):
    assert client.post("/api/impact/records",json=fixture(**payload)).status_code==422
    assert client.get("/api/impact/records?source_category=synthetic").json()==[]


@pytest.mark.parametrize("route", ["/records/999","/records/999/history","/records/999/quality","/records/999/plan","/records/999/export"])
def test_missing_records(client,route):
    assert client.get("/api/impact"+route).status_code==404


@pytest.mark.parametrize("route", ["/records?source_category=all","/summary?source_category=all","/records?limit=101","/records?offset=-1","/summary?basis=verified","/records?start=invalid","/records?status=complete"])
def test_query_boundaries(client,route):
    assert client.get("/api/impact"+route).status_code==422


def comparison(**changes):
    return {"source_category":"synthetic","category":"discarded_surplus","basis":"weighed",
        "baseline_start":"2026-10-20","baseline_end":"2026-10-20","trial_start":"2026-10-21","trial_end":"2026-10-21",**changes}


def test_comparison_valid_pairs_missing_coverage_and_denominator_not_served(client):
    base=fixture(service_date="2026-10-20",observed_diners=200)
    finalize(client,create(client,base))
    trial=fixture(service_date="2026-10-21",observed_diners=100)
    trial["measurements"][0]["mass_kg"]=3.8
    finalize(client,create(client,trial))
    # Complete counts but absent physical reading: finalize as incomplete evidence.
    finalize(client,create(client,fixture(service_date="2026-10-20",measurements=[],observed_diners=None)))
    result=client.post("/api/impact/comparison",json=comparison()).json()
    assert result["status"]=="comparable_descriptive"
    assert result["label"]=="Observational comparison — not causal evidence."
    a,b=result["periods"]["baseline"],result["periods"]["trial"]
    assert (a["services"],a["covered_observations"],a["missing_or_other_basis"])==(2,1,1)
    assert a["g_per_observed_diner"]==b["g_per_observed_diner"]==38
    assert result["difference"]["kg_per_service_trial_minus_baseline"]==-3.8
    assert result["difference"]["relative_change"]==-.5
    # Actual self-reports remain a separate empty cohort.
    blocked=client.post("/api/impact/comparison",json=comparison(source_category="user_reported")).json()
    assert blocked["status"]=="blocked" and blocked["difference"] is None


@pytest.mark.parametrize("change", ["method","scope","site","material","destination","menu"])
def test_incompatible_comparison_blocked(client,change):
    base=fixture(service_date="2026-10-20")
    trial=fixture(service_date="2026-10-21")
    if change=="method":trial["measurements"][0]["method"]="Other protocol"
    elif change=="scope":trial["measurements"][0]["scope_status"]="possible_overlap"
    elif change=="material":trial["measurements"][0]["material_type"]="food_only"
    elif change=="destination":trial["measurements"][0]["destination"]="landfill"
    else:trial[change]="Different context"
    for p in (base,trial):finalize(client,create(client,p))
    r=client.post("/api/impact/comparison",json=comparison()).json()
    assert r["status"]=="blocked" and r["reasons"]
    assert r["periods"]["baseline"]["reported_mass_kg"] is None
    assert r["periods"]["trial"]["g_per_observed_diner"] is None
    assert r["difference"] is None


def test_no_observed_diners_means_no_per_diner_rate_and_method_filter_is_explicit(client):
    for day,diners in (("2026-10-20",None),("2026-10-21",0)):
        finalize(client,create(client,fixture(service_date=day,observed_diners=diners)))
    r=client.post("/api/impact/comparison",json=comparison()).json()
    assert r["status"]=="comparable_descriptive"
    assert r["periods"]["baseline"]["g_per_observed_diner"] is None
    assert r["difference"]["g_per_diner_trial_minus_baseline"] is None
    assert client.get("/api/impact/summary?source_category=synthetic&basis=imported").json()["service_count"]==0


def test_invalid_comparison_periods_and_synthetic_cohort_mixing(client):
    for change in ({"trial_start":"2026-10-20"},{"baseline_end":"2026-10-22"},{"source_category":"all"},
        {"baseline_start":"2000-01-01"},{"category":"total"}):
        assert client.post("/api/impact/comparison",json=comparison(**change)).status_code==422


def test_body_limit_nonfinite_and_bad_json(client):
    for content in (b"x"*65537,iter([b"x"*32000,b"x"*34000])):
        assert client.post("/api/impact/records",content=content).status_code==413
    for word in ("NaN","Infinity","-Infinity"):
        content=json.dumps(fixture()).replace('"mass_kg": 7.6',f'"mass_kg": {word}')
        r=client.post("/api/impact/records",content=content,headers={"Content-Type":"application/json"})
        assert r.status_code==422,r.text
    assert client.post("/api/impact/records",content="{").status_code==422


def test_export_formula_safety_full_history_and_restart(tmp_path):
    url=f"sqlite:///{(tmp_path/'operational.db').as_posix()}"
    with TestClient(create_app(url)) as client:
        saved=finalize(client,create(client,fixture(site='=HYPERLINK("evil")',menu="+SUM(1,2)")))
        exported=client.get(f'/api/impact/records/{saved["id"]}/export?format=csv')
        assert exported.status_code==200
        rows=list(csv.DictReader(io.StringIO(exported.text)))
        assert len(rows)==2
        assert all(r["site"].startswith("'=") and r["menu"].startswith("'+") for r in rows)
        assert rows[-1]["discarded_surplus_mass_kg"]=="7.6"
        assert rows[-1]["estimated_discarded_kg"]=="8.0"
        assert "filename=\"mealloop-operational-" in exported.headers["content-disposition"]
        original=client.get(f'/api/impact/records/{saved["id"]}/export').json()
        assert original["history"][-1]==saved
        assert client.get(f'/api/impact/records/{saved["id"]}/export?format=../../evil').status_code==422
    with patch("app.impact_service.assess",side_effect=AssertionError("Frozen retrieval must not reassess")):
        with TestClient(create_app(url)) as client:
            assert client.get(f'/api/impact/records/{saved["id"]}').json()==saved
            assert client.get(f'/api/impact/records/{saved["id"]}/export').json()==original


def test_historical_and_decision_evidence_unchanged_by_operations(client):
    content=(ROOT/'data/raw/Food waste data school Finland 2024-2025.xlsx').read_bytes()
    assert hashlib.sha256(content).hexdigest()=="2ffad746b7ed5d536a0c99c37d8e249230d95d5fb2d041d85d01b69499f99624"
    client.post('/api/dataset/import',files={"file":("official.xlsx",content)})
    tables=("source_datasets","import_batches","daily_records","forecast_artifacts","forecast_runs","decision_plans")
    def snap():
        with client.app.state.engine.connect() as c:
            return {t:c.execute(text(f'SELECT * FROM {t}')).fetchall() for t in tables}
    before=snap()
    record=create(client)
    finalize(client,record)
    assert snap()==before
    assert client.get('/api/models/status').json()["status"]=="not_prepared"
    r=client.post('/api/decisions/preview',json=client.get('/api/decisions/demo').json())
    assert r.json()["recommended"]["quantity"]==440


def test_migration_0003_to_0004_preserves_original_plan_and_tables(tmp_path):
    engine=make_engine(f"sqlite:///{(tmp_path/'old03.db').as_posix()}")
    config=Config();config.set_main_option("script_location",str(ROOT/'backend/migrations'))
    with engine.begin() as c:
        config.attributes["connection"]=c
        command.upgrade(config,'0003')
        c.execute(text("INSERT INTO decision_plans(id,created_at,engine_version,evidence_type,input_fingerprint,inputs,result) VALUES(1,'2026-10-20','original-v1','assumption_based',:hash,'{}','{}')"),{"hash":"a"*64})
    before=set(inspect(engine).get_table_names())
    with engine.connect() as c:old=c.execute(text('SELECT * FROM decision_plans')).fetchall()
    migrate(engine);migrate(engine)
    assert set(inspect(engine).get_table_names())==before|{"operational_services","operational_revisions"}
    with engine.connect() as c:
        assert c.execute(text('SELECT * FROM decision_plans')).fetchall()==old
        assert c.execute(text('SELECT version_num FROM alembic_version')).scalar()=='0004'
    assert {f["referred_table"] for f in inspect(engine).get_foreign_keys("operational_revisions")}=={"operational_services","operational_revisions","decision_plans"}
    engine.dispose()
