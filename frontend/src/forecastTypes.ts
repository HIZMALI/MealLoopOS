export type Rates = { plate: number; kitchen: number; combined: number };
export type Score = { n: number } & Record<
  keyof Rates,
  { mae: number; rmse: number }
>;
export type Exclusion = {
  day_index: number;
  source_row: number;
  date: string;
  reasons: string[];
};
export type Period = {
  first_day: number;
  last_day: number;
  start_date: string;
  end_date: string;
  total: number;
  eligible: number;
  excluded: number;
  exclusions: Exclusion[];
  reason_counts: Record<string, number>;
};
export type ModelMetadata = {
  model_id: string;
  batch_id: number;
  dataset_fingerprint: string;
  config_key: string;
  version: string;
  selected_method: string;
  selected_label: string;
  created_at: string;
  quality_policy: string;
  production_training: Period;
  evaluation_fit_cutoff: Period;
  holdout_period: Period;
  source: {
    title: string;
    kind: string;
    authors: string;
    doi: string | null;
    url: string | null;
  };
  serialization: string;
};
export type ModelStatus = {
  status: "empty" | "blocked" | "not_prepared" | "ready";
  batch_id: number | null;
  reason: string | null;
  metadata: ModelMetadata | null;
};
export type Prediction = {
  day_index: number;
  source_row: number;
  date: string;
  included: boolean;
  exclusions: string[];
  actual: Rates | null;
  predictions: Record<string, Rates>;
  history_last_day: number;
  fit_cutoff_day: number;
};
export type Evaluation = {
  version: string;
  quality_policy: string;
  selected_method: string;
  selected_label: string;
  method_labels: Record<string, string>;
  selection_rule: string;
  baseline_period: Period;
  holdout_period: Period;
  production_training: Period;
  folds: {
    training: Period;
    validation: Period;
    metrics: Record<string, Score>;
  }[];
  validation_metrics: Record<string, Score>;
  holdout_metrics: Record<string, Score>;
  validation_predictions: Prediction[];
  holdout_predictions: Prediction[];
  dataset_fingerprint: string;
  raw_sha256: string;
  model_id: string;
  limitations: string[];
};
export type Scenario = {
  batch_id: number;
  service_date: string;
  planned_diners: number;
  menu: number | null;
};
export type SavedForecast = {
  id: number;
  batch_id: number;
  artifact_id: number;
  created_at: string;
  scenario: Scenario;
  result: {
    label: string;
    model_id: string;
    method: string;
    effective_method: string;
    rates_g_per_diner: Rates;
    estimated_mass_kg: Rates;
    warnings: string[];
    last_observation_date: string;
    training_eligible_days: number;
  };
};
