"""Import local measurements. Never fetch or substitute synthetic data implicitly."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.database import database_url, make_engine, migrate, sessions
from app.importer import DuplicateImport, batch_info, import_file
from app.parsing import ImportProblem, MAX_BYTES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--kind", choices=("measured", "synthetic"), default="measured")
    parser.add_argument("--baseline-days", type=int)
    args = parser.parse_args()
    if not args.file.is_file():
        parser.error("File not found. Download the official workbook from https://zenodo.org/records/20825233 or select a local file.")
    if args.file.stat().st_size > MAX_BYTES:
        parser.error("File exceeds the 10 MiB limit.")
    engine = make_engine(database_url())
    try:
        migrate(engine)
        with sessions(engine)() as session:
            batch = import_file(session, args.file.read_bytes(), args.file.name, args.kind, args.baseline_days)
            print(json.dumps(batch_info(session, batch), indent=2, ensure_ascii=True))
    except DuplicateImport as exc:
        print(str(exc))  # idempotent startup; no duplicate measurements
    except ImportProblem as exc:
        print(json.dumps({"error": str(exc), "details": exc.errors}, indent=2), file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
