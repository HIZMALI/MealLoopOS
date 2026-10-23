"""Pure exact-rational scenario enumeration. No measured/forecast data access."""
import hashlib
import json
from fractions import Fraction as F

from .decision_schemas import DecisionRequest, MAX_CANDIDATES, MAX_CAPACITY, MAX_DEMAND, MAX_SCENARIOS

VERSION = "decision03-v1"
OBJECTIVE = "Minimize probability-weighted expected surplus mass over feasible batch quantities."
TIE_BREAK = "Lowest expected surplus mass, then lowest expected unmet portions, then lowest quantity."
REASONS = {"below_minimum": "Below the minimum production quantity.",
    "exceeds_capacity": "Exceeds preparation capacity.", "not_batch_multiple": "Not a multiple of the batch increment.",
    "below_reliability": "Does not meet the scenario-conditional full-service reliability target."}
LIMITATIONS = [
    "Assumption-based scenario only: demand values, probabilities, portion mass, and operating constraints are supplied assumptions, not measured demand or validated forecasts.",
    "Modeled edible surplus is food potentially at risk of waste, not automatically discarded mass or realized food-waste prevention.",
    "Do not add modeled surplus to historical kitchen/serving waste or forecast waste as non-overlapping measurements; this can double-count the same physical food.",
    "Scenario-conditional reliability is not a calibrated real-world confidence guarantee. Results are only as defensible as the demand assumptions.",
    "The Finland dataset does not record production, unconstrained demand, customers turned away, or validated production-plan effects. It cannot establish the effectiveness of these plans.",
    "This is a one-menu, single-service calculation with fixed portion mass and linear quantities; no nutrition, staffing, inventory, food safety, cost, carbon, donation, or causal impact model is included.",
    "Sensitivity cases are additional user-specified demand assumptions, not validation of demand forecasts. No constraints are relaxed automatically.",
]


def engine_metadata():
    return {"engine_version": VERSION, "evidence_type": "assumption_based", "algorithm": "Exact enumeration of integer multiples of the batch increment from zero through capacity.",
        "objective": OBJECTIVE, "tie_break": TIE_BREAK,
        "limits": {"maximum_scenarios": MAX_SCENARIOS, "maximum_demand": MAX_DEMAND, "maximum_capacity": MAX_CAPACITY,
            "maximum_candidates": MAX_CANDIDATES, "maximum_request_bytes": 65536, "maximum_portion_mass_g": 10000},
        "probability_sum_tolerance": 1e-9, "probability_policy": "Weights are used unchanged; no normalization. Feasibility uses exact comparisons on validated decimal representations.",
        "zero_demand_policy": "Expected fill rate is 1 by convention when expected demand is zero; no demand remains unserved.",
        "sensitivity_rounding": "Scale each integer demand by (1 +/- percentage/100), then round half up to whole portions.",
        "rejection_reason_labels": REASONS, "assumptions_and_limitations": LIMITATIONS}


