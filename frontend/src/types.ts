export type Source = {
  key: string;
  title: string;
  kind: "measured" | "synthetic";
  doi: string | null;
  url: string | null;
  authors: string | null;
  license: string | null;
};
export type Batch = {
  id: number;
  filename: string;
  sha256: string;
  imported_at: string;
  row_count: number;
  baseline_days: number | null;
  source: Source;
  inspection: {
    sheet: string;
    sheets: string[];
    headers: string[];
    header_mapping: Record<string, string>;
    ignored_columns: string[];
    issue_counts: Record<string, number>;
    flagged_rows: number;
    date_count: number;
    date_ordered: boolean;
    date_start: string | null;
    date_end: string | null;
    verified_official_file: boolean;
    missing_counts: Record<string, number>;
    mass_policy: string;
  };
};
export type Metrics = {
  days: number;
  plate_waste_kg: number | null;
  kitchen_serving_waste_kg: number | null;
  combined_recorded_waste_kg: number | null;
  complete_waste_kg: number | null;
  average_waste_per_diner_g: number | null;
  average_daily_combined_kg: number | null;
  average_daily_plate_kg: number | null;
  average_daily_kitchen_kg: number | null;
  diners_recorded: number | null;
  coverage: {
    plate_days: number;
    kitchen_days: number;
    complete_days: number;
    per_diner_days: number;
    per_diner_diners: number;
  };
};
export type Overview = {
  batch: Batch;
  metrics: Metrics;
  periods: (Metrics & { phase: string })[];
  interpretation: string;
};
export type Daily = {
  day_index: number;
  source_row: number;
  date: string | null;
  label: string;
  phase: string;
  menu: number | null;
  diners: number | null;
  plate_waste_kg: number | null;
  kitchen_serving_waste_kg: number | null;
  combined_waste_kg: number | null;
  waste_per_diner_g: number | null;
  reported_plate_waste_g: number | null;
  reported_plate_g_per_diner: number | null;
  reported_kitchen_g_per_diner: number | null;
  issues: string[];
};
export type Charts = {
  batch_id: number;
  daily: Daily[];
  menus: (Metrics & { menu: number })[];
  menu_missing_days: number;
};
export type Status = {
  status: string;
  batches: Batch[];
  active_batch_id: number | null;
  official_source: Source;
};
