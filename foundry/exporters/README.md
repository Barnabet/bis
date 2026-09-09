# Native report exporters

`export_snapshot(snapshot, format, output_dir, policy="compatible")` compiles the built-in native revenue snapshot into actual DOCX, XLSX, native-flow PDF, or PPTX bytes. It returns `path`, `filename`, `media_type`, `sha256`, `size_bytes`, `manifest`, and `manifest_path`. Use a fresh job directory. Existing artifacts are never overwritten.

The exporter reads only the snapshot. It does not read source files, discover data, run models, rewrite accepted prose, or execute generated reporting code. Snapshot schema/reference validation and pivot-source reconciliation run before rendering. Each manifest identifies the exact snapshot digest, program, source snapshot, adapter code digest, renderer/library version, actual artifact digest and per-component representation and location.

## Capability envelope

The tested core contains the summary and commentary, a regional table, a grouped revenue chart and a region-by-period sum pivot. Source data for editable charts and pivot caches contains only the approved regional aggregates. Materialized values remain authoritative; exports contain no formulas. Ratios require IEEE floating-point storage in Office, while exact decimals remain in the native snapshot. Currency conversion to a native number rejects loss of its exact decimal display precision.

DOCX uses explicit 18-point paragraph indentation and 18-mm margins from the flow recipe, repeated table headers, and a static chart and pivot result. Native PDF uses its declared Helvetica flow profile and the same required content. It does not claim Word pagination equivalence. Static chart and PDF text support the declared Windows Latin font profile; unsupported glyphs block visibly. PPTX keeps the fixture on two slides with an editable native chart and tables. Required content can continue across additional table slides rather than disappear. Unsupported asset nodes, chart types and pivot configurations block.

XLSX contains actual SpreadsheetML pivot definition, cache definition, cache records, relationships, materialized cells and approved source data. An independent openpyxl parser verifies those parts and the cache count. The bundled LibreOffice renderer also opens and renders the fixture. These checks do **not** certify interactive behavior in Microsoft Excel.

- `compatible` includes the native XLSX pivot with an explicit pending certification warning.
- `strict` blocks the required native XLSX pivot until target-application interaction is certified.
- `static` explicitly permits replacing native pivot interaction with a static displayed result.

The pivot adapter follows [Microsoft's PivotTable documentation](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-pivottables). It is deliberately limited to flat approved `region`, `period`, `revenue` aggregates. It does not support slicers, macros, external connections, OLAP, calculated fields or transaction drill-down.

## Precision previews

`foundry.exporters.preview.render_office_preview(artifact_path, output_dir, timeout_seconds=30)` renders an already generated Office artifact into PDF. Configure `FOUNDRY_SOFFICE` to a controlled local executable, or install a compatible `soffice` on PATH. The helper rejects external relationships and active-content parts, creates a unique temporary profile, invokes the executable without a shell, enforces a timeout and validates the PDF. It returns both source and preview hashes, the rendering engine's version, page count and `origin="exact_office_artifact"`.

This is an optional local conversion helper, not a production sandbox for arbitrary uploaded Office documents. The host should call it only for exports produced by this application and enforce its deployment's resource and isolation policy. Missing backends and timeouts produce explicit `ExportError` codes. A PDF produced this way certifies the chosen engine's rendering only; Microsoft Office compatibility remains a separate test.

## Verification

Run `.venv/bin/python -m pytest tests/test_exports.py -q`. Tests inspect real files through independent readers and exercise exact values, coverage, native chart/pivot parts, approved embedded datasets, formula-like text, strict capability gates, contradictory pivot caches, immutable output bytes, and preview failure handling. Visual QA also renders all four fixture formats. The acceptance unit is the resulting file and its declared capability scope, not merely a valid ZIP or successful function call.
