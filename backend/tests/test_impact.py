from copy import deepcopy
from datetime import datetime, timezone
import random

import pytest
from pydantic import ValidationError

from app.impact import accounting, assess, mass_inventory
from app.impact_schemas import Measurement, PlanReference, ServiceInput
from app.impact_service import demo_inputs

NOW=datetime(2026,10,23,12,tzinfo=timezone.utc)


def sample(**changes):
    return ServiceInput.model_validate({**deepcopy(demo_inputs()["complete"]),**changes})


def test_acceptance_food_conservation_and_separate_mass():
    r=sample()
    a=assess(r,now=NOW)
    assert a["accounting"]["remaining_portions"]==40
    assert r.served+sum(r.dispositions.model_dump().values())==r.prepared==440
    assert a["accounting"]["reconciled"] and a["can_finalize"]
    assert a["accounting"]["estimated_discarded_kg"]==8
    assert r.measurements[0].mass_kg==7.6
    assert a["combined_weighed_kg"]==9.7  # not 17.7, 15.6 or a modeled reduction
    assert a["labels"][0]=="Synthetic demonstration"
    assert a["independently_verified"] is False
    assert a["planning_timing"]=="unlinked"
    assert a["actual_minus_recommended"] is None


def test_unknown_disposition_reconciles_but_cannot_be_finalized():
    a=assess(ServiceInput.model_validate(demo_inputs()["incomplete"]),now=NOW)
    assert a["accounting"]["remaining_portions"]==30
    assert a["accounting"]["discrepancy_portions"]==0
    assert a["accounting"]["reconciled"]
    assert a["accounting"]["unknown_portions"]==5
    assert not a["can_finalize"] and not a["entry_complete"]
    assert a["combined_weighed_kg"] is None
    assert any("unknown disposition" in b for b in a["finalization_blockers"])


@pytest.mark.parametrize("dispositions,discrepancy,missing", [
    ({"donated":10,"retained":10,"repurposed":0,"discarded":5,"unknown":0},15,[]),
    ({"donated":10,"retained":10,"repurposed":0,"discarded":50,"unknown":0},-30,[]),
    ({"donated":40},0,["retained","repurposed","discarded","unknown"]),
    ({},40,["donated","retained","repurposed","discarded","unknown"]),
])
def test_incomplete_discrepancy_is_not_silently_balanced(dispositions,discrepancy,missing):
    a=assess(sample(dispositions=dispositions),now=NOW)
    assert a["accounting"]["discrepancy_portions"]==discrepancy
    assert a["accounting"]["missing_dispositions"]==missing
    assert not a["can_finalize"]
    assert not a["accounting"]["reconciled"]


def test_missing_is_not_zero_and_served_does_not_define_demand():
    a=assess(sample(prepared=None,served=None,portion_mass_g=None,turn_aways=None,observed_diners=None,dispositions={},measurements=[]),now=NOW)
    assert a["accounting"]["remaining_portions"] is None
    assert a["accounting"]["estimated_discarded_kg"] is None
    assert a["accounting"]["unknown_portions"] is None
    assert len(a["missing_measurement_categories"])==3
    assert any("unmet demand is unknown" in s for s in a["issues"])
    zero=assess(sample(prepared=0,served=0,turn_aways=0,dispositions={k:0 for k in sample().dispositions.model_dump()}),now=NOW)
    assert zero["accounting"]["remaining_portions"]==0
    assert zero["accounting"]["estimated_discarded_kg"]==0


@pytest.mark.parametrize("change", [
    {"prepared":-1},{"served":441},{"prepared":True},{"served":"400"},{"served":400.5},
    {"prepared":100001},{"turn_aways":-1},{"turn_aways":True},{"observed_diners":-1},
    {"portion_mass_g":0.0},{"portion_mass_g":float("nan")},{"portion_mass_g":float("inf")},{"portion_mass_g":10001.0},
    {"portion_mass_g":"400"},{"service_date":"2025-02-29"},{"service_date":"1999-01-01"},
    {"service_date":"2101-01-01"},{"menu":""},{"menu":"a"*151},{"site":"a"*101},
    {"operator_notes":"a"*1001},{"menu":"bad\x00name"},{"decision_plan_id":0},
    {"created_at":"2020-01-01T00:00:00Z"},{"prospective":True},{"independently_verified":True},
    {"source_category":"historical_measured"},{"source_category":"user_reported_documented","documents":[]},
    {"dispositions":{"discarded":-1}},{"dispositions":{"donated":True}},
])
def test_invalid_operational_input(change):
    with pytest.raises(ValidationError):
        sample(**change)


