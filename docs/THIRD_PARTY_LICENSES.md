# Third-party licenses

Review date: October 23, 2026. MealLoop OS's original software uses **MIT**; see the root `LICENSE`. This grant does not relicense third-party code, the Finland workbook or its data-derived artifacts. Attribution for the unchanged workbook and transformed representations remains in `data/README.md` under CC BY 4.0. Source metadata was rechecked against the official Zenodo API; its license, authors and published MD5 still match the bundled snapshot.

## Executed inventory

`scripts/license_inventory.py` checks all **41 exact Python pins** against installed distribution metadata, and inventories **129 npm lock entries**, including optional platform binaries. **83 npm entries are installed on this Windows machine; 46 optional entries are absent.** All 129 declare a license. The machine-readable versions, declarations, resolved npm URLs/integrities, installed status and notice sources are in `evaluation/dependency_licenses.json`. Python's scientific dependencies and npm locks were not changed.

The Python inventory includes MIT, BSD variants, Apache-2.0/dual choices, PSF-2.0, MPL-2.0 and NumPy's compound expression. NumPy, SciPy, Pandas and scikit-learn also contain upstream bundled notices: the aggregate retains those texts, including numerical-library terms, instead of treating the top-level identifier as the complete distribution license. The npm lock declares MIT, ISC, BSD-3-Clause, Apache-2.0, MIT AND ISC, and MPL-2.0. A declared license is a review input, not an assurance of complete legal compliance.

## Retained notices

- [Python notices](licenses/python-notices.txt): installed upstream license/copyright/author texts, including nested notices. Runtime dependencies stay installed with their original distribution metadata and license files; their executable packages are not committed here.
- [Frontend and build-tool notices](../frontend/public/assets/third-party-notices.txt): copied from installed locked packages, including nested `victory-vendor` notices. Vite copies this file to `/assets/third-party-notices.txt`; the app footer opens it. The existing asset route serves it under the same security headers.
- `openpyxl==3.1.5` and `et_xmlfile==2.0.0` wheels omit their license text. Their unmodified `LICENCE.rst` texts were obtained from the corresponding official PyPI source distributions after verifying the PyPI SHA-256. The exact download URL, source digest and archive member are recorded beside each supplement in `licenses/sources/`. No package code was copied from those archives.
- The installed Windows rolldown binding declares MIT but omits a notice file; the aggregate includes its same-version upstream parent's license. Absent optional binaries are listed rather than represented as inspected. A later Linux installation must retain and review its installed binary notices too.

Keep copyright, license and required notice texts with redistributed copies. In particular, MPL-covered dependencies retain their own source/notice obligations; the project's MIT license does not remove them. We modified no dependency source. Source distributions and npm package URLs in the inventory identify the exact upstream artifacts. Recheck applicable terms if modifying or repackaging dependencies or distributing different binaries. This engineering inventory is not a legal certification.

Rebuild offline with the exact installed locks:

```powershell
.\.venv\Scripts\python.exe scripts\license_inventory.py
npm.cmd --prefix frontend run build
```

Primary references: [MIT license text](https://opensource.org/license/mit), [CC BY 4.0 terms](https://creativecommons.org/licenses/by/4.0/), [official dataset](https://zenodo.org/records/20825233), [openpyxl release metadata](https://pypi.org/pypi/openpyxl/3.1.5/json), [et_xmlfile release metadata](https://pypi.org/pypi/et_xmlfile/2.0.0/json). The installed artifacts' own included license texts take precedence over our summary.
