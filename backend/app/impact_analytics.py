"""Coverage-aware descriptive summaries of current operational revisions only."""
from collections import Counter, defaultdict
from decimal import Decimal as D

from .impact import CATEGORIES, DISPOSITIONS, SOURCES

COMPARISON_LABEL = "Observational comparison — not causal evidence."


def total(values):
    known=[v for v in values if v is not None]
    return {"total": float(sum((D(str(v)) for v in known),D(0))) if known else None,
        "covered":len(known),"missing":len(values)-len(known)}


def scope_signature(payload, measurement):
    # Exact normalized operator declarations. Matching text is not assurance.
    return tuple(str(v).strip().casefold() for v in (payload["site"],payload["menu"],payload["disjoint_scope_note"],
        measurement["basis"],measurement["method"],measurement["scope_status"],measurement["scope_description"],
        measurement["material_type"],measurement["destination"]))


def summarize(rows, source, status="all", basis=None):
    counts={key:total([r.payload.get(key) for r in rows]) for key in ("prepared","served","turn_aways","observed_diners")}
    counts["remaining"]=total([r.assessment["accounting"]["remaining_portions"] for r in rows])
    counts.update({key:total([r.payload["dispositions"][key] for r in rows]) for key in DISPOSITIONS})
    mass={category:{kind:total([next((m["mass_kg"] for m in r.payload["measurements"] if m["category"]==category and m["basis"]==kind),None) for r in rows])
        for kind in ("weighed","estimated","imported")} for category in CATEGORIES}
    inventories=[r for r in rows if r.assessment["combined_weighed_kg"] is not None]
    signatures={tuple(scope_signature(r.payload,m) for m in sorted(r.payload["measurements"],key=lambda m:m["category"])) for r in inventories}
    compatible=len(signatures)<=1
    combined=total([r.assessment["combined_weighed_kg"] if compatible else None for r in rows])
    trends=defaultdict(list)
    for row in rows:
        trends[row.service_date.isoformat()].append(row)
    linked=[r for r in rows if r.plan_snapshot is not None]
    assessable=[r for r in linked if r.assessment["followed_exactly"] is not None]
    return {"source_category":source,"provenance_label":SOURCES[source],"status_filter":status,"basis_filter":basis,
        "service_count":len(rows),"draft_services":sum(r.status=="draft" for r in rows),"counts":counts,"mass_by_category":mass,
        "combined_weighed_kg":combined,"combined_explanation": "Only complete, disjoint and compatible three-stream inventories are included; coverage shown. Estimates never added." if compatible else "Combined inventory blocked: current services have different site/menu/scope/method definitions. Filter to a compatible cohort. Category totals remain separate reports.",
        "estimated_discarded_kg":total([r.assessment["accounting"]["estimated_discarded_kg"] for r in rows]),
        "evidence":{"complete_entries":sum(r.assessment["entry_complete"] for r in rows),"incomplete_entries":sum(not r.assessment["entry_complete"] for r in rows),
            "unknown_disposition_services":sum(r.payload["dispositions"]["unknown"] not in (None,0) for r in rows),
            "missing_disposition_services":sum(bool(r.assessment["accounting"]["missing_dispositions"]) for r in rows),
            "unreconciled_services":sum(not r.assessment["accounting"]["reconciled"] for r in rows),
            "services_missing_mass":sum(bool(r.assessment["missing_measurement_categories"]) for r in rows),
            "independently_verified_services":0},
        "adherence":{"linked_services":len(linked),"assessable_services":len(assessable),"followed_exactly":sum(r.assessment["followed_exactly"] for r in assessable),
            "prospective_captures":sum(r.assessment["planning_timing"]=="prospective_capture" for r in linked),
            "retrospective_or_unlinked":sum(r.assessment["planning_timing"]!="prospective_capture" for r in rows)},
        "methods":dict(Counter(m["basis"]+" · "+m["method"] for r in rows for m in r.payload["measurements"])),
        "daily":[{"date":date,"services":len(group),"prepared":total([r.payload["prepared"] for r in group])["total"],
            "served":total([r.payload["served"] for r in group])["total"],"remaining":total([r.assessment["accounting"]["remaining_portions"] for r in group])["total"]}
            for date,group in sorted(trends.items())],
        "notes":["Current revision of each service only; superseded snapshots are excluded to prevent revision double-counting.",
            "Each view uses exactly one provenance category. Finland historical records and synthetic cohorts are never included in user-report totals.",
            "A basis filter selects services containing that basis; other measurement bases remain explicitly separated inside those services.",
            "Category totals are separate operator reports, potentially heterogeneous; do not sum them yourself when combined inventory is unavailable.",
            "Partial coverage, explicit zeros, missing entries and drafts remain distinguishable. Entries are not proven unique physical services.",COMPARISON_LABEL]}


