import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowDownToLine,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  ClipboardList,
  FileCheck2,
  FlaskConical,
  History,
  Info,
  LoaderCircle,
  Plus,
  RefreshCw,
  Save,
} from "lucide-react";
import { api } from "./api";
import { useRuntime } from "./runtime";
import type { PlanSummary } from "./decisionTypes";
import type {
  Assessment,
  Basis,
  Category,
  ImpactComparison,
  ImpactComparisonInput,
  ImpactSummary,
  Measurement,
  OperationalRecord,
  ServiceInput,
  SourceCategory,
} from "./impactTypes";
import "./impact.css";

const SOURCES: Record<SourceCategory, string> = {
  user_reported: "User-reported observations",
  user_reported_documented: "User-reported with supporting references",
  synthetic: "Synthetic demonstration records",
};
const CATEGORIES: Record<Category, string> = {
  discarded_surplus: "Discarded prepared-food surplus",
  plate_waste: "Plate waste",
  preparation_waste: "Preparation scraps / kitchen preparation waste",
};
const DISPOSITIONS = {
  donated: "Donated for human consumption",
  retained: "Retained for later service",
  repurposed: "Repurposed for human consumption",
  discarded: "Discarded",
  unknown: "Unaccounted / unknown",
} as const;
const fmt = (n: number | null | undefined, d = 0) =>
  n == null
    ? "—"
    : n.toLocaleString("en-US", {
        maximumFractionDigits: d,
        minimumFractionDigits: d,
      });
const dateTime = (s: string) =>
  new Date(s).toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  });
