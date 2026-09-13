"""PDF pagination keeps the static pivot caption with its actual table."""
import copy
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader
import pytest

from foundry.exporters import export_snapshot
from foundry.ingestion import rows_from_csv
from foundry.runtime import prepare


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "evolution" / "absolute_change"
CAPTION = "Static pivot result under the flow view policy."


@pytest.mark.parametrize("case", ["future_q3_2026", "future_q4_2026"])
def test_composed_report_keeps_pivot_caption_on_page_with_pivot_rows(case, tmp_path):
    directory = FIXTURES / case
    data = (directory / "transactions.csv").read_bytes()
    snapshot = prepare(rows_from_csv(data)[1], json.loads((directory / "period.json").read_text()),
                       {"id": "future-source", "digest": hashlib.sha256(data).hexdigest(), "filename": "transactions.csv"},
                       reporting_policy={"selection": "largest_absolute_change"}).model_dump(mode="json")
    # The two real live drafts exposed this page break. Freeze their short,
    # fact-bound wording here so the regression requires no provider or data dir.
    snapshot.update(title="Evolution corpus B", status="review_required")
    summary = ("Posted revenue for the current window reached {{revenue.current}}, against {{revenue.comparison}} "
               "in the comparison window. The movement between the periods was {{revenue.change}}, a change of "
               "{{revenue.growth}}.\n\nThe selected region is {{driver.region}}, with a movement of {{driver.change}} "
               "between the periods.")
    if case == "future_q4_2026":
        summary = ("Posted revenue for the current window totals {{revenue.current}}, against {{revenue.comparison}} "
                   "for the comparison window. The movement between the periods is {{revenue.change}}, with growth of "
                   "{{revenue.growth}}.\n\nThe selected region is {{driver.region}}, whose revenue movement between "
                   "the periods is {{driver.change}}.")
    for key, value in snapshot["facts"].items():
        summary = summary.replace("{{" + key + "}}", value["display"])
    commentary = next(node for node in snapshot["nodes"] if node["id"] == "commentary")
    commentary.update(mode="composed", runs=[{"type": "text", "text": summary}])
    before = copy.deepcopy(snapshot)
    result = export_snapshot(snapshot, "pdf", tmp_path)
    reader = PdfReader(result["path"])
    pages = [page.extract_text() for page in reader.pages]
    caption_pages = [i for i, text in enumerate(pages) if CAPTION in text]
    assert len(caption_pages) == 1
    caption_page = pages[caption_pages[0]]
    assert "Orchard Canary" in caption_page, "The caption must not occupy a page without its final pivot row."
    assert "Revenue analysis" in caption_page
    assert reader.get_destination_page_number(reader.named_destinations["regional_pivot"]) == caption_pages[0]
    assert snapshot == before
    assert all("Orchard Canary" in text or CAPTION not in text for text in pages)
