"""Rebuildable demo state from public files only. Never reads the local database."""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, text

from .database import ROOT, make_engine, migrate, sessions
from .models import DailyRecord, ImportBatch, SourceDataset, ForecastArtifact, ForecastRun, DecisionPlan, OperationalRevision, OperationalService

DEMO_DIR = ROOT / ".public-demo"
RAW = "data/raw/Food waste data school Finland 2024-2025.xlsx"
ARTIFACT = "data/public_demo/forecast_artifact.json"
FINGERPRINTS = {
    RAW: "2ffad746b7ed5d536a0c99c37d8e249230d95d5fb2d041d85d01b69499f99624",
    "docs/evaluation/build_02_evaluation.json": "0d5bdc9386b3661502a48b69d5fc602bbf13874dba16ea852bc8a85dbc82092b",
    "docs/evaluation/build_03_evaluation.json": "5ee457fde23650315345cd3d48c21a17e2e5834910f186a5e78d6353105dd5b3",
    "docs/evaluation/build_04_evaluation.json": "d09e6523bcbc6f0efb5748f9b102273b3a1452527a8ce2fd00b9d72d4c8b863c",
    "data/fixtures/synthetic_decision_demo.json": "8e78ae6926b8e2b8233fac40e7d9b3adf328ae8629d9225fb327187a72a14945",
    "data/fixtures/synthetic_impact_demo.json": "d8c74faa720e44a0321fff75920c901479655a9b5ec77e476f000e83ae4bd860",
    ARTIFACT: "2142d76e9139eb62b45d6950599c41c9327f3bd0e4aa9683540f7fdb8655c524",
}
SYNTHETIC_CLOCK = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_files():
    for name, expected in FINGERPRINTS.items():
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or sha(path) != expected:
            raise ValueError(f"Required public source/evidence fingerprint failed: {name}. Restore the committed file; no synthetic fallback.")
    return dict(FINGERPRINTS)


def demo_paths():
    # Fixed server-owned directory. Refuse symlink/junction redirection.
    if DEMO_DIR.is_symlink() or (hasattr(DEMO_DIR, "is_junction") and DEMO_DIR.is_junction()):
        raise ValueError("Demo directory must not be a link.")
    for path in (DEMO_DIR / "demo.db", DEMO_DIR / "manifest.json"):
        if path.is_symlink():
            raise ValueError("Demo files must not be links.")
    return DEMO_DIR / "demo.db", DEMO_DIR / "manifest.json"


def readonly_url():
    db, _ = demo_paths()
    return f"sqlite:///file:{db.as_posix()}?mode=ro&uri=true"


def validate_demo():
    verify_files()
    db, manifest_path = demo_paths()
    if not db.is_file() or not manifest_path.is_file():
        raise ValueError("Public demo is not prepared. Run python scripts/prepare_public_demo.py first.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest != {"kind": "mealloop-public-demo-v1", "migration": "0004", "files": FINGERPRINTS, "database_sha256": sha(db)}:
        raise ValueError("Public demo manifest/integrity check failed. Refusing to serve unreviewed state.")
    engine = make_engine(readonly_url(), readonly=True)
    try:
        with sessions(engine)() as s:
            counts = {m.__tablename__: s.scalar(select(func.count()).select_from(m)) for m in
                      (SourceDataset, ImportBatch, DailyRecord, ForecastArtifact, ForecastRun, DecisionPlan, OperationalService, OperationalRevision)}
            if counts != {"source_datasets": 1, "import_batches": 1, "daily_records": 155, "forecast_artifacts": 1,
                          "forecast_runs": 0, "decision_plans": 1, "operational_services": 2, "operational_revisions": 3}:
                raise ValueError("Demo contains unexpected resource counts; refusing to expose it.")
            source = s.get(SourceDataset, 1)
            if source.key != "zenodo:20825233" or source.kind != "measured" or s.get(ImportBatch, 1).sha256 != FINGERPRINTS[RAW]:
                raise ValueError("Only the official measured source may enter the public dashboard.")
            if any(r.source_category != "synthetic" for r in s.scalars(select(OperationalRevision))):
                raise ValueError("Private operational records must never enter the demo.")
            if s.get(DecisionPlan, 1).inputs["scenario_kind"] != "synthetic_demo":
                raise ValueError("Only an explicit synthetic plan may enter the demo.")
            if s.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != "0004":
                raise ValueError("Unexpected demo migration version.")
            from .forecast_service import CONFIG_KEY, load_data
            _, _, _, fingerprint = load_data(s, 1)
            artifact = s.get(ForecastArtifact, 1)
            if artifact.fingerprint != fingerprint or artifact.config_key != CONFIG_KEY:
                raise ValueError("Prepared forecast/environment mismatch. Use the verified dependency lock; do not retrain at startup.")
    finally:
        engine.dispose()
    return manifest


def prepare_demo():
    verify_files()
    db, manifest_path = demo_paths()
    if db.exists() or manifest_path.exists():
        # Never reset unknown or modified files. Operator may move this generated
        # directory aside when intentionally rebuilding a corrupted demo.
        return validate_demo()
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=DEMO_DIR) as temporary:
        staged = Path(temporary) / "demo.db"
        engine = make_engine(f"sqlite:///{staged.as_posix()}")
        try:
            migrate(engine)
            from .importer import import_file
            from .forecast_service import CONFIG_KEY, load_data
            from . import impact_service
            with sessions(engine)() as s:
                raw = ROOT / RAW
                batch = import_file(s, raw.read_bytes(), raw.name)
                batch.imported_at = SYNTHETIC_CLOCK  # reproducible import timestamp, not a measurement date
                bundle = json.loads((ROOT / ARTIFACT).read_text(encoding="utf-8"))
                report = json.loads((ROOT / "docs/evaluation/build_02_evaluation.json").read_text(encoding="utf-8"))
                if bundle["evaluation"] != report or bundle["config_key"] != CONFIG_KEY:
                    raise ValueError("Prepared forecast evidence/environment mismatch; use the verified lock.")
                _, _, _, fingerprint = load_data(s, 1)
                if fingerprint != report["dataset_fingerprint"]:
                    raise ValueError("Normalized measured source fingerprint changed.")
                s.add(ForecastArtifact(batch_id=1, fingerprint=fingerprint, config_key=CONFIG_KEY,
                    model_id=report["model_id"], created_at=SYNTHETIC_CLOCK, evaluation=report, predictor=bundle["predictor"]))
                s.commit()
                # Fixture capture dates are synthetic, explicitly fixed; never
                # used to imply a prospective kitchen pilot.
                original_clock = impact_service.utc_now
                impact_service.utc_now = lambda: SYNTHETIC_CLOCK
                try:
                    rows = impact_service.add_demo(s)
                finally:
                    impact_service.utc_now = original_clock
                assert rows[0]["assessment"]["accounting"]["remaining_portions"] == 40
                assert rows[0]["assessment"]["accounting"]["estimated_discarded_kg"] == 8
                assert rows[0]["assessment"]["combined_weighed_kg"] == 9.7
                assert rows[1]["assessment"]["accounting"]["unknown_portions"] == 5
                plan = s.get(DecisionPlan, 1)
                assert plan.result["recommended"]["quantity"] == 440
                assert plan.result["comparison"]["potential_surplus_reduction_kg"] == 16
        finally:
            engine.dispose()
        manifest = {"kind": "mealloop-public-demo-v1", "migration": "0004", "files": FINGERPRINTS, "database_sha256": sha(staged)}
        os.replace(staged, db)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return validate_demo()
