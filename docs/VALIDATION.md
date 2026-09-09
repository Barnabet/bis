# Validation record

Initial export validation: 8 September 2026. Program-upgrade and image automation validation: 9 September 2026. Dataset: supplied architecture's synthetic quarterly revenue fixture, reconstructed locally because the referenced companion archive was absent. The image milestone adds the repository's 640 × 240 PNG fixture. No hidden customer dataset or unseen-period evaluation is claimed.

## Automated verification

186 Python tests pass on Python 3.12.14, with two existing dependency deprecation warnings. The suite covers native contracts, independent revenue observations, source parsing and provenance, lifecycle/application boundaries, image normalization and frozen identity, actual export structures, safe precision-preview failures, and end-to-end API operation.

The end-to-end test creates and evaluates a candidate, publishes the exact digest, generates a report, creates an editorial revision, records human acceptance, exports all four formats, checks actual bytes and manifests, and ensures exports cannot invoke preparation again. Strict XLSX native-pivot requests finish as an explicit blocked job, not a hung request.

Critical behavior tests include wrong/missing source values, no comparison rows, cancelled and out-of-period transactions, row permutation, region normalization and ties, undefined growth, fact/graph cycles, numeric prose bypass, immutable source/snapshot records, altered object bytes, stale worker publication, cancellation, and duplicate requests after a newer release becomes active.

One full-suite attempt was interrupted by the host running out of disk space. After freeing only task-generated dependency caches and the host recovering capacity, the complete suite passed. No application failure is hidden by that infrastructure interruption.

## Export verification

The following visual evidence was recorded for the earlier image-free fixture. The page and slide counts below do not describe the new image-bearing report; mixed-content results are recorded separately below.

- DOCX reopened independently and rendered through bundled LibreOffice. The fixture fits on one page, retains explicit paragraph indentation, repeated table headers, accepted facts and static pivot/chart disclosure.
- XLSX independently loaded with openpyxl. Actual pivot definition, cache definition and cache records are present and reconcile to approved regional aggregates. The workbook was rendered with LibreOffice; the pivot and chart fit on the Analysis sheet's printed page. Original transaction IDs are not embedded.
- PDF generated independently from the frozen native flow with ReportLab. Its content and named destinations were verified and its page image inspected. This route is not described as matching Word pagination.
- PPTX reopened with python-pptx and rendered with LibreOffice. The complete fixture uses two slides with native text, tables and chart; visual bounds and text were inspected.
- Final seeded draft exports show a visible draft marker and retain draft status in delivery metadata. Actual Office-to-PDF previews are stored as separate immutable artifacts linked to their source export hashes.

The actual preview engine in this environment reports LibreOfficeDev 26.8.0.0.alpha0. Its identity is recorded with the preview. Microsoft Excel pivot interaction and PowerPoint/Word engine-specific fidelity are not certified. An attempted Excel UI inspection did not reach a workbook interaction result, so no certification was inferred.

## Browser verification

For the earlier image-free workflow, the production frontend built successfully with TypeScript and Vite. The actual local API was exercised through the browser: generation completed from the explicit period/source form, and the resulting report displayed the expected EUR 1,200.00 total and 20.0% growth. Clicking the North chart bar opened `region.north.current`, its exact EUR 500.00 value, and CSV source lines 7–8. Report, workbook and both presentation slides were inspected, along with source inspection and the published program's evaluation and decisions.

The report and new-run dialog were also inspected at a 390 × 844 viewport, then the browser was restored to its normal desktop viewport. A browser-triggered DOCX export completed with its stored Office-to-PDF preview, download and fidelity manifest links. The run-history disclosure opened the earlier snapshot and exposed its four preserved exports, each with download, preview and manifest access. No browser warning or error was reported in the final checks. Export artifact visual checks are recorded separately above; the native browser views are not presented as Office pagination previews.

## Program-upgrade verification

Sixteen new tests exercise the release lifecycle, including simultaneous candidate creation, discarded version retention, initial-candidate protection, stale decisions and evaluations, publication rollback, active-release compare-and-swap, and consistent reads during concurrent publication. They verify that old release/package bytes remain unchanged, old queued requests keep their release pins, incompatible historical jobs block, and previously frozen reports remain exportable without preparation. Startup identity tests distinguish a required process restart from an installed runtime that differs from an old release.

The actual workbench upgraded the existing synthetic report type from v1.0.0 to v1.1.0 through candidate creation, three explicit policy reviews, fresh evaluation and publication. A new report used v1.1.0 and retained the expected EUR 1,200.00 total and 20.0% growth. The old version remained accessible in history. A v1.2.0 draft then confirmed that the run selector still offered active v1.1.0; that test draft was discarded with a recorded reason and retained in history. The update dialog fit a 390 × 844 viewport without horizontal overflow, the desktop viewport was restored, and final browser diagnostics were empty. The production TypeScript/Vite build passed.

## Image milestone verification

Automated image checks cover PNG/JPG/JPEG decoding, EXIF orientation, alpha retention, metadata removal, embedded color profiles, format mismatches, animation, truncation and size/dimension limits. Lifecycle checks cover non-image bindings, required descriptions and decorative images, image-aware request conflicts, immutable revision bindings, corrupt render bytes and all four exports from frozen PNG bytes after the original upload is unavailable. These checks verify that images do not change revenue facts and that export does not invoke normalization again.

Candidate evaluation includes `fixtures/report-image.png` with prose, table, chart and pivot in the same native report. It checks original/render identities and image coverage in all three views, then smoke-tests DOCX, XLSX, PDF and PPTX. The evaluation records both image digests.

The actual 640 × 240 transparent fixture was passed through the runtime and all four export adapters. Eleven rendered pages/slides were inspected: DOCX 2, PDF 2, XLSX 4 and PPTX 3. No clipping, stretching, overlap or loss of core report content was observed. Local QA records in the ignored `output/image-qa/QA.md` and `summary.json` retain the original and render identities; these generated files are not part of the source repository. This visual evidence does not certify target-application editing or accessibility.

The browser uploaded a PNG, blocked an empty description for an informative image, and exercised the decorative toggle. The existing synthetic report type was upgraded to v1.3.0 through policy review, mixed-content evaluation and publication. An informative-image run completed; all three native views loaded the snapshot-bound 640 × 240 image, and source inspection worked. All four browser-triggered export jobs completed with download, preview and fidelity-manifest links, including stored Office-to-PDF previews for DOCX/XLSX/PPTX. Downloaded artifact digests, embedded image identities and descriptions matched their records, and the original image download retained the fixture bytes. Image worksheet and slide views fit a 390 × 844 viewport without horizontal overflow; the viewport was restored afterward. Browser error diagnostics were empty, and the final production TypeScript/Vite build passed.

## Remaining product boundaries

This verifies the bounded deterministic revenue workflow. It does not measure automatic policy inference, model-backed narrative correctness, image OCR or semantic interpretation, arbitrary template recovery, malicious-code isolation, tenant authorization, heavy-data performance, advanced Office features or production reliability at scale. Microsoft Excel native pivot interaction remains uncertified, and PDF image accessibility tagging is not certified.
