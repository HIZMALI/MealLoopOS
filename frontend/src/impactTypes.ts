export type SourceCategory =
  "synthetic" | "user_reported" | "user_reported_documented";
export type Basis = "weighed" | "estimated" | "imported";
export type Category =
  "discarded_surplus" | "plate_waste" | "preparation_waste";
export type Dispositions = {
  donated: number | null;
  retained: number | null;
  repurposed: number | null;
  discarded: number | null;
  unknown: number | null;
};
export type Measurement = {
  category: Category;
  mass_kg: number | null;
  basis: Basis;
  method: string;
  scope_description: string;
  scope_status: "disjoint_stream" | "unresolved" | "possible_overlap";
  material_type:
    "food_only" | "inedible_only" | "food_and_inedible" | "unspecified";
  destination:
    | "landfill"
    | "sewer"
    | "compost"
    | "anaerobic_digestion"
    | "animal_feed"
    | "other"
    | "unspecified";
  gross_kg: number | null;
  tare_kg: number | null;
  notes: string;
};
export type ServiceInput = {
  service_date: string;
  site: string;
  menu: string;
  decision_plan_id: number | null;
  prepared: number | null;
  served: number | null;
  turn_aways: number | null;
  observed_diners: number | null;
  portion_mass_g: number | null;
  source_category: SourceCategory;
  count_method: string;
  operator_notes: string;
  dispositions: Dispositions;
  measurements: Measurement[];
  disjoint_scope_note: string;
  documents: { label: string; reference: string }[];
};
export type PlanReference = {
  id: number;
  created_at: string;
  planning_date: string;
  menu: number | null;
  engine_version: string;
  input_fingerprint: string;
  scenario_kind: string;
  baseline_portions: number;
  recommended_portions: number | null;
  modeled_baseline_surplus_kg: number;
  modeled_recommended_surplus_kg: number | null;
  modeled_surplus_difference_kg: number | null;
  evidence_type: "assumption_based";
};
export type Assessment = {
  assessment_version: string;
  provenance_label: string;
  independently_verified: false;
  labels: string[];
  entry_complete: boolean;
  can_finalize: boolean;
  finalization_blockers: string[];
  issues: string[];
  accounting: {
    remaining_portions: number | null;
    known_disposition_portions: number;
    discrepancy_portions: number | null;
    missing_dispositions: string[];
    reconciled: boolean;
    unknown_portions: number | null;
    estimated_discarded_kg: number | null;
    estimate_label: string;
  };
  measurement_categories_present: string[];
  missing_measurement_categories: string[];
  physically_weighed_categories: string[];
  combined_weighed_kg: number | null;
  combined_mass_explanation: string;
  planning_timing: string;
  planning_timing_explanation: string;
  actual_minus_recommended: number | null;
  actual_minus_baseline: number | null;
  followed_exactly: boolean | null;
  limitations: string[];
};
export type OperationalRecord = {
  id: number;
  revision_id: number;
  version: number;
  status: "draft" | "finalized";
  event: string;
  correction_reason: string | null;
  changed_fields: string[];
  created_at: string;
  service_created_at: string;
  previous_revision_id: number | null;
  record: ServiceInput;
  assessment: Assessment;
  plan_reference: PlanReference | null;
};
export type Covered = {
  total: number | null;
  covered: number;
  missing: number;
};
export type ImpactSummary = {
  source_category: SourceCategory;
  provenance_label: string;
  status_filter: string;
  basis_filter: Basis | null;
  service_count: number;
  draft_services: number;
  counts: Record<string, Covered>;
  mass_by_category: Record<Category, Record<Basis, Covered>>;
  combined_weighed_kg: Covered;
  combined_explanation: string;
  estimated_discarded_kg: Covered;
  evidence: {
    complete_entries: number;
    incomplete_entries: number;
    unknown_disposition_services: number;
    missing_disposition_services: number;
    unreconciled_services: number;
    services_missing_mass: number;
    independently_verified_services: number;
  };
  adherence: {
    linked_services: number;
    assessable_services: number;
    followed_exactly: number;
    prospective_captures: number;
    retrospective_or_unlinked: number;
  };
  methods: Record<string, number>;
  daily: {
    date: string;
    services: number;
    prepared: number | null;
    served: number | null;
    remaining: number | null;
  }[];
  notes: string[];
};
export type ImpactComparisonInput = {
  source_category: SourceCategory;
  category: Category;
  basis: Basis;
  baseline_start: string;
  baseline_end: string;
  trial_start: string;
  trial_end: string;
  site: string | null;
  menu: string | null;
};
export type ComparisonPeriod = {
  services: number;
  covered_observations: number;
  missing_or_other_basis: number;
  reported_mass_kg: number | null;
  kg_per_covered_service: number | null;
  g_per_observed_diner: number | null;
  diner_covered_services: number;
  observed_diners: number | null;
  paired_mass_kg: number | null;
  methods: Record<string, number>;
  menus: Record<string, number>;
  sites: Record<string, number>;
};
export type ImpactComparison = {
  label: string;
  source_category: SourceCategory;
  basis: Basis;
  category: Category;
  status: "blocked" | "comparable_descriptive";
  reasons: string[];
  periods: { baseline: ComparisonPeriod; trial: ComparisonPeriod };
  difference: {
    kg_per_service_trial_minus_baseline: number;
    relative_change: number | null;
    g_per_diner_trial_minus_baseline: number | null;
  } | null;
  notes: string[];
};
