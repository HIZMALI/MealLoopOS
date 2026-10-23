import hashlib
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .models import DailyRecord, ImportBatch, SourceDataset
from .parsing import ImportProblem, parse_records

OFFICIAL_MD5 = "3f7e610fedc1810f7e8bc1bd47103ee7"
SYNTHETIC_FIXTURE_SHA256 = "def4f7ca198c1a895b4f0860bfaaedd1aad95bc534d3ee6396d35e18e3b9ea41"
SOURCE = {"key": "zenodo:20825233", "title": "Food waste dataset: secondary school in Finland 2024–2025",
    "kind": "measured", "doi": "10.5281/zenodo.20825233", "url": "https://zenodo.org/records/20825233",
    "authors": "Arja Kuusisto; Jenni Latva; Ella Wilén", "license": "CC BY 4.0"}


class DuplicateImport(ImportProblem):
    pass


def import_file(session, content, filename, kind="measured", baseline_days=None):
    digest = hashlib.sha256(content).hexdigest()
    if hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest() == SYNTHETIC_FIXTURE_SHA256 and kind != "synthetic":
        raise ImportProblem("This is the bundled synthetic test fixture. Select Synthetic test fixture in the UI or use --kind synthetic in the CLI.")
    if session.scalar(select(ImportBatch).where(ImportBatch.sha256 == digest)):
        raise DuplicateImport("This exact file has already been imported. Select its existing batch; records were not duplicated.")
    official = hashlib.md5(content).hexdigest() == OFFICIAL_MD5
    if official and kind != "measured":
        raise ImportProblem("This is the verified Zenodo workbook. Its data kind must be measured.")
    if official and baseline_days not in (None, 135):
        raise ImportProblem("The verified Zenodo dataset uses 135 baseline days followed by 20 intervention days.")
    split = 135 if official else baseline_days
    records, inspection = parse_records(content, filename, split)
    if official and len(records) != 155:
        raise ImportProblem("The official workbook must contain 155 records.")
    inspection["verified_official_file"] = official
    inspection["mass_policy"] = "Kilogram columns take precedence. PW g is converted only if a kg column is absent; reported per-diner fields are retained for audit only."
    source_info = SOURCE if official else {"key": f"local:{kind}", "title": "User-supplied measurements" if kind == "measured" else "Synthetic test data — not measurements",
        "kind": kind, "doi": None, "url": None, "authors": None, "license": "User responsible for reuse rights"}
    source = session.scalar(select(SourceDataset).where(SourceDataset.key == source_info["key"]))
    if source is None:
        source = SourceDataset(**source_info)
        session.add(source)
    # Never use client filenames as paths, and never persist uploaded raw bytes server-side.
    safe_name = re.sub(r"[^\w .()\-]", "_", Path(filename.replace("\\", "/")).name)[:180] or "upload.xlsx"
    try:
        session.flush()
        batch = ImportBatch(source_id=source.id, filename=safe_name, sha256=digest, row_count=len(records), baseline_days=split, inspection=inspection)
        session.add(batch)
        session.flush()
        session.add_all(DailyRecord(batch_id=batch.id, **record) for record in records)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateImport("Import conflicted with another upload. Refresh the batch list before retrying.") from exc
    return batch


def batch_info(session, batch):
    source = session.get(SourceDataset, batch.source_id)
    return {"id": batch.id, "filename": batch.filename, "sha256": batch.sha256,
        "imported_at": batch.imported_at.isoformat(), "row_count": batch.row_count, "baseline_days": batch.baseline_days,
        "inspection": batch.inspection,
        "source": {key: getattr(source, key) for key in ("key", "title", "kind", "doi", "url", "authors", "license")}}
