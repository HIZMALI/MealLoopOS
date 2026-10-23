"""Deterministic accounting and evidence assessment; no forecast inference."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from .impact_schemas import ServiceInput

VERSION = "impact04-v1"
CATEGORIES = ["discarded_surplus", "plate_waste", "preparation_waste"]
DISPOSITIONS = ["donated", "retained", "repurposed", "discarded", "unknown"]
SOURCES = {"synthetic": "Synthetic demonstration", "user_reported": "User-reported observation — not independently verified",
    "user_reported_documented": "User-reported with supporting references — not independently verified"}
LIMITATIONS = [
    "A complete entry is not independent verification or causal evidence of a software effect.",
    "Served portions do not reveal unconstrained demand. Unknown turn-aways remain missing.",
    "Rescued, retained and repurposed portions are separate from discarded-food measurements. Their eventual consumption or safe handling is not certified.",
    "Portion-to-mass conversions are estimates; never add them to physical readings of the same food.",
    "Planning assumptions and baseline quantities are not counterfactual observations or achieved waste prevention.",
    "Scope/method declarations and document references are supplied by the operator, not independently checked.",
    "Local append-only history is not cryptographically tamper-proof. Authentication is required before public deployment.",
]


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def accounting(record: ServiceInput):
    remaining = record.prepared - record.served if record.prepared is not None and record.served is not None else None
    values = record.dispositions.model_dump()
    missing = [k for k,v in values.items() if v is None]
    known = sum(v for v in values.values() if v is not None)
    discrepancy = remaining - known if remaining is not None else None
    estimate = (float(D(values["discarded"]) * D(str(record.portion_mass_g)) / 1000)
        if values["discarded"] is not None and record.portion_mass_g is not None else None)
    return {"remaining_portions": remaining, "known_disposition_portions": known, "discrepancy_portions": discrepancy,
        "missing_dispositions": missing, "reconciled": not missing and discrepancy == 0,
        "unknown_portions": values["unknown"], "estimated_discarded_kg": estimate,
        "estimate_label": "Portion-count conversion estimate; not a scale reading. Never added to physical measurements."}


def mass_inventory(record):
    measurements = record.measurements
    if len(measurements) != len(CATEGORIES):
        return None, "No combined total: all three waste streams need entries; missing mass is not zero."
    if not record.disjoint_scope_note or any(m.scope_status != "disjoint_stream" for m in measurements):
        return None, "No combined total: disjoint stream boundaries are unresolved or possible overlap is declared."
    if any(m.basis != "weighed" for m in measurements):
        return None, "No combined physically weighed total: estimated/imported values are shown separately."
    if len({m.method.strip().casefold() for m in measurements}) != 1:
        return None, "No combined total: measurement methods differ; review their compatibility."
    if len({m.material_type for m in measurements}) != 1 or any(m.material_type == "unspecified" or m.destination == "unspecified" for m in measurements):
        return None, "No combined total: material definitions or waste destinations are unspecified/incompatible."
    return float(sum((D(str(m.mass_kg)) for m in measurements), D(0))), "Sum of three operator-declared disjoint, compatible weighed streams. Self-reported scopes; synthetic readings remain synthetic."


def assess(record, plan=None, *, now):
    counts = accounting(record)
    issues, blockers, labels = [], [], []
    if counts["remaining_portions"] is None:
        blockers.append("Enter both actual prepared and served counts.")
    if counts["missing_dispositions"]:
        blockers.append("Enter all five disposition counts, including explicit zeros where observed.")
    if counts["discrepancy_portions"] not in (None, 0):
        blockers.append(f'Disposition discrepancy: {counts["discrepancy_portions"]} portions remain relative to the known entries. No balancing value was invented.')
    if counts["unknown_portions"] not in (None, 0):
        blockers.append(f'{counts["unknown_portions"]} portions have unknown disposition. Resolve this knowledge gap before finalizing.')
    if not record.count_method:
        blockers.append("Describe the count measurement method.")
    if record.service_date > utc(now).date():
        blockers.append("A future service cannot be finalized as an observed operation (server UTC date policy).")
    present = [m.category for m in record.measurements]
    missing_mass = [k for k in CATEGORIES if k not in present]
    weighed = [m.category for m in record.measurements if m.basis == "weighed"]
    mass, explanation = mass_inventory(record)
    if missing_mass:
        issues.append("Missing mass categories: " + ", ".join(missing_mass) + ".")
    if record.turn_aways is None:
        issues.append("Turn-aways were not recorded; actual unmet demand is unknown.")
    if record.portion_mass_g is None:
        issues.append("No portion mass supplied; count conversion estimate is unavailable.")
    if mass is None:
        issues.append(explanation)
    if any(m.basis != "weighed" for m in record.measurements):
        issues.append("Non-weighed entries remain estimates/imported reports, not physical readings.")
    timing, timing_note = "unlinked", "No saved pre-service plan is linked; this is a retrospective observation."
    diff_rec = diff_base = followed = None
    if plan:
        # With a date but no independently captured service start time, use the
        # earliest start of that calendar date anywhere (UTC+14). Same-day
        # capture never proves prospective planning. Date itself is self-reported.
        earliest = datetime.combine(record.service_date, datetime.min.time(), timezone.utc) - timedelta(hours=14)
        if utc(plan.created_at) < earliest:
            timing = "prospective_capture"
            timing_note = "Server plan timestamp predates the earliest possible start of the reported service date (UTC+14 boundary). Service date/occurrence remain operator-reported."
        else:
            timing = "retrospective"
            timing_note = "Server timestamp does not prove this plan existed before service. Same-day/backfilled plans are retrospective; a user cannot supply the capture timestamp."
        if record.prepared is not None:
            diff_base = record.prepared - plan.baseline_portions
            if plan.recommended_portions is not None:
                diff_rec = record.prepared - plan.recommended_portions
                followed = diff_rec == 0
        if plan.recommended_portions is None:
            issues.append("Linked plan had no feasible recommendation; adherence to a recommendation is undefined.")
    if timing != "prospective_capture":
        labels.append("Retrospective observation")
    else:
        labels.append("Prospectively captured plan relative to reported date")
    if any(m.scope_status != "disjoint_stream" for m in record.measurements) or (record.measurements and not record.disjoint_scope_note):
        labels.append("Measurement scope unresolved")
    complete = not blockers and not issues
    labels.insert(0, "Synthetic demonstration" if record.source_category == "synthetic" else ("Complete self-reported record" if complete else "Incomplete record"))
    if record.source_category == "synthetic" and not complete:
        labels.append("Incomplete record")
    return {"assessment_version": VERSION, "provenance_label": SOURCES[record.source_category], "independently_verified": False,
        "labels": labels, "entry_complete": complete, "can_finalize": not blockers, "finalization_blockers": blockers,
        "issues": issues, "accounting": counts, "measurement_categories_present": present,
        "missing_measurement_categories": missing_mass, "physically_weighed_categories": weighed,
        "combined_weighed_kg": mass, "combined_mass_explanation": explanation,
        "planning_timing": timing, "planning_timing_explanation": timing_note,
        "actual_minus_recommended": diff_rec, "actual_minus_baseline": diff_base, "followed_exactly": followed,
        "limitations": LIMITATIONS}


def metadata():
    return {"assessment_version": VERSION, "source_categories": SOURCES, "mass_categories": CATEGORIES,
        "dispositions": DISPOSITIONS, "measurement_bases": ["weighed", "estimated", "imported"],
        "limits": {"maximum_request_bytes": 65536, "maximum_count": 100000, "maximum_mass_kg": 1000000,
            "maximum_analytics_records": 5000, "maximum_list_page": 100},
        "prospective_policy": "Server plan timestamp must predate the earliest possible start of the reported date (UTC+14); date matching required. No client capture timestamp is accepted.",
        "limitations": LIMITATIONS, "standard_guidance": "https://flwprotocol.org/flw-standard/"}
