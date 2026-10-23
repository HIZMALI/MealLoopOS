"""Reproduce all scientific evidence in disposable state without editing originals."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    from app.demo import verify_files

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".run/scientific-reproduction.json")
    args = parser.parse_args()
    fingerprints = verify_files()
    run_dir = ROOT / ".run"
    run_dir.mkdir(exist_ok=True)
    comparisons = {}
    with tempfile.TemporaryDirectory(prefix="science-", dir=run_dir) as folder:
        work = Path(folder)
        assert work.resolve().parent == run_dir.resolve()
        env = {**os.environ, "MEALLOOP_MODE": "LOCAL",
               "MEALLOOP_DATABASE_URL": "sqlite:///" + (work / "science.db").as_posix(),
               "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}

        def run(script, *arguments):
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, arguments)],
                                    cwd=ROOT, env=env, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(f"{script} failed; no evidence accepted.\n{result.stdout}\n{result.stderr}")

        run("import_dataset.py", ROOT / "data/raw/Food waste data school Finland 2024-2025.xlsx")
        for number, script in ((2, "evaluate_forecasts.py"), (3, "evaluate_decisions.py"), (4, "evaluate_impact.py")):
            output = work / f"reproduced-{number}.json"
            run(script, "--output", output)
            original = ROOT / f"docs/evaluation/build_0{number}_evaluation.json"
            data = output.read_bytes()
            if data != original.read_bytes():
                raise RuntimeError(f"Scientific evidence differs: {original.name}")
            comparisons[original.relative_to(ROOT).as_posix()] = {
                "byte_identical": True, "sha256": hashlib.sha256(data).hexdigest()}

    report = {"passed": True, "comparisons": comparisons, "public_input_fingerprints": fingerprints,
              "normal_operational_database_used": False,
              "notice": "Explicit offline evaluation only. Synthetic arithmetic is not a real pilot or achieved savings."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"passed": True, "byte_identical_evaluations": len(comparisons)}))


if __name__ == "__main__":
    main()
