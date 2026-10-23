"""Operational revision workflow. All mutation appends; provenance cannot change."""
import csv
import io
import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .database import ROOT
from .decision_schemas import DecisionRequest, SavedPlan
from .decision_service import demo_request, get_plan, saved_info
from .decisions import preview as decision_preview
from .impact import assess, metadata, utc
from .impact_schemas import Assessment, ComparisonInput, CorrectionInput, PlanReference, RecordResult, ServiceInput, Source, Basis, VersionInput
from .models import DecisionPlan, OperationalRevision as Revision, OperationalService as Service


def utc_now():
    return datetime.now(timezone.utc)


def fail(status, message):
    raise HTTPException(status, detail={"message": message})


def plan_reference(session, record):
    if record.decision_plan_id is None:
        return None
    p = get_plan(session, record.decision_plan_id)
    if p.inputs["planning_date"] != record.service_date.isoformat():
        fail(422, "Plan service date must match the operational service date. Keep unrelated plans separate.")
    if record.menu.isdigit() and p.inputs["menu"] is not None and int(record.menu) != p.inputs["menu"]:
        fail(422, "Numeric menu identifier disagrees with the linked plan.")
    if p.inputs["scenario_kind"] == "synthetic_demo" and record.source_category != "synthetic":
        fail(422, "A synthetic demo plan may only link to a synthetic operational record.")
    base, rec, comp = p.result["baseline"], p.result["recommended"], p.result["comparison"]
    return PlanReference(id=p.id, created_at=utc(p.created_at), planning_date=p.inputs["planning_date"], menu=p.inputs["menu"],
        engine_version=p.engine_version, input_fingerprint=p.input_fingerprint, scenario_kind=p.inputs["scenario_kind"],
        baseline_portions=base["quantity"], recommended_portions=rec["quantity"] if rec else None,
        modeled_baseline_surplus_kg=base["expected_surplus_kg"], modeled_recommended_surplus_kg=rec["expected_surplus_kg"] if rec else None,
        modeled_surplus_difference_kg=comp["potential_surplus_reduction_kg"] if comp else None, evidence_type="assumption_based")


def current_query():
    latest = select(Revision.service_id, func.max(Revision.version).label("version")).group_by(Revision.service_id).subquery()
    return select(Revision).join(latest, (Revision.service_id == latest.c.service_id) & (Revision.version == latest.c.version))


def filtered_query(source, status="all", basis=None, site=None, menu=None, start=None, end=None):
    query = current_query().where(Revision.source_category == source)
    if status != "all":
        query = query.where(Revision.status == status)
    if start:
        query = query.where(Revision.service_date >= start)
    if end:
        query = query.where(Revision.service_date <= end)
    # Portable JSON inspection is kept outside SQL; at most 5000 heads are read.
    return query


def heads(session, source, *, status="all", basis=None, site=None, menu=None, start=None, end=None):
    rows = session.scalars(filtered_query(source, status, start=start, end=end).order_by(Revision.service_date.desc(), Revision.service_id.desc()).limit(5001)).all()
    if len(rows) > 5000:
        fail(422, "This cohort exceeds the 5,000-record analytics limit. Narrow the service date range.")
    return [r for r in rows if (site is None or r.payload["site"] == site) and (menu is None or r.payload["menu"] == menu)
        and (basis is None or any(m["basis"] == basis for m in r.payload["measurements"]))]


def current(session, service_id):
    r = session.scalar(current_query().where(Revision.service_id == service_id))
    if r is None:
        fail(404, "Operational service record not found.")
    return r


def result(session, r):
    service = session.get(Service, r.service_id)
    return {"id": r.service_id, "revision_id": r.id, "version": r.version, "status": r.status, "event": r.event,
        "correction_reason": r.correction_reason, "created_at": utc(r.created_at), "service_created_at": utc(service.created_at),
        "changed_fields": r.changed_fields,
        "previous_revision_id": r.previous_revision_id, "record": r.payload, "assessment": r.assessment, "plan_reference": r.plan_snapshot}


