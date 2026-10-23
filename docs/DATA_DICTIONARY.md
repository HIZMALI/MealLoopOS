# Data dictionary and inspected source layout

## Actual workbook inspection

Inspected the official, checksum-matched 31,210-byte workbook on October 23, 2026 (Europe/Istanbul), before implementing its mapping. Inspection used the ZIP/XML structure and openpyxl with cached values, followed by the same validated parser used by the API. Reproduce with `python scripts/inspect_dataset.py`; the captured output is `docs/workbook-inspection.json`.

- One sheet: **`food waste school meals 2024-25`**.
- Excel physical dimension: **A1:P743**. Most trailing rows/columns are formatting only.
- Header row: **1**. Measurement rows: **2–156**, exactly **155 school days**.
- Real date cells exist: **2024-08-08 through 2025-04-11**, Excel date format `dd/mm/yyyy`, chronological source order. Dates were observed, not inferred from the title or description.
- All menus and diners are present; menus range **1–25**, diners **251–546**.
- No exact duplicate records, duplicate dates, negative masses, or zero-diner days were found in this workbook.
- Missing kitchen/serving mass and its per-diner representation on Excel row **19**, day **18**, **2024-09-02**. Plate mass **9.116 kg**, diners **419** remain available.
- Redundant source values conflict on Excel rows **137** and **152** (detailed below).

## Source-to-normalized mapping

| Source header | Normalized field | Unit / type | Source missing | Source display format | Policy |
| --- | --- | --- | ---: | --- | --- |
| `DATE` | `date` | Nullable ISO date | 0 | `dd/mm/yyyy` | Preserve recorded date and original row order |
| `MENU` | `menu` | Nullable integer, 1–25 | 0 | General | Numeric meal identifier; no invented names |
| `KSW kg` | `kitchen_serving_waste_kg` | Nullable nonnegative kg | 1 | `0.00` | Primary kitchen/serving mass |
| `PW kg` | `plate_waste_kg` | Nullable nonnegative kg | 0 | General | Primary plate mass |
| `PW g` | `reported_plate_waste_g` | Nullable nonnegative g | 0 | General on 154 cells; `0` on one | Audit representation; never added to kg |
| `DINERS` | `diners` | Nullable nonnegative integer | 0 | General | Observed diner count; no production implication |
| `PW/g/diner` | `reported_plate_g_per_diner` | Nullable nonnegative g/diner | 0 | `0.000` | Audit only; derived display uses primary mass and matched diners |
| `KSW/g/diner` | `reported_kitchen_g_per_diner` | Nullable nonnegative g/diner | 1 | `0.000` | Audit only; not an extra mass stream |

Extra normalized fields: `batch_id`, `day_index` (one-based nonempty measurement sequence), `source_row` (one-based physical input row), `phase` (`baseline`, `intervention`, or `unassigned`), and `issues` (list of audit codes). Blank physical rows are ignored; nonblank rows with neither waste mass are rejected. Formatting-only cells are not records.

## Source conflicts retained

| Day / Excel row | Date | Source conflict | Handling |
| --- | --- | --- | --- |
| 136 / 137 | 2025-03-17 | PW 11.633 kg, KSW 2.410 kg, 340 diners imply plate **34.214706** and kitchen **7.088235** g/diner; workbook reports **8.250035** and **21.768363** | Retain all reported values; use primary kg for descriptive statistics; flag both per-diner conflicts |
| 151 / 152 | 2025-04-07 | PW **6.510 kg** conflicts with **6,751 g**; reported plate **24.371841 g/diner** also conflicts with 277 diners and kg mass (**23.501805 g/diner**) | Retain both units and the reported per-diner value; kg takes precedence; flag both conflicts |

Comparison tolerances: **0.5 g** for redundant plate mass; **0.05 g/diner** for redundant daily rates. These tolerate floating point representation and small rounding, not substantive disagreements. Three rows have audit notes; one row can contain multiple notes. These flags do not assert which measurement is scientifically correct.

## Accepted local formats

Accept `.xlsx` or UTF-8 / UTF-8-BOM `.csv`. CSV separators: comma or semicolon (selected from the first line). Decimal commas are supported in semicolon-separated CSV or quoted comma-separated fields. Thousands separators are unsupported and rejected. Dates accept actual Excel dates, ISO `YYYY-MM-DD`, or `DD/MM/YYYY` strings; numeric CSV serial dates are rejected rather than guessed. The first non-empty row is the header. Exactly one matching data sheet is required; separate ambiguous sheets before import.

Case-insensitive header aliases:

| Meaning | Accepted aliases |
| --- | --- |
| Plate kg | `PW kg`, `PW`, `plate_waste_kg`, `plate waste kg` |
| Plate grams | `PW g`, `plate_waste_g` |
| Kitchen/serving kg | `KSW kg`, `KSW`, `kitchen_serving_waste_kg`, `kitchen serving waste kg` |
| Diners | `DINERS`, `diner count` |
| Menu | `MENU`, `menu identifier` |
| Date | `DATE` |
| Reported plate per diner | `PW/g/diner`, `reported_plate_g_per_diner` |
| Reported kitchen per diner | `KSW/g/diner`, `reported_kitchen_g_per_diner` |

