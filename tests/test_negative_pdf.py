"""Real PDF exports preserve the runtime's signed monetary displays."""

import copy
import hashlib
import json
from pathlib import Path
import re

from pypdf import PdfReader
import pytest

from foundry.exporters import ExportError, export_snapshot
from foundry.ingestion import rows_from_csv
from foundry.runtime import prepare


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "evolution"


def future_snapshot(corpus, case, selection):
    directory = FIXTURES / corpus / case
    source = (directory / "transactions.csv").read_bytes()
    return prepare(rows_from_csv(source)[1], json.loads((directory / "period.json").read_text()),
                   {"id": "future-source", "digest": hashlib.sha256(source).hexdigest(), "filename": "transactions.csv"},
                   reporting_policy={"selection": selection}).model_dump(mode="json")


@pytest.mark.parametrize("corpus,case,selection,expected", [
    ("absolute_change", "future_q1_2026", "largest_absolute_change",
     ["−€800.00", "−€700.00", "-800.00", "-88.9%"]),
    ("current_revenue", "future_q1_2026", "largest_current_revenue",
     ["−€200.00", "−€230.00", "-200.00", "-20.0%"]),
    ("percentage_change", "future_q1_2026", "largest_percentage_change",
     ["−€90.00", "−€390.00", "-90.00", "-90.0%"]),
    ("percentage_change", "future_q3_2026", "largest_percentage_change",
     ["−€100.00", "+€555.00", "-100.00", "-100.0%"]),
    ("absolute_change", "future_q2_2026", "largest_absolute_change",
     ["−€300.00", "+€25.00", "-300.00"]),
])
def test_actual_declining_period_pdf_keeps_signed_facts_and_table_cells(corpus, case, selection, expected, tmp_path):
    snapshot = future_snapshot(corpus, case, selection)
    before = copy.deepcopy(snapshot)
    result = export_snapshot(snapshot, "pdf", tmp_path)
    reader = PdfReader(result["path"])
    text = re.sub(r"\s+", " ", " ".join(page.extract_text() for page in reader.pages))
    assert all(value in text for value in expected)
    assert "■" not in text
    assert snapshot == before
    fonts = {str(font.get_object().get("/BaseFont")) for page in reader.pages
             for font in page["/Resources"]["/Font"].values()}
    assert "/Symbol" in fonts
    assert set(reader.named_destinations) == {"summary", "commentary", "regional_table", "regional_chart", "regional_pivot"}
    assert result["manifest"]["details"]["font_profile"] == "Helvetica / Windows Latin; Symbol for U+2212 minus"


def test_negative_regional_cell_does_not_need_negative_aggregate_or_selected_region(tmp_path):
    snapshot = future_snapshot("current_revenue", "future_q2_2026", "largest_current_revenue")
    assert snapshot["facts"]["revenue.change"]["value"] == "325.00"
    assert snapshot["facts"]["driver.change"]["value"] == "400.00"
    result = export_snapshot(snapshot, "pdf", tmp_path)
    text = " ".join(page.extract_text() for page in PdfReader(result["path"]).pages)
    assert "Cypress" in text and "-375.00" in text and "-75.0%" in text


@pytest.mark.parametrize("unsupported", ["東京", "Ж", "∑", "−東京"])
def test_allowing_exact_minus_does_not_allow_unapproved_glyphs(unsupported, tmp_path):
    snapshot = future_snapshot("absolute_change", "future_q1_2026", "largest_absolute_change")
    next(node for node in snapshot["nodes"] if node["id"] == "commentary")["runs"] = [{"type": "text", "text": unsupported}]
    before = copy.deepcopy(snapshot)
    with pytest.raises(ExportError) as failure:
        export_snapshot(snapshot, "pdf", tmp_path)
    assert failure.value.code == "unsupported_font_glyph"
    assert snapshot == before
    assert not list(tmp_path.glob("*.pdf"))
