"""Rebuild dependency license inventory and notices from the installed exact locks.

Offline. The two upstream sdist license supplements have recorded provenance.
Platform-optional npm packages absent here remain explicitly uninspected binaries.
"""
import hashlib
import importlib.metadata
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def license_file(path):
    return bool(re.match(r"^(?:licen[cs]e|copying|notice|copyright|authors)(?:[._-].*)?$", path.name, re.I))


def main():
    python = []
    python_text = ["MealLoop OS third-party Python notices. Upstream terms apply; not covered by the project's MIT license.\n"]
    for line in (ROOT / "backend/requirements-lock.txt").read_text().splitlines():
        name, version = line.split("==")
        dist = importlib.metadata.distribution(name)
        if dist.version != version:
            raise ValueError(f"Installed version differs: {name}")
        md = dist.metadata
        expression = md.get("License-Expression") or md.get("License") or "; ".join(
            c for c in md.get_all("Classifier", []) if c.startswith("License ::"))
        texts = []
        for f in sorted(dist.files or []):
            if license_file(Path(str(f))) and dist.locate_file(f).is_file():
                texts.append((str(f), dist.locate_file(f).read_text(encoding="utf-8", errors="replace")))
        if not texts:
            supplement = ROOT / f"docs/licenses/sources/{name}-{version}-LICENSE.txt"
            texts = [(supplement.relative_to(ROOT).as_posix(), supplement.read_text(encoding="utf-8"))]
        python.append({"name": name, "version": version, "license_metadata": expression,
                       "notice_sources": [p for p, _ in texts]})
        for p, content in texts:
            python_text.append(f"\n===== {name} {version} :: {p} =====\n{content}\n")
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text())
    npm = []
    npm_text = ["MealLoop OS third-party frontend/build-tool notices. Upstream terms apply.\n",
                "Collected from installed locked npm packages, including nested vendored notices.\n",
                "Absent platform-specific optional binaries are listed in docs/evaluation/dependency_licenses.json; they are not bundled here.\n"]
    for key, package in sorted(lock["packages"].items()):
        if not key:
            continue
        folder = ROOT / "frontend" / key
        texts = []
        if folder.exists():
            for path in sorted(folder.rglob("*")):
                relative = path.relative_to(folder)
                if "node_modules" not in relative.parts and path.is_file() and license_file(path):
                    texts.append((relative.as_posix(), path.read_text(encoding="utf-8", errors="replace")))
        if folder.exists() and not texts:
            # The installed native rolldown binding carries no license text; its
            # same-version upstream parent supplies the binding's declared MIT terms.
            if key != "node_modules/@rolldown/binding-win32-x64-msvc":
                raise ValueError(f"Missing installed package notice: {key}")
            parent = ROOT / "frontend/node_modules/rolldown/LICENSE"
            texts = [("rolldown/LICENSE (upstream parent)", parent.read_text(encoding="utf-8"))]
        npm.append({"path": key, "version": package["version"], "license": package["license"],
                    "resolved": package.get("resolved"), "integrity": package.get("integrity"),
                    "installed_on_windows": folder.exists(), "optional": package.get("optional", False),
                    "notice_sources": [p for p, _ in texts]})
        for p, content in texts:
            npm_text.append(f"\n===== {key} {package['version']} :: {p} =====\n{content}\n")
    target = ROOT / "frontend/public/assets/third-party-notices.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(npm_text), encoding="utf-8", newline="\n")
    py_target = ROOT / "docs/licenses/python-notices.txt"
    py_target.write_text("".join(python_text), encoding="utf-8", newline="\n")
    report = {"python": python, "npm": npm, "python_count": len(python), "npm_lock_count": len(npm),
              "npm_installed_count": sum(p["installed_on_windows"] for p in npm),
              "software_license": "MIT; original MealLoop OS software only",
              "dataset_license": "CC BY 4.0; see data/README.md",
              "limits": "Metadata and included texts reviewed on Windows. Not a legal certification or a Linux binary notice audit. No dependency was modified or vendored as executable code.",
              "notices_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in (target, py_target)}}
    output = ROOT / "docs/evaluation/dependency_licenses.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("python_count", "npm_lock_count", "npm_installed_count", "notices_sha256")}))


if __name__ == "__main__":
    main()
