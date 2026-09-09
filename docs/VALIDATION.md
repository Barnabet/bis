# Validation record

Date: 8 September 2026. Dataset: supplied architecture's synthetic quarterly revenue fixture, reconstructed locally because the referenced companion archive was absent. No hidden customer dataset or unseen-period evaluation is claimed.

## Automated verification

100 Python tests pass on Python 3.12.14. The suite covers native contracts, independent revenue observations, source parsing and provenance, lifecycle/application boundaries, actual export structures, safe precision-preview failures, and end-to-end API operation.

The end-to-end test creates and evaluates a candidate, publishes the exact digest, generates a report, creates an editorial revision, records human acceptance, exports all four formats, checks actual bytes and manifests, and ensures exports cannot invoke preparation again. Strict XLSX native-pivot requests finish as an explicit blocked job, not a hung request.

Critical behavior tests include wrong/missing source values, no comparison rows, cancelled and out-of-period transactions, row permutation, region normalization and ties, undefined growth, fact/graph cycles, numeric prose bypass, immutable source/snapshot records, altered object bytes, stale worker publication, cancellation, and duplicate requests after a newer release becomes active.

One full-suite attempt was interrupted by the host running out of disk space. After freeing only task-generated dependency caches and the host recovering capacity, the complete suite passed. No application failure is hidden by that infrastructure interruption.

## Export verification

- DOCX reopened independently and rendered through bundled LibreOffice. The fixture fits on one page, retains explicit paragraph indentation, repeated table headers, accepted facts and static pivot/chart disclosure.
- XLSX independently loaded with openpyxl. Actual pivot definition, cache definition and cache records are present and reconcile to approved regional aggregates. The workbook was rendered with LibreOffice; the pivot and chart fit on the Analysis sheet's printed page. Original transaction IDs are not embedded.
- PDF generated independently from the frozen native flow with ReportLab. Its content and named destinations were verified and its page image inspected. This route is not described as matching Word pagination.
- PPTX reopened with python-pptx and rendered with LibreOffice. The complete fixture uses two slides with native text, tables and chart; visual bounds and text were inspected.
- Final seeded draft exports show a visible draft marker and retain draft status in delivery metadata. Actual Office-to-PDF previews are stored as separate immutable artifacts linked to their source export hashes.

The actual preview engine in this environment reports LibreOfficeDev 26.8.0.0.alpha0. Its identity is recorded with the preview. Microsoft Excel pivot interaction and PowerPoint/Word engine-specific fidelity are not certified. An attempted Excel UI inspection did not reach a workbook interaction result, so no certification was inferred.

## Browser verification

The production frontend builds successfully with TypeScript and Vite. The actual local API was exercised through the browser: generation completed from the explicit period/source form, and the resulting report displayed the expected EUR 1,200.00 total and 20.0% growth. Clicking the North chart bar opened `region.north.current`, its exact EUR 500.00 value, and CSV source lines 7–8. Report, workbook and both presentation slides were inspected, along with source inspection and the published program's evaluation and decisions.

The report and new-run dialog were also inspected at a 390 × 844 viewport, then the browser was restored to its normal desktop viewport. A browser-triggered DOCX export completed with its stored Office-to-PDF preview, download and fidelity manifest links. The run-history disclosure opened the earlier snapshot and exposed its four preserved exports, each with download, preview and manifest access. No browser warning or error was reported in the final checks. Export artifact visual checks are recorded separately above; the native browser views are not presented as Office pagination previews.

## Remaining product boundaries

This verifies the bounded deterministic revenue workflow. It does not measure automatic policy inference, model-backed narrative correctness, arbitrary image/template recovery, malicious-code isolation, tenant authorization, heavy-data performance, advanced Office features or production reliability at scale.
