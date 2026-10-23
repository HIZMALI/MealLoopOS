# Impact Ledger measurement protocol — Build 04

Assessment version: **impact04-v1**. This is a local operational reporting and accounting protocol, not an independently assured inventory, food safety procedure or causal trial. The original Finland workbook and Builds 02/03 remain unchanged.

## Evidence and provenance

Keep three sources separate: historical Finland measurements, assumption-based Decision Studio plans, and newly entered operational records. Operational provenance is exactly one of `synthetic`, `user_reported`, or `user_reported_documented`. The last category requires one or more supporting references; the app does not upload/read/authenticate their contents. All operator reports remain independently unverified. Provenance is immutable across revisions. Synthetic records never enter actual self-report cohorts, original measured tables or forecast training.

Public [FLW Standard guidance](https://flwprotocol.org/flw-standard/) organizes measurement around scope, methods, destinations, uncertainty, reporting and assurance. Its [official FAQ](https://flwprotocol.org/flw-standard/faqs/) explains that food retained for human consumption is reported separately from the waste inventory, and that quantification methods depend on the inventory's purpose and resources. MealLoop adopts explicit declarations and disclosures for these concerns; it does not claim standards conformance or certification.

The public [terms and definitions](https://flwprotocol.org/flw-standard/tools-resources/terms-definitions/) distinguish food and associated inedible parts. The ledger therefore records material type and destination with every mass entry. These declarations are operator reports, not independent validation of physical boundaries.

## Service identity and counts

Record a service date, optional site, menu ID/description and source category. Enter prepared and served whole portions when known. Enforce `0 ≤ served ≤ prepared ≤ 100000`. Drafts may leave either count blank; no remaining count is derived without both. Record turn-aways separately; neither prepared nor served counts establish unconstrained demand. Record unique observed diners separately if a per-diner rate is needed; portions served may include second helpings and are not substituted for diners.

```text
remaining = prepared − served
known_disposition_total = sum(non-missing disposition entries)
discrepancy = remaining − known_disposition_total
```

Five mutually exclusive dispositions describe only unserved prepared portions: donated for human consumption, retained for later service, repurposed for human consumption, discarded, and unknown/unaccounted. Every destination is nullable. A blank is not zero, including when the known entries happen to match the remaining count. Negative/positive discrepancies remain visible and never generate balancing entries. Unknown disposition can reconcile arithmetic while leaving knowledge incomplete.

The app gives no food safety certification or recommendation to donate/store unsafe food. Staff must follow existing kitchen procedures. Retained/donated/repurposed counts do not establish eventual consumption and are not treated as discarded waste.

## Mass categories and methods

There is at most one mass entry per category per revision:

| Category | Intended boundary |
| --- | --- |
| Discarded prepared-food surplus | Unserved prepared food discarded; excludes plate returns and preparation scraps |
| Plate waste | Returned served food; excludes unserved food and preparation scraps |
| Preparation waste | Preparation scraps/parts; excludes the other two streams |

These are proposed disjoint definitions, not automatic factual assertions. Operators describe the actual scope, relationship to other entries, method, material (`food_only`, `inedible_only`, `food_and_inedible`, `unspecified`), destination, notes and basis (`weighed`, `estimated`, `imported`). Imported means manually entered from another report; it does not certify original weighing. No file-import endpoint was added. Keep source documents externally and use references/notes to locate them.

Mass is finite, nonnegative kg, bounded at 1,000,000 kg. Missing category entries stay absent. An enabled mass entry needs a net value or both gross/tare readings. Gross/tare are supported only for weighed entries; require gross ≥ tare. Net is gross − tare using decimal arithmetic. If net was supplied, a difference exceeding **0.000001 kg** rejects the entry; a supplied reading within tolerance is retained. If absent, the server calculates net and retains both readings. Containers/packaging should be excluded and added water/other scope limitations documented.

A combined three-stream scale inventory is returned only when all categories are present, every entry is weighed, scope relationships are declared disjoint, a disjoint-scope explanation exists, method labels match after case/whitespace normalization, and material definitions match with known destinations. Otherwise, category reports stay separate and combined mass is null with an explanation. Across services the combined inventory additionally requires matching site/menu/scope/method/material/destination declarations; partial compatible coverage is explicit. This conservative rule avoids merging unlike inventories. Different menu/site cohorts can be inspected separately.

Portion-count conversion is a separate estimate:

```text
estimated_discarded_kg = discarded_portions × portion_mass_g / 1000
```

It is null without both inputs and is never added to or substituted for a scale reading of the same food. Portion mass must be finite, >0 and ≤10,000 g. No cost, carbon or prevented-waste conversion is implemented.

## Plans and capture timing

A linked plan must exist, match service date, and match a numeric menu identifier when both are provided. Synthetic demo plans can link only to synthetic services. The original saved result is retrieved, not reoptimized. The operational revision stores the plan ID, server creation time, input hash/version, original quantities and modeled comparison; the original full JSON remains accessible. Actual preparation is entered separately.

Display actual prepared minus recommendation/baseline and exact adherence where a recommendation exists. An infeasible plan has no recommendation, so adherence is unknown. Baseline is not proof of a counterfactual and modeled surplus is not realized prevention.

Only server timestamps can establish plan capture. Without an independently captured service start time, the conservative cutoff is the **earliest possible start of the reported calendar date anywhere (UTC+14)**: date midnight UTC minus 14 hours. A plan captured strictly before that cutoff is labeled prospectively captured **relative to the reported date**. Everything later, including same-day or backfilled plans, is retrospective. Unlinked observations are retrospective. Matching service date and trusted server clock are still assumptions about reporting; service occurrence/date are unverified. The frontend cannot supply a capture timestamp. Finalization rejects dates after the server UTC date; this may conservatively delay a local-calendar record near midnight.

## Drafts, finalization and evidence quality

Creation always appends a draft. Finalization requires both actual counts, all five disposition entries, exact reconciliation, unknown=0, a count method and a non-future service date under the UTC policy. Mass entries are optional for finalizing **counts**. Finalization is not an evidence certification: a finalized record can still disclose incomplete mass coverage or unknown turn-aways.

`entry_complete` is stricter: no count blockers, no missing turn-away/portion-mass information, and a complete compatible weighed inventory. It does not imply independent verification, prospective observation or causal validity. Classification includes synthetic demonstration, incomplete record, complete self-reported record, scope unresolved and retrospective/prospective capture labels as applicable. Results give reasons and coverage, never a scientific confidence percentage.

Every correction requires a reason (5–1,000 characters), expected current version and a complete replacement input snapshot. It appends another draft with parent revision and changed-field list; earlier snapshots remain unchanged. Finalizing appends another event. Unique service/version constraints and optimistic version checks reject competing/stale updates with 409. Latest revisions supersede previous ones in summaries; a pending correction draft excludes that service from finalized-only comparison until finalized again. Each service is bounded at 200 revisions. This history is not cryptographically tamper-proof or authenticated.

## Operational summaries and descriptive comparisons

Summaries select exactly one provenance category, current revisions only, explicit lifecycle/basis/date/site/menu filters, and up to 5,000 cohort records. Count/mass values include coverage/missingness. A basis filter selects services containing that basis; other entries inside the service remain separately labeled. Synthetic values are always simulated. Charts use persisted reported counts and leave missing values as gaps. The database does not prove that separately created identities represent distinct physical services; operators must avoid duplicates.

Comparisons use ordered non-overlapping baseline/trial periods, finalized current revisions, one source/category/basis, and matching normalized declarations for site/menu, disjoint scope note, scope description/status, material, destination and method. Unresolved boundaries or mismatches block pooled metrics. Missing/other-basis entries are excluded with counts shown. Exact matching is conservative; no semantic equivalence is inferred from free text. Use consistent protocol definitions and put dates in date fields, not scope labels.

Where compatible, report category kg, kg per covered service and signed trial-minus-baseline differences, not just unequal-period totals. A relative difference is null at a zero baseline. For per-diner rates use only covered readings with separately observed positive unique diners:

```text
g_per_diner = 1000 × sum(paired category kg) / sum(paired observed diners)
```

Missing/zero diner denominators do not use served portions. Expose matched mass, diners and service coverage. Context includes menus, sites, method counts and attendance. Every comparison states **“Observational comparison — not causal evidence.”** It does not adjust for attendance, menu, weather, staffing or other confounding and cannot establish a software effect.

## Reproduction and assurance limits

Run `.venv/Scripts/python.exe scripts/evaluate_impact.py`. A disposable local SQLite database and fixed **synthetic** server clock exercise creation, plan linkage, finalization, failed validation, corrections/history, source isolation and restart retrieval twice. Independent integer/decimal calculations verify 40 remaining portions, a separate 8 kg estimate, and 9.7 kg simulated scale sum with a 7.6 kg surplus reading; unknown=5 blocks finalization. Output is deterministic LF JSON at `docs/evaluation/build_04_evaluation.json`. No real pilot occurred.

JSON exports retain full revision evidence. CSV exports retain each revision and separate mass/basis/scope/estimate columns, blanks for missingness and formula-escaped free text. Server filenames never come from user labels. Request bodies are bounded at 64 KiB including chunked transfer. There is no login, actor identity, attachment assurance or production deployment. See `IMPACT_EVIDENCE_LIMITATIONS.md` before making any public statement based on these entries.
