"""Independent arithmetic, invariants, bounded validation and exact optimization."""
import json
import random
from fractions import Fraction as F

import pytest
from pydantic import ValidationError

from app.decision_schemas import DecisionPreview, DecisionRequest
from app.decision_service import demo_request
from app.decisions import evaluate_quantity, preview, shifted_request


def request(**changes):
    return DecisionRequest.model_validate({**demo_request().model_dump(), "sensitivity_percent": 0.0, **changes})


def test_synthetic_acceptance_and_weighted_outcome_audit():
    result = preview(demo_request())
    DecisionPreview.model_validate(result)
    assert result["evidence_type"] == "assumption_based"
    assert result["scenario_kind"] == "synthetic_demo"
    base, chosen = result["baseline"], result["recommended"]
    assert (base["quantity"], chosen["quantity"]) == (480, 440)
    assert (base["expected_surplus_portions"], base["expected_surplus_kg"]) == (76, 30.4)
    assert (chosen["expected_surplus_portions"], chosen["expected_surplus_kg"]) == (36, 14.4)
    assert result["comparison"]["potential_surplus_reduction_kg"] == 16
    assert result["comparison"]["potential_surplus_reduction_portions"] == 40
    assert chosen["expected_demand_portions"] == 404
    for plan in (base, chosen):
        assert plan["probability_fully_served"] == plan["expected_fill_rate"] == 1
        assert plan["expected_unmet_portions"] == 0
        assert sum(o["probability"] * o["surplus_mass_kg"] for o in plan["outcomes"]) == pytest.approx(plan["expected_surplus_kg"])
    assert len(result["candidates"]) == 51
    assert result["feasibility"]["feasible_candidates"] == 7
    assert result["feasibility"]["rejected_candidates"] == 44


def test_service_requirement_changes_optimum_and_cannot_choose_zero():
    loose = preview(request(reliability_target=0.7))
    rec = loose["recommended"]
    assert rec["quantity"] == 400
    assert rec["expected_surplus_portions"] == 8
    assert rec["expected_surplus_kg"] == 3.2
    assert rec["expected_unmet_portions"] == 12
    assert rec["probability_fully_served"] == 0.7
    assert rec["expected_fill_rate"] == pytest.approx(392 / 404)
    assert not loose["candidates"][0]["feasible"]
    assert preview(request(reliability_target=1.0))["recommended"]["quantity"] == 440


@pytest.mark.parametrize("capacity,minimum,step,expected,issue", [
    (430, 0, 10, 440, "service_capacity_conflict"),
    (449, 441, 10, 450, "minimum_batch_capacity_conflict"),
    (9, 9, 10, 440, "minimum_batch_capacity_conflict"),
    (0, 1, 10, 440, "minimum_batch_capacity_conflict"),
])
def test_infeasible_constraints_are_explained_without_relaxation(capacity, minimum, step, expected, issue):
    r = preview(request(maximum_capacity=capacity, minimum_portions=minimum, batch_increment=step))
    assert r["status"] == "infeasible"
    assert r["recommended"] is None and r["comparison"] is None
    assert r["feasibility"]["required_capacity"] == expected
    assert issue in [i["code"] for i in r["feasibility"]["issues"]]
    assert all(i["adjustments_to_consider"] for i in r["feasibility"]["issues"])
    assert all(not c["feasible"] for c in r["candidates"])
    assert r["inputs"]["maximum_capacity"] == capacity


def test_batch_grid_minimum_and_invalid_baseline_are_not_hidden():
    r = preview(request(batch_increment=13, maximum_capacity=499, minimum_portions=441, baseline_portions=501))
    assert r["recommended"]["quantity"] == 442
    assert r["feasibility"]["maximum_grid_quantity"] == 494
    assert r["baseline"]["rejection_reasons"] == ["exceeds_capacity", "not_batch_multiple"]
    assert {c["quantity"] % 13 for c in r["candidates"]} == {0}


def test_zero_demand_zero_capacity_zero_weights_and_relative_denominators():
    r = preview(request(demand_scenarios=[{"name": "None", "demand_portions": 0, "probability": 1.0},
        {"name": "Impossible", "demand_portions": 100, "probability": 0.0}], maximum_capacity=0, baseline_portions=10))
    rec = r["recommended"]
    assert rec["quantity"] == rec["expected_surplus_kg"] == rec["expected_unmet_portions"] == 0
    assert rec["expected_fill_rate"] == rec["probability_fully_served"] == 1
    assert rec["zero_expected_demand"]
    assert r["baseline"]["capacity_use"] is None
    assert rec["capacity_use"] == 0
    assert r["comparison"]["metrics"]["capacity_use"]["relative_change"] is None
    zero = preview(request(baseline_portions=0, demand_scenarios=[{"name": "None", "demand_portions": 0, "probability": 1.0}]))
    assert zero["comparison"]["relative_surplus_reduction"] is None
    assert any("no-demand convention" in note for note in zero["numeric_notes"])