def append(session, service, record, *, parent=None, event="created", status="draft", reason=None):
    if parent and parent.version >= 200:
        fail(422,"This service reached the 200-revision bound. Export its audit history and review the data collection process.")
    now = utc_now()
    reference = plan_reference(session, record)
    quality = assess(record, reference, now=now)
    if status == "finalized" and not quality["can_finalize"]:
        fail(422, "Cannot finalize: " + " ".join(quality["finalization_blockers"]))
    payload=record.model_dump(mode="json")
    def changed(old,new,path=""):
        if isinstance(old,dict) and isinstance(new,dict):
            return [v for k in sorted(set(old)|set(new)) for v in changed(old.get(k),new.get(k),f"{path}.{k}".strip("."))]
        return [path] if old!=new else []
    row = Revision(service_id=service.id, version=parent.version+1 if parent else 1, previous_revision_id=parent.id if parent else None,
        created_at=now, event=event, status=status, correction_reason=reason, source_category=record.source_category,
        changed_fields=changed(parent.payload,payload) if parent else sorted(payload),
        service_date=record.service_date, decision_plan_id=record.decision_plan_id, payload=payload,
        assessment=quality, plan_snapshot=reference.model_dump(mode="json") if reference else None)
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        fail(409, "A concurrent revision was saved first. Refresh the record and retry with its current version.")
    return row


def expected(row, version):
    if row.version != version:
        fail(409, f"Stale revision: expected {version}, current version is {row.version}. Refresh before saving.")


def demo_inputs():
    return json.loads((ROOT / "data/fixtures/synthetic_impact_demo.json").read_text(encoding="utf-8"))


def add_demo(session):
    found = session.scalars(select(Service).where(Service.demo_key.in_(["impact04-complete", "impact04-incomplete"]))).all()
    if len(found) == 2:
        return [result(session, current(session, s.id)) for s in sorted(found, key=lambda s:s.id)]
    fixture = demo_inputs()
    date = fixture["complete"]["service_date"]
    request = DecisionRequest.model_validate({**demo_request().model_dump(mode="json"), "planning_date": date})
    calculation = decision_preview(request)
    plan = DecisionPlan(created_at=utc_now(), engine_version=calculation["engine_version"], evidence_type="assumption_based",
        input_fingerprint=calculation["input_fingerprint"], inputs=request.model_dump(mode="json"), result=calculation, context_reference=None)
    session.add(plan)
    session.flush()
    rows=[]
    for kind in ("complete", "incomplete"):
        service = Service(created_at=utc_now(), demo_key=f"impact04-{kind}")
        session.add(service)
        session.flush()
        record = ServiceInput.model_validate({**fixture[kind], "decision_plan_id": plan.id})
        first = append(session, service, record)
        rows.append(append(session, service, record, parent=first, event="finalized", status="finalized") if kind=="complete" else first)
    session.commit()
    return [result(session,r) for r in rows]


def safe_csv(value):
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


def export_csv(records):
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    columns = ["service_id","version","status","source_category","service_date","site","menu","prepared","served","turn_aways","observed_diners",
        "remaining_portions","donated","retained","repurposed","discarded","unknown","discrepancy_portions","estimated_discarded_kg",
        "combined_weighed_kg","entry_complete","planning_timing","assessment_version"]
    mass_fields=("mass_kg","basis","method","scope_status","scope_description","material_type","destination","gross_kg","tare_kg")
    columns.extend(f"{category}_{field}" for category in ("discarded_surplus","plate_waste","preparation_waste") for field in mass_fields)
    writer.writerow(columns)
    for r in records:
        p,a = r["record"],r["assessment"]
        values=[r["id"],r["version"],r["status"],p["source_category"],p["service_date"],p["site"],p["menu"],p["prepared"],p["served"],p["turn_aways"],p["observed_diners"],
            a["accounting"]["remaining_portions"],*[p["dispositions"][k] for k in ("donated","retained","repurposed","discarded","unknown")],
            a["accounting"]["discrepancy_portions"],a["accounting"]["estimated_discarded_kg"],a["combined_weighed_kg"],a["entry_complete"],a["planning_timing"],a["assessment_version"]]
        values.extend(next((m.get(field) for m in p["measurements"] if m["category"]==category),None)
            for category in ("discarded_surplus","plate_waste","preparation_waste") for field in mass_fields)
        writer.writerow([safe_csv(v) if isinstance(v,str) else ("" if v is None else v) for v in values])
    return out.getvalue()


