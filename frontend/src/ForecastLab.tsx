import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  FlaskConical,
  Info,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { api } from "./api";
import { useRuntime } from "./runtime";
import type {
  Evaluation,
  ModelStatus,
  Rates,
  SavedForecast,
} from "./forecastTypes";
import "./forecast.css";

const number = (n: number, d = 2) =>
  n.toLocaleString("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
const dateLabel = (s: string) =>
  new Date(`${s.slice(0, 10)}T12:00:00`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
const tomorrow = () => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const targetLabels = {
  plate: "Plate waste",
  kitchen: "Kitchen & serving waste",
  combined: "Combined waste",
};
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

export default function ForecastLab({
  batchId,
  revision,
  onImport,
}: {
  batchId: number | null;
  revision: number;
  onImport: () => void;
}) {
  const publicDemo = useRuntime().read_only;
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [runs, setRuns] = useState<SavedForecast[]>([]);
  const [result, setResult] = useState<
    (Pick<SavedForecast, "scenario" | "result"> & { id?: number }) | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [training, setTraining] = useState(false);
  const [predicting, setPredicting] = useState(false);
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");
  const [serviceDate, setServiceDate] = useState(tomorrow);
  const [diners, setDiners] = useState(publicDemo ? "400" : "");
  const [menu, setMenu] = useState(publicDemo ? "1" : "");
  const generation = useRef(0);
  const refresh = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true);
    setError("");
    setResult(null);
    setEvaluation(null);
    setStatus(null);
    setRuns([]);
    try {
      const s = await api<ModelStatus>(
        `/models/status${batchId ? `?batch_id=${batchId}` : ""}`,
      );
      if (current !== generation.current) return;
      setStatus(s);
      if (s.status === "ready") {
        const [e, h] = await Promise.all([
          api<Evaluation>(`/models/evaluation?batch_id=${s.batch_id}`),
          publicDemo
            ? Promise.resolve([])
            : api<SavedForecast[]>(`/forecasts/runs?batch_id=${s.batch_id}`),
        ]);
        if (current !== generation.current) return;
        setEvaluation(e);
        setRuns(h);
      }
    } catch (e) {
      if (current === generation.current) setError((e as Error).message);
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [batchId]);
  useEffect(() => {
    void refresh();
    return () => {
      generation.current++;
    };
  }, [refresh, revision]);

  async function train() {
    if (!batchId) return;
    setTraining(true);
    setError("");
    try {
      await api("/models/train", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ batch_id: batchId }),
      });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setTraining(false);
    }
  }
  async function forecast(e: FormEvent) {
    e.preventDefault();
    setFormError("");
    if (
      !/^\d+$/.test(diners) ||
      Number(diners) < 1 ||
      Number(diners) > 1_000_000
    ) {
      setFormError("Enter a planned diner count from 1 to 1,000,000.");
      return;
    }
    if (
      menu &&
      (!/^\d+$/.test(menu) || Number(menu) < 1 || Number(menu) > 10000)
    ) {
      setFormError(
        "Use a menu identifier from 1 to 10,000, or leave it blank for the documented fallback.",
      );
      return;
    }
    setPredicting(true);
    setResult(null);
    try {
      const scenario = {
        batch_id: batchId!,
        service_date: serviceDate,
        planned_diners: Number(diners),
        menu: menu ? Number(menu) : null,
      };
      if (publicDemo) {
        const estimate = await api<SavedForecast["result"]>(
          "/forecasts/preview",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(scenario),
          },
        );
        setResult({ scenario, result: estimate });
        return;
      }
      const saved = await api<SavedForecast>("/forecasts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          batch_id: batchId,
          service_date: serviceDate,
          planned_diners: Number(diners),
          menu: menu ? Number(menu) : null,
        }),
      });
      setResult(saved);
      setRuns((previous) => [saved, ...previous].slice(0, 20));
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setPredicting(false);
    }
  }
  const meta = status?.metadata;
  return (
    <div className="forecast-lab">
      <div className="forecast-intro">
        <span className="forecast-symbol">
          <BrainCircuit size={23} />
        </span>
        <div>
          <strong>Plan with evidence. Keep the assumptions visible.</strong>
          <p>
            Forecast waste per diner from past observations. Use your planned
            attendance to estimate kilograms.
          </p>
        </div>
        <span className="badge forecast-badge">
          <FlaskConical size={13} /> FORECAST LAB
        </span>
      </div>
      {error && (
        <div className="error-state" role="alert">
          <h2>Forecast Lab needs attention</h2>
          <p>{error}</p>
          <button
            className="button"
            disabled={loading || training}
            onClick={() => void refresh()}
          >
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      )}
      {loading ? (
        <div className="loading-state forecast-loading" role="status">
          <LoaderCircle size={25} className="spin" />
          <p>Loading model status and frozen validation evidence…</p>
        </div>
      ) : status?.status === "empty" ? (
        <Card title="Connect measured data first">
          <div className="empty">
            <span className="empty-icon">
              <BrainCircuit size={25} />
            </span>
            <h2>No forecasting dataset yet</h2>
            <p>
              Import the official measured workbook to run the chronological
              evaluation.
            </p>
            <button className="button primary" onClick={onImport}>
              Import dataset <ArrowRight size={14} />
            </button>
          </div>
        </Card>
      ) : status?.status === "blocked" ? (
        <div className="caution" role="status">
          <ShieldCheck size={23} />
          <div>
            <strong>This batch cannot supply forecast evidence</strong>
            <p>{status.reason}</p>
            <p>
              Select the official measured dataset in Data & imports. Source
              records remain unchanged.
            </p>
          </div>
        </div>
      ) : status?.status === "not_prepared" ? (
        <Card
          title="Prepare an auditable forecasting model"
          eyebrow="CHRONOLOGICAL EVALUATION"
        >
          <div className="prepare-model">
            <span className="empty-icon">
              <BrainCircuit size={28} />
            </span>
            <h3>Five candidates. One frozen selection rule.</h3>
            <p>
              Compare three historical baselines and two Ridge models on
              baseline-period validation. Then evaluate the selected method on
              the separate intervention holdout. Preparation persists a
              reusable, dataset-specific artifact.
            </p>
            <p>
              All targets use primary kilograms and valid diners. Missing or
              conflicted days are excluded and reported. A simple baseline may
              be selected.
            </p>
            {!publicDemo && (
              <button
                className="button primary"
                disabled={training}
                onClick={() => void train()}
              >
                {training ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Sparkles size={16} />
                )}{" "}
                {training
                  ? "Evaluating chronological windows…"
                  : "Evaluate & prepare model"}
              </button>
            )}
            {publicDemo && (
              <p>
                The prepared demo artifact is unavailable. Contact the demo
                operator; visitors cannot train models.
              </p>
            )}
          </div>
        </Card>
      ) : (
        meta &&
        evaluation && (
          <>
            <div className="model-ready">
              <CheckCircle2 size={17} />
              <span>Ready · {meta.selected_label}</span>
              <span className="muted">
                {meta.version} · {meta.production_training.eligible} eligible
                production-training days
              </span>
              <button
                className="text-button"
                onClick={() => void refresh()}
                disabled={training || predicting}
              >
                <RefreshCw size={13} /> Refresh evidence
              </button>
            </div>
            <div className="forecast-scenario-grid">
              <Card
                title="A future service scenario"
                eyebrow="YOUR PLANNING ASSUMPTIONS"
                className="scenario-panel"
              >
                <p className="panel-description">
                  A forecast uses the latest observed history. Planned
                  attendance is your assumption, used only for mass conversion.
                </p>
                <form onSubmit={forecast}>
                  <label className="field" htmlFor="forecast-date">
                    Future service date
                    <input
                      id="forecast-date"
                      required
                      type="date"
                      value={serviceDate}
                      onChange={(e) => setServiceDate(e.target.value)}
                      disabled={predicting}
                    />
                  </label>
                  <p className="field-help">
                    Must follow the last recorded date:{" "}
                    {dateLabel(meta.production_training.end_date)}. Long gaps
                    have not been validated.
                  </p>
                  <div className="scenario-inputs">
                    <label className="field" htmlFor="forecast-diners">
                      Planned diner count{" "}
                      <span title="A user assumption, not predicted attendance.">
                        <Info size={12} />
                      </span>
                      <input
                        id="forecast-diners"
                        type="number"
                        min="1"
                        max="1000000"
                        step="1"
                        required
                        placeholder="e.g. 400"
                        value={diners}
                        onChange={(e) => setDiners(e.target.value)}
                        disabled={predicting}
                      />
                    </label>
                    <label className="field" htmlFor="forecast-menu">
                      Menu identifier <span className="muted">optional</span>
                      <input
                        id="forecast-menu"
                        type="number"
                        min="1"
                        max="10000"
                        step="1"
                        placeholder="1–25 in this dataset"
                        value={menu}
                        onChange={(e) => setMenu(e.target.value)}
                        disabled={predicting}
                      />
                    </label>
                  </div>
                  <p className="field-help">
                    Missing or unseen menus use the recent 10-day mean fallback.
                  </p>
                  {formError && (
                    <div className="form-error" role="alert">
                      {formError}
                    </div>
                  )}
                  <button
                    className="button primary forecast-submit"
                    type="submit"
                    disabled={predicting}
                  >
                    {predicting ? (
                      <LoaderCircle className="spin" size={16} />
                    ) : (
                      <Sparkles size={16} />
                    )}{" "}
                    {predicting ? "Generating estimate…" : "Generate forecast"}
                  </button>
                </form>
              </Card>
              <Card
                title="Forecast results"
                eyebrow="ESTIMATES, NOT MEASUREMENTS"
                action={
                  <span className="badge forecast-badge">MODEL ESTIMATE</span>
                }
              >
                {!result ? (
                  <div className="forecast-result-empty">
                    <FlaskConical size={30} />
                    <h3>Your next service, estimated.</h3>
                    <p>
                      Enter a date, planned diner count, and optional menu. No
                      forecast runs automatically.
                    </p>
                  </div>
                ) : (
                  <div aria-live="polite">
                    <p className="panel-description">
                      {dateLabel(result.scenario.service_date)} ·{" "}
                      {number(result.scenario.planned_diners, 0)} planned diners
                      ·{" "}
                      {result.scenario.menu
                        ? `Menu ${result.scenario.menu}`
                        : "Menu not supplied"}
                    </p>
                    <div className="forecast-results">
                      {(Object.keys(targetLabels) as (keyof Rates)[]).map(
                        (key) => (
                          <div
                            className={
                              key === "combined" ? "combined-result" : ""
                            }
                            key={key}
                          >
                            <span>{targetLabels[key]}</span>
                            <strong>
                              {number(result.result.rates_g_per_diner[key])}{" "}
                              <small>g/diner</small>
                            </strong>
                            <p>
                              {number(result.result.estimated_mass_kg[key], 3)}{" "}
                              <b>estimated kg</b>
                            </p>
                          </div>
                        ),
                      )}
                    </div>
                    <p className="scientific-note">
                      {result.id
                        ? `Run #${result.id}`
                        : "Stateless preview · not saved"}{" "}
                      ·{" "}
                      {evaluation.method_labels[result.result.effective_method]}{" "}
                      · {result.result.training_eligible_days} eligible history
                      days.
                    </p>
                    <details className="forecast-warnings">
                      <summary>
                        Assumptions & limitations (
                        {result.result.warnings.length})
                      </summary>
                      {result.result.warnings.map((w) => (
                        <p key={w}>{w}</p>
                      ))}
                    </details>
                    {result.result.warnings
                      .filter(
                        (w) => w.includes("Long-gap") || w.includes("fallback"),
                      )
                      .map((w) => (
                        <p className="forecast-inline-warning" key={w}>
                          <Info size={13} />
                          {w}
                        </p>
                      ))}
                  </div>
                )}
              </Card>
            </div>
            <Validation evaluation={evaluation} />
            <Card
              title="Training provenance & model information"
              eyebrow="A REPRODUCIBLE RECORD"
            >
              <div className="model-provenance">
                <div>
                  <h3>{meta.source.title}</h3>
                  <p>
                    {meta.source.authors ||
                      "User-provided measured source; provenance unverified."}
                  </p>
                  <p>
                    Production artifact: {meta.production_training.eligible}{" "}
                    eligible / {meta.production_training.total} recorded days
                    through {dateLabel(meta.production_training.end_date)}. This
                    fit is separate from the historical holdout evaluation.
                  </p>
                  {meta.source.doi && (
                    <a
                      className="text-button"
                      target="_blank"
                      rel="noreferrer"
                      href={`https://doi.org/${meta.source.doi}`}
                    >
                      Source DOI: {meta.source.doi}
                    </a>
                  )}
                </div>
                <dl className="details">
                  <div>
                    <dt>Model ID</dt>
                    <dd>
                      <code>{meta.model_id}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>Quality policy</dt>
                    <dd>{meta.quality_policy}</dd>
                  </div>
                  <div>
                    <dt>Evaluation fit</dt>
                    <dd>
                      {meta.evaluation_fit_cutoff.eligible} eligible baseline
                      days; cutoff{" "}
                      {dateLabel(meta.evaluation_fit_cutoff.end_date)}
                    </dd>
                  </div>
                  <div>
                    <dt>Storage</dt>
                    <dd>{meta.serialization}</dd>
                  </div>
                </dl>
              </div>
              <details className="technical-details">
                <summary>Dataset fingerprint & configuration</summary>
                <p>Normalized data SHA-256</p>
                <code>{meta.dataset_fingerprint}</code>
                <p>Configuration / environment SHA-256</p>
                <code>{meta.config_key}</code>
              </details>
            </Card>
            {runs.length > 0 && (
              <Card
                title="Saved forecast runs"
                action={
                  <span className="subtle-tag">
                    Latest {runs.length} · this batch
                  </span>
                }
              >
                <p className="panel-description">
                  Each run keeps its scenario assumptions and exact artifact ID.
                  Historical runs can refer to older artifacts.
                </p>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Run</th>
                        <th>Service date</th>
                        <th>Planned diners</th>
                        <th>Menu</th>
                        <th>Combined g/diner</th>
                        <th>Estimated kg</th>
                        <th>Artifact</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runs.map((run) => (
                        <tr key={run.id}>
                          <td>#{run.id}</td>
                          <td>{dateLabel(run.scenario.service_date)}</td>
                          <td>{run.scenario.planned_diners}</td>
                          <td>{run.scenario.menu ?? "Fallback"}</td>
                          <td>
                            {number(run.result.rates_g_per_diner.combined)}
                          </td>
                          <td>
                            {number(run.result.estimated_mass_kg.combined, 3)}
                          </td>
                          <td>
                            <code>{run.result.model_id}</code>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </>
        )
      )}
    </div>
  );
}

function Validation({ evaluation: e }: { evaluation: Evaluation }) {
  const [period, setPeriod] = useState("holdout");
  const [target, setTarget] = useState<keyof Rates>("combined");
  const scores =
    period === "holdout" ? e.holdout_metrics : e.validation_metrics;
  const rows =
    period === "holdout" ? e.holdout_predictions : e.validation_predictions;
  const selectedValidation = e.validation_metrics[e.selected_method];
  const selectedHoldout = e.holdout_metrics[e.selected_method];
  const series = rows.map((r) => ({
    day: r.day_index,
    date: r.date,
    included: r.included,
    actual: r.actual?.[target] ?? null,
    predicted: r.predictions[e.selected_method][target],
  }));
  return (
    <div className="forecast-validation">
      <div className="forecast-stat-grid">
        <section className="metric-card featured">
          <p className="eyebrow">SELECTED ON BASELINE VALIDATION</p>
          <h3>{e.selected_label}</h3>
          <p>
            {!e.selected_method.startsWith("ridge")
              ? "Ridge did not improve combined validation MAE."
              : "Lowest combined validation MAE among tested candidates."}
          </p>
        </section>
        <section className="metric-card">
          <p className="eyebrow">
            BASELINE VALIDATION · {selectedValidation.n} DAYS
          </p>
          <div className="metric-value">
            {number(selectedValidation.combined.mae)}
            <span>g/diner MAE</span>
          </div>
          <p>RMSE {number(selectedValidation.combined.rmse)} g/diner</p>
        </section>
        <section className="metric-card">
          <p className="eyebrow">
            FINAL HOLDOUT · {selectedHoldout.n} / {e.holdout_period.total} DAYS
          </p>
          <div className="metric-value">
            {number(selectedHoldout.combined.mae)}
            <span>g/diner MAE</span>
          </div>
          <p>RMSE {number(selectedHoldout.combined.rmse)} g/diner</p>
        </section>
      </div>
      <Card
        title="Forecast validation"
        eyebrow="MEASURED ACTUALS VS HISTORICAL FORECASTS"
        action={
          <div className="chart-controls">
            <select
              aria-label="Evaluation period"
              value={period}
              onChange={(ev) => setPeriod(ev.target.value)}
            >
              <option value="holdout">Final intervention holdout</option>
              <option value="validation">Baseline validation</option>
            </select>
            <select
              aria-label="Forecast validation target"
              value={target}
              onChange={(ev) => setTarget(ev.target.value as keyof Rates)}
            >
              {Object.entries(targetLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        }
      >
        <div className="chart-legend">
          <span>
            <i className="legend-dot plate" />
            Measured actual · strict quality
          </span>
          <span>
            <i className="forecast-legend-dot" />
            Historical forecast · {e.selected_label}
          </span>
          <span className="chart-unit">Grams / diner</span>
        </div>
        <div
          className="trend-chart large"
          role="img"
          aria-label={`Actual versus predicted ${target} waste; ${rows.filter((r) => r.included).length} scored days. Exact values available below.`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={series}
              margin={{ left: -15, right: 15, top: 18, bottom: 0 }}
            >
              <CartesianGrid
                vertical={false}
                strokeDasharray="3 5"
                stroke="#e9ece5"
              />
              <XAxis
                dataKey="day"
                tickFormatter={(v) => `Day ${v}`}
                minTickGap={22}
                tick={{ fontSize: 10, fill: "#7c8579" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#7c8579" }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                labelFormatter={(_, payload) => {
                  const item = payload?.[0]?.payload;
                  return item
                    ? `Day ${item.day} · ${dateLabel(item.date)}${item.included ? "" : " · target excluded"}`
                    : "";
                }}
                formatter={(v, name) => [
                  `${number(Number(v))} g/diner`,
                  String(name),
                ]}
                contentStyle={{
                  borderRadius: 10,
                  fontSize: 11,
                  border: "1px solid #e5e8df",
                }}
              />
              <Area
                name="Measured actual"
                dataKey="actual"
                type="linear"
                stroke="#59794e"
                fill="#eaf0e0"
                strokeWidth={2}
                connectNulls={false}
                isAnimationActive={false}
              />
              <Line
                name="Historical forecast"
                dataKey="predicted"
                stroke="#b58c53"
                strokeWidth={2}
                strokeDasharray="5 4"
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <p className="chart-footnote">
          Excluded targets remain gaps and are not scored. Predictions are one
          step ahead; earlier eligible observations become available only after
          their service day. These historical forecasts use frozen evaluation
          fits, not the all-data production artifact.
        </p>
        <div className="table-scroll">
          <table className="forecast-comparison">
            <thead>
              <tr>
                <th>Candidate method</th>
                <th>Plate MAE</th>
                <th>Kitchen MAE</th>
                <th>Combined MAE</th>
                <th>Combined RMSE</th>
                <th>Scored days</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(scores).map(([method, s]) => (
                <tr
                  key={method}
                  className={
                    method === e.selected_method ? "selected-model-row" : ""
                  }
                >
                  <td>
                    <strong>{e.method_labels[method]}</strong>
                    {method === e.selected_method && (
                      <span className="subtle-tag">Selected</span>
                    )}
                  </td>
                  <td>{number(s.plate.mae)}</td>
                  <td>{number(s.kitchen.mae)}</td>
                  <td>{number(s.combined.mae)}</td>
                  <td>{number(s.combined.rmse)}</td>
                  <td>{s.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="chart-footnote">
          All errors are g/diner, with equal weight per eligible day. Selection
          uses pooled baseline-validation combined MAE only; holdout results do
          not change the selected method.
        </p>
        <details className="forecast-ledger">
          <summary>All target metrics & exact prediction ledger</summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Plate RMSE</th>
                  <th>Kitchen RMSE</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(scores).map(([m, s]) => (
                  <tr key={m}>
                    <td>{e.method_labels[m]}</td>
                    <td>{number(s.plate.rmse)}</td>
                    <td>{number(s.kitchen.rmse)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Day / source row</th>
                  <th>Date</th>
                  <th>Actual {target} g/diner</th>
                  <th>Forecast {target} g/diner</th>
                  <th>Quality</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.day_index}>
                    <td>
                      {r.day_index} / {r.source_row}
                    </td>
                    <td>{dateLabel(r.date)}</td>
                    <td>
                      {r.actual ? number(r.actual[target], 4) : "Excluded"}
                    </td>
                    <td>
                      {number(r.predictions[e.selected_method][target], 4)}
                    </td>
                    <td>
                      {r.included
                        ? "Included"
                        : r.exclusions.join(", ").replaceAll("_", " ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </Card>
      <div className="forecast-protocol-grid">
        <Card
          title="Chronology, with a hard boundary"
          eyebrow="NO SHUFFLING · NO FUTURE TARGETS"
        >
          <p className="panel-description">
            Three expanding training windows within the first 135 recorded days.
            Ridge preprocessing and weights fit only on each training window;
            history advances one service day at a time.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Window</th>
                  <th>Training days</th>
                  <th>Eligible</th>
                  <th>Validation days</th>
                  <th>Eligible</th>
                </tr>
              </thead>
              <tbody>
                {e.folds.map((f, i) => (
                  <tr key={i}>
                    <td>{i + 1}</td>
                    <td>
                      {f.training.first_day}–{f.training.last_day}
                    </td>
                    <td>{f.training.eligible}</td>
                    <td>
                      {f.validation.first_day}–{f.validation.last_day}
                    </td>
                    <td>{f.validation.eligible}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="scientific-note">
            Baseline: {dateLabel(e.baseline_period.start_date)} –{" "}
            {dateLabel(e.baseline_period.end_date)}. Final holdout:{" "}
            {dateLabel(e.holdout_period.start_date)} –{" "}
            {dateLabel(e.holdout_period.end_date)}; {e.holdout_period.eligible}{" "}
            eligible of {e.holdout_period.total} days. The selection is frozen
            before this holdout.
          </p>
        </Card>
        <Card
          title="Strict quality, visible exclusions"
          eyebrow={e.quality_policy}
        >
          <p className="panel-description">
            Use paired primary kg measurements and positive observed diners to
            calculate both targets. Exclude a whole day if either target is
            missing or any source conflict/duplicate flag is present. No target
            imputation or silent repair.
          </p>
          <div className="forecast-exclusions">
            {[
              ...e.baseline_period.exclusions,
              ...e.holdout_period.exclusions,
            ].map((row) => (
              <div key={row.day_index}>
                <strong>
                  Day {row.day_index}{" "}
                  <span>
                    · {dateLabel(row.date)} · source row {row.source_row}
                  </span>
                </strong>
                <p>{row.reasons.join(" · ").replaceAll("_", " ")}</p>
              </div>
            ))}
          </div>
          <p className="scientific-note">
            Evaluation coverage: {e.baseline_period.eligible}/
            {e.baseline_period.total} eligible baseline days;{" "}
            {e.holdout_period.eligible}/{e.holdout_period.total} holdout days.
            All original measurements and audit notes remain available.
          </p>
        </Card>
      </div>
      <div className="caution forecast-caveat">
        <Info size={20} />
        <div>
          <strong>
            Historical validation is not proof of operational impact.
          </strong>
          {e.limitations.map((l) => (
            <p key={l}>{l}</p>
          ))}
        </div>
      </div>
    </div>
  );
}