def test_deterministic_tie_break_minimizes_unmet_before_quantity():
    # Reliability zero deliberately permits shortage; all Q<=50 have zero surplus.
    r = preview(request(reliability_target=0.0, maximum_capacity=40, batch_increment=10,
        demand_scenarios=[{"name": "Only", "demand_portions": 50, "probability": 1.0}]))
    assert r["recommended"]["quantity"] == 40
    assert r["recommended"]["expected_surplus_kg"] == 0
    assert r["recommended"]["expected_unmet_portions"] == 10


def test_probability_sum_tolerance_never_normalizes_or_relaxes_reliability():
    scenarios = [{"name": "a", "demand_portions": 1, "probability": 0.5},
                 {"name": "b", "demand_portions": 2, "probability": 0.4999999995}]
    r = preview(request(demand_scenarios=scenarios, reliability_target=1.0))
    assert r["inputs"]["demand_scenarios"] == scenarios
    assert r["probability_sum"] == 0.9999999995
    assert r["status"] == "infeasible"
    assert r["feasibility"]["required_capacity"] is None
    assert any("remain unchanged" in n for n in r["numeric_notes"])
    scenarios[1]["probability"] = 0.499999998
    with pytest.raises(ValidationError, match="never normalized"):
        request(demand_scenarios=scenarios)


def test_sensitivity_is_explicit_half_up_rounded_and_may_be_infeasible():
    r = preview(request(maximum_capacity=480, sensitivity_percent=10.0))
    lower, upper = r["sensitivity"]
    assert [s["demand_portions"] for s in lower["demand_scenarios"]] == [324, 360, 396]
    assert lower["recommended"]["quantity"] == 400
    assert [s["demand_portions"] for s in upper["demand_scenarios"]] == [396, 440, 484]
    assert upper["status"] == "infeasible" and upper["recommended"] is None
    assert upper["feasibility"]["required_capacity"] == 490
    assert r["recommended"]["quantity"] == 440  # no sensitivity leakage into the main solution
    one = request(demand_scenarios=[{"name": "tiny", "demand_portions": 5, "probability": 1.0}])
    assert shifted_request(one, 10).demand_scenarios[0].demand_portions == 6
    assert shifted_request(one, -10).demand_scenarios[0].demand_portions == 5
    assert preview(one)["sensitivity"] == []


@pytest.mark.parametrize("changes", [
    {"baseline_portions": -1}, {"baseline_portions": 1.5}, {"baseline_portions": "480"}, {"baseline_portions": True},
    {"baseline_portions": 100001}, {"portion_mass_g": 0}, {"portion_mass_g": -1.0}, {"portion_mass_g": 10001.0},
    {"portion_mass_g": float("nan")}, {"portion_mass_g": float("inf")}, {"portion_mass_g": True},
    {"batch_increment": 0}, {"batch_increment": 10001}, {"batch_increment": 1.5},
    {"maximum_capacity": -1}, {"maximum_capacity": 10001}, {"maximum_capacity": True},
    {"maximum_capacity": 10000, "batch_increment": 1}, {"minimum_portions": -1}, {"minimum_portions": 10001},
    {"reliability_target": -0.1}, {"reliability_target": 1.01}, {"reliability_target": float("inf")},
    {"reliability_target": "0.95"}, {"sensitivity_percent": -1.0}, {"sensitivity_percent": 50.1},
    {"sensitivity_percent": float("nan")}, {"planning_date": "2025-02-29"}, {"planning_date": "1999-01-01"},
    {"planning_date": "2101-01-01"}, {"menu": 0}, {"menu": 1.5}, {"menu": True}, {"context_batch_id": 0},
    {"title": "a" * 101}, {"title": "bad\x00label"}, {"evidence_type": "measured"},
    {"demand_scenarios": []},
    {"demand_scenarios": [{"name": str(i), "demand_portions": i, "probability": 1 / 31} for i in range(31)]},
    {"demand_scenarios": [{"name": "a", "demand_portions": 100000, "probability": 1.0}], "sensitivity_percent": 10.0},
])
def test_invalid_planning_inputs_rejected(changes):
    with pytest.raises(ValidationError):
        request(**changes)