def compare(rows, request):
    groups={"baseline":[r for r in rows if request.baseline_start<=r.service_date<=request.baseline_end],
        "trial":[r for r in rows if request.trial_start<=r.service_date<=request.trial_end]}
    signatures=set()
    reasons=[]
    results={}
    for name, group in groups.items():
        covered=[]
        methods=Counter()
        for row in group:
            for m in row.payload["measurements"]:
                if m["category"]!=request.category:
                    continue
                methods[m["basis"]+" · "+m["method"]]+=1
                if m["basis"]!=request.basis:
                    continue
                covered.append((row,m))
                signatures.add(scope_signature(row.payload,m))
                if m["scope_status"]!="disjoint_stream" or not row.payload["disjoint_scope_note"] or m["material_type"]=="unspecified" or m["destination"]=="unspecified":
                    reasons.append("Selected measurement boundaries, material or destination are unresolved.")
        if not covered:
            reasons.append(f"No covered {request.basis} {request.category} observations in {name}.")
        mass=sum((D(str(m["mass_kg"])) for _,m in covered),D(0))
        paired=[(r,m) for r,m in covered if r.payload.get("observed_diners") is not None and r.payload["observed_diners"]>0]
        diners=sum(r.payload["observed_diners"] for r,_ in paired)
        paired_mass=sum((D(str(m["mass_kg"])) for _,m in paired),D(0))
        results[name]={"services":len(group),"covered_observations":len(covered),"missing_or_other_basis":len(group)-len(covered),
            "reported_mass_kg":float(mass) if covered else None,"kg_per_covered_service":float(mass/len(covered)) if covered else None,
            "g_per_observed_diner":float(paired_mass*1000/diners) if diners else None,"diner_covered_services":len(paired),
            "observed_diners":diners if paired else None,"paired_mass_kg":float(paired_mass) if paired else None,
            "methods":dict(methods),"menus":dict(Counter(r.payload["menu"] for r in group)),"sites":dict(Counter(r.payload["site"] for r in group))}
    if len(signatures)>1:
        reasons.append("Incompatible site/menu/scope/material/destination/method declarations. Narrow the filters or correct the definitions with an audit reason; no pooled comparison is valid.")
    blocked=bool(reasons)
    # Do not publish comparable aggregate values if definitions differ. Coverage
    # and method/context counts remain visible to explain rejection.
    if blocked:
        for period in results.values():
            for key in ("reported_mass_kg","kg_per_covered_service","g_per_observed_diner","paired_mass_kg"):
                period[key]=None
    difference=None
    if not blocked:
        a,b=results["baseline"],results["trial"]
        delta=float(D(str(b["kg_per_covered_service"]))-D(str(a["kg_per_covered_service"])))
        difference={"kg_per_service_trial_minus_baseline":delta,"relative_change":delta/a["kg_per_covered_service"] if a["kg_per_covered_service"] else None,
            "g_per_diner_trial_minus_baseline":float(D(str(b["g_per_observed_diner"]))-D(str(a["g_per_observed_diner"]))) if a["g_per_observed_diner"] is not None and b["g_per_observed_diner"] is not None else None}
    return {"label":COMPARISON_LABEL,"source_category":request.source_category,"basis":request.basis,"category":request.category,
        "status":"blocked" if blocked else "comparable_descriptive","reasons":list(dict.fromkeys(reasons)),"periods":results,"difference":difference,
        "notes":["Finalized current revisions only. Missing/other-basis records are excluded with coverage shown; no imputation.",
            "Per-diner metrics use separately observed unique diners, never prepared or served portions. Paired masses and denominators use the same services.",
            "Method and scope compatibility uses exact normalized operator declarations; this is not independent assurance.",
            "Date, site, menu and attendance context do not control confounding. Differences cannot establish software effects, verified savings or a counterfactual baseline."]}
