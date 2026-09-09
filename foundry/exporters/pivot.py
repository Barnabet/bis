"""Narrow SpreadsheetML pivot writer: region × period, one sum measure.

This writes a real pivot definition and cache, rather than renaming a table.
Open XML structure can be checked independently. Excel interaction remains a
separate certification gate; the application must not infer it from ZIP parts.

Reference: https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-pivottables
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"


def _xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _sub(parent, tag, **attributes):
    return ET.SubElement(parent, f"{{{MAIN}}}{tag}", {k: str(v) for k, v in attributes.items()})


def _rels(*entries):
    root = ET.Element(f"{{{PKG}}}Relationships")
    for identifier, kind, target in entries:
        ET.SubElement(root, f"{{{PKG}}}Relationship", Id=identifier, Type=f"{REL}/{kind}", Target=target)
    return root


def add_flat_pivot(path: Path, rows: list[dict], *, source_sheet="Approved data", target_sheet_number=2) -> dict:
    """Attach a native pivot to an existing workbook with materialized cells.

    The writer intentionally supports only these three approved aggregate
    columns. It cannot embed transaction rows, paths or external connections.
    The source worksheet has headers at A1:C1. The target cached display begins
    at A3 (caption), A4:C4 (field labels), A5 (first data row).
    """
    if not rows or any(set(row) != {"region", "period", "revenue"} for row in rows):
        raise ValueError("The pivot requires approved region, period, revenue aggregate rows.")
    regions = sorted({str(row["region"]) for row in rows}, key=str.casefold)
    periods = ["comparison", "current"]
    if set(str(row["period"]) for row in rows) != set(periods):
        raise ValueError("The pivot requires current and comparison periods.")
    cache = ET.Element(f"{{{MAIN}}}pivotCacheDefinition", {
        f"{{{REL}}}id": "rId1", "saveData": "1", "refreshOnLoad": "0",
        "enableRefresh": "1", "createdVersion": "6", "refreshedVersion": "6",
        "minRefreshableVersion": "3", "recordCount": str(len(rows)),
    })
    source = _sub(cache, "cacheSource", type="worksheet")
    _sub(source, "worksheetSource", ref=f"A1:C{len(rows) + 1}", sheet=source_sheet)
    fields = _sub(cache, "cacheFields", count=3)
    for name, values in [("region", regions), ("period", periods)]:
        field = _sub(fields, "cacheField", name=name, numFmtId=0)
        shared = _sub(field, "sharedItems", count=len(values), containsString=1,
                      containsNumber=0, containsSemiMixedTypes=0, containsNonDate=1)
        for value in values:
            _sub(shared, "s", v=value)
    field = _sub(fields, "cacheField", name="revenue", numFmtId=4)
    _sub(field, "sharedItems", count=0, containsString=0, containsNumber=1,
         containsSemiMixedTypes=0, containsNonDate=1)
    records = ET.Element(f"{{{MAIN}}}pivotCacheRecords", count=str(len(rows)))
    for row in rows:
        record = _sub(records, "r")
        _sub(record, "x", v=regions.index(str(row["region"])))
        _sub(record, "x", v=periods.index(str(row["period"])))
        value = Decimal(str(row["revenue"]))
        if not value.is_finite():
            raise ValueError("Pivot amounts must be finite.")
        _sub(record, "n", v=str(value))

    pivot = ET.Element(f"{{{MAIN}}}pivotTableDefinition", {
        "name": "RegionalRevenuePivot", "cacheId": "0", "dataCaption": "Revenue (EUR)",
        "rowHeaderCaption": "Region", "colHeaderCaption": "Period", "updatedVersion": "6",
        "minRefreshableVersion": "3", "createdVersion": "6", "useAutoFormatting": "1",
        "rowGrandTotals": "0", "colGrandTotals": "0", "compact": "0", "compactData": "0",
        "outline": "0", "outlineData": "0", "gridDropZones": "1", "showDrill": "1",
        "enableDrill": "1", "showHeaders": "1", "showDropZones": "1",
    })
    _sub(pivot, "location", ref=f"A3:C{len(regions) + 4}", firstHeaderRow=1, firstDataRow=2, firstDataCol=1)
    fields = _sub(pivot, "pivotFields", count=3)
    for axis, values in [("axisRow", regions), ("axisCol", periods)]:
        field = _sub(fields, "pivotField", axis=axis, showAll=0, defaultSubtotal=0,
                     compact=0, outline=0, subtotalTop=0)
        items = _sub(field, "items", count=len(values))
        for index in range(len(values)):
            _sub(items, "item", x=index)
    _sub(fields, "pivotField", dataField=1, showAll=0)
    rf = _sub(pivot, "rowFields", count=1)
    _sub(rf, "field", x=0)
    ri = _sub(pivot, "rowItems", count=len(regions))
    for index in range(len(regions)):
        _sub(_sub(ri, "i"), "x", v=index)
    cf = _sub(pivot, "colFields", count=1)
    _sub(cf, "field", x=1)
    ci = _sub(pivot, "colItems", count=len(periods))
    for index in range(len(periods)):
        _sub(_sub(ci, "i"), "x", v=index)
    df = _sub(pivot, "dataFields", count=1)
    _sub(df, "dataField", name="Revenue (EUR)", fld=2, subtotal="sum", numFmtId=4)
    _sub(pivot, "pivotTableStyleInfo", name="PivotStyleMedium9", showRowHeaders=1,
         showColHeaders=1, showRowStripes=0, showColStripes=0, showLastColumn=1)

    with ZipFile(path) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    workbook = ET.fromstring(parts["xl/workbook.xml"])
    rels = ET.fromstring(parts["xl/_rels/workbook.xml.rels"])
    existing = {r.attrib["Id"] for r in rels}
    index = 1
    while f"rId{index}" in existing:
        index += 1
    relation_id = f"rId{index}"
    caches = _sub(workbook, "pivotCaches")
    _sub(caches, "pivotCache", cacheId=0).set(f"{{{REL}}}id", relation_id)
    ET.SubElement(rels, f"{{{PKG}}}Relationship", Id=relation_id,
                  Type=f"{REL}/pivotCacheDefinition", Target="pivotCache/pivotCacheDefinition1.xml")
    sheet_rels_name = f"xl/worksheets/_rels/sheet{target_sheet_number}.xml.rels"
    sheet_rels = ET.fromstring(parts[sheet_rels_name]) if sheet_rels_name in parts else _rels()
    existing = {r.attrib["Id"] for r in sheet_rels}
    index = 1
    while f"rId{index}" in existing:
        index += 1
    ET.SubElement(sheet_rels, f"{{{PKG}}}Relationship", Id=f"rId{index}",
                  Type=f"{REL}/pivotTable", Target="../pivotTables/pivotTable1.xml")
    content_types = ET.fromstring(parts["[Content_Types].xml"])
    new_parts = [
        ("/xl/pivotTables/pivotTable1.xml", "pivotTable"),
        ("/xl/pivotCache/pivotCacheDefinition1.xml", "pivotCacheDefinition"),
        ("/xl/pivotCache/pivotCacheRecords1.xml", "pivotCacheRecords"),
    ]
    for name, kind in new_parts:
        ET.SubElement(content_types, f"{{{CT}}}Override", PartName=name,
                      ContentType=f"application/vnd.openxmlformats-officedocument.spreadsheetml.{kind}+xml")
    parts.update({
        "xl/workbook.xml": _xml(workbook),
        "xl/_rels/workbook.xml.rels": _xml(rels),
        sheet_rels_name: _xml(sheet_rels),
        "[Content_Types].xml": _xml(content_types),
        "xl/pivotTables/pivotTable1.xml": _xml(pivot),
        "xl/pivotTables/_rels/pivotTable1.xml.rels": _xml(_rels(("rId1", "pivotCacheDefinition", "../pivotCache/pivotCacheDefinition1.xml"))),
        "xl/pivotCache/pivotCacheDefinition1.xml": _xml(cache),
        "xl/pivotCache/_rels/pivotCacheDefinition1.xml.rels": _xml(_rels(("rId1", "pivotCacheRecords", "pivotCacheRecords1.xml"))),
        "xl/pivotCache/pivotCacheRecords1.xml": _xml(records),
    })
    replacement = path.with_suffix(".pivot.tmp")
    with ZipFile(replacement, "w", ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    replacement.replace(path)
    return {"source_sheet": source_sheet, "source_range": f"A1:C{len(rows)+1}",
            "record_count": len(rows), "cache_fields": ["region", "period", "revenue"],
            "target_certification": "pending", "adapter": "flat-region-period-sum-v1"}
