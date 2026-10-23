# Decision Studio methodology

Engine: **decision03-v1**. Evidence: **assumption_based**. Scope: one menu, one service, fixed portion mass, finite user-specified demand distribution. This describes executed `backend/app/decisions.py` code, not a validated demand or impact model.

## Evidence boundary

The Finland workbook records historical waste and observed diners, not prepared portions, unconstrained demand, turn-aways, separately identified edible surplus, or effects of alternate plans. A predicted g/diner waste rate cannot establish those quantities. Decision Studio never converts waste forecasts or historical diners into demand/production inputs. The engine runs without any imported data or forecasting artifact.

Every production quantity, demand level/weight, portion mass, service target and capacity is an assumption. Optional historical context is provenance only: its source may be measured, while the decision remains assumption-based. The demo has a separate `synthetic_demo` label. Modeled surplus is food potentially at risk of waste, not automatically discarded mass. A difference is not realized prevention, a causal estimate, or proof of effectiveness. Adding surplus to historical kitchen/serving waste could double-count the same food.

## Validated inputs

| Input | Policy |
| --- | --- |
| Planning date | Valid calendar date, year 2000–2100; not a measured service date or forecast origin |
| Optional menu | Integer 1–10,000 or null; identifier only |
| Optional title | ≤100 printable characters; surrounding whitespace stripped |
| Baseline portions | Strict integer 0–100,000; comparator may violate current constraints |
| Portion mass g | Finite number >0 and ≤10,000; constant across portions/scenarios |
| Batch increment b | Strict integer 1–10,000 |
| Capacity C / minimum M | Strict integers 0–10,000; conflicting limits produce infeasibility |
| Reliability r | Finite number 0–1; illustrative default 0.95 |
| Demand scenarios | 1–30; unique names ignoring case/surrounding whitespace, ≤60 printable characters |
| Demand Dᵢ | Strict integer 0–100,000 portions |
| Probability pᵢ | Finite number 0–1; sum within 1e-9 of 1 |
| Sensitivity s | Finite percentage 0–50; zero disables; editor/demo default 10%, API default 0 |
| Optional reference | Positive existing batch ID when saving; preview needs no lookup |

Unknown fields are rejected. Integer fields reject fractions, booleans and numeric strings. Masses/probabilities/targets also reject strings/booleans. Distinct names may have equal demands; no silent merging occurs. Zero-weight scenarios contribute zero. The candidate grid is bounded by `floor(C/b)+1 ≤ 2001`, including later rejections. Requests are limited to 64 KiB, including chunked transfer. Upward sensitivity cannot exceed the demand bound. Dates/labels never become file paths.

## Mathematical definitions

For nonnegative integer production Q and assumed demand Dᵢ:

```text
servedᵢ  = min(Q, Dᵢ)
surplusᵢ = max(Q − Dᵢ, 0)
unmetᵢ   = max(Dᵢ − Q, 0)
surplus_massᵢ_kg = surplusᵢ × portion_mass_g / 1000

E[demand] = Σ pᵢ Dᵢ
E[served] = Σ pᵢ servedᵢ
E[surplus portions] = Σ pᵢ surplusᵢ
E[unmet] = Σ pᵢ unmetᵢ
E[surplus kg] = Σ pᵢ surplus_massᵢ_kg
P(fully served | specified scenarios) = Σ pᵢ · 1[Q ≥ Dᵢ]
expected_fill_rate = E[served] / E[demand]
```

If expected demand is zero, fill rate is **1 by explicit no-demand convention**; expected unserved demand is zero. Zero-weight positive-demand cases do not change this. At zero capacity, capacity use is 0 for Q=0; a positive baseline has undefined capacity use (null). An over-capacity baseline can exceed 100% use and is marked infeasible.

For weights totaling exactly 1, `E[served]+E[unmet]=E[demand]` and `E[served]+E[surplus]=Q`. With accepted weight roundoff, the second identity is `Q × Σpᵢ`. Increasing Q cannot increase unmet portions or decrease surplus portions. Tests enforce these identities using independent references.

## Exact optimization and infeasibility

Enumerate **all** Q in `0, b, 2b, …, floor(C/b)b`. Feasibility additionally requires `Q ≥ M` and exact weighted full-service probability ≥r. Enumeration enforces integer/batch/capacity limits. Return every candidate's metrics, feasibility and rejection reasons. Evaluate the baseline with the same definitions, retaining off-grid, below-minimum, over-capacity and insufficient-service warnings.

Choose the lexicographically smallest tuple `(expected surplus kg, expected unmet portions, Q)`. Surplus is the objective; lower unmet demand and lower Q are deterministic tie-breaks. When r=0, shortage is explicitly allowed: among equal-surplus quantities, unmet demand is minimized first. Zero production is never feasible when it fails the requested service target. No LLM or stochastic solver generates advice.

