"""Recompute a synthetic acceptance case; no measured data or model is used."""
import argparse
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.database import ROOT
from app.decision_service import demo_request
from app.decisions import engine_metadata, preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/evaluation/build_03_evaluation.json")
    args = parser.parse_args()
    request = demo_request()
    result = preview(request)
    # Independent brute-force objective/reliability calculation, without core
    # engine metric helpers. Hardcoded values appear only as acceptance checks.
    points = []
    for q in range(request.minimum_portions, request.maximum_capacity + 1):
        if q % request.batch_increment:
            continue
        p = sum((Fraction(str(s.probability)) for s in request.demand_scenarios if q >= s.demand_portions), Fraction(0))
        if p < Fraction(str(request.reliability_target)):
            continue
        surplus = sum((Fraction(str(s.probability)) * max(q - s.demand_portions, 0) for s in request.demand_scenarios), Fraction(0))
        unmet = sum((Fraction(str(s.probability)) * max(s.demand_portions - q, 0) for s in request.demand_scenarios), Fraction(0))
        points.append((surplus * Fraction(str(request.portion_mass_g)) / 1000, unmet, q))
    reference_q = min(points)[2]
    observed = {"recommended_quantity": result["recommended"]["quantity"],
        "baseline_surplus_portions": result["baseline"]["expected_surplus_portions"],
        "baseline_surplus_kg": result["baseline"]["expected_surplus_kg"],
        "recommended_surplus_portions": result["recommended"]["expected_surplus_portions"],
        "recommended_surplus_kg": result["recommended"]["expected_surplus_kg"],
        "modeled_surplus_difference_portions": result["comparison"]["potential_surplus_reduction_portions"],
        "modeled_surplus_difference_kg": result["comparison"]["potential_surplus_reduction_kg"]}
    expected = {"recommended_quantity": 440, "baseline_surplus_portions": 76.0, "baseline_surplus_kg": 30.4,
        "recommended_surplus_portions": 36.0, "recommended_surplus_kg": 14.4,
        "modeled_surplus_difference_portions": 40.0, "modeled_surplus_difference_kg": 16.0}
    if observed != expected or reference_q != observed["recommended_quantity"]:
        raise SystemExit("Synthetic acceptance check failed; no evidence was published.")
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if preview(request) != result:
        raise SystemExit("Deterministic repeat check failed.")
    evidence = {"evidence_type": "assumption_based", "scenario_kind": "synthetic_demo",
        "notice": "SYNTHETIC DEMO SCENARIO. These are assumed quantities, not measured school records, realized waste prevention, or causal evidence.",
        "metadata": engine_metadata(), "calculation": result,
        "verification": {"expected_acceptance_values": expected, "executed_values": observed,
            "independent_brute_force_quantity": reference_q, "acceptance_passed": True,
            "repeat_identical": True, "canonical_calculation_sha256": hashlib.sha256(canonical).hexdigest()}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "evidence_type": "assumption_based", "scenario_kind": "synthetic_demo",
        "executed_values": observed, "feasible_candidates": result["feasibility"]["feasible_candidates"],
        "rejected_candidates": result["feasibility"]["rejected_candidates"], "acceptance_passed": True}, indent=2))


if __name__ == "__main__":
    main()
