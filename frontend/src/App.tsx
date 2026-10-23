import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowDownToLine,
  ArrowRight,
  BarChart3,
  BookOpen,
  Check,
  CheckCircle2,
  ClipboardList,
  Database,
  ExternalLink,
  FileSpreadsheet,
  FlaskConical,
  Info,
  Layers3,
  LayoutDashboard,
  Leaf,
  LoaderCircle,
  Menu as MenuIcon,
  RefreshCw,
  Scale,
  ShieldCheck,
  Sprout,
  TrendingUp,
  Upload,
  Users,
  Utensils,
  X,
} from "lucide-react";
import { api } from "./api";
import ForecastLab from "./ForecastLab";
import DecisionStudio from "./DecisionStudio";
import ImpactLedger from "./ImpactLedger";
import DemoJourney from "./DemoJourney";
import { useRuntime } from "./runtime";
import type { Batch, Charts, Daily, Metrics, Overview, Status } from "./types";

type View =
  | "demo"
  | "overview"
  | "trends"
  | "menus"
  | "data"
  | "methodology"
  | "forecast"
  | "decisions"
  | "impact";
const navigation = [
  { id: "demo", name: "Explore MealLoop OS", icon: Sprout },
  { id: "overview", name: "Overview", icon: LayoutDashboard },
  { id: "trends", name: "Waste trends", icon: TrendingUp },
  { id: "menus", name: "Menu analysis", icon: Utensils },
  { id: "forecast", name: "Forecast Lab", icon: FlaskConical },
  { id: "decisions", name: "Decision Studio", icon: Scale },
  { id: "impact", name: "Impact Ledger", icon: ClipboardList },
  { id: "data", name: "Data & imports", icon: Database },
  { id: "methodology", name: "Methodology", icon: BookOpen },
] as const;
const fmt = (n: number | null | undefined, decimals = 1) =>
  n == null
    ? "—"
    : n.toLocaleString("en-US", {
        maximumFractionDigits: decimals,
        minimumFractionDigits: decimals,
      });
const dateFmt = (s: string | null) =>
  s
    ? new Date(`${s.slice(0, 10)}T12:00:00`).toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "No dates supplied";
const humanIssue = (s: string) =>
  s.replaceAll("_", " ").replace("kg g conflict", "kg / grams conflict");

