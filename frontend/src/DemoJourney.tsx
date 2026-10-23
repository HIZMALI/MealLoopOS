import {
  ArrowRight,
  BarChart3,
  FlaskConical,
  Scale,
  ClipboardList,
} from "lucide-react";

export default function DemoJourney({
  go,
}: {
  go: (view: "overview" | "forecast" | "decisions" | "impact") => void;
}) {
  const steps = [
    {
      view: "overview",
      icon: BarChart3,
      tag: "REAL HISTORICAL MEASUREMENTS",
      title: "Understand what was wasted",
      description:
        "Explore 155 school days from Finland. Check trends, missing measurements and descriptive period comparisons.",
      action: "Open Waste Intelligence",
    },
    {
      view: "forecast",
      icon: FlaskConical,
      tag: "EVALUATED MODEL ESTIMATES",
      title: "Inspect the forecasting evidence",
      description:
        "See why the recent 10-day mean beat Ridge on chronological validation. One school and 18 eligible holdout days limit generalization.",
      action: "Explore Forecast Lab",
    },
    {
      view: "decisions",
      icon: Scale,
      tag: "SYNTHETIC DEMAND ASSUMPTIONS",
      title: "Try a production decision",
      description:
        "Run the example, then change reliability from 95% to 70%. Compare surplus and unmet demand under your assumptions.",
      action: "Try the kitchen scenario",
    },
    {
      view: "impact",
      icon: ClipboardList,
      tag: "SYNTHETIC OPERATIONAL ACCOUNTING",
      title: "Follow the evidence",
      description:
        "Inspect 440 prepared, 400 served and 40 remaining portions. Keep the 8 kg estimate separate from the simulated 7.6 kg surplus reading.",
      action: "Inspect Impact Ledger",
    },
  ] as const;
  return (
    <div className="demo-journey">
      <div className="demo-intro">
        <span className="badge">A 2–3 MINUTE GUIDED JOURNEY</span>
        <h2>Measure. Forecast. Decide. Verify.</h2>
        <p>
          Four connected tools, with clear boundaries between evidence and
          assumptions. Start anywhere; each step explains what the result can
          support.
        </p>
      </div>
      <div className="demo-steps">
        {steps.map((step, i) => (
          <section className="panel demo-step" key={step.view}>
            <div className="demo-step-top">
              <span className="demo-number">0{i + 1}</span>
              <step.icon size={24} />
            </div>
            <p className="eyebrow">{step.tag}</p>
            <h2>{step.title}</h2>
            <p>{step.description}</p>
            <a
              className="button"
              href={`#${step.view}`}
              onClick={(e) => {
                e.preventDefault();
                go(step.view);
              }}
            >
              {step.action}
              <ArrowRight size={15} />
            </a>
          </section>
        ))}
      </div>
      <section className="panel demo-boundaries">
        <h2>What this demonstration establishes</h2>
        <p>
          The Finland workbook is real, attributed historical data. Forecasts
          are estimates; optimization depends on assumed demand. All operational
          examples are synthetic, including their scale readings. No prospective
          kitchen pilot, independently verified outcome or causal waste
          reduction has been established.
        </p>
        <p>
          The study’s original intervention predates MealLoop OS. Modeled
          surplus differences are not achieved savings.
        </p>
        <a
          href="https://doi.org/10.5281/zenodo.20825233"
          target="_blank"
          rel="noreferrer"
        >
          Kuusisto, Latva & Wilén · Zenodo · CC BY 4.0
        </a>
      </section>
    </div>
  );
}
