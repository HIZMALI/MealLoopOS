# Data provenance and reuse

## Official measured dataset

**Arja Kuusisto** (University of Vaasa), **Jenni Latva** (Uniarts Helsinki), and **Ella Wilén** (City of Lapua, Finland). 2026. *Food waste dataset: secondary school in Finland 2024–2025*, version 1. Zenodo. Published June 24, 2026.

- Record: https://zenodo.org/records/20825233
- DOI: https://doi.org/10.5281/zenodo.20825233
- Official record API: https://zenodo.org/api/records/20825233
- License in the official API metadata: **`cc-by-4.0`** (verified October 23, 2026, Europe/Istanbul).
- License terms: https://creativecommons.org/licenses/by/4.0/
- File: `raw/Food waste data school Finland 2024-2025.xlsx`, **31,210 bytes**.
- Published MD5: `3f7e610fedc1810f7e8bc1bd47103ee7` (matched the download).
- SHA-256: `2ffad746b7ed5d536a0c99c37d8e249230d95d5fb2d041d85d01b69499f99624`.

The source workbook is included **unchanged**. `raw/zenodo-record.json` is a snapshot retrieved from the official API documenting authors, license, source, and checksum. CC BY 4.0 permits sharing and adaptation with attribution, a license link, and indication of changes. Retain this notice when sharing these files or derivatives. No endorsement by the researchers or their institutions is implied.

MealLoop OS changes the *representation*: normalized field names, ISO dates, row/phase indices, import metadata, audit flags, and descriptive aggregates. It does not edit the original workbook or correct conflicting measurements. Row numbers and redundant reported values are preserved in the normalized database. No source measurements are imputed.

The source describes daily school measurements from August 2024 to April 2025: 135 baseline days followed by 20 days of artist-designed interventions. That intervention predates this software. See `docs/DATA_DICTIONARY.md` for the inspection findings.

## Prepared demo and local storage

`public_demo/forecast_artifact.json` is an inert prepared predictor and a copy of the unchanged historical forecast evaluation derived from the attributed Finland measurements. It was reproduced and compared to that evaluation; it contains no uploaded/private data or executable model serialization. Representation/estimates are derived; the raw measurements remain unchanged. Public-demo preparation validates this file and seeds a separate ignored `.public-demo/` database. Synthetic planning/operational examples are automatically seeded only in that isolated public environment, never into the normal local DB. Fixed synthetic capture/import metadata supports repeatability and is not evidence of service occurrence. See `docs/PUBLIC_DEMO_SECURITY.md`.

`mealloop.db` is created locally and ignored by Git. Sources, immutable batches, and normalized rows are separate tables. UI upload bytes are discarded after normalization. Keep the original uploaded file externally if you need exact-file reproducibility; batch SHA-256 and display filename remain in the database.

## Synthetic fixture

`fixtures/synthetic_test.csv` was authored for this project's tests. Every value is **synthetic**, including its missing values, zero diners, and duplicate row. It contains no real observations or recorded dates. It is never loaded automatically. Use `--kind synthetic` in the CLI or choose **Synthetic test fixture** in the UI. It provides no evidence about real food waste or intervention effects.

The header-only file `frontend/public/template.csv` is an input format template, not a dataset.

`fixtures/synthetic_decision_demo.json` is a separate **SYNTHETIC DEMO SCENARIO**. Demand levels, probabilities, prepared quantities, portion mass and constraints are illustrative assumptions, not Finland measurements or an attendance forecast. It is loaded only by an explicit demo action, tests, or `scripts/evaluate_decisions.py`, and never imported into measured daily records. It supports no real-world impact claim. Saved plans live in `decision_plans` with `evidence_type=assumption_based`.

`fixtures/synthetic_impact_demo.json` contains **synthetic operational examples**. Preparation, service counts, food destinations and scale readings are simulated; no real kitchen pilot or weighing occurred. The complete example reconciles 40 remaining portions and a 9.7 kg simulated disjoint-stream inventory, separately from its 8 kg portion-count estimate. The incomplete example has five portions of unknown disposition. Only an explicit **Add synthetic examples** action, tests or `scripts/evaluate_impact.py` loads these examples. They are stored separately in operational tables with immutable `synthetic` provenance, never in Finland daily records or actual self-report cohorts. The evaluator uses a fixed test clock and disposable database solely for reproducibility.
