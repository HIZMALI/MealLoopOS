import io
import zipfile
from datetime import date

import pytest
from openpyxl import Workbook
from app.parsing import ImportProblem, MAX_BYTES, parse_records


def test_csv_missing_data_zero_diners_and_order(csv_data):
    rows, info = parse_records(csv_data, "data.csv", 2)
    assert len(rows) == 3
    assert rows[1]["kitchen_serving_waste_kg"] is None
    assert rows[0]["date"] == date(2025, 1, 1)
    assert rows[2]["diners"] == 0
    assert "zero_diners_per_diner_unavailable" in rows[2]["issues"]
    assert [r["phase"] for r in rows] == ["baseline", "baseline", "intervention"]
    assert info["missing_counts"]["kitchen_serving_waste_kg"] == 1


def test_no_dates_never_invented_and_duplicate_rows_preserved():
    rows, info = parse_records(b"PW kg,KSW kg,DINERS\n1,2,10\n1,2,10\n", "f.csv")
    assert len(rows) == 2 and rows[0]["date"] is None
    assert rows[1]["source_row"] == 3
    assert info["date_count"] == 0
    assert rows[0]["phase"] == "unassigned"
    assert "duplicate_measurements_preserved" in rows[1]["issues"]


def test_units_converted_without_double_counting():
    rows, _ = parse_records(b"PW g,KSW kg,DINERS,PW/g/diner\n1500,2,10,150\n", "f.csv")
    assert rows[0]["plate_waste_kg"] == 1.5
    assert rows[0]["reported_plate_waste_g"] == 1500
    assert rows[0]["reported_plate_g_per_diner"] == 150


def test_conflicts_preserved_kg_precedence_and_no_cell_fallback():
    rows, info = parse_records(b"PW kg,PW g,KSW kg,DINERS,PW/g/diner,KSW/g/diner\n1,9000,2,10,7,8\n,1000,2,10,,\n", "f.csv")
    assert rows[0]["plate_waste_kg"] == 1
    assert rows[0]["reported_plate_waste_g"] == 9000
    assert rows[1]["plate_waste_kg"] is None
    assert info["issue_counts"]["plate_kg_g_conflict"] == 1
    assert info["issue_counts"]["plate_per_diner_conflict"] == 1
    assert info["issue_counts"]["kitchen_per_diner_conflict"] == 1


@pytest.mark.parametrize("value", ["nope", "NaN", "inf", "-1", "1e309", "1000001", "=1+2"])
def test_invalid_numeric_mass_rejected(value):
    with pytest.raises(ImportProblem, match="Import rejected") as result:
        parse_records(f"PW kg,KSW kg,DINERS\n{value},1,10\n".encode(), "f.csv")
    assert result.value.errors[0]["field"] == "plate_waste_kg"


@pytest.mark.parametrize("column,value", [("DINERS", "2.5"), ("DINERS", "-1"), ("MENU", "26"), ("MENU", "0"), ("MENU", "1.5")])
def test_count_and_menu_validation(column, value):
    header = "PW kg,KSW kg,DINERS" + (",MENU" if column == "MENU" else "")
    row = f"1,2,{value}" if column == "DINERS" else f"1,2,10,{value}"
    with pytest.raises(ImportProblem):
        parse_records(f"{header}\n{row}\n".encode(), "f.csv")


@pytest.mark.parametrize("data", [b"PW kg,DINERS\n1,2\n", b"PW kg,KSW kg\n1,2\n", b"PW/g/diner,KSW/g/diner,DINERS\n1,2,3\n", b"PW kg,KSW kg,DINERS\n,,10\n", b"PW kg,PW,KSW kg,DINERS\n1,2,3,4\n"])
def test_missing_measurements_fields_and_duplicate_headers(data):
    with pytest.raises(ImportProblem):
        parse_records(data, "f.csv")


def test_semicolon_decimal_comma_utf8_bom():
    rows, _ = parse_records("\ufeffPW kg;KSW kg;DINERS\n1,5;2,25;10\n".encode(), "f.csv")
    assert rows[0]["plate_waste_kg"] == 1.5
    assert rows[0]["kitchen_serving_waste_kg"] == 2.25


@pytest.mark.parametrize("value", ["45512", "12/31/2024", "yesterday"])
def test_invalid_or_ambiguous_date(value):
    with pytest.raises(ImportProblem):
        parse_records(f"DATE,PW kg,KSW kg,DINERS\n{value},1,2,10\n".encode(), "f.csv")


def test_date_duplicates_and_nonchronological_order_retained():
    rows, info = parse_records(b"DATE,PW kg,KSW kg,DINERS\n2025-01-02,1,2,10\n2025-01-01,2,2,20\n2025-01-01,3,2,30\n", "f.csv")
    assert not info["date_ordered"]
    assert rows[0]["date"] == date(2025, 1, 2)
    assert "duplicate_date_preserved" in rows[2]["issues"]


@pytest.mark.parametrize("split", [-1, 4])
def test_invalid_split(csv_data, split):
    with pytest.raises(ImportProblem, match="Baseline"):
        parse_records(csv_data, "f.csv", split)


def workbook_bytes(multiple=False):
    book = Workbook()
    sheet = book.active
    sheet.append(["DATE", "MENU", "KSW kg", "PW kg", "PW g", "DINERS", "PW/g/diner", "KSW/g/diner"])
    sheet.append([date(2025, 1, 1), 1, None, 1, 1000, 10, 100, None])
    sheet.cell(50, 1).number_format = "dd/mm/yyyy"  # formatting is not a measurement
    if multiple:
        book.copy_worksheet(sheet)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_excel_real_dates_and_formatting_only_rows():
    rows, info = parse_records(workbook_bytes(), "f.xlsx")
    assert len(rows) == 1
    assert rows[0]["date"] == date(2025, 1, 1)
    assert rows[0]["kitchen_serving_waste_kg"] is None
    assert len(info["headers"]) == 8


def test_multiple_matching_sheets_rejected():
    with pytest.raises(ImportProblem, match="exactly one"):
        parse_records(workbook_bytes(True), "f.xlsx")


@pytest.mark.parametrize("content,name", [(b"", "f.csv"), (b"x", "f.exe"), (b"not a zip", "f.xlsx"), (b"\xff\xfe", "f.csv"), (b"x" * (MAX_BYTES + 1), "f.csv")], ids=["empty", "extension", "corrupt-xlsx", "encoding", "oversized"])
def test_invalid_files(content, name):
    with pytest.raises(ImportProblem):
        parse_records(content, name)


def test_zip_expansion_limit():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("large.xml", b"0" * (50 * 1024 * 1024 + 1))
    with pytest.raises(ImportProblem, match="expands"):
        parse_records(buffer.getvalue(), "f.xlsx")
