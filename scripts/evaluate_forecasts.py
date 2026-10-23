"""Reproduce the frozen protocol from normalized official measurements, offline."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import select
from app.database import ROOT, database_url, make_engine, migrate, sessions
from app.forecast_service import load_data, prepare
from app.forecasting import ForecastProblem
from app.models import ImportBatch, SourceDataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", type=int)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/evaluation/build_02_evaluation.json")
    args = parser.parse_args()
    engine = make_engine(database_url())
    try:
        migrate(engine)
        with sessions(engine)() as session:
            batch_id = args.batch_id or session.scalar(select(ImportBatch.id).join(SourceDataset)
                .where(SourceDataset.key == "zenodo:20825233").order_by(ImportBatch.id.desc()).limit(1))
            if not batch_id:
                parser.error("No official measured batch. Run scripts/import_dataset.py with the bundled real workbook first.")
            batch, source, _, _ = load_data(session, batch_id)
            if source.kind != "measured" or not batch.inspection.get("verified_official_file"):
                parser.error("Reproducible scientific evidence requires the verified official measured batch.")
            # Always execute a fresh evaluation for reproducibility; API preparation is cached.
            from app.forecasting import evaluate, validate_dataset
            _, _, rows, fingerprint = load_data(session, batch_id)
            validate_dataset(batch, source, rows)
            fresh, predictor = evaluate(rows)
            artifact = prepare(session, batch_id)
            fresh.update({k: artifact.evaluation[k] for k in ("dataset_fingerprint", "raw_sha256", "source", "model_id")})
            if fresh != artifact.evaluation or predictor != artifact.predictor:
                raise ForecastProblem("Recomputed results differ from the persisted artifact. Do not publish inconsistent evidence; inspect environment/version changes.")
            args.output.parent.mkdir(exist_ok=True, parents=True)
            args.output.write_text(json.dumps(fresh, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
            print(json.dumps({"selected_method": fresh["selected_method"], "fingerprint": fingerprint,
                "validation": fresh["validation_metrics"], "holdout": fresh["holdout_metrics"],
                "coverage": {k: fresh[k]["eligible"] for k in ("baseline_period", "holdout_period", "production_training")},
                "output": str(args.output)}, indent=2))
    except ForecastProblem as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
