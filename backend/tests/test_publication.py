"""Publication safeguards must detect staged and deleted sensitive material."""
import importlib.util
import json
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("publication_audit", ROOT / "scripts/publication_audit.py")
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


@pytest.mark.parametrize("name", [".env.local", "backend/.env.production", "data/nested/user.sqlite3",
    "backup/private.db-wal", ".run/log.txt", "data/uploads/user.csv", "keys/id_ed25519", "nested/node_modules/x.js", ".venv/.env.example"])
def test_private_publication_paths(name):
    assert scanner.private_path(name)


@pytest.mark.parametrize("name", [".env.example", "docs/PUBLIC_DEMO_SECURITY.md", "data/raw/source.xlsx",
    "data/public_demo/forecast_artifact.json", "docs/screenshots/demo.png"])
def test_intended_publication_paths(name):
    assert not scanner.private_path(name)


def test_sqlite_content_and_archived_credentials_detected():
    assert scanner.inspect_bytes(b"SQLite format 3\x00" + b"x" * 20, "renamed.bin")[0]["rule"] == "sqlite_content"
    token = b"gh" + b"p_" + b"a" * 36
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("sheet.xml", token)
    findings = scanner.inspect_bytes(archive.getvalue(), "source.xlsx")
    assert any(f.get("member") == "sheet.xml" and f["rule"] == "github_token" for f in findings)
    assert token.decode() not in json.dumps(findings)


def test_deleted_history_and_staged_bytes_scanned(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    git("init", "--initial-branch=main")
    git("config", "user.name", "Publication test")
    git("config", "user.email", "fixture@example.invalid")
    secret = "gh" + "p_" + "a" * 36
    (tmp_path / "deleted.txt").write_text(secret)
    git("add", "deleted.txt")
    git("commit", "-m", "Synthetic scanner fixture")
    git("rm", "deleted.txt")
    git("commit", "-m", "Delete fixture")
    (tmp_path / "staged.txt").write_text(secret)
    git("add", "staged.txt")
    (tmp_path / "staged.txt").write_text("Working tree looks clean")
    report = scanner.audit(tmp_path)
    assert not report["passed"]
    assert any(f["scope"] == "git_blob" for f in report["findings"])
    assert any(f["scope"] == "index" for f in report["findings"])
    assert secret not in json.dumps(report)


def test_future_private_files_are_ignored():
    paths = ["backend/.env.production", "data/nested/operator.sqlite3", "data/nested/operator.db-wal",
             "data/uploads/example.xlsx", ".public-demo/demo.db", ".run/start.log", "backend/keys/operator.pem"]
    result = subprocess.run(["git", "check-ignore", "--stdin", "-z"], cwd=ROOT,
                            input=("\0".join(paths) + "\0").encode(), capture_output=True, check=True)
    assert set(result.stdout.decode().strip("\0").split("\0")) == set(paths)


def test_blueprint_exact_public_hostname_self_reference():
    blueprint = (ROOT / "render.yaml").read_text()
    assert "plan: free" in blueprint and "autoDeployTrigger: \"off\"" in blueprint
    assert "value: PUBLIC_DEMO" in blueprint and "MEALLOOP_DATABASE_URL" not in blueprint
    assert "- key: MEALLOOP_PUBLIC_HOSTS\n        fromService:\n          name: mealloop-os-demo\n          type: web\n          envVarKey: RENDER_EXTERNAL_HOSTNAME" in blueprint
    assert "value: 3.14.0" in blueprint and "value: 24.13.1" in blueprint
    assert "backend/requirements-lock.txt" in blueprint and "npm --prefix frontend ci" in blueprint
    assert "startCommand: python scripts/serve.py" in blueprint
    assert "healthCheckPath: /api/health" in blueprint