def impact_router(factory, *, public_demo=False):
    from .impact_analytics import summarize, compare
    router = APIRouter(prefix="/api/impact", tags=["Impact Ledger"])

    @router.get("/metadata")
    def meta():
        return metadata()

    @router.get("/demo")
    def demo():
        return demo_inputs()

    @router.post("/demo", response_model=list[RecordResult], status_code=201)
    def seed():
        with factory() as session:
            try:
                return add_demo(session)
            except IntegrityError:
                session.rollback()
                fail(409, "Synthetic examples were added concurrently. Refresh the ledger.")

    @router.post("/preview", response_model=Assessment)
    def preview(record:ServiceInput):
        with factory() as session:
            return assess(record, plan_reference(session,record), now=utc_now())

    @router.post("/records", response_model=RecordResult, status_code=201)
    def create(record:ServiceInput):
        with factory() as session:
            service=Service(created_at=utc_now())
            session.add(service)
            session.flush()
            row=append(session,service,record)
            session.commit()
            return result(session,row)

    @router.get("/records", response_model=list[RecordResult])
    def listing(source_category:Source="synthetic" if public_demo else "user_reported", status:str=Query("all", pattern="^(all|draft|finalized)$"),
        basis:Basis|None=None, site:str|None=Query(None,max_length=100), menu:str|None=Query(None,max_length=150),
        start:date|None=None, end:date|None=None, limit:int=Query(20,ge=1,le=100), offset:int=Query(0,ge=0,le=100000)):
        with factory() as session:
            return [result(session,r) for r in heads(session,source_category,status=status,basis=basis,site=site,menu=menu,start=start,end=end)[offset:offset+limit]]

    @router.get("/summary")
    def summary(source_category:Source="synthetic" if public_demo else "user_reported", status:str=Query("all",pattern="^(all|draft|finalized)$"),basis:Basis|None=None,
        site:str|None=Query(None,max_length=100),menu:str|None=Query(None,max_length=150),start:date|None=None,end:date|None=None):
        with factory() as session:
            return summarize(heads(session,source_category,status=status,basis=basis,site=site,menu=menu,start=start,end=end),source_category,status,basis)

    @router.post("/comparison")
    def comparison(request:ComparisonInput):
        with factory() as session:
            rows=heads(session,request.source_category,status="finalized",site=request.site,menu=request.menu,start=request.baseline_start,end=request.trial_end)
            return compare(rows,request)

    @router.get("/records/{service_id}", response_model=RecordResult)
    def detail(service_id:int):
        with factory() as session:
            return result(session,current(session,service_id))

    @router.get("/records/{service_id}/history", response_model=list[RecordResult])
    def history(service_id:int):
        with factory() as session:
            current(session,service_id)
            return [result(session,r) for r in session.scalars(select(Revision).where(Revision.service_id==service_id).order_by(Revision.version)).all()]

    @router.get("/records/{service_id}/quality",response_model=Assessment)
    def quality(service_id:int):
        with factory() as session:
            return current(session,service_id).assessment

    @router.get("/records/{service_id}/plan",response_model=SavedPlan)
    def original_plan(service_id:int):
        with factory() as session:
            row=current(session,service_id)
            if row.decision_plan_id is None:
                fail(404,"This service has no linked Decision Studio plan.")
            return saved_info(get_plan(session,row.decision_plan_id))

    @router.post("/records/{service_id}/revisions",response_model=RecordResult,status_code=201)
    def correction(service_id:int,request:CorrectionInput):
        with factory() as session:
            old=current(session,service_id)
            expected(old,request.expected_version)
            if old.source_category!=request.record.source_category:
                fail(422,"Source category is immutable across revisions. Synthetic records cannot become actual observations.")
            row=append(session,session.get(Service,service_id),request.record,parent=old,event="corrected",reason=request.correction_reason)
            session.commit()
            return result(session,row)

    @router.post("/records/{service_id}/finalize",response_model=RecordResult,status_code=201)
    def finalize(service_id:int,request:VersionInput):
        with factory() as session:
            old=current(session,service_id)
            expected(old,request.expected_version)
            if old.status=="finalized":
                fail(409,"This revision is already finalized. Append a correction with a reason to change it.")
            row=append(session,session.get(Service,service_id),ServiceInput.model_validate(old.payload),parent=old,event="finalized",status="finalized")
            session.commit()
            return result(session,row)

    @router.get("/records/{service_id}/export")
    def export(service_id:int,format:str=Query("json",pattern="^(json|csv)$")):
        with factory() as session:
            current(session,service_id)
            records=[RecordResult.model_validate(result(session,r)).model_dump(mode="json") for r in session.scalars(select(Revision).where(Revision.service_id==service_id).order_by(Revision.version)).all()]
            data=export_csv(records) if format=="csv" else json.dumps({"notice":"Operational self-reports/synthetic examples, not independent verification or causal impact. All revisions preserved.","history":records},sort_keys=True,indent=2,allow_nan=False)+"\n"
            return Response(data,media_type="text/csv" if format=="csv" else "application/json",headers={"Content-Disposition":f'attachment; filename="mealloop-operational-{service_id}.{format}"'})

    return router
