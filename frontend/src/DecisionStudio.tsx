import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowDownToLine,
  ArrowRight,
  CheckCircle2,
  FlaskConical,
  Info,
  LoaderCircle,
  Plus,
  RefreshCw,
  Save,
  Scale,
  Trash2,
} from "lucide-react";
import { api } from "./api";
import { useRuntime } from "./runtime";
import type { Batch } from "./types";
import type { ModelStatus } from "./forecastTypes";
import type {
  DecisionMetadata,
  DecisionRequest,
  DecisionResult,
  PlanSummary,
  SavedDecision,
} from "./decisionTypes";
import "./decision.css";

const fmt = (n: number | null | undefined, d = 2) =>
  n == null
    ? "—"
    : n.toLocaleString("en-US", {
        minimumFractionDigits: d,
        maximumFractionDigits: d,
      });
const pct = (n: number | null | undefined) =>
  n == null ? "—" : `${fmt(n * 100)}%`;
function tomorrow() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
type Draft = {
  planning_date: string;
  title: string;
  menu: string;
  scenario_kind: "synthetic_demo" | "user_assumptions";
  baseline_portions: string;
  portion_mass_g: string;
  batch_increment: string;
  maximum_capacity: string;
  minimum_portions: string;
  reliability_percent: string;
  sensitivity_percent: string;
  context_batch_id: number | null;
  scenarios: { name: string; demand: string; probability: string }[];
};
const blank = (): Draft => ({
  planning_date: tomorrow(),
  title: "",
  menu: "",
  scenario_kind: "user_assumptions",
  baseline_portions: "",
  portion_mass_g: "",
  batch_increment: "10",
  maximum_capacity: "",
  minimum_portions: "0",
  reliability_percent: "95",
  sensitivity_percent: "10",
  context_batch_id: null,
  scenarios: [],
});
const toDraft = (r: DecisionRequest): Draft => ({
  planning_date: r.planning_date,
  title: r.title,
  menu: r.menu?.toString() || "",
  scenario_kind: r.scenario_kind,
  baseline_portions: String(r.baseline_portions),
  portion_mass_g: String(r.portion_mass_g),
  batch_increment: String(r.batch_increment),
  maximum_capacity: String(r.maximum_capacity),
  minimum_portions: String(r.minimum_portions),
  reliability_percent: String(r.reliability_target * 100),
  sensitivity_percent: String(r.sensitivity_percent),
  context_batch_id: r.context_batch_id,
  scenarios: r.demand_scenarios.map((s) => ({
    name: s.name,
    demand: String(s.demand_portions),
    probability: String(s.probability),
  })),
});
function numeric(value: string, label: string, integer = false) {
  if (!value.trim()) throw new Error(`${label} is required.`);
  const n = Number(value);
  if (!Number.isFinite(n) || (integer && !/^\d+$/.test(value)))
    throw new Error(
      `${label} must be a finite ${integer ? "nonnegative integer" : "number"}.`,
    );
  return n;
}
function toRequest(d: Draft): DecisionRequest {
  return {
    planning_date: d.planning_date,
    title: d.title,
    menu: d.menu ? numeric(d.menu, "Menu", true) : null,
    scenario_kind: d.scenario_kind,
    baseline_portions: numeric(d.baseline_portions, "Existing plan", true),
    portion_mass_g: numeric(d.portion_mass_g, "Portion mass"),
    batch_increment: numeric(d.batch_increment, "Batch increment", true),
    maximum_capacity: numeric(d.maximum_capacity, "Capacity", true),
    minimum_portions: numeric(d.minimum_portions, "Minimum production", true),
    reliability_target:
      numeric(d.reliability_percent, "Reliability target") / 100,
    sensitivity_percent: numeric(d.sensitivity_percent, "Sensitivity shift"),
    context_batch_id: d.context_batch_id,
    demand_scenarios: d.scenarios.map((s) => ({
      name: s.name,
      demand_portions: numeric(
        s.demand,
        `Demand for ${s.name || "unnamed scenario"}`,
        true,
      ),
      probability: numeric(
        s.probability,
        `Probability for ${s.name || "unnamed scenario"}`,
      ),
    })),
  };
}
function Card({
  title,
  eyebrow,
  action,
  children,
  className = "",
}: {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <h2>{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export default function DecisionStudio({
  batch,
  demoStart = false,
}: {
  batch: Batch | null;
  demoStart?: boolean;
}) {
  const publicDemo = useRuntime().read_only;
  const [draft, setDraft] = useState<Draft>(blank),
    [metadata, setMetadata] = useState<DecisionMetadata | null>(null);
  const [result, setResult] = useState<DecisionResult | null>(null),
    [saved, setSaved] = useState<SavedDecision | null>(null);
  const [busy, setBusy] = useState(false),
    [saving, setSaving] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [plans, setPlans] = useState<PlanSummary[]>([]),
    [historyError, setHistoryError] = useState(""),
    [historyBusy, setHistoryBusy] = useState(false),
    [offset, setOffset] = useState(0);
  const [modelContext, setModelContext] = useState<ModelStatus | null>(null),
    [contextError, setContextError] = useState(false);
  const generation = useRef(0);
  const disabled = busy || saving;
  async function loadMetadata() {
    try {
      setMetadata(await api<DecisionMetadata>("/decisions/metadata"));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function loadPlans(next = 0) {
    setHistoryBusy(true);
    setHistoryError("");
    try {
      const p = await api<PlanSummary[]>(
        `/decisions/plans?limit=10&offset=${next}`,
      );
      setPlans(p);
      setOffset(next);
    } catch (e) {
      setHistoryError((e as Error).message);
    } finally {
      setHistoryBusy(false);
    }
  }
  useEffect(() => {
    void loadMetadata();
    void loadPlans();
    if (demoStart || publicDemo) void demo();
  }, []);
  useEffect(() => {
    let active = true;
    setModelContext(null);
    setContextError(false);
    if (batch)
      api<ModelStatus>(`/models/status?batch_id=${batch.id}`)
        .then((s) => {
          if (active) setModelContext(s);
        })
        .catch(() => {
          if (active) setContextError(true);
        });
    return () => {
      active = false;
    };
  }, [batch?.id]);
  function edit(next: Draft) {
    generation.current++;
    setDraft(next);
    setResult(null);
    setSaved(null);
    setError("");
    setNotice("");
  }
  async function demo() {
    setBusy(true);
    setError("");
    try {
      const r = await api<DecisionRequest>("/decisions/demo");
      edit(toDraft(r));
      setNotice(
        "SYNTHETIC DEMO SCENARIO loaded. Every demand, weight, and plan is illustrative and editable. Run optimization to calculate results.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function calculate(e: FormEvent) {
    e.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    const token = ++generation.current;
    try {
      const request = toRequest(draft);
      if (!request.demand_scenarios.length)
        throw new Error("Add at least one possible demand scenario.");
      const next = await api<DecisionResult>("/decisions/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      if (token === generation.current) {
        setResult(next);
        setSaved(null);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (!result) return;
    setSaving(true);
    setError("");
    try {
      const next = await api<SavedDecision>("/decisions/plans", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(result.inputs),
      });
      setSaved(next);
      setResult(next.result);
      setNotice(
        `Saved immutable assumption-based plan #${next.id}. Editing inputs creates a new calculation; this snapshot stays unchanged.`,
      );
      await loadPlans();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function openPlan(id: number) {
    setBusy(true);
    setError("");
    try {
      const next = await api<SavedDecision>(`/decisions/plans/${id}`);
      setDraft(toDraft(next.inputs));
      setSaved(next);
      setResult(next.result);
      setNotice(
        `Loaded saved plan #${id} · ${next.engine_version}. This is an immutable calculation snapshot, not a measurement.`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const total = draft.scenarios.reduce(
    (sum, s) => sum + (Number(s.probability) || 0),
    0,
  );
  const field = (key: keyof Draft, value: string) =>
    edit({ ...draft, [key]: value });
  return (
    <div className="decision-studio">
      <div className="decision-evidence-banner">
        <span className="decision-symbol">
          <Scale size={24} />
        </span>
        <div>
          <strong>ASSUMPTION-BASED SCENARIO</strong>
          <p>
            Explore preparation quantities under your possible demand levels.
            These calculations are separate from measured food waste and
            historical forecasts.
          </p>
        </div>
        <span className="badge decision-badge">
          {draft.scenario_kind === "synthetic_demo"
            ? "SYNTHETIC DEMO SCENARIO"
            : "USER-SPECIFIED ASSUMPTIONS"}
        </span>
      </div>
      <div className="decision-toolbar">
        <p>One menu. One service. A transparent, bounded optimization.</p>
        <div>
          <button
            className="button"
            disabled={disabled}
            onClick={() => {
              edit(blank());
              setNotice(
                "Blank assumption editor ready. Enter your planning inputs.",
              );
            }}
          >
            Start blank
          </button>
          <button
            className="button primary"
            disabled={disabled}
            onClick={() => void demo()}
          >
            <FlaskConical size={15} /> Load synthetic demo
          </button>
        </div>
      </div>
      {notice && (
        <div className="notice" role="status">
          <CheckCircle2 size={16} />
          <span>{notice}</span>
          <button
            className="icon-button"
            aria-label="Dismiss planning notification"
            onClick={() => setNotice("")}
          >
            <span>×</span>
          </button>
        </div>
      )}
      <form onSubmit={calculate} className="decision-form">
        <fieldset disabled={disabled}>
          <div className="decision-input-grid">
            <Card
              title="Service & production plan"
              eyebrow="YOUR EDITABLE ASSUMPTIONS"
            >
              <div className="decision-fields">
                <label className="field" htmlFor="decision-date">
                  Planning date
                  <input
                    id="decision-date"
                    type="date"
                    min="2000-01-01"
                    max="2100-12-31"
                    required
                    value={draft.planning_date}
                    onChange={(e) => field("planning_date", e.target.value)}
                  />
                </label>
                <label className="field" htmlFor="decision-menu">
                  Menu identifier <span className="muted">optional</span>
                  <input
                    id="decision-menu"
                    type="number"
                    min="1"
                    max="10000"
                    step="1"
                    placeholder="e.g. 1"
                    value={draft.menu}
                    onChange={(e) => field("menu", e.target.value)}
                  />
                </label>
                <label className="field decision-full" htmlFor="decision-title">
                  Scenario title <span className="muted">optional</span>
                  <input
                    id="decision-title"
                    maxLength={100}
                    placeholder="A name for this hypothetical plan"
                    value={draft.title}
                    onChange={(e) => field("title", e.target.value)}
                  />
                </label>
                <label className="field" htmlFor="decision-baseline">
                  Existing prepared portions
                  <input
                    id="decision-baseline"
                    type="number"
                    min="0"
                    max="100000"
                    step="1"
                    required
                    value={draft.baseline_portions}
                    onChange={(e) => field("baseline_portions", e.target.value)}
                  />
                </label>
                <label className="field" htmlFor="decision-mass">
                  Portion mass · grams
                  <input
                    id="decision-mass"
                    type="number"
                    min="0.000001"
                    max="10000"
                    step="any"
                    required
                    value={draft.portion_mass_g}
                    onChange={(e) => field("portion_mass_g", e.target.value)}
                  />
                </label>
                <label className="field" htmlFor="decision-batch">
                  Production batch increment
                  <input
                    id="decision-batch"
                    type="number"
                    min="1"
                    max="10000"
                    step="1"
                    required
                    value={draft.batch_increment}
                    onChange={(e) => field("batch_increment", e.target.value)}
                  />
                </label>
                <label className="field" htmlFor="decision-capacity">
                  Maximum capacity · portions
                  <input
                    id="decision-capacity"
                    type="number"
                    min="0"
                    max="10000"
                    step="1"
                    required
                    value={draft.maximum_capacity}
                    onChange={(e) => field("maximum_capacity", e.target.value)}
                  />
                </label>
                <label className="field" htmlFor="decision-minimum">
                  Minimum production · portions
                  <input
                    id="decision-minimum"
                    type="number"
                    min="0"
                    max="10000"
                    step="1"
                    required
                    value={draft.minimum_portions}
                    onChange={(e) => field("minimum_portions", e.target.value)}
                  />
                </label>
              </div>
              <p className="field-help">
                The existing plan is a comparator. It can violate the new
                constraints; those violations will be identified rather than
                hidden.
              </p>
            </Card>
            <Card
              title="Service objective & sensitivity"
              eyebrow="CONSTRAINTS STAY EXPLICIT"
            >
              <label className="field" htmlFor="decision-reliability">
                Minimum full-service reliability · %{" "}
                <span title="Sum of scenario probabilities fully served; not real-world confidence.">
                  <Info size={12} />
                </span>
                <input
                  id="decision-reliability"
                  type="number"
                  min="0"
                  max="100"
                  step="any"
                  required
                  value={draft.reliability_percent}
                  onChange={(e) => field("reliability_percent", e.target.value)}
                />
              </label>
              <p className="field-help">
                Illustrative default: 95%. This is conditional on your specified
                demand scenarios, not a calibrated real-world guarantee.
              </p>
              <label className="field" htmlFor="decision-sensitivity">
                Additional demand shift · ± %
                <input
                  id="decision-sensitivity"
                  type="number"
                  min="0"
                  max="50"
                  step="any"
                  required
                  value={draft.sensitivity_percent}
                  onChange={(e) => field("sensitivity_percent", e.target.value)}
                />
              </label>
              <p className="field-help">
                Re-solve after shifting possible demand up/down, rounded half up
                to integer portions. Zero disables extra cases. This tests
                assumptions, not forecast accuracy.
              </p>
              <div className="decision-rule">
                <Scale size={20} />
                <p>
                  Minimize modeled expected surplus while meeting the service
                  target, batch size, minimum quantity, and capacity. No
                  automatic constraint relaxation.
                </p>
              </div>
              {batch && (
                <label className="context-checkbox">
                  <input
                    type="checkbox"
                    checked={draft.context_batch_id !== null}
                    onChange={(e) =>
                      edit({
                        ...draft,
                        context_batch_id: e.target.checked ? batch.id : null,
                      })
                    }
                  />
                  <span>
                    Attach historical batch #
                    {draft.context_batch_id ?? batch.id} as a reference only. It
                    does not supply demand assumptions.
                  </span>
                </label>
              )}
            </Card>
          </div>
          <Card
            title="Possible demand scenarios"
            eyebrow="A FINITE DISTRIBUTION YOU SPECIFY"
            action={
              <button
                type="button"
                className="button small"
                disabled={
                  draft.scenarios.length >=
                  (metadata?.limits.maximum_scenarios ?? 30)
                }
                onClick={() =>
                  edit({
                    ...draft,
                    scenarios: [
                      ...draft.scenarios,
                      {
                        name: `Scenario ${draft.scenarios.length + 1}`,
                        demand: "",
                        probability: "",
                      },
                    ],
                  })
                }
              >
                <Plus size={14} /> Add demand scenario
              </button>
            }
          >
            {!draft.scenarios.length ? (
              <div className="decision-demand-empty">
                <FlaskConical size={24} />
                <p>
                  No possible demand levels yet. Add a scenario or explicitly
                  load the synthetic demo.
                </p>
              </div>
            ) : (
              <div className="demand-editor">
                {draft.scenarios.map((s, i) => (
                  <div className="demand-editor-row" key={i}>
                    <label className="field" htmlFor={`demand-name-${i}`}>
                      Scenario {i + 1} name
                      <input
                        id={`demand-name-${i}`}
                        aria-label={`Scenario ${i + 1} name`}
                        maxLength={60}
                        required
                        value={s.name}
                        onChange={(e) =>
                          edit({
                            ...draft,
                            scenarios: draft.scenarios.map((x, j) =>
                              j === i ? { ...x, name: e.target.value } : x,
                            ),
                          })
                        }
                      />
                    </label>
                    <label className="field" htmlFor={`demand-quantity-${i}`}>
                      Possible demand · portions
                      <input
                        id={`demand-quantity-${i}`}
                        aria-label={`Scenario ${i + 1} demand`}
                        type="number"
                        min="0"
                        max="100000"
                        step="1"
                        required
                        value={s.demand}
                        onChange={(e) =>
                          edit({
                            ...draft,
                            scenarios: draft.scenarios.map((x, j) =>
                              j === i ? { ...x, demand: e.target.value } : x,
                            ),
                          })
                        }
                      />
                    </label>
                    <label className="field" htmlFor={`demand-prob-${i}`}>
                      Probability · 0 to 1
                      <input
                        id={`demand-prob-${i}`}
                        aria-label={`Scenario ${i + 1} probability`}
                        type="number"
                        min="0"
                        max="1"
                        step="any"
                        required
                        value={s.probability}
                        onChange={(e) =>
                          edit({
                            ...draft,
                            scenarios: draft.scenarios.map((x, j) =>
                              j === i
                                ? { ...x, probability: e.target.value }
                                : x,
                            ),
                          })
                        }
                      />
                    </label>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Remove demand scenario ${i + 1}`}
                      onClick={() =>
                        edit({
                          ...draft,
                          scenarios: draft.scenarios.filter((_, j) => i !== j),
                        })
                      }
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div
              className={`probability-total ${Math.abs(total - 1) <= 1e-9 ? "valid" : "invalid"}`}
              aria-live="polite"
            >
              <strong>Probability total: {fmt(total, 6)}</strong>
              <span>
                Must equal 1 within 1e-9. Incorrect totals are rejected; weights
                are never normalized.
              </span>
            </div>
          </Card>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
          <div className="decision-run-bar">
            <span>
              {metadata
                ? `${metadata.engine_version} · up to ${metadata.limits.maximum_candidates.toLocaleString("en-US")} batch candidates`
                : "The server validates all bounds before optimization."}
            </span>
            <button className="button primary" type="submit">
              {busy ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Scale size={16} />
              )}{" "}
              {busy ? "Enumerating feasible quantities…" : "Run optimization"}
            </button>
          </div>
        </fieldset>
      </form>
      {result ? (
        <>
          <div className="decision-result-toolbar">
            <div>
              <span className="badge decision-badge">
                ASSUMPTION-BASED RESULT
              </span>
              <p>
                {result.inputs.title || "Untitled planning scenario"} ·{" "}
                {result.inputs.planning_date} · {result.engine_version}
              </p>
            </div>
            <div>
              {!publicDemo && (
                <button
                  className="button"
                  disabled={disabled}
                  onClick={() => void save()}
                >
                  {saving ? (
                    <LoaderCircle className="spin" size={15} />
                  ) : (
                    <Save size={15} />
                  )}{" "}
                  {saved ? `Save another snapshot` : "Save plan snapshot"}
                </button>
              )}
              {publicDemo && (
                <p className="field-help">
                  Preview only · saving and exports require a local workspace.
                </p>
              )}
              {saved && !publicDemo && (
                <>
                  <a
                    className="button small"
                    download
                    href={`/api/decisions/plans/${saved.id}/export?format=json`}
                  >
                    <ArrowDownToLine size={13} /> JSON
                  </a>
                  <a
                    className="button small"
                    download
                    href={`/api/decisions/plans/${saved.id}/export?format=csv`}
                  >
                    <ArrowDownToLine size={13} /> CSV
                  </a>
                </>
              )}
            </div>
          </div>
          <Results
            result={result}
            labels={metadata?.rejection_reason_labels ?? {}}
          />
          {saved && (
            <p className="decision-snapshot-note">
              Saved plan #{saved.id} ·{" "}
              {new Date(saved.created_at).toLocaleString("en-GB")} · immutable
              input fingerprint <code>{saved.input_fingerprint}</code>
              {saved.context_reference &&
                ` · Reference batch #${saved.context_reference.batch_id}: ${saved.context_reference.source_title}. ${saved.context_reference.role}`}
            </p>
          )}
        </>
      ) : (
        <Card title="Ready for a transparent calculation">
          <div className="decision-result-empty">
            <Scale size={28} />
            <h3>Your assumptions, a verifiable plan.</h3>
            <p>
              Enter inputs and run optimization. Editing any input clears
              previous results so an old recommendation cannot appear current.
            </p>
          </div>
        </Card>
      )}
      <Card
        title={
          publicDemo ? "Prepared synthetic example" : "Saved planning scenarios"
        }
        eyebrow="IMMUTABLE ASSUMPTION SNAPSHOTS"
        action={
          <button
            className="text-button"
            disabled={historyBusy || disabled}
            onClick={() => void loadPlans(offset)}
          >
            <RefreshCw size={13} /> Refresh plans
          </button>
        }
      >
        {historyBusy ? (
          <p className="panel-message" role="status">
            Loading saved plans…
          </p>
        ) : historyError ? (
          <div className="form-error" role="alert">
            {historyError}
            <button
              className="button small"
              onClick={() => void loadPlans(offset)}
            >
              Retry history
            </button>
          </div>
        ) : !plans.length ? (
          <p className="panel-message">
            {offset
              ? "No more plans on this page."
              : "No saved planning scenarios yet. Run a calculation and save its snapshot."}
          </p>
        ) : (
          <div className="saved-decision-list">
            {plans.map((p) => (
              <button
                className="saved-decision-item"
                disabled={disabled}
                onClick={() => void openPlan(p.id)}
                key={p.id}
              >
                <span className="decision-symbol">
                  <Scale size={18} />
                </span>
                <div>
                  <strong>
                    #{p.id} · {p.title || "Untitled scenario"}
                  </strong>
                  <p>
                    {p.planning_date} ·{" "}
                    {p.scenario_kind === "synthetic_demo"
                      ? "SYNTHETIC DEMO"
                      : "USER ASSUMPTIONS"}{" "}
                    · {p.baseline_portions} →{" "}
                    {p.recommended_portions ?? "No feasible plan"} portions ·{" "}
                    {p.engine_version}
                  </p>
                </div>
                <ArrowRight size={16} />
              </button>
            ))}
          </div>
        )}
        <div className="pagination">
          <span>
            Showing saved plans {plans.length ? offset + 1 : 0}–
            {offset + plans.length} · assumption-based only
          </span>
          <div>
            <button
              className="button small"
              disabled={!offset || historyBusy || disabled}
              onClick={() => void loadPlans(Math.max(0, offset - 10))}
            >
              Previous plans
            </button>
            <button
              className="button small"
              disabled={plans.length < 10 || historyBusy || disabled}
              onClick={() => void loadPlans(offset + 10)}
            >
              Next plans
            </button>
          </div>
        </div>
      </Card>
      <Card
        title="Evidence boundaries & historical context"
        eyebrow="MEASUREMENTS REMAIN SEPARATE"
      >
        <div className="decision-context-grid">
          <div>
            <span className="badge">HISTORICAL CONTEXT ONLY</span>
            <h3>
              {batch ? batch.source.title : "No historical dataset selected"}
            </h3>
            <p>
              {batch
                ? `${batch.row_count} imported records · source kind: ${batch.source.kind}.`
                : "Decision Studio runs from complete assumptions without importing data or preparing a forecasting model."}
            </p>
            <p>
              {contextError
                ? "Forecast context is unavailable. This does not affect scenario calculations."
                : modelContext?.metadata
                  ? `Forecast Lab method: ${modelContext.metadata.selected_label}. Training through ${modelContext.metadata.production_training.end_date}.`
                  : modelContext?.reason || "No forecasting model is required."}
            </p>
            <p>
              This context is read-only. Waste rates and historical diner counts
              never become production quantities or future demand here.
            </p>
          </div>
          <div>
            <span className="badge decision-badge">
              ASSUMPTION-BASED SCENARIO
            </span>
            <p>
              Prepared portions, possible demand, probability weights, portion
              mass, and service constraints come from the editor. Modeled edible
              surplus is potentially at risk of waste; it is not automatically
              discarded.
            </p>
            <p>
              Do not add modeled surplus to historical kitchen/serving waste or
              claim the difference as verified food-waste prevention.
            </p>
            <p>
              To establish operational impact, collect actual preparation,
              demand/turn-aways, edible surplus disposition, and service
              outcomes under a prospective evaluation.
            </p>
          </div>
        </div>
        <details className="technical-details">
          <summary>Algorithm, bounds & scientific limitations</summary>
          {metadata ? (
            <>
              <p>{metadata.objective}</p>
              <p>Tie break: {metadata.tie_break}</p>
              <p>{metadata.probability_policy}</p>
              <p>{metadata.zero_demand_policy}</p>
              <p>{metadata.sensitivity_rounding}</p>
              <p>
                Input bounds: {metadata.limits.maximum_scenarios} demand
                scenarios,{" "}
                {metadata.limits.maximum_demand.toLocaleString("en-US")} demand
                portions,{" "}
                {metadata.limits.maximum_capacity.toLocaleString("en-US")}{" "}
                preparation capacity,{" "}
                {metadata.limits.maximum_candidates.toLocaleString("en-US")}{" "}
                candidates; 64 KiB request body.
              </p>
              {metadata.assumptions_and_limitations.map((l) => (
                <p key={l}>{l}</p>
              ))}
            </>
          ) : (
            <button
              className="button small"
              onClick={() => void loadMetadata()}
            >
              Load calculation metadata
            </button>
          )}
        </details>
      </Card>
    </div>
  );
}

function Results({
  result: r,
  labels,
}: {
  result: DecisionResult;
  labels: Record<string, string>;
}) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    setIndex(
      Math.max(
        0,
        r.candidates.findIndex(
          (c) =>
            c.quantity ===
            (r.recommended?.quantity ?? r.feasibility.maximum_grid_quantity),
        ),
      ),
    );
  }, [r]);
  const inspected = r.candidates[Math.min(index, r.candidates.length - 1)];
  const rec = r.recommended,
    comparison = r.comparison;
  const chart = r.candidates.map((c) => ({
    ...c,
    feasible_surplus: c.feasible ? c.expected_surplus_kg : null,
    infeasible_surplus: c.feasible ? null : c.expected_surplus_kg,
  }));
  const rows: [string, string, (v: number | null | undefined) => string][] = [
    ["quantity", "Prepared portions", (n) => fmt(n, 0)],
    ["expected_surplus_portions", "Modeled surplus · portions", (n) => fmt(n)],
    ["expected_surplus_kg", "Modeled expected surplus · kg", (n) => fmt(n)],
    [
      "expected_unmet_portions",
      "Expected unserved demand · portions",
      (n) => fmt(n),
    ],
    [
      "probability_fully_served",
      "Scenario-conditional full-service reliability",
      pct,
    ],
    ["expected_fill_rate", "Expected demand fulfillment", pct],
    ["capacity_use", "Capacity use", pct],
  ];
  return (
    <div className="decision-results">
      {r.status === "infeasible" ? (
        <div className="caution decision-infeasible" role="status">
          <Info size={23} />
          <div>
            <strong>
              No feasible production plan under the selected constraints.
            </strong>
            {r.feasibility.issues.map((issue) => (
              <div key={issue.code}>
                <p>{issue.message}</p>
                <ul>
                  {issue.adjustments_to_consider.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="decision-feasible">
          <CheckCircle2 size={17} />
          <span>
            {r.feasibility.feasible_candidates} feasible quantities out of{" "}
            {r.candidates.length} batch candidates. All configured constraints
            are met by the selected plan.
          </span>
        </div>
      )}
      <div className="decision-metric-grid">
        <section className="metric-card featured">
          <p className="eyebrow">RECOMMENDED UNDER THESE ASSUMPTIONS</p>
          <div className="metric-value">
            {fmt(rec?.quantity, 0)}
            <span>portions</span>
          </div>
          <p>
            {rec
              ? "Exact objective minimum with deterministic tie-breaking."
              : "Resolve conflicting constraints and rerun."}
          </p>
        </section>
        <section className="metric-card">
          <p className="eyebrow">MODELED EXPECTED SURPLUS</p>
          <div className="metric-value">
            {fmt(rec?.expected_surplus_kg)}
            <span>kg</span>
          </div>
          <p>Potentially at risk of waste; not measured discard.</p>
        </section>
        <section className="metric-card">
          <p className="eyebrow">POTENTIAL REDUCTION IN MODELED SURPLUS</p>
          <div className="metric-value">
            {fmt(comparison?.potential_surplus_reduction_kg)}
            <span>kg</span>
          </div>
          <p>
            {comparison
              ? `${comparison.relative_surplus_reduction == null ? "Relative reduction undefined: zero baseline surplus." : `${pct(comparison.relative_surplus_reduction)} of modeled baseline surplus.`} Negative means an increase.`
              : "No comparison without a feasible recommendation."}
          </p>
        </section>
        <section className="metric-card">
          <p className="eyebrow">SCENARIO-CONDITIONAL SERVICE RELIABILITY</p>
          <div className="metric-value">
            {pct(rec?.probability_fully_served)}
          </div>
          <p>Not a calibrated real-world confidence guarantee.</p>
        </section>
      </div>
      <Card
        title="Existing plan vs constrained optimum"
        eyebrow="SAME DEMAND ASSUMPTIONS · SAME ENGINE"
        action={<span className="subtle-tag">Assumption-based comparison</span>}
      >
        {!r.baseline.feasible && (
          <div className="caution">
            <Info size={17} />
            <div>
              <strong>The existing plan violates selected constraints.</strong>
              <p>
                {r.baseline.rejection_reasons
                  .map(
                    (reason) => labels[reason] || reason.replaceAll("_", " "),
                  )
                  .join(" ")}
              </p>
            </div>
          </div>
        )}
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Metric</th>
                <th>Existing plan</th>
                <th>Recommended</th>
                <th>Difference · recommended − baseline</th>
                <th>Relative change</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([key, label, format]) => {
                const delta = comparison?.metrics[key];
                return (
                  <tr key={key}>
                    <td>{label}</td>
                    <td>
                      {format(
                        r.baseline[key as keyof typeof r.baseline] as
                          number | null,
                      )}
                    </td>
                    <td>
                      {format(
                        rec?.[key as keyof typeof rec] as number | undefined,
                      )}
                    </td>
                    <td>
                      {format === pct &&
                      delta?.difference_recommended_minus_baseline != null
                        ? `${fmt(delta.difference_recommended_minus_baseline * 100)} pp`
                        : format(delta?.difference_recommended_minus_baseline)}
                    </td>
                    <td>{pct(delta?.relative_change)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="chart-footnote">
          Unit differences are signed; pp means percentage points. Relative
          changes use the baseline denominator and are unavailable when it is
          zero. No result is a claim of actual prevented waste.{" "}
          {r.baseline.zero_expected_demand
            ? "Expected demand is zero; fulfillment is 100% by explicit no-demand convention."
            : ""}
        </p>
        <details className="decision-outcomes">
          <summary>Per-demand outcome audit</summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Assumed demand</th>
                  <th>Weight</th>
                  <th>Existing surplus</th>
                  <th>Existing unmet</th>
                  <th>Recommended surplus</th>
                  <th>Recommended unmet</th>
                </tr>
              </thead>
              <tbody>
                {r.baseline.outcomes.map((o, i) => (
                  <tr key={o.name}>
                    <td>
                      {o.name} · {o.demand_portions} portions
                    </td>
                    <td>{fmt(o.probability, 6)}</td>
                    <td>{o.surplus_portions}</td>
                    <td>{o.unmet_portions}</td>
                    <td>{rec?.outcomes[i].surplus_portions ?? "—"}</td>
                    <td>{rec?.outcomes[i].unmet_portions ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </Card>
      <Card
        title="Production trade-off explorer"
        eyebrow="INSPECT THE EXACT ENUMERATED GRID"
      >
        <div className="decision-chart-legend">
          <span>
            <i className="legend-dot plate" />
            Modeled surplus · kg
          </span>
          <span>
            <i className="decision-amber-dot" />
            Unserved demand · portions
          </span>
          <span>
            <i className="decision-feasible-dot" />
            Feasible
          </span>
          <span>
            <i className="decision-rejected-dot" />
            Infeasible
          </span>
        </div>
        <div
          className="decision-trade-chart"
          role="img"
          aria-label="Modeled surplus and unserved demand by production quantity; exact values are available in the candidate ledger."
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={chart}
              margin={{ left: 0, right: 0, top: 14, bottom: 0 }}
            >
              <CartesianGrid
                vertical={false}
                strokeDasharray="3 5"
                stroke="#e9ece5"
              />
              <XAxis
                type="number"
                dataKey="quantity"
                domain={[0, Math.max(1, r.feasibility.maximum_grid_quantity)]}
                tick={{ fontSize: 10 }}
              />
              <YAxis
                yAxisId="surplus"
                tick={{ fontSize: 10 }}
                width={42}
                label={{
                  value: "Surplus kg",
                  angle: -90,
                  position: "insideLeft",
                  fill: "#80906d",
                  fontSize: 10,
                }}
              />
              <YAxis
                yAxisId="unmet"
                orientation="right"
                tick={{ fontSize: 10 }}
                width={45}
                label={{
                  value: "Unserved portions",
                  angle: 90,
                  position: "insideRight",
                  fill: "#a58e62",
                  fontSize: 10,
                }}
              />
              <Tooltip
                labelFormatter={(v) => `${v} prepared portions`}
                formatter={(v, n) => [fmt(Number(v)), String(n)]}
                contentStyle={{
                  borderRadius: 9,
                  fontSize: 11,
                  border: "1px solid #e5e8df",
                }}
              />
              <Line
                yAxisId="surplus"
                name="Modeled expected surplus · kg"
                dataKey="expected_surplus_kg"
                stroke="#789462"
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
              />
              <Line
                yAxisId="unmet"
                name="Expected unserved · portions"
                dataKey="expected_unmet_portions"
                stroke="#b89154"
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
              />
              <Scatter
                yAxisId="surplus"
                name="Feasible surplus · kg"
                dataKey="feasible_surplus"
                fill="#557b44"
                isAnimationActive={false}
              />
              <Scatter
                yAxisId="surplus"
                name="Infeasible surplus · kg"
                dataKey="infeasible_surplus"
                fill="#bac3b0"
                isAnimationActive={false}
              />
              {r.baseline.quantity <= r.feasibility.maximum_grid_quantity && (
                <ReferenceLine
                  yAxisId="surplus"
                  x={r.baseline.quantity}
                  stroke="#7f99ac"
                  strokeDasharray="4 3"
                  label={{ value: "Existing", fill: "#7f99ac", fontSize: 10 }}
                />
              )}
              {rec && (
                <ReferenceLine
                  yAxisId="surplus"
                  x={rec.quantity}
                  stroke="#527446"
                  label={{
                    value: "Recommended",
                    fill: "#527446",
                    fontSize: 10,
                  }}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div
          className="decision-reliability-chart"
          role="img"
          aria-label="Scenario-conditional full-service reliability, with the required threshold."
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={chart}
              margin={{ left: 0, right: 45, top: 12, bottom: 0 }}
            >
              <CartesianGrid
                vertical={false}
                strokeDasharray="3 5"
                stroke="#e9ece5"
              />
              <XAxis
                type="number"
                dataKey="quantity"
                domain={[0, Math.max(1, r.feasibility.maximum_grid_quantity)]}
                tick={{ fontSize: 10 }}
              />
              <YAxis
                domain={[0, 1]}
                tickFormatter={(v) => `${Math.round(v * 100)}%`}
                tick={{ fontSize: 10 }}
                width={42}
              />
              <Tooltip
                labelFormatter={(v) => `${v} prepared portions`}
                formatter={(v) => [
                  pct(Number(v)),
                  "Scenario-conditional full-service reliability",
                ]}
                contentStyle={{ borderRadius: 9, fontSize: 11 }}
              />
              <Line
                name="Full-service reliability"
                dataKey="probability_fully_served"
                type="stepAfter"
                stroke="#819c66"
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
              />
              <ReferenceLine
                y={r.inputs.reliability_target}
                stroke="#b18d55"
                strokeDasharray="4 4"
                label={{
                  value: `Target ${pct(r.inputs.reliability_target)}`,
                  position: "insideTopLeft",
                  fontSize: 10,
                  fill: "#a78c5e",
                }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        {r.baseline.quantity > r.feasibility.maximum_grid_quantity && (
          <p className="scientific-note">
            The existing plan is above the plotted capacity grid. Its exact
            results and constraint violation remain in the comparison.
          </p>
        )}
        <div className="quantity-inspector">
          <label htmlFor="decision-q-slider">
            Explore production quantity:{" "}
            <strong>{inspected.quantity} portions</strong> ·{" "}
            <span
              className={
                inspected.feasible
                  ? "inspection-feasible"
                  : "inspection-infeasible"
              }
            >
              {inspected.feasible
                ? "Feasible under assumptions"
                : "Infeasible under selected constraints"}
            </span>
          </label>
          <input
            id="decision-q-slider"
            aria-label="Explore production quantity"
            type="range"
            min="0"
            max={Math.max(0, r.candidates.length - 1)}
            step="1"
            value={Math.min(index, r.candidates.length - 1)}
            onChange={(e) => setIndex(Number(e.target.value))}
          />
          <div className="inspector-metrics">
            <span>
              Modeled surplus{" "}
              <strong>{fmt(inspected.expected_surplus_kg)} kg</strong>
            </span>
            <span>
              Unserved demand{" "}
              <strong>{fmt(inspected.expected_unmet_portions)} portions</strong>
            </span>
            <span>
              Full-service reliability{" "}
              <strong>{pct(inspected.probability_fully_served)}</strong>
            </span>
          </div>
          {!inspected.feasible && (
            <p>
              {inspected.rejection_reasons
                .map((reason) => labels[reason] || reason)
                .join(" ")}
            </p>
          )}
          <p>
            Exploration only. The slider does not change the optimized
            recommendation or saved assumptions.
          </p>
        </div>
        <details className="decision-outcomes">
          <summary>
            All candidate quantities, feasibility & rejection reasons
          </summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Q</th>
                  <th>Surplus kg</th>
                  <th>Unserved portions</th>
                  <th>Full-service reliability</th>
                  <th>Feasible</th>
                  <th>Rejected because</th>
                </tr>
              </thead>
              <tbody>
                {r.candidates.map((c) => (
                  <tr key={c.quantity}>
                    <td>{c.quantity}</td>
                    <td>{fmt(c.expected_surplus_kg, 4)}</td>
                    <td>{fmt(c.expected_unmet_portions, 4)}</td>
                    <td>{pct(c.probability_fully_served)}</td>
                    <td>{c.feasible ? "Yes" : "No"}</td>
                    <td>
                      {c.rejection_reasons
                        .map((reason) => labels[reason] || reason)
                        .join(" ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </Card>
      <Card
        title="Demand sensitivity"
        eyebrow="ADDITIONAL ASSUMPTIONS · NOT FORECAST VALIDATION"
      >
        {!r.sensitivity.length ? (
          <p className="panel-message">
            Additional sensitivity is disabled. Set a nonzero shift percentage
            and rerun to explore changed demand assumptions.
          </p>
        ) : (
          <>
            <p className="panel-description">
              Each possible demand is shifted by the explicit percentage and
              rounded half up to whole portions. Weights, portion mass, service
              threshold, and operating constraints stay fixed.
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Assumption shift</th>
                    <th>Expected demand</th>
                    <th>Recommended Q</th>
                    <th>Modeled surplus kg</th>
                    <th>Unserved portions</th>
                    <th>Full-service reliability</th>
                  </tr>
                </thead>
                <tbody>
                  {r.sensitivity.map((s) => (
                    <tr key={s.demand_shift_percent}>
                      <td>
                        {s.demand_shift_percent > 0 ? "+" : ""}
                        {fmt(s.demand_shift_percent)}%
                      </td>
                      <td>{fmt(s.baseline.expected_demand_portions)}</td>
                      <td>{s.recommended?.quantity ?? "Infeasible"}</td>
                      <td>{fmt(s.recommended?.expected_surplus_kg)}</td>
                      <td>{fmt(s.recommended?.expected_unmet_portions)}</td>
                      <td>{pct(s.recommended?.probability_fully_served)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <details className="decision-outcomes">
              <summary>
                Shifted demand values and feasibility explanations
              </summary>
              {r.sensitivity.map((s) => (
                <div
                  className="sensitivity-assumption"
                  key={s.demand_shift_percent}
                >
                  <strong>
                    {s.demand_shift_percent > 0 ? "+" : ""}
                    {fmt(s.demand_shift_percent)}% additional demand assumption
                  </strong>
                  <p>
                    {s.demand_scenarios
                      .map(
                        (d) =>
                          `${d.name}: ${d.demand_portions} portions at ${pct(d.probability)}`,
                      )
                      .join(" · ")}
                  </p>
                  {s.feasibility.issues.map((i) => (
                    <p key={i.code}>
                      {i.message} {i.adjustments_to_consider.join(" ")}
                    </p>
                  ))}
                </div>
              ))}
            </details>
          </>
        )}
      </Card>
      <details className="decision-audit">
        <summary>
          Calculation assumptions, numeric policy & immutable identity
        </summary>
        <p>{r.objective}</p>
        <p>{r.tie_break}</p>
        <p>
          Input fingerprint: <code>{r.input_fingerprint}</code>
        </p>
        {r.numeric_notes.map((n) => (
          <p key={n}>{n}</p>
        ))}
        {r.assumptions_and_limitations.map((l) => (
          <p key={l}>{l}</p>
        ))}
      </details>
    </div>
  );
}
