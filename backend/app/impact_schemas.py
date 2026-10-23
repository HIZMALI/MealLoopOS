"""Strict operational inputs. No client-supplied verification or capture timestamps."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Category = Literal["discarded_surplus", "plate_waste", "preparation_waste"]
Source = Literal["synthetic", "user_reported", "user_reported_documented"]
Basis = Literal["weighed", "estimated", "imported"]
Count = Annotated[int, Field(strict=True, ge=0, le=100_000)]
Mass = Annotated[float, Field(strict=True, ge=0, le=1_000_000, allow_inf_nan=False)]
Text = Annotated[str, Field(max_length=1000)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="after")
    @classmethod
    def printable(cls, value):
        if isinstance(value, str) and any(not c.isprintable() and c not in "\n\t" for c in value):
            raise ValueError("Text contains unsupported control characters.")
        return value


class Disposition(Input):
    donated: Count | None = None
    retained: Count | None = None
    repurposed: Count | None = None
    discarded: Count | None = None
    unknown: Count | None = None


class Document(Input):
    label: Annotated[str, Field(min_length=1, max_length=100)]
    reference: Annotated[str, Field(min_length=1, max_length=500)]


class Measurement(Input):
    category: Category
    mass_kg: Mass | None = None
    basis: Basis
    method: Annotated[str, Field(min_length=1, max_length=100)]
    scope_description: Annotated[str, Field(min_length=3, max_length=500)]
    scope_status: Literal["disjoint_stream", "unresolved", "possible_overlap"] = "unresolved"
    material_type: Literal["food_only", "inedible_only", "food_and_inedible", "unspecified"] = "unspecified"
    destination: Literal["landfill", "sewer", "compost", "anaerobic_digestion", "animal_feed", "other", "unspecified"] = "unspecified"
    gross_kg: Mass | None = None
    tare_kg: Mass | None = None
    notes: Text = ""

    @model_validator(mode="after")
    def net_mass(self):
        if self.gross_kg is not None or self.tare_kg is not None:
            if self.basis != "weighed" or self.gross_kg is None or self.tare_kg is None:
                raise ValueError("Gross and tare require both values and a weighed basis.")
            net = Decimal(str(self.gross_kg)) - Decimal(str(self.tare_kg))
            if net < 0:
                raise ValueError("Gross mass must be at least tare mass.")
            if self.mass_kg is not None and abs(Decimal(str(self.mass_kg)) - net) > Decimal("0.000001"):
                raise ValueError("Net mass disagrees with gross minus tare (tolerance 0.000001 kg).")
            if self.mass_kg is None:
                self.mass_kg = float(net)
        if self.mass_kg is None:
            raise ValueError("Enter a mass or both gross and tare values; missing is not zero.")
        return self


class ServiceInput(Input):
    service_date: date
    site: Annotated[str, Field(max_length=100)] = ""
    menu: Annotated[str, Field(min_length=1, max_length=150)]
    decision_plan_id: Annotated[int | None, Field(strict=True, gt=0)] = None
    prepared: Count | None = None
    served: Count | None = None
    turn_aways: Count | None = None
    observed_diners: Count | None = None
    portion_mass_g: Annotated[float | None, Field(strict=True, gt=0, le=10_000, allow_inf_nan=False)] = None
    source_category: Source
    count_method: Annotated[str, Field(max_length=200)] = ""
    operator_notes: Text = ""
    dispositions: Disposition = Field(default_factory=Disposition)
    measurements: Annotated[list[Measurement], Field(max_length=3)] = Field(default_factory=list)
    disjoint_scope_note: Annotated[str, Field(max_length=500)] = ""
    documents: Annotated[list[Document], Field(max_length=5)] = Field(default_factory=list)

    @field_validator("service_date")
    @classmethod
    def calendar_range(cls, value):
        if not 2000 <= value.year <= 2100:
            raise ValueError("Service dates must fall between 2000 and 2100.")
        return value

    @model_validator(mode="after")
    def validate_record(self):
        if self.prepared is not None and self.served is not None and self.served > self.prepared:
            raise ValueError("Served portions cannot exceed prepared portions.")
        categories = [m.category for m in self.measurements]
        if len(categories) != len(set(categories)):
            raise ValueError("Use one entry per mass category; combine repeat readings externally with documented scope.")
        if self.source_category == "user_reported_documented" and not self.documents:
            raise ValueError("Documented self-report requires at least one supporting reference. References are not independent verification.")
        return self


class VersionInput(Input):
    expected_version: Annotated[int, Field(strict=True, ge=1)]


class CorrectionInput(VersionInput):
    correction_reason: Annotated[str, Field(min_length=5, max_length=1000)]
    record: ServiceInput


class Accounting(BaseModel):
    remaining_portions: int | None
    known_disposition_portions: int
    discrepancy_portions: int | None
    missing_dispositions: list[str]
    reconciled: bool
    unknown_portions: int | None
    estimated_discarded_kg: float | None
    estimate_label: str


class PlanReference(BaseModel):
    id: int
    created_at: datetime
    planning_date: str
    menu: int | None
    engine_version: str
    input_fingerprint: str
    scenario_kind: str
    baseline_portions: int
    recommended_portions: int | None
    modeled_baseline_surplus_kg: float
    modeled_recommended_surplus_kg: float | None
    modeled_surplus_difference_kg: float | None
    evidence_type: Literal["assumption_based"]


class Assessment(BaseModel):
    assessment_version: str
    provenance_label: str
    independently_verified: Literal[False]
    labels: list[str]
    entry_complete: bool
    can_finalize: bool
    finalization_blockers: list[str]
    issues: list[str]
    accounting: Accounting
    measurement_categories_present: list[str]
    missing_measurement_categories: list[str]
    physically_weighed_categories: list[str]
    combined_weighed_kg: float | None
    combined_mass_explanation: str
    planning_timing: Literal["prospective_capture", "retrospective", "unlinked"]
    planning_timing_explanation: str
    actual_minus_recommended: int | None
    actual_minus_baseline: int | None
    followed_exactly: bool | None
    limitations: list[str]


class RecordResult(BaseModel):
    id: int
    revision_id: int
    version: int
    status: Literal["draft", "finalized"]
    event: str
    correction_reason: str | None
    changed_fields: list[str]
    created_at: datetime
    service_created_at: datetime
    previous_revision_id: int | None
    record: ServiceInput
    assessment: Assessment
    plan_reference: PlanReference | None


class ComparisonInput(Input):
    source_category: Source
    category: Category
    basis: Basis = "weighed"
    baseline_start: date
    baseline_end: date
    trial_start: date
    trial_end: date
    site: Annotated[str | None, Field(max_length=100)] = None
    menu: Annotated[str | None, Field(max_length=150)] = None

    @model_validator(mode="after")
    def periods(self):
        if not (self.baseline_start <= self.baseline_end < self.trial_start <= self.trial_end):
            raise ValueError("Use ordered, non-overlapping baseline and trial periods.")
        if any(not 2000 <= d.year <= 2100 for d in (self.baseline_start,self.baseline_end,self.trial_start,self.trial_end)):
            raise ValueError("Comparison dates must fall between 2000 and 2100.")
        if (self.trial_end - self.baseline_start).days > 3660:
            raise ValueError("Comparison range cannot exceed ten years.")
        return self
