"""Download the unchanged official workbook after checking its record license."""
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API = "https://zenodo.org/api/records/20825233"
EXPECTED_MD5 = "3f7e610fedc1810f7e8bc1bd47103ee7"


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "MealLoopOS/0.5.0 (dataset download)"}), timeout=45) as response:
        data = response.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise RuntimeError("Remote content exceeds the 10 MiB limit.")
    return data


if __name__ == "__main__":
    try:
        metadata_bytes = fetch(API)
        metadata = json.loads(metadata_bytes)
        if metadata["metadata"].get("license", {}).get("id") != "cc-by-4.0":
            raise RuntimeError("License differs from reviewed CC BY 4.0; review the record before reuse.")
        file = next(f for f in metadata["files"] if f["key"] == "Food waste data school Finland 2024-2025.xlsx")
        # Fixed official endpoint: metadata does not control download hosts or local paths.
        content = fetch("https://zenodo.org/api/records/20825233/files/Food%20waste%20data%20school%20Finland%202024-2025.xlsx/content")
        if file["checksum"] != f"md5:{EXPECTED_MD5}" or hashlib.md5(content).hexdigest() != EXPECTED_MD5:
            raise RuntimeError("Official checksum changed. Inspect the new workbook before updating the mapping.")
        target = ROOT / "data/raw"
        target.mkdir(exist_ok=True, parents=True)
        path = target / "Food waste data school Finland 2024-2025.xlsx"
        if path.exists() and path.read_bytes() != content:
            raise RuntimeError("Local workbook differs; move it aside manually to preserve your work.")
        path.write_bytes(content)
        (target / "zenodo-record.json").write_bytes(metadata_bytes)
        print(f"Downloaded {path} ({len(content)} bytes), checksum verified. CC BY 4.0. See data/README.md for attribution.")
    except Exception as exc:
        raise SystemExit(f"Download failed: {exc}\nManual path: https://zenodo.org/records/20825233 → download .xlsx → data/raw/ → run scripts/import_dataset.py. No synthetic replacement was made.")
