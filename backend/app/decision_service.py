"""Preview, immutable saving, retrieval, and safe fixed-name exports."""
import csv
import io
import json
from datetime import timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select

from .database import ROOT
from .decision_schemas import DecisionPreview, DecisionRequest, PlanSummary, SavedPlan
from .decisions import engine_metadata, preview
from .models import DecisionPlan, ImportBatch, SourceDataset


def demo_request():
    return DecisionRequest.model_validate_json((ROOT / "data/fixtures/synthetic_decision_demo.json").read_text(encoding="utf-8"))


def context_reference(session, batch_id):
    if batch_id is None:
        return None
    batch = session.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(404, detail={"message": "Historical context batch not found. Remove the optional reference or choose an existing batch."})
    source = session.get(SourceDataset, batch.source_id)
    return {"batch_id": batch.id, "source_title": source.title, "source_kind": source.kind,
        "source_doi": source.doi, "raw_sha256": batch.sha256,
        "role": "Read-only provenance reference. No historical measurement or forecast was used to infer demand, production, surplus, or impact."}


def saved_info(plan):
    created = plan.created_at.replace(tzinfo=timezone.utc) if plan.created_at.tzinfo is None else plan.created_at
    return {"id": plan.id, "created_at": created, "engine_version": plan.engine_version,
        "evidence_type": plan.evidence_type, "input_fingerprint": plan.input_fingerprint,
        "inputs": plan.inputs, "result": plan.result, "context_reference": plan.context_reference}


def save_plan(session, request):
    reference = context_reference(session, request.context_batch_id)
    result = preview(request)  # never trust a client-submitted result
    plan = DecisionPlan(engine_version=result["engine_version"], evidence_type="assumption_based",
        input_fingerprint=result["input_fingerprint"], inputs=request.model_dump(mode="json"),
        result=result, context_reference=reference)
    session.add(plan)
    session.commit()
    return saved_info(plan)


def get_plan(session, plan_id):
    plan = session.get(DecisionPlan, plan_id)
    if plan is None:
        raise HTTPException(404, detail={"message": "Saved planning scenario not found."})
    return plan


def csv_export(plan):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    # Only fixed headers and server-calculated numeric fields: user-controlled
    # names/titles never enter spreadsheet cells, preventing formula injection.
    writer.writerow(["evidence_type", "scenario_kind", "engine_version", "input_fingerprint", "quantity", "feasible",
        "expected_demand_portions", "expected_served_portions", "expected_surplus_portions", "expected_surplus_kg",
        "expected_unmet_portions", "probability_fully_served", "expected_fill_rate", "capacity_use", "rejection_reasons"])
    for row in plan.result["candidates"]:
        writer.writerow(["assumption_based", plan.inputs["scenario_kind"], plan.engine_version, plan.input_fingerprint,
            *[row[k] for k in ("quantity", "feasible", "expected_demand_portions", "expected_served_portions", "expected_surplus_portions",
                "expected_surplus_kg", "expected_unmet_portions", "probability_fully_served", "expected_fill_rate", "capacity_use")],
            ";".join(row["rejection_reasons"])])
    return output.getvalue()


def decision_router(factory, *, public_demo=False):
    router = APIRouter(prefix="/api/decisions", tags=["Decision Studio"])

    @router.get("/metadata")
    def metadata():
        result = engine_metadata()
        if public_demo:
            result["limits"].update(maximum_scenarios=10, maximum_candidates=201)
        return result

    @router.get("/demo", response_model=DecisionRequest)
    def demo():
        return demo_request()

    @router.post("/preview", response_model=DecisionPreview)
    def calculate(request: DecisionRequest):
        return preview(request)

    @router.post("/plans", response_model=SavedPlan, status_code=201)
    def save(request: DecisionRequest):
        with factory() as session:
            return save_plan(session, request)

    @router.get("/plans", response_model=list[PlanSummary])
    def plans(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=100_000)):
        with factory() as session:
            rows = session.scalars(select(DecisionPlan).order_by(DecisionPlan.id.desc()).offset(offset).limit(limit)).all()
            return [{"id": r.id, "created_at": saved_info(r)["created_at"], "title": r.inputs["title"],
                "planning_date": r.inputs["planning_date"], "scenario_kind": r.inputs["scenario_kind"],
                "evidence_type": r.evidence_type, "engine_version": r.engine_version, "status": r.result["status"],
                "baseline_portions": r.inputs["baseline_portions"],
                "recommended_portions": r.result["recommended"]["quantity"] if r.result["recommended"] else None} for r in rows]

    @router.get("/plans/{plan_id}", response_model=SavedPlan)
    def retrieve(plan_id: int):
        if plan_id < 1:
            raise HTTPException(422, detail={"message": "Plan ID must be positive."})
        with factory() as session:
            return saved_info(get_plan(session, plan_id))

    @router.get("/plans/{plan_id}/export")
    def export(plan_id: int, format: str = Query("json", pattern="^(json|csv)$")):
        with factory() as session:
            plan = get_plan(session, plan_id)
            if format == "csv":
                data, media = csv_export(plan), "text/csv"
            else:
                data, media = json.dumps(SavedPlan.model_validate(saved_info(plan)).model_dump(mode="json"), indent=2,
                    sort_keys=True, allow_nan=False) + "\n", "application/json"
            return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="mealloop-assumption-plan-{plan.id}.{format}"'})

    return router
