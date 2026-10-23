"""Offline publication scan of the index, worktree and all local Git objects.

Findings never print matched secret values. This bounded heuristic is not a
secret-scanner certification. It never edits Git history or private runtime data.
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 10 * 1024 * 1024
RULES = {
    "private_key": rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    "aws_access_key": rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "github_token": rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b",
    "api_token": rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b",
    "credential_url": rb"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/:@]{1,100}:[^\s/@]{8,100}@",
    "literal_credential": rb"(?im)^\s*(?:export\s+)?(?:[A-Z_]*(?:API_KEY|ACCESS_TOKEN|SECRET_KEY|PASSWORD))\s*[:=]\s*[\"']([A-Za-z0-9_+/=-]{16,})[\"']\s*[,;]?\s*$",
}


def private_path(name):
    p = PurePosixPath(name.lower())
    base = p.name
    return (any(part in {".venv", "venv", "node_modules", ".run", ".public-demo", "__pycache__",
                            ".pytest_cache", ".mypy_cache", ".ruff_cache", "uploads", "credentials"}
                for part in p.parts)
            or ((base == ".env" or base.startswith(".env.")) and base not in (".env.example", ".env.sample"))
            or base in {".npmrc", ".pypirc", ".netrc", "id_rsa", "id_ed25519", "credentials.json"}
            or bool(re.search(r"\.(?:db|sqlite3?)(?:-.*)?$|\.(?:log|pem|key|p12|pfx|pyc|pyo)$", base))
            or name.startswith("frontend/dist/"))


def inspect_bytes(data, label):
    findings = []
    if len(data) > MAX_BYTES:
        return [{"object": label, "rule": "oversized_requires_manual_review"}]
    if data.startswith(b"SQLite format 3\x00"):
        findings.append({"object": label, "rule": "sqlite_content"})
    for rule, pattern in RULES.items():
        if re.search(pattern, data):
            findings.append({"object": label, "rule": rule})
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(i.file_size for i in archive.infolist()) > MAX_BYTES:
                    findings.append({"object": label, "rule": "archive_expansion_requires_review"})
                else:
                    for member in archive.infolist():
                        if not member.is_dir():
                            raw = archive.read(member)
                            for rule, pattern in RULES.items():
                                if re.search(pattern, raw):
                                    findings.append({"object": label, "member": member.filename, "rule": rule})
        except zipfile.BadZipFile:
            findings.append({"object": label, "rule": "unreadable_archive"})
    return findings


def git(root, *args):
    return subprocess.check_output(["git", "-c", "core.quotepath=false", *args], cwd=root)


def audit(root):
    root = Path(root).resolve()
    findings = []
    tracked = git(root, "ls-files", "-z").decode().strip("\0").split("\0")
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z").decode().strip("\0").split("\0")
    files = sorted(set(filter(None, tracked + untracked)))
    file_inventory = []
    for name in files:
        path = root / name
        if private_path(name):
            findings.append({"object": name, "scope": "worktree", "rule": "private_path"})
        if path.is_symlink():
            findings.append({"object": name, "scope": "worktree", "rule": "symlink_requires_review"})
            continue
        if path.is_file():
            data = path.read_bytes()
            findings.extend(dict(f, scope="worktree") for f in inspect_bytes(data, name))
            file_inventory.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    # Scan index blobs independently: staged bytes may differ from working files.
    index_entries = git(root, "ls-files", "--stage", "-z").split(b"\0")
    for entry in filter(None, index_entries):
        fields, name = entry.split(b"\t", 1)
        mode, oid, stage = fields.split()
        if stage != b"0" or mode == b"160000":
            findings.append({"object": name.decode(), "scope": "index", "rule": "unmerged_or_submodule_requires_review"})
            if mode == b"160000":
                continue
        data = git(root, "cat-file", "blob", oid.decode())
        findings.extend(dict(f, scope="index") for f in inspect_bytes(data, name.decode()))
    # Include reflog-only commits in path review, and unreachable blobs in content review.
    commits = git(root, "rev-list", "--all", "--reflog").decode().splitlines()
    historical_paths = set()
    for commit in commits:
        historical_paths.update(filter(None, git(root, "ls-tree", "-r", "--name-only", "-z", commit).decode().split("\0")))
        findings.extend(dict(f, scope="commit_metadata") for f in inspect_bytes(git(root, "cat-file", "commit", commit), commit))
    for name in sorted(historical_paths):
        if private_path(name):
            findings.append({"object": name, "scope": "history", "rule": "private_path"})
    objects = git(root, "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype) %(objectsize)").decode().splitlines()
    blobs = [line.split() for line in objects if line.split()[1] == "blob"]
    for oid, _, size in blobs:
        if int(size) > MAX_BYTES:
            findings.append({"object": oid, "scope": "git_blob", "rule": "oversized_requires_manual_review"})
        else:
            findings.extend(dict(f, scope="git_blob") for f in inspect_bytes(git(root, "cat-file", "blob", oid), oid))
    # Inventory every on-disk file, including ignored runtimes, without publishing contents.
    disk_files = []
    for folder, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d != ".git" and not (Path(folder) / d).is_symlink()]
        disk_files.extend((Path(folder) / n).relative_to(root).as_posix() for n in names)
    ignored = git(root, "ls-files", "--others", "--ignored", "--exclude-standard", "-z").decode().split("\0")
    ignored = set(filter(None, ignored))
    uncovered = sorted(set(disk_files) - set(files) - ignored)
    if uncovered:
        findings.append({"scope": "disk", "rule": "unclassified_disk_files", "paths": uncovered})
    return {"scan": "publication-v1", "passed": not findings,
            "scope": "Index, nonignored worktree, all local Git blobs, all ref/reflog commit trees and metadata; ignored file names only.",
            "limitations": "Heuristic patterns do not prove absence of secrets; screenshots are visually reviewed separately. No ignored private contents are copied. No remote account or cloud is inspected.",
            "tracked_files": len(list(filter(None, tracked))), "nonignored_files": len(files),
            "disk_files_excluding_git": len(disk_files), "ignored_files": len(ignored),
            "commits_including_reflogs": len(commits), "historical_paths": len(historical_paths),
            "git_blobs_scanned": len(blobs), "findings": findings,
            "files": file_inventory,
            "ignored_roots": sorted({p.split('/')[0] for p in ignored})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".run/publication-audit.json")
    args = parser.parse_args()
    report = audit(ROOT)
    # The report cannot contain its own final digest; remove only this output row.
    relative = args.output.resolve().relative_to(ROOT).as_posix()
    report["files"] = [f for f in report["files"] if f["path"] != relative]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("passed", "tracked_files", "nonignored_files", "commits_including_reflogs", "git_blobs_scanned", "ignored_roots", "findings")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
