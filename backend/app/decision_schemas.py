"""Bounded assumptions and typed, explicitly non-measured decision evidence."""
from datetime import date as DateValue, datetime
from fractions import Fraction
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_SCENARIOS = 30
MAX_DEMAND = 100_000
MAX_CAPACITY = 10_000
MAX_CANDIDATES = 2001
PROBABILITY_TOLERANCE = Fraction(1, 1_000_000_000)
Quantity = Annotated[int, Field(strict=True, ge=0, le=MAX_DEMAND)]
Probability = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DemandScenario(StrictInput):
    name: Annotated[str, Field(min_length=1, max_length=60)]
    demand_portions: Quantity
    probability: Probability

    @field_validator("name")
    @classmethod
    def printable_name(cls, value):
        if any(not c.isprintable() for c in value):
            raise ValueError("Scenario names must contain printable characters only.")
        return value


class DecisionRequest(StrictInput):
    planning_date: DateValue
    title: Annotated[str, Field(max_length=100)] = ""
    menu: Annotated[int | None, Field(strict=True, ge=1, le=10_000)] = None
    scenario_kind: Literal["user_assumptions", "synthetic_demo"] = "user_assumptions"
    baseline_portions: Quantity
    portion_mass_g: Annotated[float, Field(strict=True, gt=0, le=10_000, allow_inf_nan=False)]
    batch_increment: Annotated[int, Field(strict=True, ge=1, le=10_000)]
    maximum_capacity: Annotated[int, Field(strict=True, ge=0, le=MAX_CAPACITY)]
    minimum_portions: Annotated[int, Field(strict=True, ge=0, le=MAX_CAPACITY)] = 0
    reliability_target: Probability = 0.95
    demand_scenarios: Annotated[list[DemandScenario], Field(min_length=1, max_length=MAX_SCENARIOS)]
    sensitivity_percent: Annotated[float, Field(strict=True, ge=0, le=50, allow_inf_nan=False)] = 0
    context_batch_id: Annotated[int | None, Field(strict=True, gt=0)] = None

    @field_validator("planning_date")
    @classmethod
    def valid_date(cls, value):
        if not 2000 <= value.year <= 2100:
            raise ValueError("Planning dates must fall between 2000 and 2100.")
        return value

    @field_validator("title")
    @classmethod
    def printable_title(cls, value):
        if any(not c.isprintable() for c in value):
            raise ValueError("Titles must contain printable characters only.")
        return value

    @model_validator(mode="after")
    def validate_distribution_and_cost(self):
        total = sum((Fraction(str(s.probability)) for s in self.demand_scenarios), Fraction(0))
        if abs(total - 1) > PROBABILITY_TOLERANCE:
            raise ValueError(f"Probability weights must sum to 1 within 1e-9 (received {float(total):.12g}). Weights are never normalized.")
        names = [s.name.casefold() for s in self.demand_scenarios]
        if len(names) != len(set(names)):
            raise ValueError("Demand scenario names must be unique, ignoring case.")
        if self.maximum_capacity // self.batch_increment + 1 > MAX_CANDIDATES:
            raise ValueError(f"The full batch grid may contain at most {MAX_CANDIDATES} candidates. Increase the batch increment or reduce capacity.")
        multiplier = 1 + Fraction(str(self.sensitivity_percent)) / 100
        if any(s.demand_portions * multiplier > MAX_DEMAND for s in self.demand_scenarios):
            raise ValueError("Upward sensitivity demand exceeds 100,000 portions. Reduce demand or the sensitivity percentage.")
        return self


class Outcome(BaseModel):
    name: str
    demand_portions: int
    probability: float
    served_portions: int
    surplus_portions: int
    unmet_portions: int
    surplus_mass_kg: float
    fully_served: bool


class Candidate(BaseModel):
    quantity: int
    expected_demand_portions: float
    expected_served_portions: float
    expected_surplus_portions: float
    expected_unmet_portions: float
    expected_surplus_kg: float
    probability_fully_served: float
    expected_fill_rate: float
    zero_expected_demand: bool
    capacity_use: float | None
    feasible: bool
    rejection_reasons: list[str]


class PlanEvaluation(Candidate):
    outcomes: list[Outcome]


class Difference(BaseModel):
    baseline: float | None
    recommended: float | None
    difference_recommended_minus_baseline: float | None
    relative_change: float | None


class Comparison(BaseModel):
    potential_surplus_reduction_kg: float
    potential_surplus_reduction_portions: float
    relative_surplus_reduction: float | None
    metrics: dict[str, Difference]


class ConstraintIssue(BaseModel):
    code: str
    message: str
    adjustments_to_consider: list[str]


class Feasibility(BaseModel):
    feasible_candidates: int
    rejected_candidates: int
    required_capacity: int | None
    maximum_grid_quantity: int
    maximum_reliability_on_grid: float
    issues: list[ConstraintIssue]


class SensitivityResult(BaseModel):
    demand_shift_percent: float
    evidence_type: Literal["assumption_based"]
    demand_scenarios: list[DemandScenario]
    status: Literal["optimal", "infeasible"]
    baseline: PlanEvaluation
    recommended: PlanEvaluation | None
    feasibility: Feasibility
    comparison: Comparison | None


class DecisionPreview(BaseModel):
    engine_version: str
    evidence_type: Literal["assumption_based"]
    scenario_kind: Literal["user_assumptions", "synthetic_demo"]
    objective: str
    tie_break: str
    probability_sum: float
    inputs: DecisionRequest
    input_fingerprint: str
    status: Literal["optimal", "infeasible"]
    baseline: PlanEvaluation
    recommended: PlanEvaluation | None
    comparison: Comparison | None
    feasibility: Feasibility
    candidates: list[Candidate]
    sensitivity: list[SensitivityResult]
    assumptions_and_limitations: list[str]
    numeric_notes: list[str]


class ContextReference(BaseModel):
    batch_id: int
    source_title: str
    source_kind: str
    source_doi: str | None
    raw_sha256: str
    role: str


class SavedPlan(BaseModel):
    id: int
    created_at: datetime
    engine_version: str
    evidence_type: Literal["assumption_based"]
    input_fingerprint: str
    inputs: DecisionRequest
    result: DecisionPreview
    context_reference: ContextReference | None


class PlanSummary(BaseModel):
    id: int
    created_at: datetime
    title: str
    planning_date: str
    scenario_kind: str
    evidence_type: Literal["assumption_based"]
    engine_version: str
    status: str
    baseline_portions: int
    recommended_portions: int | None