def fingerprint(request):
    data = {"engine_version": VERSION, "inputs": request.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def exact_metrics(quantity, request):
    demand, served, surplus, unmet, reliability = (F(0) for _ in range(5))
    for s in request.demand_scenarios:
        p, d = F(str(s.probability)), s.demand_portions
        demand += p * d
        served += p * min(quantity, d)
        surplus += p * max(quantity - d, 0)
        unmet += p * max(d - quantity, 0)
        if quantity >= d:
            reliability += p
    return {"expected_demand_portions": demand, "expected_served_portions": served,
        "expected_surplus_portions": surplus, "expected_unmet_portions": unmet,
        "expected_surplus_kg": surplus * F(str(request.portion_mass_g)) / 1000,
        "probability_fully_served": reliability,
        "expected_fill_rate": served / demand if demand else F(1)}


def evaluate_quantity(quantity, request, *, outcomes=False):
    metrics = exact_metrics(quantity, request)
    reasons = []
    if quantity < request.minimum_portions:
        reasons.append("below_minimum")
    if quantity > request.maximum_capacity:
        reasons.append("exceeds_capacity")
    if quantity % request.batch_increment:
        reasons.append("not_batch_multiple")
    if metrics["probability_fully_served"] < F(str(request.reliability_target)):
        reasons.append("below_reliability")
    result = {"quantity": quantity, **{k: float(v) for k, v in metrics.items()},
        "zero_expected_demand": metrics["expected_demand_portions"] == 0,
        "capacity_use": quantity / request.maximum_capacity if request.maximum_capacity else (0.0 if quantity == 0 else None),
        "feasible": not reasons, "rejection_reasons": reasons}
    if outcomes:
        result["outcomes"] = [{"name": s.name, "demand_portions": s.demand_portions, "probability": s.probability,
            "served_portions": min(quantity, s.demand_portions), "surplus_portions": max(quantity - s.demand_portions, 0),
            "unmet_portions": max(s.demand_portions - quantity, 0),
            "surplus_mass_kg": float(F(max(quantity - s.demand_portions, 0)) * F(str(request.portion_mass_g)) / 1000),
            "fully_served": quantity >= s.demand_portions} for s in request.demand_scenarios]
    return result, metrics


def compare(baseline, recommended):
    if recommended is None:
        return None
    keys = ["quantity", "expected_surplus_portions", "expected_surplus_kg", "expected_unmet_portions",
            "probability_fully_served", "expected_fill_rate", "capacity_use"]
    metrics = {}
    for key in keys:
        a, b = baseline[key], recommended[key]
        exact_change = F(str(b)) - F(str(a)) if a is not None and b is not None else None
        change = float(exact_change) if exact_change is not None else None
        metrics[key] = {"baseline": a, "recommended": b, "difference_recommended_minus_baseline": change,
            "relative_change": float(exact_change / F(str(a))) if a not in (None, 0) and exact_change is not None else None}
    difference = float(F(str(baseline["expected_surplus_kg"])) - F(str(recommended["expected_surplus_kg"])))
    return {"potential_surplus_reduction_kg": difference,
        "potential_surplus_reduction_portions": float(F(str(baseline["expected_surplus_portions"])) - F(str(recommended["expected_surplus_portions"]))),
        "relative_surplus_reduction": difference / baseline["expected_surplus_kg"] if baseline["expected_surplus_kg"] else None,
        "metrics": metrics}


def required_capacity(request):
    cumulative, threshold = F(0), F(str(request.reliability_target))
    required_demand = 0 if threshold == 0 else None
    for s in sorted(request.demand_scenarios, key=lambda x: x.demand_portions):
        cumulative += F(str(s.probability))
        if required_demand is None and cumulative >= threshold:
            required_demand = s.demand_portions
    if required_demand is None:
        return None
    minimum = max(request.minimum_portions, required_demand)
    return ((minimum + request.batch_increment - 1) // request.batch_increment) * request.batch_increment


def optimize_base(request, *, include_candidates=True):
    candidates, best, best_key = [], None, None
    feasible_count, rejected_count = 0, 0
    largest = request.maximum_capacity // request.batch_increment * request.batch_increment
    for quantity in range(0, largest + 1, request.batch_increment):
        candidate, exact = evaluate_quantity(quantity, request)
        if include_candidates:
            candidates.append(candidate)
        if candidate["feasible"]:
            feasible_count += 1
            key = (exact["expected_surplus_kg"], exact["expected_unmet_portions"], quantity)
            if best_key is None or key < best_key:
                best, best_key = quantity, key
        else:
            rejected_count += 1
    baseline = evaluate_quantity(request.baseline_portions, request, outcomes=True)[0]
    recommended = evaluate_quantity(best, request, outcomes=True)[0] if best is not None else None
    required = required_capacity(request)
    max_reliability = exact_metrics(largest, request)["probability_fully_served"]
    issues = []
    if recommended is None:
        next_minimum = ((request.minimum_portions + request.batch_increment - 1) // request.batch_increment) * request.batch_increment
        if next_minimum > request.maximum_capacity:
            issues.append({"code": "minimum_batch_capacity_conflict",
                "message": f"The smallest batch multiple at or above the minimum is {next_minimum}, exceeding capacity {request.maximum_capacity}.",
                "adjustments_to_consider": [f"Consider capacity of at least {next_minimum}, if operationally available.",
                    "Review the minimum or batch increment only if operationally justified, then rerun."]})
        if max_reliability < F(str(request.reliability_target)):
            issues.append({"code": "service_capacity_conflict", "message": f"At the largest allowed batch quantity ({largest}), full-service probability is {float(max_reliability):.12g}, below target {request.reliability_target}.",
                "adjustments_to_consider": ([f"A capacity of at least {required} portions is required for the current demand assumptions and batch/minimum rules."] if required is not None else
                    ["The unchanged probability weights cannot reach this target. Re-enter weights that sum exactly to 1."]) +
                    [f"Alternatively review a target at or below {float(max_reliability):.12g}, or revise demand assumptions only with justification. No constraint was relaxed."]})
    return {"status": "optimal" if recommended else "infeasible", "baseline": baseline, "recommended": recommended,
        "comparison": compare(baseline, recommended), "candidates": candidates,
        "feasibility": {"feasible_candidates": feasible_count, "rejected_candidates": rejected_count,
            "required_capacity": required, "maximum_grid_quantity": largest,
            "maximum_reliability_on_grid": float(max_reliability), "issues": issues}}


def shifted_request(request, percentage):
    multiplier = 1 + F(str(percentage)) / 100
    scenarios = []
    for scenario in request.demand_scenarios:
        value = scenario.demand_portions * multiplier
        rounded = (2 * value.numerator + value.denominator) // (2 * value.denominator)
        scenarios.append({**scenario.model_dump(), "demand_portions": rounded})
    # Revalidate all assumptions; never silently clip an out-of-range demand.
    return DecisionRequest.model_validate({**request.model_dump(), "demand_scenarios": scenarios, "sensitivity_percent": 0.0})


def preview(request):
    result = optimize_base(request)
    total = sum((F(str(s.probability)) for s in request.demand_scenarios), F(0))
    sensitivity = []
    if request.sensitivity_percent:
        for percentage in (-request.sensitivity_percent, request.sensitivity_percent):
            shifted = shifted_request(request, percentage)
            case = optimize_base(shifted, include_candidates=False)
            case.pop("candidates")
            sensitivity.append({"demand_shift_percent": percentage, "evidence_type": "assumption_based",
                "demand_scenarios": [s.model_dump() for s in shifted.demand_scenarios], **case})
    notes = ["Exact rational arithmetic uses the decimal representations of validated JSON numbers. No probability weights are normalized.",
        "Reliability comparisons are exact; the probability-sum input tolerance does not relax service constraints.",
        "Relative changes are null when the baseline denominator is zero. Capacity use is null for a positive baseline with zero capacity."]
    if total != 1:
        notes.append(f"Probability weights total {float(total):.17g}, within 1e-9 of 1. They remain unchanged, so weighted probability totals can differ from 1 by that input roundoff. For an exact reliability target of 1, enter weights summing exactly to 1.")
    if result["baseline"]["zero_expected_demand"]:
        notes.append("Expected demand is zero. Expected fill rate is 1 by explicit no-demand convention; no division by zero is performed.")
    return {"engine_version": VERSION, "evidence_type": "assumption_based", "scenario_kind": request.scenario_kind,
        "objective": OBJECTIVE, "tie_break": TIE_BREAK, "probability_sum": float(total),
        "inputs": request.model_dump(mode="json"), "input_fingerprint": fingerprint(request),
        **result, "sensitivity": sensitivity, "assumptions_and_limitations": LIMITATIONS, "numeric_notes": notes}