const jsonPost = (value: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(value),
});
function Panel({
  title,
  eyebrow,
  children,
  action,
}: {
  title: string;
  eyebrow?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="panel">
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
function Badge({ source }: { source: SourceCategory }) {
  return (
    <span
      className={`badge ${source === "synthetic" ? "synthetic" : ""} impact-source`}
    >
      {source === "synthetic" ? (
        <FlaskConical size={13} />
      ) : (
        <ClipboardList size={13} />
      )}{" "}
      {source === "synthetic"
        ? "SYNTHETIC DEMONSTRATION"
        : "SELF-REPORTED · UNVERIFIED"}
    </span>
  );
}

type Filters = {
  status: "all" | "draft" | "finalized";
  basis: "" | Basis;
  start: string;
  end: string;
  site: string;
  menu: string;
};
const emptyFilters = (): Filters => ({
  status: "all",
  basis: "",
  start: "",
  end: "",
  site: "",
  menu: "",
});
export default function ImpactLedger() {
  const publicDemo = useRuntime().read_only;
  const [source, setSource] = useState<SourceCategory>(
    publicDemo ? "synthetic" : "user_reported",
  );
  const [view, setView] = useState<"ledger" | "editor" | "comparison">(
    "ledger",
  );
  const [filters, setFilters] = useState<Filters>(emptyFilters),
    [applied, setApplied] = useState<Filters>(emptyFilters);
  const [summary, setSummary] = useState<ImpactSummary | null>(null),
    [records, setRecords] = useState<OperationalRecord[]>([]);
  const [selected, setSelected] = useState<OperationalRecord | null>(null),
    [editing, setEditing] = useState<OperationalRecord | null>(null);
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [offset, setOffset] = useState(0);
  const [plans, setPlans] = useState<PlanSummary[]>([]),
    [planError, setPlanError] = useState("");
  const generation = useRef(0);
  async function loadPlans() {
    try {
      setPlans(await api<PlanSummary[]>("/decisions/plans?limit=100"));
      setPlanError("");
    } catch (e) {
      setPlanError((e as Error).message);
    }
  }
  useEffect(() => {
    void loadPlans();
  }, []);
  async function load(nextOffset = 0, settings = applied, cohort = source) {
    const token = ++generation.current;
    setLoading(true);
    setError("");
    const q = new URLSearchParams({
      source_category: cohort,
      status: settings.status,
    });
    for (const key of ["basis", "start", "end", "site", "menu"] as const)
      if (settings[key]) q.set(key, settings[key]);
    try {
      const [s, r] = await Promise.all([
        api<ImpactSummary>(`/impact/summary?${q}`),
        api<OperationalRecord[]>(
          `/impact/records?${q}&limit=10&offset=${nextOffset}`,
        ),
      ]);
      if (token === generation.current) {
        setSummary(s);
        setRecords(r);
        setOffset(nextOffset);
      }
    } catch (e) {
      if (token === generation.current) {
        setError((e as Error).message);
        setSummary(null);
        setRecords([]);
      }
    } finally {
      if (token === generation.current) setLoading(false);
    }
  }
  useEffect(() => {
    setSummary(null);
    setRecords([]);
    setOffset(0);
    void load(0, applied, source);
  }, [source]);
  function newRecord() {
    setEditing(null);
    setSelected(null);
    setView("editor");
    setError("");
    setNotice("");
  }
  async function open(id: number) {
    setBusy(true);
    setError("");
    try {
      setSelected(await api<OperationalRecord>(`/impact/records/${id}`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (publicDemo && selected) {
      const detail = document.getElementById("impact-record-detail");
      detail?.focus();
      detail?.scrollIntoView({ block: "start" });
    }
  }, [publicDemo, selected]);
  async function examples() {
    setBusy(true);
    setError("");
    try {
      const examples = await api<OperationalRecord[]>("/impact/demo", {
        method: "POST",
      });
      setSource("synthetic");
      setApplied(emptyFilters());
      setFilters(emptyFilters());
      setView("ledger");
      setSelected(examples[0]);
      setNotice(
        "Explicitly synthetic examples added. No real service or physical weighing occurred. The incomplete example remains a draft.",
      );
      await load(0, emptyFilters(), "synthetic");
      await loadPlans();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function saved(record: OperationalRecord) {
    setSource(record.record.source_category);
    setFilters(emptyFilters());
    setApplied(emptyFilters());
    setView("ledger");
    setEditing(null);
    setSelected(record);
    setNotice(
      `Service #${record.id} · revision ${record.version} saved as a draft. Review the evidence before finalizing counts.`,
    );
    await load(0, emptyFilters(), record.record.source_category);
  }
  async function finalize() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const next = await api<OperationalRecord>(
        `/impact/records/${selected.id}/finalize`,
        jsonPost({ expected_version: selected.version }),
      );
      setSelected(next);
      setNotice(
        `Revision ${next.version} finalized. Finalization preserves the snapshot; it does not provide independent verification or prove impact.`,
      );
      await load(offset);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="impact-ledger">
      <div className="impact-banner">
        <span className="impact-symbol">
          <ClipboardList size={25} />
        </span>
        <div>
          <p className="eyebrow">OPERATIONAL EVIDENCE</p>
          <h2>What was planned. What happened. What is supported.</h2>
          <p>
            Keep reported service outcomes, physical readings and planning
            assumptions separate. A complete entry does not demonstrate a causal
            software effect.
          </p>
        </div>
      </div>
      <div className="impact-controls">
        {publicDemo && (
          <button
            className="button"
            disabled={busy}
            onClick={() => {
              setView("ledger");
              void open(1);
            }}
          >
            Inspect complete example
          </button>
        )}
        <div className="impact-tabs" aria-label="Impact Ledger views">
          {(
            [
              ["ledger", "Records & overview"],
              [
                "editor",
                publicDemo ? "Try simulated accounting" : "Record a service",
              ],
              ["comparison", "Descriptive comparison"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              className={view === id ? "active" : ""}
              aria-pressed={view === id}
              onClick={() => {
                setView(id);
                if (id === "editor") {
                  setEditing(null);
                  setSelected(null);
                }
              }}
            >
              {label}
            </button>
          ))}
        </div>
        {!publicDemo && (
          <button
            className="button"
            disabled={busy}
            onClick={() => void examples()}
          >
            <FlaskConical size={15} /> Add synthetic examples
          </button>
        )}
      </div>
      <div className="impact-cohort">
        <label className="field" htmlFor="impact-cohort">
          Evidence cohort
          <select
            id="impact-cohort"
            value={source}
            onChange={(e) => {
              setSource(e.target.value as SourceCategory);
              setSelected(null);
              setView("ledger");
              setEditing(null);
              setNotice("");
            }}
          >
            {Object.entries(SOURCES)
              .filter(([id]) => !publicDemo || id === "synthetic")
              .map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
          </select>
        </label>
        <div>
          <Badge source={source} />
          <p>
            One provenance category at a time. Finland historical measurements
            are outside these totals. Supporting references are not independent
            verification.
          </p>
        </div>
      </div>
      {notice && (
        <div className="notice" role="status">
          <CheckCircle2 size={17} />
          <span>{notice}</span>
          <button
            className="icon-button"
            aria-label="Dismiss ledger notification"
            onClick={() => setNotice("")}
          >
            ×
          </button>
        </div>
      )}
      {error && (
        <div className="form-error" role="alert">
          {error}
          <button
            className="button small"
            onClick={() => {
              void load(offset);
              if (selected) void open(selected.id);
            }}
          >
            Refresh ledger
          </button>
        </div>
      )}
      {view === "editor" ? (
        <ServiceEditor
          key={editing ? `${editing.id}-${editing.version}` : `new-${source}`}
          source={source}
          editing={editing}
          plans={plans}
          planError={planError}
          onPlans={() => void loadPlans()}
          onSaved={saved}
          onCancel={() => setView("ledger")}
        />
      ) : view === "comparison" ? (
        <ComparisonEditor source={source} />
      ) : (
        <>
          <Panel
            title="Operational history"
            eyebrow="CURRENT REVISIONS · EXPLICIT COVERAGE"
            action={
              <button
                className="text-button"
                disabled={loading || busy}
                onClick={() => void load(offset)}
              >
                <RefreshCw size={14} /> Refresh records
              </button>
            }
          >
            <form
              className="impact-filter-form"
              onSubmit={(e) => {
                e.preventDefault();
                setApplied({ ...filters });
                setSelected(null);
                void load(0, filters);
              }}
            >
              <label className="field">
                Lifecycle
                <select
                  aria-label="Lifecycle filter"
                  value={filters.status}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      status: e.target.value as Filters["status"],
                    })
                  }
                >
                  <option value="all">Draft & finalized</option>
                  <option value="draft">Draft only</option>
                  <option value="finalized">Finalized only</option>
                </select>
              </label>
              <label className="field">
                Measurement basis
                <select
                  aria-label="Measurement basis filter"
                  value={filters.basis}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      basis: e.target.value as Filters["basis"],
                    })
                  }
                >
                  <option value="">All reported methods</option>
                  <option value="weighed">Contains weighed readings</option>
                  <option value="estimated">Contains estimates</option>
                  <option value="imported">Contains imported reports</option>
                </select>
              </label>
              <label className="field">
                From date
                <input
                  type="date"
                  aria-label="Ledger from date"
                  value={filters.start}
                  onChange={(e) =>
                    setFilters({ ...filters, start: e.target.value })
                  }
                />
              </label>
              <label className="field">
                Through date
                <input
                  type="date"
                  aria-label="Ledger through date"
                  value={filters.end}
                  onChange={(e) =>
                    setFilters({ ...filters, end: e.target.value })
                  }
                />
              </label>
              <label className="field">
                Site exact match
                <input
                  maxLength={100}
                  aria-label="Site filter"
                  value={filters.site}
                  onChange={(e) =>
                    setFilters({ ...filters, site: e.target.value })
                  }
                  placeholder="Any site"
                />
              </label>
              <label className="field">
                Menu exact match
                <input
                  maxLength={150}
                  aria-label="Menu filter"
                  value={filters.menu}
                  onChange={(e) =>
                    setFilters({ ...filters, menu: e.target.value })
                  }
                  placeholder="Any menu"
                />
              </label>
              <button className="button" type="submit" disabled={loading}>
                Apply filters
              </button>
            </form>
            <p className="impact-help">
              A method filter selects services containing that basis; their
              other mass entries stay separately labeled. Drafts are included
              only when selected. Totals show reported coverage, not inferred
              outcomes.
            </p>
          </Panel>
          {loading ? (
            <div className="loading-state" role="status">
              <LoaderCircle size={25} className="spin" />
              <p>Reading persisted operational evidence…</p>
            </div>
          ) : (
            summary && (
              <>
                <Dashboard summary={summary} />
                <Panel
                  title="Service record ledger"
                  eyebrow={`${SOURCES[source].toUpperCase()} · LATEST REVISION PER SERVICE`}
                  action={
                    <button className="button small" onClick={newRecord}>
                      <Plus size={14} />{" "}
                      {publicDemo
                        ? "Try simulated accounting"
                        : "New service record"}
                    </button>
                  }
                >
                  {!records.length ? (
                    <div className="impact-empty">
                      <ClipboardList size={30} />
                      <h3>
                        {offset
                          ? "No more records on this page."
                          : "No records in this cohort yet."}
                      </h3>
                      <p>
                        Enter an observed service with its limitations, or
                        explicitly add synthetic examples for demonstration. No
                        dataset or forecasting model is required.
                      </p>
                    </div>
                  ) : (
                    <div className="impact-record-list">
                      {records.map((r) => (
                        <button
                          key={r.id}
                          className={`impact-record-item ${selected?.id === r.id ? "selected" : ""}`}
                          disabled={busy}
                          onClick={() => void open(r.id)}
                        >
                          <span className="impact-symbol">
                            <ClipboardList size={18} />
                          </span>
                          <div>
                            <strong>
                              #{r.id} · {r.record.service_date} ·{" "}
                              {r.record.site || "Site unspecified"}
                            </strong>
                            <p>
                              Menu {r.record.menu} · prepared{" "}
                              {fmt(r.record.prepared)} / served{" "}
                              {fmt(r.record.served)} · revision {r.version}
                            </p>
                            <span>{r.assessment.labels.join(" · ")}</span>
                          </div>
                          <span className={`impact-status ${r.status}`}>
                            {r.status}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="pagination">
                    <span>
                      {records.length
                        ? `${offset + 1}–${offset + records.length}`
                        : "0"}{" "}
                      shown · immutable revision history available
                    </span>
                    <div>
                      <button
                        className="button small"
                        disabled={!offset || loading}
                        onClick={() => void load(Math.max(0, offset - 10))}
                      >
                        Previous records
                      </button>
                      <button
                        className="button small"
                        disabled={records.length < 10 || loading}
                        onClick={() => void load(offset + 10)}
                      >
                        Next records
                      </button>
                    </div>
                  </div>
                </Panel>
              </>
            )
          )}
          {selected && (
            <div id="impact-record-detail" tabIndex={-1}>
              <RecordDetail
                key={`${selected.id}-${selected.version}`}
                data={selected}
                busy={busy}
                onFinalize={() => void finalize()}
                onCorrection={() => {
                  setEditing(selected);
                  setView("editor");
                  setError("");
                }}
              />
            </div>
          )}
        </>
      )}
      <Panel
        title="Evidence boundaries"
        eyebrow="REPORTING WITH ACCOUNTABILITY"
      >
        <div className="impact-boundaries">
          <div>
            <BookOpen size={19} />
            <h3>Three separate evidence sources</h3>
            <p>
              Historical Finland measurements remain in Overview and Forecast
              Lab. Decision Studio plans are assumption-based. This ledger
              contains operator reports or explicit synthetic demonstrations;
              documentation does not make them independently verified.
            </p>
          </div>
          <div>
            <Info size={19} />
            <h3>Food destinations stay distinct</h3>
            <p>
              Donation, retention and repurposing are not automatically
              discarded waste. No food safety assurance is provided. Portion
              estimates never replace scale readings. Observational differences
              do not establish prevention or a software effect.
            </p>
          </div>
        </div>
        <p className="impact-help">
          Measurement design draws on public{" "}
          <a
            href="https://flwprotocol.org/flw-standard/"
            target="_blank"
            rel="noreferrer"
          >
            FLW Protocol guidance
          </a>
          . This local application claims no certification or standards
          compliance. Follow the kitchen’s established safety procedures and
          retain original supporting records.
        </p>
      </Panel>
    </div>
  );
}

function Dashboard({ summary: s }: { summary: ImpactSummary }) {
  const synthetic = s.source_category === "synthetic";
  const metrics = [
    [
      "RECORDED SERVICES",
      s.service_count,
      `${s.draft_services} drafts · current revisions only`,
    ],
    [
      "PREPARED PORTIONS",
      s.counts.prepared.total,
      `${s.counts.prepared.covered} covered / ${s.service_count} records`,
    ],
    [
      "SERVED PORTIONS",
      s.counts.served.total,
      `${s.counts.served.covered} covered; not unconstrained demand`,
    ],
    [
      "RECORDED REMAINING",
      s.counts.remaining.total,
      `${s.counts.remaining.covered} matched preparation / service counts`,
    ],
  ] as const;
  return (
    <>
      <div className="impact-metrics">
        {metrics.map(([label, value, note]) => (
          <section className="metric-card" key={label}>
            <p className="eyebrow">{label}</p>
            <div className="metric-value">{fmt(value)}</div>
            <p>{note}</p>
          </section>
        ))}
      </div>
      <div className="impact-two-column">
        <Panel
          title="Where remaining food was reported"
          eyebrow="MUTUALLY EXCLUSIVE PORTION DESTINATIONS"
        >
          <div className="impact-destinations">
            {Object.entries(DISPOSITIONS).map(([key, label]) => (
              <div key={key}>
                <span>{label}</span>
                <strong>{fmt(s.counts[key].total)}</strong>
                <small>
                  {s.counts[key].covered} reported · {s.counts[key].missing}{" "}
                  missing
                </small>
              </div>
            ))}
          </div>
          <div className="impact-caution">
            <Info size={17} />
            <p>
              {s.evidence.unknown_disposition_services} services contain unknown
              disposition; {s.evidence.missing_disposition_services} have
              missing destination entries; {s.evidence.unreconciled_services} do
              not fully reconcile. Missing values are never balanced
              automatically.
            </p>
          </div>
        </Panel>
        <Panel
          title="Mass records, with their measurement basis"
          eyebrow={
            synthetic
              ? "SIMULATED READINGS · NEVER REAL MEASUREMENTS"
              : "OPERATOR-REPORTED MASS · KG"
          }
        >
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Waste stream</th>
                  <th>{synthetic ? "Simulated scale" : "Weighed"}</th>
                  <th>Estimated</th>
                  <th>Imported</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(CATEGORIES).map(([key, label]) => (
                  <tr key={key}>
                    <td>{label}</td>
                    {(["weighed", "estimated", "imported"] as const).map(
                      (b) => (
                        <td key={b}>
                          {fmt(s.mass_by_category[key as Category][b].total, 2)}
                          <small>
                            {s.mass_by_category[key as Category][b].covered}/
                            {s.service_count} covered
                          </small>
                        </td>
                      ),
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="impact-mass-total">
            <strong>
              {synthetic
                ? "Compatible simulated scale sum"
                : "Compatible physically weighed inventory"}
              : {fmt(s.combined_weighed_kg.total, 2)} kg
            </strong>
            <p>
              {s.combined_weighed_kg.covered}/{s.service_count} covered.{" "}
              {s.combined_explanation}
            </p>
          </div>
          <p className="impact-estimate">
            Portion-count conversion estimate for discarded portions:{" "}
            <strong>{fmt(s.estimated_discarded_kg.total, 2)} kg</strong> ·{" "}
            {s.estimated_discarded_kg.covered} covered. This estimate is
            separate and never added to the scale inventory.
          </p>
        </Panel>
      </div>
      <div className="impact-two-column">
        <Panel
          title="Preparation and service history"
          eyebrow="PERSISTED CURRENT REVISIONS · PORTIONS"
        >
          {s.daily.length ? (
            <div
              className="impact-history-chart"
              role="img"
              aria-label="Persisted prepared and served portion counts by service date; missing values remain gaps."
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={s.daily}
                  margin={{ left: -16, right: 0, top: 10, bottom: 0 }}
                >
                  <CartesianGrid
                    vertical={false}
                    strokeDasharray="3 5"
                    stroke="#e7ebdf"
                  />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }} />
                  <Bar
                    dataKey="prepared"
                    name="Reported prepared portions"
                    fill="#b4c39b"
                    radius={[3, 3, 0, 0]}
                    isAnimationActive={false}
                  />
                  <Bar
                    dataKey="served"
                    name="Reported served portions"
                    fill="#6d8a58"
                    radius={[3, 3, 0, 0]}
                    isAnimationActive={false}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="panel-message">
              The chart will use saved operational records in this cohort.
            </p>
          )}
          <details className="impact-details">
            <summary>Exact daily count ledger</summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Services</th>
                    <th>Prepared</th>
                    <th>Served</th>
                    <th>Remaining</th>
                  </tr>
                </thead>
                <tbody>
                  {s.daily.map((d) => (
                    <tr key={d.date}>
                      <td>{d.date}</td>
                      <td>{d.services}</td>
                      <td>{fmt(d.prepared)}</td>
                      <td>{fmt(d.served)}</td>
                      <td>{fmt(d.remaining)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </Panel>
        <Panel
          title="Completeness and planning adherence"
          eyebrow="DESCRIPTIVE EVIDENCE · NO CONFIDENCE SCORE"
        >
          <div className="impact-quality-grid">
            <div>
              <strong>{s.evidence.complete_entries}</strong>
              <span>Complete entries</span>
            </div>
            <div>
              <strong>{s.evidence.incomplete_entries}</strong>
              <span>Incomplete entries</span>
            </div>
            <div>
              <strong>{s.evidence.services_missing_mass}</strong>
              <span>Missing mass categories</span>
            </div>
            <div>
              <strong>
                {s.adherence.followed_exactly}/{s.adherence.assessable_services}
              </strong>
              <span>Preparation matched a linked recommendation</span>
            </div>
          </div>
          <p className="impact-help">
            {s.adherence.linked_services} linked plans;{" "}
            {s.adherence.prospective_captures} prospectively captured relative
            to reported dates; {s.adherence.retrospective_or_unlinked}{" "}
            retrospective/unlinked. Adherence does not establish effectiveness.
          </p>
          <details className="impact-details">
            <summary>Methods, coverage rules & exclusions</summary>
            {Object.entries(s.methods).map(([m, n]) => (
              <p key={m}>
                {m}: {n} entries
              </p>
            ))}
            {s.notes.map((n) => (
              <p key={n}>{n}</p>
            ))}
          </details>
        </Panel>
      </div>
    </>
  );
}

type MassDraft = Omit<Measurement, "mass_kg" | "gross_kg" | "tare_kg"> & {
  enabled: boolean;
  mass_kg: string;
  gross_kg: string;
  tare_kg: string;
};
type Draft = {
  service_date: string;
  site: string;
  menu: string;
  decision_plan_id: string;
  prepared: string;
  served: string;
  turn_aways: string;
  observed_diners: string;
  portion_mass_g: string;
  source_category: SourceCategory;
  count_method: string;
  operator_notes: string;
  dispositions: Record<keyof typeof DISPOSITIONS, string>;
  measurements: Record<Category, MassDraft>;
  disjoint_scope_note: string;
  documents: string;
};
const str = (n: number | null | undefined) => (n == null ? "" : String(n));
function initial(source: SourceCategory, input?: ServiceInput): Draft {
  const today = new Date();
  const date = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const measures = {} as Record<Category, MassDraft>;
  for (const category of Object.keys(CATEGORIES) as Category[]) {
    const m = input?.measurements.find((m) => m.category === category);
    measures[category] = {
      category,
      enabled: !!m,
      mass_kg: str(m?.mass_kg),
      basis: m?.basis ?? "weighed",
      method: m?.method ?? "",
      scope_description: m?.scope_description ?? "",
      scope_status: m?.scope_status ?? "unresolved",
      material_type: m?.material_type ?? "unspecified",
      destination: m?.destination ?? "unspecified",
      gross_kg: str(m?.gross_kg),
      tare_kg: str(m?.tare_kg),
      notes: m?.notes ?? "",
    };
  }
  return {
    service_date: input?.service_date ?? date,
    site: input?.site ?? "",
    menu: input?.menu ?? "",
    decision_plan_id: str(input?.decision_plan_id),
    prepared: str(input?.prepared),
    served: str(input?.served),
    turn_aways: str(input?.turn_aways),
    observed_diners: str(input?.observed_diners),
    portion_mass_g: str(input?.portion_mass_g),
    source_category: input?.source_category ?? source,
    count_method: input?.count_method ?? "",
    operator_notes: input?.operator_notes ?? "",
    dispositions: Object.fromEntries(
      Object.keys(DISPOSITIONS).map((k) => [
        k,
        str(input?.dispositions[k as keyof typeof DISPOSITIONS]),
      ]),
    ) as Draft["dispositions"],
    measurements: measures,
    disjoint_scope_note: input?.disjoint_scope_note ?? "",
    documents:
      input?.documents.map((d) => `${d.label} | ${d.reference}`).join("\n") ??
      "",
  };
}
function numberOrNull(value: string, label: string, integer = false) {
  if (!value.trim()) return null;
  const n = Number(value);
  if (!Number.isFinite(n) || (integer && !/^\d+$/.test(value)))
    throw new Error(
      `${label} must be a finite ${integer ? "nonnegative integer" : "number"}.`,
    );
  return n;
}
function request(d: Draft): ServiceInput {
  return {
    service_date: d.service_date,
    site: d.site,
    menu: d.menu,
    decision_plan_id: numberOrNull(d.decision_plan_id, "Plan identifier", true),
    prepared: numberOrNull(d.prepared, "Prepared portions", true),
    served: numberOrNull(d.served, "Served portions", true),
    turn_aways: numberOrNull(d.turn_aways, "Turn-aways", true),
    observed_diners: numberOrNull(
      d.observed_diners,
      "Observed unique diners",
      true,
    ),
    portion_mass_g: numberOrNull(d.portion_mass_g, "Portion mass"),
    source_category: d.source_category,
    count_method: d.count_method,
    operator_notes: d.operator_notes,
    dispositions: Object.fromEntries(
      Object.entries(d.dispositions).map(([k, v]) => [
        k,
        numberOrNull(v, k, true),
      ]),
    ) as ServiceInput["dispositions"],
    measurements: Object.values(d.measurements)
      .filter((m) => m.enabled)
      .map(({ enabled: _, ...m }) => ({
        ...m,
        mass_kg: numberOrNull(m.mass_kg, "Mass"),
        gross_kg: numberOrNull(m.gross_kg, "Gross mass"),
        tare_kg: numberOrNull(m.tare_kg, "Tare mass"),
      })),
    disjoint_scope_note: d.disjoint_scope_note,
    documents: d.documents
      .split("\n")
      .filter((line) => line.trim())
      .map((line) => {
        const [label, ...rest] = line.split("|");
        if (!rest.length)
          throw new Error(
            "Supporting references use one line per document: Label | reference.",
          );
        return { label: label.trim(), reference: rest.join("|").trim() };
      }),
  };
}

function ServiceEditor({
  source,
  editing,
  plans,
  planError,
  onPlans,
  onSaved,
  onCancel,
}: {
  source: SourceCategory;
  editing: OperationalRecord | null;
  plans: PlanSummary[];
  planError: string;
  onPlans: () => void;
  onSaved: (r: OperationalRecord) => Promise<void>;
  onCancel: () => void;
}) {
  const publicDemo = useRuntime().read_only;
  const [draft, setDraft] = useState<Draft>(() =>
      initial(source, editing?.record),
    ),
    [reason, setReason] = useState("");
  const [assessment, setAssessment] = useState<Assessment | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    if (!publicDemo) return;
    let active = true;
    api<{ complete: ServiceInput }>("/impact/demo")
      .then((fixture) => {
        if (active) setDraft(initial("synthetic", fixture.complete));
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, [publicDemo]);
  function edit(change: Partial<Draft>) {
    setDraft({ ...draft, ...change });
    setAssessment(null);
    setError("");
  }
  const set = (key: keyof Draft, value: string) => edit({ [key]: value });
  function mass(category: Category, change: Partial<MassDraft>) {
    edit({
      measurements: {
        ...draft.measurements,
        [category]: { ...draft.measurements[category], ...change },
      },
    });
  }
  async function check() {
    setBusy(true);
    setAssessment(null);
    setError("");
    try {
      setAssessment(
        await api<Assessment>("/impact/preview", jsonPost(request(draft))),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    if (publicDemo) {
      await check();
      return;
    }
    setBusy(true);
    setError("");
    try {
      const input = request(draft);
      const next = await api<OperationalRecord>(
        editing ? `/impact/records/${editing.id}/revisions` : "/impact/records",
        jsonPost(
          editing
            ? {
                expected_version: editing.version,
                record: input,
                correction_reason: reason,
              }
            : input,
        ),
      );
      await onSaved(next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const selectable = plans.filter(
    (p) =>
      draft.source_category === "synthetic" ||
      p.scenario_kind !== "synthetic_demo",
  );
  return (
    <form className="impact-editor" onSubmit={save}>
      <fieldset disabled={busy}>
        <Panel
          title={
            editing
              ? `Append correction to service #${editing.id}`
              : publicDemo
                ? "Try synthetic service accounting"
                : "Record an operational service"
          }
          eyebrow={
            editing
              ? `ORIGINAL REVISION ${editing.version} WILL BE PRESERVED`
              : "UNKNOWN VALUES STAY BLANK · EXPLICIT ZERO MEANS OBSERVED ZERO"
          }
          action={
            <button className="text-button" type="button" onClick={onCancel}>
              <ArrowLeft size={14} /> Back to ledger
            </button>
          }
        >
          <div className="impact-form-grid">
            <label className="field">
              Service date
              <input
                aria-label="Operational service date"
                type="date"
                min="2000-01-01"
                max="2100-12-31"
                required
                value={draft.service_date}
                onChange={(e) => set("service_date", e.target.value)}
              />
            </label>
            <label className="field">
              Site / location · optional
              <input
                aria-label="Operational site"
                maxLength={100}
                value={draft.site}
                onChange={(e) => set("site", e.target.value)}
                placeholder="Kitchen or school label"
              />
            </label>
            <label className="field">
              Menu identifier or description
              <input
                aria-label="Operational menu"
                required
                maxLength={150}
                value={draft.menu}
                onChange={(e) => set("menu", e.target.value)}
                placeholder="Identifier or a short meal description"
              />
            </label>
            <label className="field">
              Record provenance
              <select
                aria-label="Operational provenance"
                disabled={!!editing}
                value={draft.source_category}
                onChange={(e) =>
                  edit({
                    source_category: e.target.value as SourceCategory,
                    decision_plan_id: "",
                  })
                }
              >
                {Object.entries(SOURCES)
                  .filter(([key]) => !publicDemo || key === "synthetic")
                  .map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
              </select>
            </label>
            <label className="field impact-wide">
              Saved Decision Studio plan · optional
              <select
                aria-label="Linked Decision Studio plan"
                value={draft.decision_plan_id}
                onChange={(e) => {
                  const p = plans.find((p) => p.id === Number(e.target.value));
                  edit({
                    decision_plan_id: e.target.value,
                    ...(p ? { service_date: p.planning_date } : {}),
                  });
                }}
              >
                <option value="">No linked plan</option>
                {selectable.map((p) => (
                  <option value={p.id} key={p.id}>
                    #{p.id} · {p.planning_date} · {p.title || "Untitled plan"} ·{" "}
                    {p.scenario_kind}
                  </option>
                ))}
              </select>
              <small>
                Selecting a plan uses its service date. Actual quantities must
                be entered separately. Up to 100 recent plans are listed; date
                and numeric menu must match. Demo plans link only to synthetic
                services.
              </small>
            </label>
          </div>
          <div className="impact-inline-actions">
            <button className="text-button" type="button" onClick={onPlans}>
              <RefreshCw size={12} /> Refresh saved plan choices
            </button>
            <p className="impact-help">
              {planError ||
                "Capture times are generated by the server. Backfilled or same-day plans do not prove prospective planning."}
            </p>
          </div>
        </Panel>
        <Panel
          title="Actual preparation and service"
          eyebrow="OPERATOR-REPORTED COUNTS · NO AUTOMATIC DEMAND INFERENCE"
        >
          <div className="impact-form-grid">
            {(
              [
                ["prepared", "Actual prepared portions"],
                ["served", "Actual served portions"],
                ["turn_aways", "Observed turn-aways · optional"],
                ["observed_diners", "Observed unique diners · optional"],
              ] as const
            ).map(([key, label]) => (
              <label className="field" key={key}>
                {label}
                <input
                  type="number"
                  aria-label={label}
                  min="0"
                  max="100000"
                  step="1"
                  value={draft[key]}
                  onChange={(e) => set(key, e.target.value)}
                />
              </label>
            ))}
            <label className="field">
              Portion mass for estimates · grams
              <input
                type="number"
                aria-label="Operational portion mass"
                min="0.000001"
                max="10000"
                step="any"
                value={draft.portion_mass_g}
                onChange={(e) => set("portion_mass_g", e.target.value)}
              />
            </label>
            <label className="field">
              Count measurement method
              <input
                maxLength={200}
                aria-label="Count measurement method"
                value={draft.count_method}
                onChange={(e) => set("count_method", e.target.value)}
                placeholder="e.g. preparation tally and service counter"
              />
            </label>
          </div>
          <p className="impact-help">
            Served must not exceed prepared. Served portions are not a count of
            unique diners or true demand. Leave unobserved turn-aways/diners
            blank; do not substitute zero. Portion mass creates only an
            estimate.
          </p>
        </Panel>
        <Panel
          title="Account for every remaining prepared portion"
          eyebrow="MUTUALLY EXCLUSIVE DESTINATIONS"
        >
          <div className="impact-disposition-form">
            {Object.entries(DISPOSITIONS).map(([key, label]) => (
              <label className="field" key={key}>
                {label}
                <input
                  type="number"
                  aria-label={`${label} portions`}
                  min="0"
                  max="100000"
                  step="1"
                  value={draft.dispositions[key as keyof typeof DISPOSITIONS]}
                  onChange={(e) =>
                    edit({
                      dispositions: {
                        ...draft.dispositions,
                        [key]: e.target.value,
                      },
                    })
                  }
                />
              </label>
            ))}
          </div>
          <p className="impact-help">
            Enter explicit zero only when observed. Counts must reconcile before
            finalizing, and unknown disposition must be resolved. Drafts
            preserve discrepancies. Donation/retention/repurposing are not
            automatically waste. Follow established kitchen safety procedures;
            this app provides no safety certification.
          </p>
        </Panel>
        <Panel
          title="Mass entries and measurement boundaries"
          eyebrow="KG · KEEP SCALE READINGS SEPARATE FROM PORTION ESTIMATES"
        >
          <p className="impact-help">
            Record only available mass categories. Each entry states its basis,
            scope, method, material and destination. Unresolved boundaries
            prevent combined totals.
          </p>
          <div className="impact-measurement-editor">
            {(Object.keys(CATEGORIES) as Category[]).map((category) => {
              const m = draft.measurements[category];
              return (
                <section className="impact-mass-editor" key={category}>
                  <label className="impact-check">
                    <input
                      type="checkbox"
                      checked={m.enabled}
                      onChange={(e) =>
                        mass(category, { enabled: e.target.checked })
                      }
                      aria-label={`Record ${CATEGORIES[category]}`}
                    />
                    <strong>{CATEGORIES[category]}</strong>
                  </label>
                  {m.enabled && (
                    <div className="impact-form-grid">
                      <label className="field">
                        Net mass · kg
                        <input
                          type="number"
                          aria-label={`${category} net mass kg`}
                          min="0"
                          max="1000000"
                          step="any"
                          value={m.mass_kg}
                          onChange={(e) =>
                            mass(category, { mass_kg: e.target.value })
                          }
                        />
                      </label>
                      <label className="field">
                        Measurement basis
                        <select
                          aria-label={`${category} basis`}
                          value={m.basis}
                          onChange={(e) =>
                            mass(category, {
                              basis: e.target.value as Basis,
                              ...(e.target.value !== "weighed"
                                ? { gross_kg: "", tare_kg: "" }
                                : {}),
                            })
                          }
                        >
                          <option value="weighed">
                            {draft.source_category === "synthetic"
                              ? "Simulated scale reading"
                              : "Directly weighed"}
                          </option>
                          <option value="estimated">Estimated mass</option>
                          <option value="imported">
                            Imported report (not asserted directly weighed)
                          </option>
                        </select>
                      </label>
                      <label className="field">
                        Measurement method
                        <input
                          aria-label={`${category} method`}
                          maxLength={100}
                          value={m.method}
                          onChange={(e) =>
                            mass(category, { method: e.target.value })
                          }
                          placeholder="Describe the actual method or source"
                        />
                      </label>
                      <label className="field">
                        Scope relationship
                        <select
                          aria-label={`${category} scope status`}
                          value={m.scope_status}
                          onChange={(e) =>
                            mass(category, {
                              scope_status: e.target
                                .value as Measurement["scope_status"],
                            })
                          }
                        >
                          <option value="unresolved">Scope unresolved</option>
                          <option value="possible_overlap">
                            Possible overlap with other entries
                          </option>
                          <option value="disjoint_stream">
                            Declared disjoint stream
                          </option>
                        </select>
                      </label>
                      <label className="field">
                        Material included
                        <select
                          aria-label={`${category} material`}
                          value={m.material_type}
                          onChange={(e) =>
                            mass(category, {
                              material_type: e.target
                                .value as Measurement["material_type"],
                            })
                          }
                        >
                          <option value="unspecified">Unspecified</option>
                          <option value="food_only">Food only</option>
                          <option value="inedible_only">
                            Associated inedible parts only
                          </option>
                          <option value="food_and_inedible">
                            Food and associated inedible parts
                          </option>
                        </select>
                      </label>
                      <label className="field">
                        Waste destination
                        <select
                          aria-label={`${category} destination`}
                          value={m.destination}
                          onChange={(e) =>
                            mass(category, {
                              destination: e.target
                                .value as Measurement["destination"],
                            })
                          }
                        >
                          {[
                            "unspecified",
                            "landfill",
                            "sewer",
                            "compost",
                            "anaerobic_digestion",
                            "animal_feed",
                            "other",
                          ].map((d) => (
                            <option key={d} value={d}>
                              {d.replaceAll("_", " ")}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field impact-wide">
                        Scope / inclusions and exclusions
                        <textarea
                          aria-label={`${category} scope description`}
                          maxLength={500}
                          value={m.scope_description}
                          onChange={(e) =>
                            mass(category, {
                              scope_description: e.target.value,
                            })
                          }
                          placeholder="Which food, service, collection stream and exclusions does this reading cover?"
                        />
                      </label>
                      {m.basis === "weighed" && (
                        <>
                          <label className="field">
                            Gross mass · kg · optional
                            <input
                              aria-label={`${category} gross kg`}
                              type="number"
                              min="0"
                              max="1000000"
                              step="any"
                              value={m.gross_kg}
                              onChange={(e) =>
                                mass(category, { gross_kg: e.target.value })
                              }
                            />
                          </label>
                          <label className="field">
                            Tare / container mass · kg · optional
                            <input
                              aria-label={`${category} tare kg`}
                              type="number"
                              min="0"
                              max="1000000"
                              step="any"
                              value={m.tare_kg}
                              onChange={(e) =>
                                mass(category, { tare_kg: e.target.value })
                              }
                            />
                          </label>
                          <p className="impact-help impact-wide">
                            Supply both gross and tare to check net mass. Leave
                            net blank to calculate it. Conflicting net values
                            are rejected, not replaced silently.
                          </p>
                        </>
                      )}
                      <label className="field impact-wide">
                        Measurement notes · optional
                        <textarea
                          aria-label={`${category} notes`}
                          maxLength={1000}
                          value={m.notes}
                          onChange={(e) =>
                            mass(category, { notes: e.target.value })
                          }
                        />
                      </label>
                    </div>
                  )}
                </section>
              );
            })}
          </div>
          <label className="field">
            Disjoint scope explanation · required for combining streams
            <textarea
              aria-label="Disjoint scope explanation"
              maxLength={500}
              value={draft.disjoint_scope_note}
              onChange={(e) => set("disjoint_scope_note", e.target.value)}
              placeholder="Explain how separate collection prevents overlap; exclude containers/packaging and transfers."
            />
          </label>
        </Panel>
        <Panel
          title="Operator context and supporting references"
          eyebrow="REFERENCES ARE NOT AN INDEPENDENT ASSURANCE PROCESS"
        >
          <label className="field">
            Operator notes
            <textarea
              aria-label="Operator notes"
              maxLength={1000}
              value={draft.operator_notes}
              onChange={(e) => set("operator_notes", e.target.value)}
            />
          </label>
          <label className="field">
            Supporting references · up to five
            <textarea
              aria-label="Supporting references"
              maxLength={3100}
              value={draft.documents}
              onChange={(e) => set("documents", e.target.value)}
              placeholder="One per line: Label | reference to a retained log, sheet or photo"
            />
          </label>
          <p className="impact-help">
            The app stores references only; no files are uploaded or
            authenticated. Keep originals externally. The documented self-report
            category requires at least one reference.
          </p>
          {editing && !publicDemo && (
            <label className="field">
              Correction reason · required
              <textarea
                aria-label="Correction reason"
                required
                minLength={5}
                maxLength={1000}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Explain why fields are changing. Previous versions remain available."
              />
            </label>
          )}
        </Panel>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <div className="impact-editor-actions">
          <span>
            {publicDemo
              ? "Synthetic calculation only. Changes and evidence checks are not saved."
              : editing
                ? `Append a new draft after version ${editing.version}; no original is overwritten.`
                : "Save an incomplete draft at any stage after service date, menu and provenance are entered."}
          </span>
          <div>
            <button
              className="button"
              type="button"
              onClick={() => void check()}
            >
              <FileCheck2 size={15} /> Check evidence
            </button>
            {!publicDemo && (
              <button className="button primary" type="submit">
                {busy ? (
                  <LoaderCircle className="spin" size={15} />
                ) : (
                  <Save size={15} />
                )}{" "}
                {editing ? "Save correction draft" : "Save service draft"}
              </button>
            )}
          </div>
        </div>
        {assessment && (
          <Evidence assessment={assessment} source={draft.source_category} />
        )}
      </fieldset>
    </form>
  );
}

function Evidence({
  assessment: a,
  source,
}: {
  assessment: Assessment;
  source: SourceCategory;
}) {
  return (
    <Panel
      title="Evidence quality and accounting"
      eyebrow={`${a.assessment_version.toUpperCase()} · DETERMINISTIC EXPLANATIONS`}
      action={<Badge source={source} />}
    >
      <div className="impact-labels">
        {a.labels.map((l) => (
          <span className="subtle-tag" key={l}>
            {l}
          </span>
        ))}
      </div>
      <div className="impact-quality-grid">
        <div>
          <strong>{fmt(a.accounting.remaining_portions)}</strong>
          <span>Remaining portions</span>
        </div>
        <div>
          <strong>{fmt(a.accounting.known_disposition_portions)}</strong>
          <span>Known allocated entries</span>
        </div>
        <div>
          <strong>{fmt(a.accounting.discrepancy_portions)}</strong>
          <span>Remaining minus known allocations</span>
        </div>
        <div>
          <strong>{fmt(a.accounting.unknown_portions)}</strong>
          <span>Unknown disposition</span>
        </div>
      </div>
      <p className="impact-help">
        {a.accounting.reconciled
          ? "All five entries reconcile arithmetically."
          : "Accounting is incomplete or does not reconcile."}{" "}
        {a.accounting.missing_dispositions.length
          ? `Missing: ${a.accounting.missing_dispositions.join(", ")}.`
          : ""}{" "}
        Unknown portions can reconcile counts while leaving disposition
        knowledge incomplete.
      </p>
      {a.finalization_blockers.length > 0 && (
        <div className="impact-caution">
          <Info size={17} />
          <div>
            <strong>Finalization blocked</strong>
            <ul>
              {a.finalization_blockers.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
      {a.issues.length > 0 && (
        <div className="impact-issues">
          <strong>Evidence limitations to resolve or disclose</strong>
          <ul>
            {a.issues.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="impact-help">
        {a.provenance_label}. {a.planning_timing_explanation} This record is not
        independently verified.
      </p>
    </Panel>
  );
}

function RecordDetail({
  data: r,
  busy,
  onFinalize,
  onCorrection,
}: {
  data: OperationalRecord;
  busy: boolean;
  onFinalize: () => void;
  onCorrection: () => void;
}) {
  const publicDemo = useRuntime().read_only;
  const [history, setHistory] = useState<OperationalRecord[] | null>(null),
    [original, setOriginal] = useState<unknown>(null),
    [error, setError] = useState(""),
    [reading, setReading] = useState(false);
  async function audit() {
    setReading(true);
    setError("");
    try {
      setHistory(
        await api<OperationalRecord[]>(`/impact/records/${r.id}/history`),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setReading(false);
    }
  }
  async function plan() {
    setReading(true);
    setError("");
    try {
      setOriginal(await api(`/impact/records/${r.id}/plan`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setReading(false);
    }
  }
  const p = r.plan_reference;
  return (
    <div className="impact-record-detail">
      <Panel
        title={`Service #${r.id} · revision ${r.version}`}
        eyebrow={`${r.status.toUpperCase()} · ${r.record.service_date} · ${r.record.site || "SITE UNSPECIFIED"}`}
        action={<Badge source={r.record.source_category} />}
      >
        <p className="impact-help">
          Server creation: {dateTime(r.service_created_at)}. This revision
          captured: {dateTime(r.created_at)}. Menu: {r.record.menu}.
        </p>
        <div className="impact-detail-actions">
          {!publicDemo && r.status === "draft" && (
            <button
              className="button primary"
              disabled={busy}
              onClick={onFinalize}
            >
              <CheckCircle2 size={15} /> Finalize counts
            </button>
          )}
          {!publicDemo && (
            <button className="button" disabled={busy} onClick={onCorrection}>
              <Plus size={14} /> Append correction
            </button>
          )}
          <button
            className="button"
            disabled={reading}
            onClick={() => void audit()}
          >
            <History size={14} /> Load audit history
          </button>
          {!publicDemo && (
            <>
              <a
                className="button small"
                download
                href={`/api/impact/records/${r.id}/export?format=json`}
              >
                <ArrowDownToLine size={13} /> Export JSON
              </a>
              <a
                className="button small"
                download
                href={`/api/impact/records/${r.id}/export?format=csv`}
              >
                <ArrowDownToLine size={13} /> Export CSV
              </a>
            </>
          )}
        </div>
        <p className="impact-help">
          Finalization requires reconciled known counts, a count method and a
          completed service date. Mass evidence may remain incomplete and
          disclosed. A correction always appends a new draft; original snapshots
          remain unchanged.
        </p>
        {r.correction_reason && (
          <p className="impact-help">
            <strong>Correction reason:</strong> {r.correction_reason}
          </p>
        )}
      </Panel>
      <Evidence assessment={r.assessment} source={r.record.source_category} />
      <div className="impact-two-column">
        <Panel
          title="Reported operational outcomes"
          eyebrow="COUNTS · OBSERVATIONS WITH DISCLOSED LIMITATIONS"
        >
          <dl className="impact-definition-list">
            {(
              [
                ["Actual prepared", r.record.prepared],
                ["Actual served", r.record.served],
                ["Observed turn-aways", r.record.turn_aways],
                ["Observed unique diners", r.record.observed_diners],
                ["Portion mass for estimates · g", r.record.portion_mass_g],
              ] as const
            ).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{fmt(value)}</dd>
              </div>
            ))}
            {Object.entries(DISPOSITIONS).map(([key, label]) => (
              <div key={key}>
                <dt>{label}</dt>
                <dd>
                  {fmt(r.record.dispositions[key as keyof typeof DISPOSITIONS])}
                </dd>
              </div>
            ))}
          </dl>
          <p className="impact-help">
            Count method: {r.record.count_method || "Not recorded"}.{" "}
            {r.record.operator_notes}
          </p>
          {r.record.documents.length > 0 && (
            <details className="impact-details">
              <summary>Supporting references · unverified contents</summary>
              {r.record.documents.map((d, i) => (
                <p key={i}>
                  <strong>{d.label}:</strong> {d.reference}
                </p>
              ))}
            </details>
          )}
        </Panel>
        <Panel
          title="Original assumption-based plan"
          eyebrow="PLANNING ESTIMATES · SEPARATE FROM OPERATIONS"
        >
          {p ? (
            <div className="impact-plan">
              <span className="badge decision-badge">
                ASSUMPTION-BASED SNAPSHOT #{p.id}
              </span>
              <p>
                Captured {dateTime(p.created_at)} · planned date{" "}
                {p.planning_date} · {p.engine_version} · {p.scenario_kind}
              </p>
              <dl className="impact-definition-list">
                <div>
                  <dt>Original baseline portions</dt>
                  <dd>{fmt(p.baseline_portions)}</dd>
                </div>
                <div>
                  <dt>Original recommendation</dt>
                  <dd>{fmt(p.recommended_portions)}</dd>
                </div>
                <div>
                  <dt>Actual prepared − recommendation</dt>
                  <dd>{fmt(r.assessment.actual_minus_recommended)}</dd>
                </div>
                <div>
                  <dt>Actual prepared − baseline</dt>
                  <dd>{fmt(r.assessment.actual_minus_baseline)}</dd>
                </div>
                <div>
                  <dt>Recommendation followed exactly</dt>
                  <dd>
                    {r.assessment.followed_exactly == null
                      ? "Unknown"
                      : r.assessment.followed_exactly
                        ? "Yes"
                        : "No"}
                  </dd>
                </div>
              </dl>
              <p>
                Plan-only modeled surplus: baseline{" "}
                {fmt(p.modeled_baseline_surplus_kg, 2)} kg; recommendation{" "}
                {fmt(p.modeled_recommended_surplus_kg, 2)} kg. These are
                assumptions, not observed outcomes or realized prevention.
              </p>
              <p>
                The baseline is a comparator, not proof of what would otherwise
                have happened. Timing:{" "}
                {r.assessment.planning_timing.replaceAll("_", " ")}.
              </p>
              <button
                className="button small"
                disabled={reading}
                onClick={() => void plan()}
              >
                Retrieve immutable original plan
              </button>
              <code>{p.input_fingerprint}</code>
            </div>
          ) : (
            <p className="panel-message">
              No saved plan is linked. The service remains a retrospective
              observation; a plan is not required to record operations.
            </p>
          )}
        </Panel>
      </div>
      <Panel
        title="Mass evidence and estimate separation"
        eyebrow={
          r.record.source_category === "synthetic"
            ? "ALL READINGS BELOW ARE SIMULATED"
            : "REPORTED MASS · METHOD AND SCOPE RETAINED"
        }
      >
        <div className="impact-reading-cards">
          <div>
            <p className="eyebrow">DISCARDED PORTION CONVERSION</p>
            <strong>
              {fmt(r.assessment.accounting.estimated_discarded_kg, 2)} kg
            </strong>
            <p>
              {fmt(r.record.dispositions.discarded)} portions ×{" "}
              {fmt(r.record.portion_mass_g)} g / 1,000. Estimate only; never
              added to readings.
            </p>
          </div>
          <div>
            <p className="eyebrow">
              {r.record.source_category === "synthetic"
                ? "COMPATIBLE SIMULATED SCALE SUM"
                : "COMPATIBLE WEIGHED INVENTORY"}
            </p>
            <strong>{fmt(r.assessment.combined_weighed_kg, 2)} kg</strong>
            <p>{r.assessment.combined_mass_explanation}</p>
          </div>
        </div>
        {!r.record.measurements.length ? (
          <p className="panel-message">
            No mass entries. Missing readings remain missing.
          </p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Stream</th>
                  <th>Reported net kg</th>
                  <th>Basis & method</th>
                  <th>Scope, material & destination</th>
                  <th>Gross / tare kg</th>
                </tr>
              </thead>
              <tbody>
                {r.record.measurements.map((m) => (
                  <tr key={m.category}>
                    <td>{CATEGORIES[m.category]}</td>
                    <td>{fmt(m.mass_kg, 3)}</td>
                    <td>
                      {r.record.source_category === "synthetic"
                        ? "Simulated "
                        : ""}
                      {m.basis} · {m.method}
                      <small>{m.notes}</small>
                    </td>
                    <td>
                      {m.scope_description}
                      <small>
                        {m.scope_status.replaceAll("_", " ")} ·{" "}
                        {m.material_type.replaceAll("_", " ")} ·{" "}
                        {m.destination.replaceAll("_", " ")}
                      </small>
                    </td>
                    <td>
                      {fmt(m.gross_kg, 3)} / {fmt(m.tare_kg, 3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="impact-help">
          Disjoint scope declaration:{" "}
          {r.record.disjoint_scope_note || "Not provided"}
        </p>
      </Panel>
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      {history && (
        <Panel
          title="Append-only audit history"
          eyebrow="EVERY PRIOR SNAPSHOT IS PRESERVED"
        >
          <div className="impact-audit-list">
            {history.map((h) => (
              <details key={h.revision_id}>
                <summary>
                  Version {h.version} · {h.status} · {h.event} ·{" "}
                  {dateTime(h.created_at)}
                </summary>
                <p>
                  {h.correction_reason ||
                    "Server-captured creation / lifecycle event."}
                </p>
                <p>
                  Changed input fields:{" "}
                  {h.changed_fields.join(", ") ||
                    "None; lifecycle finalization only"}
                  .
                </p>
                <p>
                  Prepared {fmt(h.record.prepared)}, served{" "}
                  {fmt(h.record.served)}, unknown{" "}
                  {fmt(h.record.dispositions.unknown)}.{" "}
                  {h.assessment.labels.join(" · ")}.
                </p>
                <pre>{JSON.stringify(h.record, null, 2)}</pre>
              </details>
            ))}
          </div>
          <p className="impact-help">
            This local history is application-level append-only storage. It is
            not cryptographically tamper-proof; no actor authentication or
            independent assurance is implemented.
          </p>
        </Panel>
      )}
      {original !== null && (
        <Panel
          title="Immutable Decision Studio snapshot"
          eyebrow="STORED ORIGINAL RESULT · NO REOPTIMIZATION"
        >
          <details className="impact-details" open>
            <summary>Original plan JSON</summary>
            <pre>{JSON.stringify(original, null, 2)}</pre>
          </details>
        </Panel>
      )}
    </div>
  );
}

function ComparisonEditor({ source }: { source: SourceCategory }) {
  const [draft, setDraft] = useState({
    category: "discarded_surplus" as Category,
    basis: "weighed" as Basis,
    baseline_start: "",
    baseline_end: "",
    trial_start: "",
    trial_end: "",
    site: "",
    menu: "",
  });
  const [result, setResult] = useState<ImpactComparison | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    setResult(null);
    setError("");
  }, [source]);
  function edit(change: Partial<typeof draft>) {
    setDraft({ ...draft, ...change });
    setResult(null);
    setError("");
  }
  async function compare(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setResult(null);
    setError("");
    try {
      const input: ImpactComparisonInput = {
        ...draft,
        source_category: source,
        site: draft.site || null,
        menu: draft.menu || null,
      };
      setResult(
        await api<ImpactComparison>("/impact/comparison", jsonPost(input)),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="impact-comparison">
      <Panel
        title="Compare compatible operational periods"
        eyebrow="OBSERVATIONAL COMPARISON — NOT CAUSAL EVIDENCE"
      >
        <form onSubmit={compare}>
          <fieldset disabled={busy}>
            <div className="impact-form-grid">
              <label className="field">
                Waste category
                <select
                  aria-label="Comparison waste category"
                  value={draft.category}
                  onChange={(e) =>
                    edit({ category: e.target.value as Category })
                  }
                >
                  {Object.entries(CATEGORIES).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Measurement basis
                <select
                  aria-label="Comparison measurement basis"
                  value={draft.basis}
                  onChange={(e) => edit({ basis: e.target.value as Basis })}
                >
                  <option value="weighed">
                    {source === "synthetic" ? "Simulated scale" : "Weighed"}
                  </option>
                  <option value="estimated">
                    Estimated mass · separate analysis
                  </option>
                  <option value="imported">
                    Imported mass · separate analysis
                  </option>
                </select>
              </label>
              {(
                [
                  ["baseline_start", "Baseline start"],
                  ["baseline_end", "Baseline end"],
                  ["trial_start", "Trial start"],
                  ["trial_end", "Trial end"],
                ] as const
              ).map(([key, label]) => (
                <label className="field" key={key}>
                  {label}
                  <input
                    required
                    type="date"
                    aria-label={label}
                    min="2000-01-01"
                    max="2100-12-31"
                    value={draft[key]}
                    onChange={(e) => edit({ [key]: e.target.value })}
                  />
                </label>
              ))}
              <label className="field">
                Site exact match · optional
                <input
                  aria-label="Comparison site"
                  maxLength={100}
                  value={draft.site}
                  onChange={(e) => edit({ site: e.target.value })}
                />
              </label>
              <label className="field">
                Menu exact match · optional
                <input
                  aria-label="Comparison menu"
                  maxLength={150}
                  value={draft.menu}
                  onChange={(e) => edit({ menu: e.target.value })}
                />
              </label>
            </div>
            <p className="impact-help">
              Uses finalized current revisions only, within{" "}
              {SOURCES[source].toLowerCase()}. Periods must be ordered and
              non-overlapping. Scope/material/destination/method and site/menu
              declarations must match. Separately observed unique diners are
              required for per-diner rates; served portions are never
              substituted.
            </p>
            <button className="button primary" type="submit">
              {busy ? (
                <LoaderCircle className="spin" size={15} />
              ) : (
                <FileCheck2 size={15} />
              )}{" "}
              Compare reported periods
            </button>
          </fieldset>
        </form>
      </Panel>
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      {result && (
        <Panel
          title={
            result.status === "blocked"
              ? "Comparison blocked: incompatible or missing evidence"
              : "Compatible descriptive comparison"
          }
          eyebrow={result.label.toUpperCase()}
          action={<Badge source={source} />}
        >
          <p className="impact-help">
            {CATEGORIES[result.category]} · {result.basis} basis. Matching
            definitions are operator declarations, not independent assurance.
          </p>
          {result.reasons.length > 0 && (
            <div className="impact-caution">
              <Info size={17} />
              <ul>
                {result.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Baseline</th>
                  <th>Trial</th>
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    ["services", "Finalized services", 0],
                    [
                      "covered_observations",
                      "Covered category observations",
                      0,
                    ],
                    [
                      "missing_or_other_basis",
                      "Missing / other-basis observations",
                      0,
                    ],
                    ["reported_mass_kg", "Comparable reported mass · kg", 3],
                    ["kg_per_covered_service", "Kg per covered service", 3],
                    ["g_per_observed_diner", "G per observed unique diner", 2],
                    [
                      "diner_covered_services",
                      "Services with valid paired diner counts",
                      0,
                    ],
                    ["observed_diners", "Matched observed diners", 0],
                    ["paired_mass_kg", "Mass paired to valid diners · kg", 3],
                  ] as const
                ).map(([key, label, d]) => (
                  <tr key={key}>
                    <td>{label}</td>
                    <td>{fmt(result.periods.baseline[key], d)}</td>
                    <td>{fmt(result.periods.trial[key], d)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.difference && (
            <p className="impact-comparison-difference">
              Trial minus baseline:{" "}
              <strong>
                {fmt(result.difference.kg_per_service_trial_minus_baseline, 3)}{" "}
                kg per covered service
              </strong>
              ; relative change{" "}
              {result.difference.relative_change == null
                ? "undefined at zero baseline"
                : `${fmt(result.difference.relative_change * 100, 2)}%`}
              . Per-diner difference:{" "}
              {fmt(result.difference.g_per_diner_trial_minus_baseline, 2)} g.
              These descriptive differences are not verified savings.
            </p>
          )}
          <details className="impact-details">
            <summary>Context and method counts</summary>
            {(["baseline", "trial"] as const).map((p) => (
              <div key={p}>
                <strong>{p}</strong>
                <p>
                  Menus: {JSON.stringify(result.periods[p].menus)}. Sites:{" "}
                  {JSON.stringify(result.periods[p].sites)}. Methods:{" "}
                  {JSON.stringify(result.periods[p].methods)}.
                </p>
              </div>
            ))}
          </details>
          {result.notes.map((n) => (
            <p key={n} className="impact-help">
              {n}
            </p>
          ))}
        </Panel>
      )}
    </div>
  );
}
