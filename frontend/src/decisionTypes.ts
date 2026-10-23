export type DemandAssumption = {
  name: string;
  demand_portions: number;
  probability: number;
};
export type DecisionRequest = {
  planning_date: string;
  title: string;
  menu: number | null;
  scenario_kind: "synthetic_demo" | "user_assumptions";
  baseline_portions: number;
  portion_mass_g: number;
  batch_increment: number;
  maximum_capacity: number;
  minimum_portions: number;
  reliability_target: number;
  demand_scenarios: DemandAssumption[];
  sensitivity_percent: number;
  context_batch_id: number | null;
};
export type Candidate = {
  quantity: number;
  expected_demand_portions: number;
  expected_served_portions: number;
  expected_surplus_portions: number;
  expected_unmet_portions: number;
  expected_surplus_kg: number;
  probability_fully_served: number;
  expected_fill_rate: number;
  zero_expected_demand: boolean;
  capacity_use: number | null;
  feasible: boolean;
  rejection_reasons: string[];
};
export type Outcome = DemandAssumption & {
  served_portions: number;
  surplus_portions: number;
  unmet_portions: number;
  surplus_mass_kg: number;
  fully_served: boolean;
};
export type PlanEvaluation = Candidate & { outcomes: Outcome[] };
export type Feasibility = {
  feasible_candidates: number;
  rejected_candidates: number;
  required_capacity: number | null;
  maximum_grid_quantity: number;
  maximum_reliability_on_grid: number;
  issues: {
    code: string;
    message: string;
    adjustments_to_consider: string[];
  }[];
};
export type Comparison = {
  potential_surplus_reduction_kg: number;
  potential_surplus_reduction_portions: number;
  relative_surplus_reduction: number | null;
  metrics: Record<
    string,
    {
      baseline: number | null;
      recommended: number | null;
      difference_recommended_minus_baseline: number | null;
      relative_change: number | null;
    }
  >;
};
export type DecisionResult = {
  engine_version: string;
  evidence_type: "assumption_based";
  scenario_kind: "synthetic_demo" | "user_assumptions";
  objective: string;
  tie_break: string;
  probability_sum: number;
  inputs: DecisionRequest;
  input_fingerprint: string;
  status: "optimal" | "infeasible";
  baseline: PlanEvaluation;
  recommended: PlanEvaluation | null;
  comparison: Comparison | null;
  feasibility: Feasibility;
  candidates: Candidate[];
  sensitivity: {
    demand_shift_percent: number;
    evidence_type: "assumption_based";
    demand_scenarios: DemandAssumption[];
    status: "optimal" | "infeasible";
    baseline: PlanEvaluation;
    recommended: PlanEvaluation | null;
    feasibility: Feasibility;
    comparison: Comparison | null;
  }[];
  assumptions_and_limitations: string[];
  numeric_notes: string[];
};
export type SavedDecision = {
  id: number;
  created_at: string;
  engine_version: string;
  evidence_type: "assumption_based";
  input_fingerprint: string;
  inputs: DecisionRequest;
  result: DecisionResult;
  context_reference: {
    batch_id: number;
    source_title: string;
    source_kind: string;
    source_doi: string | null;
    raw_sha256: string;
    role: string;
  } | null;
};
export type PlanSummary = {
  id: number;
  created_at: string;
  title: string;
  planning_date: string;
  scenario_kind: string;
  evidence_type: "assumption_based";
  engine_version: string;
  status: string;
  baseline_portions: number;
  recommended_portions: number | null;
};
export type DecisionMetadata = {
  engine_version: string;
  objective: string;
  tie_break: string;
  probability_sum_tolerance: number;
  probability_policy: string;
  zero_demand_policy: string;
  sensitivity_rounding: string;
  limits: {
    maximum_scenarios: number;
    maximum_demand: number;
    maximum_capacity: number;
    maximum_candidates: number;
    maximum_request_bytes: number;
    maximum_portion_mass_g: number;
  };
  rejection_reason_labels: Record<string, string>;
  assumptions_and_limitations: string[];
};
