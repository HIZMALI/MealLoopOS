# What Impact Ledger evidence can and cannot show

Build 04 records operational reports with accounting rules and an audit trail. It does **not** demonstrate achieved food-waste reductions, a real pilot, independent verification, standards certification, calibrated confidence, food safety or causal impact. Operational examples remain explicitly synthetic.

## Three different claims

| Evidence | Legitimate statement | Unsupported statement |
| --- | --- | --- |
| Finland workbook | Historical waste/diner observations with original provenance and quality flags | MealLoop OS caused the study's intervention or its outcomes |
| Decision Studio | The mathematical optimum under stated demand assumptions | The baseline would certainly occur, demand is known, or predicted surplus was prevented |
| Operational self-report | An operator entered counts/readings and declared scopes; changes are traceable | Entries are independently verified or caused by the software |
| Synthetic ledger example | Arithmetic/workflows behave correctly for simulated inputs | A kitchen served meals, weighed food or prevented waste |

The [FLW Protocol's public FAQ](https://flwprotocol.org/flw-standard/faqs/) distinguishes inventory reporting from assurance and keeps food rescued for human consumption outside waste inventory results. This implementation follows that separation in its local model; declarations in software are not proof of physical boundaries or conformance. No ISO certification/compliance claim is made and no proprietary ISO requirements are implemented.

## Data-entry completeness is not validity

Counts may reconcile despite error, duplicate reporting or deliberate misstatement. Unknown disposition is a knowledge gap even when it balances the arithmetic. A finalized count snapshot may lack mass readings or turn-aways. A complete self-report is still a self-report. Supporting references can be nonexistent, incomplete or inaccurate; the app retains references only and does not inspect/authenticate source files. Local labels cannot provide independent assurance.

Server timestamps show capture on this installation under its clock, not when an actual service/measurement took place. A prospective label is relative to the reported date and conservative UTC+14 boundary, not independent proof of intervention timing. Wrong service dates, clock errors and administrator changes undermine that inference. Backfilled and same-day plans are retrospective. The UTC finalization-date policy can delay local-day finalization near midnight. Versioning records changes but supplies no authenticated operator identity or cryptographic tamper protection.

## Measurements, estimates and destinations

Weighing can include tare mistakes, packaging, added water, missed collections, transferred material or incompatible scopes. Method/scope matching is based on operator text, not a verified measurement protocol. Category totals may be heterogeneous reports; do not manually sum them when the combined inventory is unavailable. Missing entries are not zero. Reused, retained, repurposed and donated food is not automatically discarded, and eventual consumption is not proven. Food safety decisions remain with qualified staff and established kitchen procedures.

A count × portion-mass estimate is different from a scale reading. The example's 8 kg estimate and simulated 7.6 kg surplus reading refer to the same modeled stream and must never be added together. Even the 9.7 kg simulated three-stream sum is only valid under its explicitly disjoint definitions and contains no real physical measurements.

Served portions do not reveal unconstrained demand or the number of unique diners. Turn-aways can be unrecorded, and unmet demand can include people who did not queue. Positive independently entered diner counts are required for reported per-diner calculations; neither serving nor preparation counts are substituted. Paired coverage can differ between periods, so averages may represent different subsets.

## Comparisons and planning adherence

Exact preparation adherence can coexist with poor service, inaccurate demand assumptions, unsafe handling or more waste. Actual minus baseline quantities are descriptive differences; baseline is an assumed comparator, not a measured counterfactual. Before/after differences can reflect attendance, menu, season, staffing, measurement methods and selection/missingness. The ledger does not control these confounders or estimate treatment effects. A lower kg-per-service value is not verified savings, and lower g/diner with a larger group can coexist with higher total kg.

Comparisons intentionally require matching source/site/menu/scope/material/destination/method declarations. This may block semantically compatible records whose descriptions differ; review definitions and correct them only with an honest reason. Do not relabel incompatible measurements merely to enable comparison. Synthetic, documented and undocumented self-report cohorts remain separately selectable; the app never creates a pooled synthetic/actual result. The historical Finland inventory is outside operational summaries.

## What a future real evaluation needs

Co-design definitions and service/safety constraints with kitchen staff. Retain original logs and scale records; distinguish intended from actual destinations, unknown outcomes and unique diners. Check collection/tare/scope consistency and record missed measurements without imputation. Establish authenticated roles, data retention, backups and independent review where appropriate before public deployment. Predeclare prospective comparisons, service outcomes and confounder handling with suitable methodological support. Publish only the evidence the design actually supports.

These are future gates, not an implemented trial. Current execution was on Windows / Python 3.14 / local SQLite, with browser workflows and deterministic tests. Python 3.11 and PostgreSQL deployment, production load, formal accessibility certification, external assurance and real-world impact have not been verified. No costs/emissions factors, attendance predictions, testimonials, donation routing or LLM advice are provided.