function Badge({ synthetic = false }: { synthetic?: boolean }) {
  return (
    <span className={`badge ${synthetic ? "synthetic" : ""}`}>
      {synthetic ? <FlaskConical size={13} /> : <ShieldCheck size={13} />}
      {synthetic ? "SYNTHETIC TEST DATA" : "MEASURED DATA"}
    </span>
  );
}
function Panel({
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
function Empty({
  title,
  children,
  icon = <Database size={26} />,
}: {
  title: string;
  children: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">{icon}</span>
      <h2>{title}</h2>
      <div>{children}</div>
    </div>
  );
}

export default function App() {
  const runtime = useRuntime();
  const publicDemo = runtime.read_only;
  const [demoRequested, setDemoRequested] = useState(publicDemo);
  const [view, setView] = useState<View>(() =>
    navigation.some((n) => n.id === location.hash.slice(1))
      ? (location.hash.slice(1) as View)
      : publicDemo
        ? "demo"
        : "overview",
  );
  const [status, setStatus] = useState<Status | null>(null);
  const [batchId, setBatchId] = useState<number | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [charts, setCharts] = useState<Charts | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [isMobile, setIsMobile] = useState(
    () => window.matchMedia("(max-width: 760px)").matches,
  );
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const statusGeneration = useRef(0);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 760px)");
    const changed = () => setIsMobile(media.matches);
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);

  const loadStatus = useCallback(async (selected?: number) => {
    const generation = ++statusGeneration.current;
    setError("");
    setLoading(true);
    try {
      const next = await api<Status>("/dataset/status");
      if (generation !== statusGeneration.current) return;
      setStatus(next);
      setBatchId(
        (current) =>
          selected ??
          (next.batches.some((b) => b.id === current)
            ? current
            : next.active_batch_id),
      );
      setRevision((r) => r + 1);
      if (!next.batches.length) {
        setOverview(null);
        setCharts(null);
        setLoading(false);
      }
    } catch (e) {
      if (generation === statusGeneration.current) {
        setError((e as Error).message);
        setLoading(false);
      }
    }
  }, []);
  useEffect(() => {
    if (!mobileNav || !isMobile) return;
    const sidebar = document.getElementById("workspace-navigation");
    const links = sidebar?.querySelectorAll<HTMLElement>(
      "a[href], button:not(:disabled)",
    );
    links?.[0]?.focus();
    function keyboard(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileNav(false);
        document.getElementById("navigation-toggle")?.focus();
      }
      if (event.key === "Tab" && links?.length) {
        const first = links[0],
          last = links[links.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", keyboard);
    return () => document.removeEventListener("keydown", keyboard);
  }, [mobileNav, isMobile]);
  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);
  useEffect(() => {
    const onHash = () => {
      const id = location.hash.slice(1);
      if (navigation.some((n) => n.id === id)) setView(id as View);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    if (!batchId) return;
    let active = true;
    setLoading(true);
    setError("");
    setOverview(null);
    setCharts(null);
    Promise.all([
      api<Overview>(`/overview?batch_id=${batchId}`),
      api<Charts>(`/charts?batch_id=${batchId}`),
    ])
      .then(([o, c]) => {
        if (active) {
          setOverview(o);
          setCharts(c);
        }
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [batchId, revision]);
  const go = (id: View) => {
    setView(id);
    location.hash = id;
    setMobileNav(false);
    document.getElementById("main-content")?.focus();
    window.scrollTo({ top: 0, behavior: "instant" });
  };
  const batch = overview?.batch;
  const synthetic = batch?.source.kind === "synthetic";
  const title = navigation.find((n) => n.id === view)?.name || "Overview";

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside
        id="workspace-navigation"
        className={`sidebar ${mobileNav ? "open" : ""}`}
        inert={isMobile && !mobileNav}
      >
        <a className="brand" href="#overview" onClick={() => go("overview")}>
          <span className="brand-icon">
            <Leaf size={23} />
          </span>
          <span>
            MealLoop<span className="brand-os">OS</span>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">
            <Sprout size={19} />
          </span>
          <div>
            <strong>School meals</strong>
            <span>Waste intelligence workspace</span>
          </div>
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation">
          {navigation.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              onClick={() => go(item.id)}
              className={view === item.id ? "active" : ""}
              aria-current={view === item.id ? "page" : undefined}
            >
              <item.icon size={18} />
              <span>{item.name}</span>
              {view === item.id && <span className="nav-dot" />}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="purpose">
            <span className="purpose-icon">
              <Sprout size={23} />
            </span>
            <h3>
              Better meals.
              <br />
              Less left behind.
            </h3>
            <p>Understanding waste is the first step toward preventing it.</p>
            <button onClick={() => go("methodology")}>
              Our approach <ArrowRight size={14} />
            </button>
          </div>
          <div className="build-info">
            <span className="status-dot" /> v0.5.0{" "}
            <span>Arbiter Hacks V1</span>
          </div>
        </div>
      </aside>
      {mobileNav && (
        <button
          className="nav-backdrop"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        />
      )}
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-toggle"
              id="navigation-toggle"
              aria-controls="workspace-navigation"
              aria-expanded={mobileNav}
              aria-label="Open navigation"
              onClick={() => setMobileNav(true)}
            >
              <MenuIcon size={20} />
            </button>
            <span>Workspace</span>
            <span className="slash">/</span>
            <strong>{title}</strong>
          </div>
          <div className="topbar-right">
            <span className="local-pill">
              <span className="status-dot" />{" "}
              {publicDemo ? "Public demo · read-only" : "Local workspace"}
            </span>
            <span className="avatar" title="MealLoop OS workspace">
              ML
            </span>
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          <div className="page-heading">
            <div>
              <p className="eyebrow">FOOD WASTE INTELLIGENCE</p>
              <h1>
                {view === "overview" ? "A clearer picture. Less waste." : title}
              </h1>
              <p className="page-subtitle">
                {view === "demo"
                  ? "From food waste measurements to evidence-aware production decisions."
                  : view === "overview"
                    ? "Turn daily measurements into a better understanding of school food waste."
                    : view === "data"
                      ? "Trace every insight back to its source."
                      : view === "impact"
                        ? "Account for service outcomes. Keep every claim tied to its evidence."
                        : view === "decisions"
                          ? "Explore production plans with explicit assumptions and service constraints."
                          : view === "forecast"
                            ? "Forecast future waste. See exactly how the evidence holds up."
                            : view === "methodology"
                              ? "Transparent calculations. Honest interpretations."
                              : view === "menus"
                                ? "Compare recorded waste across the rolling lunch cycle."
                                : "Explore daily patterns without losing the detail."}
              </p>
            </div>
            {!publicDemo &&
              view !== "demo" &&
              view !== "decisions" &&
              view !== "impact" && (
                <button
                  className="button primary"
                  onClick={() => setUploadOpen(true)}
                >
                  <Upload size={16} /> Import dataset
                </button>
              )}
          </div>
          {view !== "demo" && (
            <a className="demo-entry" href="#demo" onClick={() => go("demo")}>
              Try the live demo <ArrowRight size={14} />
            </a>
          )}
          {publicDemo && (
            <div className="demo-mode-note" role="note">
              <ShieldCheck size={18} />
              <p>
                <strong>Public demo · no visitor changes are saved.</strong>{" "}
                Imports, training, saves, corrections and exports are available
                only in a local workspace. Please use fictional inputs.
              </p>
            </div>
          )}
          {notice && (
            <div className="notice" role="status">
              <CheckCircle2 size={17} />
              <span>{notice}</span>
              <button
                aria-label="Dismiss notification"
                className="icon-button"
                onClick={() => setNotice("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {view !== "demo" && view !== "decisions" && view !== "impact" && (
            <div className="context-bar">
              <div>
                <span className="context-icon">
                  <FileSpreadsheet size={18} />
                </span>
                <div>
                  <strong>
                    {batch
                      ? batch.inspection.verified_official_file
                        ? "Secondary school · Western Finland"
                        : batch.source.title
                      : "Dataset workspace"}
                  </strong>
                  <span>
                    {batch
                      ? `${dateFmt(batch.inspection.date_start)}${batch.inspection.date_end ? ` — ${dateFmt(batch.inspection.date_end)}` : ""} · ${batch.row_count} recorded days`
                      : "Connect your first dataset to get started"}
                  </span>
                </div>
              </div>
              <div className="context-actions">
                {status && status.batches.length > 1 && (
                  <label className="sr-only" htmlFor="batch-select">
                    Select import batch
                  </label>
                )}
                {status && status.batches.length > 1 && (
                  <select
                    id="batch-select"
                    value={batchId ?? ""}
                    onChange={(e) => setBatchId(Number(e.target.value))}
                  >
                    {status.batches.map((b) => (
                      <option key={b.id} value={b.id}>
                        Batch {b.id} · {b.source.kind} · {b.filename}
                      </option>
                    ))}
                  </select>
                )}
                {batch && <Badge synthetic={synthetic} />}
                <button
                  className="icon-button"
                  aria-label="Refresh data"
                  disabled={loading}
                  onClick={() => void loadStatus()}
                >
                  <RefreshCw size={16} className={loading ? "spin" : ""} />
                </button>
              </div>
            </div>
          )}
          {view === "demo" ? (
            <DemoJourney
              go={(id) => {
                setDemoRequested(true);
                go(id);
              }}
            />
          ) : view === "impact" ? (
            <ImpactLedger />
          ) : view === "decisions" ? (
            <DecisionStudio batch={batch ?? null} demoStart={demoRequested} />
          ) : error ? (
            <div role="alert" className="error-state">
              <Info size={24} />
              <h2>We couldn’t load the workspace</h2>
              <p>{error}</p>
              <button className="button" onClick={() => void loadStatus()}>
                Try again
              </button>
            </div>
          ) : view === "methodology" ? (
            <Methodology />
          ) : view === "forecast" ? (
            <ForecastLab
              key={batchId ?? "empty"}
              batchId={batchId}
              revision={revision}
              onImport={() => setUploadOpen(true)}
            />
          ) : loading ? (
            <div className="loading-state" role="status">
              <LoaderCircle className="spin" size={26} />
              <p>Reading your measurements…</p>
              <div className="skeleton-row">
                {[1, 2, 3, 4].map((x) => (
                  <div key={x} />
                ))}
              </div>
            </div>
          ) : !overview || !charts ? (
            <Panel title="Every better decision starts with real data">
              <Empty title="Your workspace is ready">
                <p>
                  Import the Finland school workbook or a compatible CSV.
                  <br />
                  No measurements are shown until you supply a dataset.
                </p>
                <button
                  className="button primary"
                  onClick={() => setUploadOpen(true)}
                >
                  <Upload size={16} /> Import your first dataset
                </button>
                <a
                  href="https://zenodo.org/records/20825233"
                  target="_blank"
                  rel="noreferrer"
                >
                  Get the official workbook <ExternalLink size={13} />
                </a>
              </Empty>
            </Panel>
          ) : (
            <>
              {synthetic && (
                <div className="caution">
                  <FlaskConical size={19} />
                  <div>
                    <strong>Synthetic test data</strong>
                    <p>
                      These values are a test fixture. They are not real
                      measurements, savings, or intervention evidence.
                    </p>
                  </div>
                </div>
              )}
              {view === "overview" && (
                <>
                  <MetricCards metrics={overview.metrics} />
                  <div className="overview-middle">
                    <TrendChart
                      charts={charts}
                      batch={overview.batch}
                      compact
                    />
                    <SourceCard batch={overview.batch} go={go} />
                  </div>
                  <div className="overview-bottom">
                    <PeriodComparison overview={overview} />
                    <MenuAnalysis
                      charts={charts}
                      compact
                      onExpand={() => go("menus")}
                    />
                  </div>
                  <div className="interpretation">
                    <Info size={16} />
                    <p>
                      Observation, before optimization. This dashboard describes
                      recorded waste; it does not estimate production, prove
                      causation, or claim savings.
                    </p>
                    <button onClick={() => go("methodology")}>
                      Read methodology <ArrowRight size={14} />
                    </button>
                  </div>
                </>
              )}
              {view === "trends" && (
                <>
                  <MetricCards metrics={overview.metrics} />
                  <TrendChart charts={charts} batch={overview.batch} />
                  <PeriodComparison overview={overview} />
                  <RecordTable records={charts.daily} />
                </>
              )}
              {view === "menus" && (
                <>
                  <MenuAnalysis charts={charts} />
                  <MenuTable charts={charts} />
                </>
              )}
              {view === "data" && (
                <DataView
                  batch={overview.batch}
                  status={status!}
                  charts={charts}
                  onSelect={setBatchId}
                  onUpload={() => setUploadOpen(true)}
                />
              )}
            </>
          )}
          <footer>
            <span>
              <Leaf size={14} /> MealLoop OS{" "}
              <span className="footer-dot">·</span> Built for a less wasteful
              tomorrow.
            </span>
            <span>
              Arbiter Hacks V1 <span className="footer-dot">/</span> Rethinking
              Waste
            </span>
            <a href="/assets/third-party-notices.txt" target="_blank" rel="noreferrer">
              Third-party notices
            </a>
          </footer>
        </main>
      </div>
      {uploadOpen && !publicDemo && (
        <ImportDialog
          onClose={() => setUploadOpen(false)}
          onImported={async (b) => {
            setUploadOpen(false);
            setNotice(
              `Imported ${b.row_count} records. ${b.inspection.flagged_rows} row(s) have audit notes.`,
            );
            await loadStatus(b.id);
          }}
        />
      )}
    </div>
  );
}

function MetricCards({ metrics: m }: { metrics: Metrics }) {
  const cards = [
    {
      label: "Total plate waste",
      value: m.plate_waste_kg,
      unit: "kg",
      icon: Utensils,
      note: `${m.coverage.plate_days} of ${m.days} days recorded`,
      style: "",
    },
    {
      label: "Kitchen & serving waste",
      value: m.kitchen_serving_waste_kg,
      unit: "kg",
      icon: Layers3,
      note: `${m.coverage.kitchen_days} of ${m.days} days recorded`,
      style: "",
    },
    {
      label: "Combined recorded waste",
      value: m.combined_recorded_waste_kg,
      unit: "kg",
      icon: BarChart3,
      note: "Sum of available mass measurements",
      style: "featured",
    },
    {
      label: "Average waste per diner",
      value: m.average_waste_per_diner_g,
      unit: "g",
      icon: Users,
      note: `Diner-weighted · ${m.coverage.per_diner_days} complete days`,
      style: "",
    },
  ];
  return (
    <div className="metric-grid">
      {cards.map((c) => (
        <section key={c.label} className={`metric-card ${c.style}`}>
          <div className="metric-label">
            {c.label}
            <span className="metric-icon">
              <c.icon size={17} />
            </span>
          </div>
          <div className="metric-value">
            {fmt(c.value)}
            <span>{c.unit}</span>
          </div>
          <p>
            <span className="tiny-dot" />
            {c.note}
          </p>
        </section>
      ))}
    </div>
  );
}

function TrendChart({
  charts,
  batch,
  compact = false,
}: {
  charts: Charts;
  batch: Batch;
  compact?: boolean;
}) {
  const [phase, setPhase] = useState("all");
  const [unit, setUnit] = useState("kg");
  const records = charts.daily.filter(
    (d) => phase === "all" || d.phase === phase,
  );
  const hasSplit =
    batch.baseline_days != null &&
    batch.baseline_days > 0 &&
    batch.baseline_days < batch.row_count;
  const data = records.map((d) => ({ ...d, tick: `Day ${d.day_index}` }));
  return (
    <Panel
      title="Daily waste trend"
      eyebrow="THE DAILY PICTURE"
      className="trend-panel"
      action={
        <div className="chart-controls">
          <label
            className="sr-only"
            htmlFor={compact ? "phase-compact" : "phase"}
          >
            Trend period
          </label>
          <select
            id={compact ? "phase-compact" : "phase"}
            value={phase}
            onChange={(e) => setPhase(e.target.value)}
          >
            <option value="all">All recorded days</option>
            {hasSplit && (
              <>
                <option value="baseline">Baseline</option>
                <option value="intervention">Intervention</option>
              </>
            )}
          </select>
          {!compact && (
            <select
              aria-label="Trend unit"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
            >
              <option value="kg">Total mass · kg</option>
              <option value="g">Per diner · g</option>
            </select>
          )}
        </div>
      }
    >
      <div className="chart-legend">
        <span>
          <i className="legend-dot plate" />
          {unit === "kg" ? "Plate waste" : "Combined waste"}
        </span>
        {unit === "kg" && (
          <span>
            <i className="legend-dot kitchen" />
            Kitchen & serving
          </span>
        )}
        {unit === "g" && <span>Complete days only</span>}
        <span className="chart-unit">
          {unit === "kg" ? "Kilograms / day" : "Grams / diner"}
        </span>
      </div>
      <div
        className={`trend-chart ${compact ? "" : "large"}`}
        role="img"
        aria-label={`Daily waste chart with ${records.length} school days; values available in the record table.`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 16, right: 16, left: -20, bottom: 0 }}
          >
            <defs>
              <linearGradient
                id={`plate-${compact}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="0%" stopColor="#587951" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#587951" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient
                id={`kitchen-${compact}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="0%" stopColor="#b6bf83" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#b6bf83" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 5"
              vertical={false}
              stroke="#e9ece5"
            />
            <XAxis
              dataKey="day_index"
              tickFormatter={(v) => `Day ${v}`}
              minTickGap={32}
              tick={{ fontSize: 11, fill: "#7c8579" }}
              axisLine={false}
              tickLine={false}
              dy={8}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#7c8579" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              labelFormatter={(_, payload) => {
                const d = payload?.[0]?.payload as Daily | undefined;
                return d
                  ? `Day ${d.day_index} · ${d.date ? dateFmt(d.date) : "No date supplied"} · ${d.phase}`
                  : "";
              }}
              formatter={(v, name) => [
                `${fmt(Number(v))} ${unit}`,
                String(name),
              ]}
              contentStyle={{
                borderRadius: 10,
                border: "1px solid #e5e8df",
                fontSize: 12,
              }}
            />
            {hasSplit && phase === "all" && (
              <ReferenceLine
                x={batch.baseline_days! + 1}
                stroke="#8b9578"
                strokeDasharray="4 4"
                label={{
                  value: "Intervention",
                  position: "insideTopLeft",
                  fill: "#7c8579",
                  fontSize: 10,
                }}
              />
            )}
            {unit === "kg" ? (
              <>
                <Area
                  name="Kitchen & serving"
                  type="linear"
                  dataKey="kitchen_serving_waste_kg"
                  stroke="#adb77c"
                  fill={`url(#kitchen-${compact})`}
                  strokeWidth={1.7}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                <Area
                  name="Plate waste"
                  type="linear"
                  dataKey="plate_waste_kg"
                  stroke="#55774e"
                  fill={`url(#plate-${compact})`}
                  strokeWidth={2}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </>
            ) : (
              <Area
                name="Combined waste"
                dataKey="waste_per_diner_g"
                stroke="#55774e"
                fill={`url(#plate-${compact})`}
                strokeWidth={2}
                connectNulls={false}
                isAnimationActive={false}
              />
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="chart-footnote">
        Source row order preserved.{" "}
        {batch.inspection.date_count === 0
          ? "Dates are unavailable; the x-axis uses school-day sequence."
          : "School-day sequence on the x-axis; hover for recorded dates."}{" "}
        Gaps indicate missing measurements.
      </p>
    </Panel>
  );
}

function SourceCard({ batch: b, go }: { batch: Batch; go: (v: View) => void }) {
  return (
    <section className="source-card">
      <div className="source-top">
        <span className="source-icon">
          <FileSpreadsheet size={21} />
        </span>
        <span className="connected">
          <Check size={12} /> Imported
        </span>
      </div>
      <p className="eyebrow">YOUR DATA, IN CONTEXT</p>
      <h2>
        {b.inspection.verified_official_file
          ? "Real school days.\nReal measurements."
          : "A traceable source.\nA clearer starting point."}
      </h2>
      <p>
        {b.inspection.verified_official_file
          ? "Daily food waste from a secondary school in Western Finland."
          : b.source.title}
      </p>
      <div className="source-stats">
        <div>
          <strong>{b.row_count}</strong>
          <span>school days</span>
        </div>
        <div>
          <strong>
            {b.baseline_days ?? "—"}{" "}
            <small>
              / {b.baseline_days == null ? "—" : b.row_count - b.baseline_days}
            </small>
          </strong>
          <span>baseline / intervention</span>
        </div>
      </div>
      <div className="source-quality">
        <Info size={15} />
        <span>
          {b.inspection.flagged_rows} rows with audit notes. Missing values and
          source conflicts stay visible.
        </span>
      </div>
      <button onClick={() => go("data")}>
        Explore source & quality <ArrowRight size={16} />
      </button>
    </section>
  );
}

function PeriodComparison({ overview: o }: { overview: Overview }) {
  const baseline = o.periods.find((p) => p.phase === "baseline");
  const intervention = o.periods.find((p) => p.phase === "intervention");
  return (
    <Panel
      title="Baseline & intervention"
      eyebrow="A DESCRIPTIVE COMPARISON"
      action={<span className="subtle-tag">Observed periods</span>}
    >
      {!baseline || !intervention ? (
        <p className="panel-message">
          No two-period split is assigned. The official workbook uses the first
          135 and last 20 rows; custom uploads need an explicit baseline count.
        </p>
      ) : (
        <>
          <p className="panel-description">
            Average daily waste on days with both mass measurements.
          </p>
          <div className="period-head">
            <span>Recorded period</span>
            <span>kg / day</span>
            <span>g / diner</span>
          </div>
          {[baseline, intervention].map((p, i) => (
            <div className="period-row" key={p.phase}>
              <div>
                <span className={`period-marker ${i ? "intervention" : ""}`} />
                <div>
                  <strong>{i ? "Intervention" : "Baseline"}</strong>
                  <span>
                    {p.days} days · {p.coverage.complete_days} complete mass
                    days
                  </span>
                  <span>
                    {p.coverage.per_diner_days} per-diner days ·{" "}
                    {fmt(p.coverage.per_diner_diners, 0)} diners
                  </span>
                </div>
              </div>
              <strong>{fmt(p.average_daily_combined_kg)}</strong>
              <strong>{fmt(p.average_waste_per_diner_g)}</strong>
            </div>
          ))}
          <p className="scientific-note">
            <Info size={14} /> Different periods and diner counts. These figures
            do not establish a causal effect.
          </p>
        </>
      )}
    </Panel>
  );
}

function MenuAnalysis({
  charts,
  compact = false,
  onExpand,
}: {
  charts: Charts;
  compact?: boolean;
  onExpand?: () => void;
}) {
  const [sort, setSort] = useState("menu");
  const all = [...charts.menus].sort((a, b) =>
    sort === "waste"
      ? (b.average_waste_per_diner_g ?? -1) -
        (a.average_waste_per_diner_g ?? -1)
      : a.menu - b.menu,
  );
  const data = (
    compact
      ? [...all]
          .sort(
            (a, b) =>
              (b.average_waste_per_diner_g ?? -1) -
              (a.average_waste_per_diner_g ?? -1),
          )
          .slice(0, 6)
      : all
  ).map((m) => ({ ...m, label: `Menu ${m.menu}` }));
  return (
    <Panel
      title="Waste by menu"
      eyebrow="THE LUNCH CYCLE"
      action={
        compact ? (
          <button className="text-button" onClick={onExpand}>
            View all <ArrowRight size={14} />
          </button>
        ) : (
          <select
            aria-label="Menu sorting"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            <option value="menu">Menu identifier</option>
            <option value="waste">Highest waste per diner</option>
          </select>
        )
      }
    >
      <p className="panel-description">
        Diner-weighted combined waste · grams per diner
        {compact ? " · six highest observed" : ""}
      </p>
      {!data.length ? (
        <Empty title="No menu identifiers">
          <p>Menu data was not supplied with this import.</p>
        </Empty>
      ) : (
        <div
          style={{ height: compact ? 206 : Math.max(280, data.length * 29) }}
          role="img"
          aria-label="Waste by menu chart; exact values are in the menu table."
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ left: -10, right: 30, top: 12 }}
            >
              <CartesianGrid
                horizontal={false}
                strokeDasharray="3 5"
                stroke="#e9ece5"
              />
              <XAxis
                type="number"
                tick={{ fontSize: 10, fill: "#7c8579" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey="label"
                tick={{ fontSize: 11, fill: "#566151" }}
                axisLine={false}
                tickLine={false}
                width={72}
              />
              <Tooltip
                formatter={(v) => [
                  `${fmt(Number(v))} g / diner`,
                  "Combined waste",
                ]}
                contentStyle={{
                  borderRadius: 10,
                  border: "1px solid #e5e8df",
                  fontSize: 12,
                }}
                cursor={{ fill: "#f3f5ee" }}
              />
              <Bar
                dataKey="average_waste_per_diner_g"
                fill="#91a27b"
                radius={[0, 3, 3, 0]}
                barSize={compact ? 12 : 16}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="chart-footnote">
        Menu numbers identify meals, not portion sizes. Exposure and period mix
        differ.
        {charts.menu_missing_days > 0 &&
          ` ${charts.menu_missing_days} day(s) have no menu identifier.`}
      </p>
    </Panel>
  );
}

function MenuTable({ charts }: { charts: Charts }) {
  return (
    <Panel title="Menu measurements">
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Menu identifier</th>
              <th>Days</th>
              <th>Complete days</th>
              <th>Plate · kg</th>
              <th>Kitchen · kg</th>
              <th>Combined · g/diner</th>
            </tr>
          </thead>
          <tbody>
            {charts.menus.map((m) => (
              <tr key={m.menu}>
                <td>
                  <strong>Menu {m.menu}</strong>
                </td>
                <td>{m.days}</td>
                <td>{m.coverage.complete_days}</td>
                <td>{fmt(m.plate_waste_kg, 3)}</td>
                <td>{fmt(m.kitchen_serving_waste_kg, 3)}</td>
                <td>{fmt(m.average_waste_per_diner_g, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="chart-footnote">
        Combined per-diner values use only complete mass days with positive
        diner counts. Missing values appear as —.
      </p>
    </Panel>
  );
}

function RecordTable({
  records,
  flaggedOnly = false,
}: {
  records: Daily[];
  flaggedOnly?: boolean;
}) {
  const [page, setPage] = useState(0);
  const data = flaggedOnly
    ? records.filter((r) => r.issues.length > 0)
    : records;
  useEffect(() => setPage(0), [records, flaggedOnly]);
  const pages = Math.max(1, Math.ceil(data.length / 15));
  return (
    <Panel
      title={flaggedOnly ? "Rows with audit notes" : "Daily measurement ledger"}
      action={<span className="subtle-tag">{data.length} records</span>}
    >
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Day / row</th>
              <th>Recorded date</th>
              <th>Menu</th>
              <th>Diners</th>
              <th>Plate · kg</th>
              <th>Kitchen · kg</th>
              <th>Audit notes</th>
            </tr>
          </thead>
          <tbody>
            {data.slice(page * 15, page * 15 + 15).map((r) => (
              <tr key={r.day_index}>
                <td>
                  <strong>{r.day_index}</strong>{" "}
                  <span className="muted">/ {r.source_row}</span>
                </td>
                <td>{r.date ? dateFmt(r.date) : "—"}</td>
                <td>{r.menu ?? "—"}</td>
                <td>{r.diners ?? "—"}</td>
                <td>{fmt(r.plate_waste_kg, 3)}</td>
                <td>{fmt(r.kitchen_serving_waste_kg, 3)}</td>
                <td className="audit-cell">
                  {r.issues.length ? (
                    r.issues.map((issue) => (
                      <span key={issue} className="issue-tag">
                        {humanIssue(issue)}
                      </span>
                    ))
                  ) : (
                    <span className="muted">No flags</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!data.length && (
        <p className="panel-message">No rows have audit notes.</p>
      )}
      <div className="pagination">
        <span>
          Page {page + 1} of {pages} · Missing values appear as —
        </span>
        <div>
          <button
            className="button small"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </button>
          <button
            className="button small"
            disabled={page + 1 >= pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </Panel>
  );
}

function DataView({
  batch: b,
  status,
  charts,
  onSelect,
  onUpload,
}: {
  batch: Batch;
  status: Status;
  charts: Charts;
  onSelect: (id: number) => void;
  onUpload: () => void;
}) {
  const publicDemo = useRuntime().read_only;
  const [allRows, setAllRows] = useState(false);
  return (
    <div className="data-view">
      <div className="data-columns">
        <Panel
          title="Source & provenance"
          eyebrow="A TRACEABLE FOUNDATION"
          action={<Badge synthetic={b.source.kind === "synthetic"} />}
        >
          <h3>{b.source.title}</h3>
          <p className="panel-description">
            {b.source.authors ||
              "User-supplied source; attribution has not been independently verified."}
          </p>
          <dl className="details">
            <div>
              <dt>Origin</dt>
              <dd>
                {b.inspection.verified_official_file
                  ? "Official file · checksum verified"
                  : "Local upload · provenance unverified"}
              </dd>
            </div>
            <div>
              <dt>License</dt>
              <dd>{b.source.license}</dd>
            </div>
            <div>
              <dt>DOI</dt>
              <dd>
                {b.source.doi ? (
                  <a
                    target="_blank"
                    rel="noreferrer"
                    href={`https://doi.org/${b.source.doi}`}
                  >
                    {b.source.doi} <ExternalLink size={12} />
                  </a>
                ) : (
                  "Not supplied"
                )}
              </dd>
            </div>
            <div>
              <dt>Worksheet</dt>
              <dd>{b.inspection.sheet}</dd>
            </div>
            <div>
              <dt>Imported</dt>
              <dd>
                {new Date(
                  b.imported_at.endsWith("Z") ||
                    /[+-]\d\d:\d\d$/.test(b.imported_at)
                    ? b.imported_at
                    : `${b.imported_at}Z`,
                ).toLocaleString("en-GB")}
              </dd>
            </div>
            <div>
              <dt>Ordering</dt>
              <dd>Original source row order</dd>
            </div>
          </dl>
          {b.source.url && (
            <a
              className="button"
              target="_blank"
              rel="noreferrer"
              href={b.source.url}
            >
              Open official record <ExternalLink size={14} />
            </a>
          )}
          <details className="technical-details">
            <summary>File checksum & column mapping</summary>
            <p>SHA-256</p>
            <code>{b.sha256}</code>
            <dl>
              {Object.entries(b.inspection.header_mapping).map(([h, f]) => (
                <div key={h}>
                  <dt>{h}</dt>
                  <dd>{f}</dd>
                </div>
              ))}
            </dl>
            {b.inspection.ignored_columns.length > 0 && (
              <p>Ignored columns: {b.inspection.ignored_columns.join(", ")}</p>
            )}
          </details>
        </Panel>
        <Panel title="Data quality" eyebrow="NOTHING HIDDEN">
          <div className="quality-summary">
            <span className="quality-count">{b.inspection.flagged_rows}</span>
            <div>
              <strong>rows with audit notes</strong>
              <p>Out of {b.row_count} source records</p>
            </div>
          </div>
          <div className="quality-list">
            {Object.entries(b.inspection.issue_counts).map(([issue, count]) => (
              <div key={issue}>
                <span>{humanIssue(issue)}</span>
                <strong>{count}</strong>
              </div>
            ))}
            {!Object.keys(b.inspection.issue_counts).length && (
              <p>
                <CheckCircle2 size={16} /> No import flags found.
              </p>
            )}
          </div>
          <p className="scientific-note">
            Kilogram columns determine mass totals. Conflicting reported values
            are retained in the API for audit. Missing measurements are not
            imputed.
          </p>
          {!b.inspection.date_ordered && (
            <p className="caution">
              Dates are not chronological. Original row order was retained.
            </p>
          )}
          <button className="text-button" onClick={() => setAllRows((v) => !v)}>
            {allRows ? "Show only flagged records" : "Show all source records"}{" "}
            <ArrowRight size={14} />
          </button>
        </Panel>
      </div>
      <RecordTable key={b.id} records={charts.daily} flaggedOnly={!allRows} />
      <Panel
        title="Import history"
        action={
          !publicDemo ? (
            <button className="button small" onClick={onUpload}>
              <Upload size={14} /> New import
            </button>
          ) : (
            <span className="subtle-tag">Fixed public dataset</span>
          )
        }
      >
        <div className="batch-list">
          {status.batches.map((item) => (
            <button
              key={item.id}
              className={`batch-item ${item.id === b.id ? "selected" : ""}`}
              onClick={() => onSelect(item.id)}
            >
              <FileSpreadsheet size={22} />
              <div>
                <strong>{item.filename}</strong>
                <span>
                  Batch {item.id} · {item.row_count} rows · {item.source.kind}
                  {item.inspection.verified_official_file
                    ? " · verified Zenodo file"
                    : ""}
                </span>
              </div>
              {item.id === b.id ? (
                <span className="subtle-tag">
                  <Check size={13} /> Selected
                </span>
              ) : (
                <ArrowRight size={16} />
              )}
            </button>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function Methodology() {
  return (
    <div className="methodology">
      <div className="method-intro">
        <span className="empty-icon">
          <ShieldCheck size={28} />
        </span>
        <div>
          <p className="eyebrow">EVIDENCE FIRST</p>
          <h2>Useful intelligence starts with honest numbers.</h2>
          <p>
            MealLoop OS makes recorded food waste understandable and auditable.
            Forecast Lab evaluates historical waste predictions. Decision Studio
            explores production plans from explicitly supplied demand
            assumptions. Impact Ledger records service reports, measurement
            boundaries and append-only correction history.
          </p>
        </div>
      </div>
      <div className="method-grid">
        {[
          [
            "01",
            "One measurement, one contribution",
            "Plate waste and kitchen/serving waste are separate mass streams. Combined recorded waste sums available kilograms from both. Gram and per-diner columns are alternate representations, never additional waste.",
          ],
          [
            "02",
            "A denominator that matches",
            "Average waste per diner = 1,000 × sum of combined kg ÷ sum of diners, using only rows with both mass values and positive diner counts. It is a diner-weighted average, not an average of daily ratios. Coverage is displayed alongside the result.",
          ],
          [
            "03",
            "Missing stays missing",
            "A missing value is not zero. Component totals use available observations; combined daily charts and daily averages require both waste streams. Zero diners produce an unavailable per-diner metric. Source conflicts are flagged and the kg fields take precedence.",
          ],
          [
            "04",
            "Sequence before assumptions",
            "The verified Finland workbook has dates. Original row order is always preserved. The source defines 135 baseline rows followed by 20 intervention rows. Custom uploads have no period assignment unless you explicitly supply a baseline count.",
          ],
          [
            "05",
            "Comparison is not causation",
            "The original researchers studied artist-designed interventions. MealLoop OS did not cause those interventions or their results. Unequal period lengths, menus, diner counts, and other confounders prevent a causal claim from these descriptive comparisons.",
          ],
          [
            "06",
            "A foundation, with clear limits",
            "Waste records do not reveal production or servings prepared. Forecast Lab adds model estimates with executed chronological validation, explicit quality exclusions, and a separate holdout. Decision Studio optimizes assumed demand scenarios independently. Its modeled surplus differences do not establish realized savings or operational effectiveness.",
          ],
        ].map(([n, title, text]) => (
          <section className="panel method-card" key={n}>
            <span>{n}</span>
            <h3>{title}</h3>
            <p>{text}</p>
          </section>
        ))}
      </div>
      <Panel title="Research attribution">
        <p>
          Arja Kuusisto, Jenni Latva & Ella Wilén (2026).{" "}
          <em>Food waste dataset: secondary school in Finland 2024–2025.</em>{" "}
          Zenodo. DOI: 10.5281/zenodo.20825233.
        </p>
        <p>
          Reused under{" "}
          <a
            href="https://creativecommons.org/licenses/by/4.0/"
            target="_blank"
            rel="noreferrer"
          >
            CC BY 4.0
          </a>
          . The original workbook is unchanged; MealLoop OS normalizes its
          fields and computes descriptive summaries. No endorsement is implied.
        </p>
        <a
          className="text-button"
          href="https://zenodo.org/records/20825233"
          target="_blank"
          rel="noreferrer"
        >
          View dataset record <ExternalLink size={14} />
        </a>
      </Panel>
    </div>
  );
}

function ImportDialog({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: (b: Batch) => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState("measured");
  const [baseline, setBaseline] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const dialogRef = useRef<HTMLDivElement>(null);
  const busyRef = useRef(false);
  useEffect(() => {
    const oldFocus = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busyRef.current) onClose();
      if (e.key === "Tab") {
        const items = Array.from(
          dialogRef.current?.querySelectorAll<HTMLElement>(
            "button:not([disabled]), a[href], input:not([disabled]), select:not([disabled])",
          ) || [],
        );
        const first = items[0],
          last = items.at(-1);
        if (
          e.shiftKey &&
          (document.activeElement === first ||
            document.activeElement === dialogRef.current)
        ) {
          e.preventDefault();
          last?.focus();
        } else if (
          !e.shiftKey &&
          (document.activeElement === last ||
            document.activeElement === dialogRef.current)
        ) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      oldFocus?.focus();
    };
  }, [onClose]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Select a workbook or CSV file first.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError("The maximum file size is 10 MiB.");
      return;
    }
    setError("");
    setBusy(true);
    busyRef.current = true;
    const body = new FormData();
    body.append("file", file);
    body.append("source_kind", kind);
    if (baseline !== "") body.append("baseline_days", baseline);
    try {
      const batch = await api<Batch>("/dataset/import", {
        method: "POST",
        body,
      });
      await onImported(batch);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      busyRef.current = false;
    }
  }
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className="import-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="import-title"
      >
        <div className="dialog-heading">
          <span className="empty-icon">
            <Upload size={23} />
          </span>
          <button
            className="icon-button"
            aria-label="Close import dialog"
            onClick={onClose}
            disabled={busy}
          >
            <X size={20} />
          </button>
        </div>
        <p className="eyebrow">CONNECT YOUR MEASUREMENTS</p>
        <h2 id="import-title">Import a dataset</h2>
        <p>
          Upload the original Zenodo workbook or a compatible CSV. Your data
          stays in this local workspace.
        </p>
        <form onSubmit={submit}>
          <label className="dropzone">
            <FileSpreadsheet size={30} />
            <strong>{file?.name || "Choose a workbook or CSV"}</strong>
            <span>.xlsx or UTF-8 .csv · up to 10 MiB</span>
            <input
              type="file"
              accept=".xlsx,.csv"
              disabled={busy}
              aria-label="Dataset file"
              onChange={(e) => {
                setFile(e.target.files?.[0] || null);
                setError("");
              }}
            />
          </label>
          <label className="field">
            Data kind
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              disabled={busy}
            >
              <option value="measured">Measured observations</option>
              <option value="synthetic">Synthetic test fixture</option>
            </select>
          </label>
          <label className="field">
            Baseline days{" "}
            <span className="muted">(optional for custom files)</span>
            <input
              type="number"
              min="0"
              max="10000"
              step="1"
              placeholder="Auto: 135 for the verified Zenodo workbook"
              value={baseline}
              onChange={(e) => setBaseline(e.target.value)}
              disabled={busy}
            />
          </label>
          <p className="field-help">
            For other files, leaving this blank keeps periods unassigned.
            Identical file uploads are rejected; identical daily rows are
            preserved and flagged.
          </p>
          {kind === "synthetic" && (
            <p className="caution">
              This import will be prominently labeled as synthetic test data.
            </p>
          )}
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
          <div className="import-links">
            <a
              target="_blank"
              rel="noreferrer"
              href="https://zenodo.org/records/20825233"
            >
              Official dataset <ExternalLink size={13} />
            </a>
            <a href="/template.csv" download>
              <ArrowDownToLine size={13} /> CSV template
            </a>
          </div>
          <div className="dialog-footer">
            <button
              type="button"
              className="button"
              onClick={onClose}
              disabled={busy}
            >
              Cancel
            </button>
            <button
              className="button primary"
              type="submit"
              disabled={busy || !file}
            >
              {busy ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Upload size={16} />
              )}
              {busy ? "Validating & importing…" : "Validate & import"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