If no candidate is feasible, recommendation/comparison are null. Explanations identify the first batch multiple at/above minimum exceeding capacity and/or largest-grid full-service probability below target. Required capacity is the first weighted demand quantile meeting r, combined with minimum and rounded up to a batch multiple. It may exceed the accepted capacity bound; this describes a conflict, not an authorization for an out-of-range request. Adjustments ask the user to review capacity, minimum, batch size, target or demand with operational justification. Nothing is relaxed automatically.

## Numeric and comparison policy

Finite JSON numbers are validated first. Arithmetic and comparisons use exact `fractions.Fraction` values from decimal representations of those validated numbers. Reliability/objective comparisons use no epsilon. Fractions become JSON floats at the response boundary; ordinary binary JSON parsing and displayed precision still apply. This is not arbitrary-precision decimal input storage. Comparison deltas use exposed decimal values to avoid float subtraction artifacts such as `30.4 − 14.4 = 15.999999999999998`.

The **1e-9 probability-sum tolerance** permits input roundoff only. Weights are used unchanged, never normalized. Weighted probabilities/expectations may differ correspondingly from an exactly unit-total distribution; the response records the sum and numeric note. An exact target of 1 can be infeasible when accepted weights total slightly below 1, even at sufficient capacity. The explanation asks for weights totaling exactly 1. The tolerance never relaxes service constraints.

Ledger differences are `recommended − baseline`. The prominent potential surplus reduction uses `baseline − recommended`; negative reduction means an increase. Relative changes divide by the baseline and are null at zero/undefined denominators. Absolute probability/rate changes appear as **percentage points (pp)**; relative changes use percent. No absolute-value operator hides worsening outcomes.

## Exploration and sensitivity

Charts use API candidate values with separate surplus kg/unserved-portion axes, a full-service probability curve/target, and baseline/recommendation/feasibility markers. A baseline beyond the plotted grid is explicitly identified and retained in the ledger. The slider inspects an already returned candidate; it never mutates the optimum or assumptions.

For s>0, re-solve `Dᵢ × (1−s/100)` and `Dᵢ × (1+s/100)`, rounding **half up** to a whole portion (4.5→5, 5.5→6). Weights, portion mass, baseline, target and operational constraints remain fixed. Each shifted distribution is visible and independently checked; it may be infeasible despite a feasible original case. These are additional assumptions, not forecast validation, calibrated uncertainty or observations.

## Immutable evidence and reproduction

Save appends inputs, distribution/constraints/objective, UTC calculation time, version, input fingerprint, baseline/optimum/comparison, candidate ledger, sensitivity, notes, limitations and optional provenance to `decision_plans`. Missing explicit provenance rejects save. Preview requires no DB lookup or persistence. Retrieval/export uses frozen output across restarts instead of recalculation. Repeated saves are distinct records; no edit/delete API is exposed. SHA-256 covers canonical validated inputs and engine version, including reference ID without affecting the mathematics. This is an audit identity, not a signature; DB administrators can still modify local storage. Future algorithms require a new version and compatible access to prior snapshots.

Run `.venv/Scripts/python.exe scripts/evaluate_decisions.py` offline. It validates `data/fixtures/synthetic_decision_demo.json`, executes the engine, separately brute-forces the optimum, verifies acceptance arithmetic/repetition and writes deterministic LF JSON to `docs/evaluation/build_03_evaluation.json`. All candidates and rejection reasons are included. Expected acceptance constants appear in verification code only, never production UI output logic.

The demo produces Q=440, baseline surplus 76 portions/30.4 kg, recommended surplus 36 portions/14.4 kg, difference 40 portions/16.0 kg, and full service in every specified scenario. At a 70% target Q=400 has 12 expected unserved portions; capacity 430 at 95% is infeasible. These are verified implications of synthetic assumptions only.

## Limitations and prospective validation

The model omits nutrition, food safety, preparation timing, staffing, shared capacity, inventory, substitutions, costs, emissions, donation eligibility and disposal decisions. Fixed portion mass may approximate reality poorly; probabilities are not automatically estimated/calibrated. Mathematical optimality within this model does not establish an effective kitchen policy.

Before impact claims, co-design constraints with staff and collect timestamped planned/actual preparation, portion mass, meals served, unmet demand/turn-aways, substitutions, edible surplus, reuse/donation/disposal and comparable waste measurements. Predeclare a prospective comparison design with service outcomes and confounder handling. Future demand models need pre-service input availability, chronological baseline-only selection and new external/prospective validation. Do not tune on the already reported intervention holdout or attribute the original study's intervention to MealLoop OS. Impact Ledger provides separate operational accounting, and public-demo access is isolated and read-only. Neither establishes a real pilot or impact.