@pytest.mark.parametrize("changes", [
    {"name": ""}, {"name": "x" * 61}, {"name": "a\nb"}, {"demand_portions": -1}, {"demand_portions": 1.5},
    {"demand_portions": "360"}, {"demand_portions": True}, {"demand_portions": 100001},
    {"probability": -0.1}, {"probability": 1.01}, {"probability": float("nan")},
    {"probability": float("inf")}, {"probability": True}, {"probability": "0.2"}, {"probability": 0.1},
])
def test_invalid_scenario_values_rejected(changes):
    scenarios = [s.model_dump() for s in demo_request().demand_scenarios]
    scenarios[0].update(changes)
    with pytest.raises(ValidationError):
        request(demand_scenarios=scenarios)


def test_duplicate_names_rejected_but_equal_demands_are_valid():
    scenarios = [{"name": "Low", "demand_portions": 50, "probability": 0.5},
                 {"name": " low ", "demand_portions": 50, "probability": 0.5}]
    with pytest.raises(ValidationError, match="unique"):
        request(demand_scenarios=scenarios)
    scenarios[1]["name"] = "Other"
    assert preview(request(demand_scenarios=scenarios))["recommended"]["quantity"] == 50


def test_optimizer_reproducible_identity_and_mass_scaling():
    r = request()
    a, b = preview(r), preview(DecisionRequest.model_validate_json(r.model_dump_json()))
    assert a == b
    assert len(a["input_fingerprint"]) == 64
    scaled = preview(request(portion_mass_g=800.0))
    assert scaled["recommended"]["quantity"] == a["recommended"]["quantity"]
    assert scaled["recommended"]["expected_surplus_kg"] == 2 * a["recommended"]["expected_surplus_kg"]
    assert scaled["input_fingerprint"] != a["input_fingerprint"]
    json.dumps(a, allow_nan=False)


def test_small_randomized_brute_force_and_metamorphic_properties():
    rng = random.Random(73031)
    for _ in range(150):
        # Integer hundredth weights allow a separate integer arithmetic reference.
        cut1, cut2 = sorted([rng.randrange(101), rng.randrange(101)])
        weights = [cut1, cut2 - cut1, 100 - cut2]
        demands = [rng.randrange(61) for _ in range(3)]
        step, cap, minimum, threshold = rng.randrange(1, 12), rng.randrange(81), rng.randrange(65), rng.randrange(101)
        r = request(demand_scenarios=[{"name": str(i), "demand_portions": d, "probability": w / 100} for i, (d,w) in enumerate(zip(demands, weights))],
            batch_increment=step, maximum_capacity=cap, minimum_portions=minimum, reliability_target=threshold / 100,
            portion_mass_g=375.0)
        got = preview(r)
        reference, prior_unmet, prior_surplus = [], None, None
        for q in range(0, cap + 1, step):
            surplus = sum(w * max(q-d, 0) for d,w in zip(demands, weights))
            unmet = sum(w * max(d-q, 0) for d,w in zip(demands, weights))
            reliability = sum(w for d,w in zip(demands, weights) if q >= d)
            if q >= minimum and reliability >= threshold:
                reference.append((surplus, unmet, q))
            c = evaluate_quantity(q, r)[0]
            assert c["expected_surplus_portions"] == surplus / 100
            assert c["expected_unmet_portions"] == unmet / 100
            assert c["probability_fully_served"] == reliability / 100
            assert c["expected_surplus_kg"] == pytest.approx(surplus / 100 * .375)
            assert c["expected_served_portions"] + c["expected_unmet_portions"] == pytest.approx(c["expected_demand_portions"])
            assert c["expected_served_portions"] + c["expected_surplus_portions"] == pytest.approx(q)
            if prior_unmet is not None:
                assert unmet <= prior_unmet and surplus >= prior_surplus
            prior_unmet, prior_surplus = unmet, surplus
        assert (got["recommended"]["quantity"] if got["recommended"] else None) == (min(reference)[2] if reference else None)
        if got["recommended"]:
            q = got["recommended"]["quantity"]
            assert minimum <= q <= cap and q % step == 0
            assert F(str(got["recommended"]["probability_fully_served"])) >= F(str(r.reliability_target))