@pytest.mark.parametrize("change", [
    {"mass_kg":-1.0},{"mass_kg":float("nan")},{"mass_kg":float("inf")},{"mass_kg":"7.6"},
    {"mass_kg":True},{"mass_kg":1000001.0},{"mass_kg":None},{"method":""},
    {"scope_description":""},{"category":"combined_waste"},{"basis":"verified"},
    {"gross_kg":8.0},{"tare_kg":0.4},{"gross_kg":0.5,"tare_kg":1.0},
    {"gross_kg":8.0,"tare_kg":0.3},{"gross_kg":8.0,"tare_kg":0.4,"basis":"estimated"},
])
def test_mass_validation(change):
    payload=sample().measurements[0].model_dump()
    with pytest.raises(ValidationError):
        Measurement.model_validate({**payload,**change})


def test_gross_tare_net_and_explicit_zero_preserve_readings():
    m=sample().measurements[0].model_dump()
    net=Measurement.model_validate({**m,"mass_kg":None,"gross_kg":8.0,"tare_kg":0.4})
    assert net.mass_kg==7.6 and net.gross_kg==8 and net.tare_kg==0.4
    rounded=Measurement.model_validate({**m,"mass_kg":7.6000005,"gross_kg":8.0,"tare_kg":0.4})
    assert rounded.mass_kg==7.6000005  # preserve entered reading within stated net tolerance
    assert Measurement.model_validate({**m,"mass_kg":0.0}).mass_kg==0
    assert Measurement.model_validate({**m,"mass_kg":None,"gross_kg":0.4,"tare_kg":0.4}).mass_kg==0


@pytest.mark.parametrize("field,value", [("scope_status","possible_overlap"),("scope_status","unresolved"),
    ("basis","estimated"),("basis","imported"),("method","Different scale protocol"),
    ("material_type","inedible_only"),("destination","unspecified")])
def test_combined_inventory_blocked_for_incompatible_measurement(field,value):
    p=sample().model_dump()
    p["measurements"][1][field]=value
    r=ServiceInput.model_validate(p)
    assert mass_inventory(r)[0] is None
    assert r.measurements[0].mass_kg==7.6  # never overwritten or folded into estimates


def test_missing_scopes_duplicate_categories_and_no_combined_when_partly_missing():
    assert mass_inventory(sample(disjoint_scope_note=""))[0] is None
    assert mass_inventory(sample(measurements=[sample().measurements[0].model_dump()]))[0] is None
    with pytest.raises(ValidationError,match="one entry per mass category"):
        sample(measurements=[sample().measurements[0].model_dump()]*2)


def plan(created):
    return PlanReference(id=1,created_at=created,planning_date="2026-10-22",menu=1,engine_version="original-version",input_fingerprint="a"*64,
        scenario_kind="user_assumptions",baseline_portions=480,recommended_portions=440,modeled_baseline_surplus_kg=30.4,
        modeled_recommended_surplus_kg=14.4,modeled_surplus_difference_kg=16,evidence_type="assumption_based")


@pytest.mark.parametrize("timestamp,expected", [("2026-10-21T09:59:59+00:00","prospective_capture"),
    ("2026-10-21T10:00:00+00:00","retrospective"),("2026-10-21T23:59:59+00:00","retrospective"),
    ("2026-10-22T01:00:00+00:00","retrospective"),("2026-10-23T00:00:00+00:00","retrospective")])
def test_timestamp_provenance_uses_conservative_server_boundary(timestamp,expected):
    a=assess(sample(),plan(datetime.fromisoformat(timestamp)),now=NOW)
    assert a["planning_timing"]==expected
    assert a["actual_minus_recommended"]==0
    assert a["actual_minus_baseline"]==-40
    assert a["followed_exactly"]
    assert a["independently_verified"] is False


def test_self_report_documentation_is_not_independent_verification_and_future_is_draft():
    r=sample(source_category="user_reported_documented",documents=[{"label":"Scale log","reference":"Held by operator, page 2"}])
    a=assess(r,now=NOW)
    assert a["entry_complete"] and "Complete self-reported record" in a["labels"]
    assert not a["independently_verified"]
    assert not assess(sample(service_date="2026-10-24"),now=NOW)["can_finalize"]


def test_random_count_conservation_and_conversion_never_changes_scale_values():
    rng=random.Random(40404)
    for _ in range(150):
        prepared=rng.randrange(10000)
        served=rng.randrange(prepared+1)
        remainder=prepared-served
        pieces=[]
        for _ in range(3):
            p=rng.randrange(remainder+1)
            pieces.append(p); remainder-=p
        values=dict(zip(("donated","retained","repurposed","discarded","unknown"),[*pieces,remainder,0]))
        r=sample(prepared=prepared,served=served,dispositions=values)
        a=accounting(r)
        assert served+sum(values.values())==prepared
        assert a["reconciled"] and a["discrepancy_portions"]==0
        assert a["estimated_discarded_kg"]==values["discarded"]*2/5
        assert mass_inventory(r)[0]==9.7
