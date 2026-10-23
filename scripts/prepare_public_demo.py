"""Prepare/reuse isolated public state, offline. Never imports app.main/local DB."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.demo import prepare_demo

if __name__ == "__main__":
    try:
        manifest = prepare_demo()
        print(json.dumps({"status": "ready", "kind": manifest["kind"], "database_sha256": manifest["database_sha256"]}))
    except Exception as exc:
        raise SystemExit(f"Demo preparation failed: {exc}") from None