Plate mass (kg or grams), kitchen mass, and diners **headers** are required. Individual cells may be missing. At least one waste mass must exist per non-empty row. Optional menu/date columns may be absent. Empty strings, `NA`, `N/A`, and `null` mean missing. Other nonnumeric values (including `NaN`, infinities, formulas without cached values in CSV, and negative values) reject the whole batch. Integers are required for diners and menus; menus are limited to this source's 1–25 domain. Individual numeric values are bounded at 1,000,000.

When a kg column **exists**, it is primary even when a particular kg cell is null: that cell is not filled from redundant grams. If the entire plate kg column is **absent**, a plate gram column may be converted using **kg = g / 1,000**, with an explicit per-row conversion audit code. Per-diner fields never reconstruct a missing mass. Unknown columns are listed in inspection metadata but do not affect metrics. Two aliases mapping to the same field are rejected.

Identical files are rejected by SHA-256, including when uploaded under a different filename or data-kind label. Identical rows and duplicate dates are retained with audit flags because equal measurements can represent different days. Rows are never silently dropped or reordered. Missing dates remain null; charts use `day_index`.

## Periods and provenance

The exact official file checksum identifies source `zenodo:20825233`: `measured`, CC BY 4.0, authors, URL, DOI, **135 baseline + 20 intervention**. The first intervention record is day 136, **2025-03-17**. The baseline ends **2025-03-14**.

Other measured uploads use source `local:measured`, explicitly unverified provenance, with no invented DOI/license. Synthetic uploads use `local:synthetic` and are prominently labeled. Custom phase assignments require an explicit baseline count; otherwise records are `unassigned`. The software does not infer a 20-day intervention from an arbitrary uploaded file.

## Aggregation contract

Let `Pᵢ`, `Kᵢ` be kg plate and kitchen mass, and `Nᵢ` diners.

- **Plate total**: sum observed `Pᵢ`. **Kitchen total**: sum observed `Kᵢ`. A completely unavailable component returns null, not zero.
- **Combined recorded waste**: sum all observed plate and kitchen masses; this may include partial days. Never add `PW g` or either per-diner field to these totals.
- **Complete waste mass / daily chart combined value**: `Pᵢ + Kᵢ` only where both masses exist. Otherwise null; line charts do not connect gaps.
- **Average daily combined kg**: sum combined mass / count of complete mass days. Zero-diner days can still contribute measured mass to this average.
- **Average waste per diner g**: `1,000 × Σ(Pᵢ + Kᵢ) / ΣNᵢ` over the **same** complete-mass rows with known **positive** diner counts. This is diner-weighted, not a mean of daily reported rates. Zero/missing diners exclude that row from both numerator and denominator; no eligible rows yields null.
- **Menus and periods**: apply the same rules within each group. Per-menu missing identifiers are excluded from groups and counted separately. No exposure-adjusted ranking or causal inference is claimed.
- API calculations retain floating point precision; UI totals generally round to one decimal and the ledger shows three decimals. Reports state their rounding.

Official-data regression totals: **1,407.754 kg plate**, **1,243.880 kg kitchen**, **2,651.634 kg combined recorded**. Complete mass: **2,642.518 kg over 154 days**. The per-diner denominator is **61,233 diners over those same 154 days**, giving **43.155129 g/diner**. All 155 rows record **61,652 diners**, which is deliberately *not* used as the denominator for that incomplete combined-mass numerator.

## Build 02 forecasting targets

The descriptive Build 01 aggregation contract above is unchanged. Forecasting uses a stricter **paired** quality cohort: exclude a whole target day when either primary mass is missing, diners are missing/nonpositive, or a source conflict/duplicate note is present. Both component targets are calculated as kg × 1,000 / observed diners; combined is their sum. Reported rates are never targets. This excludes days 18, 136, and 151 from modeling, leaving 152 eligible days (134 baseline, 18 holdout), while every source row remains persisted and visible.

Modeling loss is an equal-day average of errors in g/diner, distinct from the descriptive diner-weighted aggregate. Actual diners are target denominators, not forecast features. Future planned attendance is a user assumption for estimated-kg conversion. See `FORECAST_METHODOLOGY.md` for chronological availability, exclusion logs, fixed validation cutoffs, and the separate production fit.

## Research citation

Kuusisto, A.; Latva, J.; Wilén, E. (2026). *Food waste dataset: secondary school in Finland 2024–2025*. Zenodo, v1. [DOI](https://doi.org/10.5281/zenodo.20825233), [record](https://zenodo.org/records/20825233), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Original workbook unchanged; normalization and summaries are derived representations. The original artist-designed intervention was not caused by MealLoop OS.
