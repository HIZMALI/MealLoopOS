"""Execute a synthetic operational workflow against a disposable local database."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from fastapi.testclient import TestClient
from app.database import ROOT
from app.impact_service import demo_inputs
from app.main import create_app


def evaluate():
    fixtures=demo_inputs()
    f=fixtures["complete"]
    # Independent integer/decimal arithmetic, not the production accounting helpers.
    remaining=f["prepared"]-f["served"]
    allocation=sum(f["dispositions"].values())
    mass_by_category={m["category"]:Decimal(str(m["mass_kg"])) for m in f["measurements"]}
    scale_sum=sum(mass_by_category.values(),Decimal(0))
    portion_estimate=Decimal(f["dispositions"]["discarded"])*Decimal(str(f["portion_mass_g"]))/1000
    assert remaining==allocation==40
    assert mass_by_category["discarded_surplus"]==Decimal("7.6")
    assert scale_sum==Decimal("9.7") and portion_estimate==8
    incomplete=fixtures["incomplete"]
    assert incomplete["prepared"]-incomplete["served"]==sum(incomplete["dispositions"].values())==30
    assert incomplete["dispositions"]["unknown"]==5
    runtime=ROOT/".run"
    runtime.mkdir(exist_ok=True)
    # Fixed synthetic clock is deliberately not a real capture timestamp.
    now=datetime(2026,10,23,12,tzinfo=timezone.utc)
    with TemporaryDirectory(prefix="impact-evaluation-",dir=runtime) as directory:
        url=f"sqlite:///{(Path(directory)/'evaluation.db').as_posix()}"
        with patch("app.impact_service.utc_now",return_value=now):
            with TestClient(create_app(url)) as client:
                response=client.post("/api/impact/demo")
                assert response.status_code==201,response.text
                complete,unknown=response.json()
                a=complete["assessment"]
                assert a["accounting"]["remaining_portions"]==remaining
                assert a["accounting"]["estimated_discarded_kg"]==float(portion_estimate)
                assert a["combined_weighed_kg"]==float(scale_sum)
                assert complete["record"]["measurements"][0]["mass_kg"]==7.6
                assert complete["plan_reference"]["recommended_portions"]==440
                assert a["actual_minus_recommended"]==0 and a["actual_minus_baseline"]==-40
                assert not a["independently_verified"]
                assert complete["record"]["source_category"]==unknown["record"]["source_category"]=="synthetic"
                assert unknown["status"]=="draft" and not unknown["assessment"]["can_finalize"]
                assert client.post(f'/api/impact/records/{unknown["id"]}/finalize',json={"expected_version":1}).status_code==422
                assert client.post("/api/impact/records",json={**f,"served":f["prepared"]+1}).status_code==422
                assert client.get("/api/impact/summary").json()["service_count"]==0
                assert client.get("/api/dataset/status").json()["status"]=="empty"
                # An audit correction changes a note, preserving every old snapshot.
                correction=client.post(f'/api/impact/records/{complete["id"]}/revisions',json={"expected_version":2,
                    "record":{**complete["record"],"operator_notes":"Synthetic audit correction: clarified that no physical weighing occurred."},
                    "correction_reason":"Clarify simulated measurement provenance."})
                assert correction.status_code==201,correction.text
                finalized=client.post(f'/api/impact/records/{complete["id"]}/finalize',json={"expected_version":3})
                assert finalized.status_code==201,finalized.text
                history=client.get(f'/api/impact/records/{complete["id"]}/history').json()
                assert history[1]==complete and [r["version"] for r in history]==[1,2,3,4]
                summary=client.get("/api/impact/summary?source_category=synthetic").json()
                assert summary["service_count"]==2 and summary["combined_weighed_kg"]["total"]==9.7
                metadata=client.get("/api/impact/metadata").json()
            with TestClient(create_app(url)) as client:
                assert client.get(f'/api/impact/records/{complete["id"]}').json()==finalized.json()
                assert client.get(f'/api/impact/records/{complete["id"]}/history').json()==history
    return {"evidence_type":"synthetic_demonstration","notice":"No real kitchen service, pilot, physical weighing or food-waste intervention occurred. Test server clock is fixed solely for deterministic evidence.",
        "synthetic_clock":now.isoformat(),"metadata":metadata,"fixtures":fixtures,"complete_record":complete,"incomplete_record":unknown,
        "audit_history":history,"summary":summary,"verification":{"portion_conservation":True,"measurement_and_estimate_separate":True,
            "independent_remaining_portions":remaining,"independent_simulated_scale_sum_kg":float(scale_sum),
            "independent_portion_estimate_kg":float(portion_estimate),"independent_surplus_reading_kg":float(mass_by_category["discarded_surplus"]),
            "unknown_portions":5,"unknown_prevents_finalization":True,"served_exceeds_prepared_rejected":True,
            "plan_linked_to_original_440_recommendation":True,"synthetic_excluded_from_actual_cohorts":True,"original_revisions_unchanged":True,"restart_identical":True}}


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/evaluation/build_04_evaluation.json')
    args=parser.parse_args()
    first=evaluate()
    second=evaluate()
    assert first==second,"Deterministic repeat failed; no evidence emitted."
    canonical=json.dumps(first,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    first["verification"]["repeat_identical"]=True
    first["verification"]["canonical_workflow_sha256"]=hashlib.sha256(canonical).hexdigest()
    output=args.output
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(first,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"output":str(output),"evidence_type":first["evidence_type"],"verification":first["verification"]},indent=2))


if __name__=="__main__":
    main()
