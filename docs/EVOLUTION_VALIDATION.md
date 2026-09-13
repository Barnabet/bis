# Historical-to-future reporting validation

Experiment fixed on 13 September 2026 before the live model run. This tests the existing regional-revenue adapter with three selection policies. It does not implement arbitrary report or program synthesis.

## Fixed matrix and independent answers

Three distinct corpora each contain two independently authored historical DOCX/CSV pairs (Q3 and Q4 2025), followed by four later periods (Q1–Q4 2026). Current-period values and expected reports for all twelve future cases are frozen before authoring. The future Q3/Q4 comparison figures reconcile to their historical 2025 current figures, so this is a chronological reporting sequence rather than unrelated quarter labels.

| Corpus | Registered policy | Historical pairs | Future periods |
| --- | --- | ---: | ---: |
| Current revenue | Highest current revenue | 2 | 4 |
| Absolute change | Largest absolute revenue movement | 2 | 4 |
| Percentage change | Largest absolute relative movement | 2 | 4 |

Coverage includes declines, opposite-sign ties, selection changes, new and disappearing regions, zero comparison with explicit undefined regional growth, fractional currency amounts, and posted/cancelled records on and around interval boundaries. Static expected JSON and actual DOCX reports were authored without invoking the candidate runtime. A separate audit recomputed answers from physical CSV rows using integer cents and exact fractions, then read the DOCX paragraphs and cells. All 18 fixture reports were rendered and inspected.

The 72 source/period/expected/report artifacts are indexed in `fixtures/evolution/frozen-sha256.json`. Its final SHA256 is `70ec7fceede6b203b9bd92015fa988705e093dd9c85b58d9e05725f1015197f1`. Git attributes preserve exact fixture bytes, including the CSV files' CRLF record endings. Each experiment copies and hashes the fixtures before the first model call, then verifies that they and the application code remain unchanged. Requirements do not disclose the expected policy. Future reports and expected JSON are never registered in the authoring/evaluation corpus; future-only region names act as leakage canaries at the outgoing learning-request boundary.

These are public, deliberately designed synthetic cases. “Future” means later periods withheld from that authoring request, not an untouched statistical benchmark or a customer-data accuracy claim.

## Required checks

Each corpus must uniquely support and, in live mode, receive the correct model proposal for its intended policy. Learning must leave decisions unresolved and the program unpublished. The script then records predeclared synthetic-fixture review choices and publishes a release after real evaluation. All four future periods must run against that same release without further learning, policy edits or publication.

Every future snapshot is checked against all expected totals, exact ratios/display values, selected-driver values and dependencies, every regional dataset cell and row order, the complete pivot source, and exact physical source-line provenance. Its independently authored DOCX target must also map completely and match the generated native report. Checking dataset cells directly matters: the historical observation comparator checks most numeric observations against facts, which alone would not detect a corrupted dataset cell.

Four additional no-model variants per future period reverse CSV rows, split a transaction into equal-sum records, multiply included amounts by a positive factor, and change excluded amounts substantially. This adds 48 generation runs. Values, selection, scaling relationships and physical provenance must remain correct under these transformations.

Live mode adds one fact-bound commentary job per future period. Every original fact, dataset, computed node, view and release binding must remain unchanged; all requested core facts must be referenced. Completed request retries and real captured-response cache replays must avoid new model calls. DOCX, XLSX, PDF and PPTX are exported and independently reopened for every final period: 48 exports, with complete node coverage, exact prose, numeric table readback and immutable draft identities. Export stages forbid model dispatch.

Separate integrated negative tests cover contradictory historical selections, wrong target totals, unresolved ambiguity, missing windows, invalid values, duplicate transactions, unsupported currencies, schema drift and empty inputs. Admission rejection is distinguished from a durable blocked worker job. Failures must not create a plausible zero report or replace an existing valid snapshot.

## Model and review boundary

The live route is the configured local CLIProxyAPI `/v1/responses` endpoint with exact `claude-opus-5`. The fixed budget is 15 logical model jobs (3 learning, 12 composition) and at most 27 host dispatches including the existing single repair attempt per commentary. The transport observer delegates real requests, records only synthetic request bodies and safe receipts, and never records authentication headers. Offline mode forbids every model request.

The automated result is a **draft**. Every generated snapshot is `review_required`, including deterministic generation. Publication review, explicit period metadata, and final report acceptance are distinct requirements. The scripted fixture decisions are not represented as human acceptance. Missing records for one region inside an otherwise nonempty period follow the approved assumed-zero rule; the application cannot independently prove that such omissions were legitimate zero activity.

## Reproduction

```sh
uv run python scripts/validate_evolution.py --offline
# Configure the local CLIProxyAPI environment described in README.md first.
uv run python scripts/validate_evolution.py --run-live
uv run pytest
```

For exact Office-to-PDF previews, set `FOUNDRY_SOFFICE` to the local LibreOffice executable. Each invocation creates a fresh directory under ignored `output/evolution-validation/`; it never overwrites earlier evidence or the main workspace. The summary records partial failures as well as successful stages. A live structural pass remains pending independent prose and visual review.

## Findings and results

The broader cases exposed three application defects. Before live authoring, the historical observer did not recognize the adapter's explicit undefined-growth marker, and PDF export rejected the Unicode minus sign produced by its own currency formatter. Targeted regressions reproduced both failures. The fixes recognize only the exact ratio marker with an explicit undefined status, and allow the supported minus glyph without changing the source text or weakening other font checks. Visual inspection later found two PDFs with a pivot caption alone on a new page. The PDF adapter now keeps that pivot heading, table and caption together; both captured cases have regression tests.

The initial offline harness also referenced an incorrect manifest field; this was a test-harness defect. Its record includes the then-unfixed PDF glyph failure and a runtime-restart rejection when a repair changed the application during preflight. The stopped run remains at `output/evolution-validation/20260913T092906Z-b60b60/`. It made no model calls and is not counted as a live model-quality failure.

### Execution results — 13 September 2026

The corrected offline run at `output/evolution-validation/20260913T093137Z-7dbcde/` passed all three corpora, twelve future periods, 48 source transformations and 48 exports with zero model calls. The live run at `output/evolution-validation/20260913T093314Z-82b328/` used the same frozen fixture manifest and passed the following matrix:

| Check | Observed result |
| --- | --- |
| Historical learning | 3/3 sole supported policies proposed correctly; two pairs per corpus |
| Release reuse | 3 releases unchanged across four future quarters each |
| Future numeric and full target-DOCX comparisons | 12/12 passed |
| Additional source transformations and physical provenance | 48/48 passed |
| Final fact-bound commentaries | 12/12 passed host checks and independent agent review |
| First-attempt commentary acceptance by host validator | 11/12; one bounded repair |
| Real Responses calls / captured records | 16 / 16: three learning calls and thirteen commentary attempts |
| Captured-response replays | 12/12 passed with dispatch disabled and no new calls |
| Original export jobs / independent readbacks | 48/48 passed; visual PDF correction recorded separately below |
| Unexpected model dispatch attempts | 0 |
| Human report acceptance | None; all final reports remain drafts |

The absolute-change Q4 commentary initially referenced nonexistent `driver.region.change`. The host rejected it with `FACT_REFERENCE_INVALID`; the retained repair used the correct `driver.change`. Independent review found correct figures, signs, displayed percentages and selected regions in all twelve final commentaries, with no invented causes. One learning rationale calls the percentage policy `largest_absolute_percentage_change` in prose; its structured proposal is the correct registered `largest_percentage_change`, and the executable selection is correct. This is a nonblocking explanatory inconsistency, retained in the review record rather than silently corrected.

The real request log verifies that future expected reports never entered learning or composition. The 16 calls are additional to the earlier narrow live-validation session documented in `VALIDATION.md`. They count host dispatches; proxy-internal retries and upstream model identity are not independently observable.

### Export repair and final review

The caption correction was applied after the completed live run. A separate continuation at `pdf-caption-recheck-20260913T094248.195021Z/` re-exported all twelve captured final PDFs through real jobs, with provider generation and both network transports explicitly disabled. All twelve independent readbacks and complete five-node coverage checks passed with zero attempted model calls. The continuation preserved all 223 original entity records, 123 job records and 235 stored blob contents, including the 16 model-call records, 72 snapshots and three releases. Only twelve new export jobs and export records were added. Original summaries, PDFs and failed visual evidence remain intact.

All twelve DOCX exports were inspected across 16 LibreOffice-rendered pages; all twelve XLSX exports across 36 worksheet pages; all twelve PPTX exports across 24 slides; and all twelve corrected native PDFs across 18 pages. Both previously orphaned PDF captions now share a page with the complete pivot heading and table. The final 48-artifact set spans 94 inspected pages/slides. No clipping, missing figures or chart-label overlap was found. Four DOCX pivot tables continue onto a second page with repeated headers and their final row/caption; this is a visible pagination limitation, not missing content. These are render inspections, not certification of Microsoft Office editing, interactive pivot behavior or accessibility. Original PDF failure images and hashes remain alongside `visual-review-corrected-pdf.json`; DOCX/XLSX review records are in `visual-qa-word-workbook/`.

The final offline suite passes **485 tests** on Python 3.12.14, with two existing dependency deprecation warnings. Its 107 new cases include independent-answer/readback mutation checks, integrated failure paths, undefined-growth observations, negative PDF glyphs and both caption regressions. No frontend code changed in this milestone.

The main application was restarted and both existing report types were upgraded through the normal candidate/review/evaluate/publish API. `Example-driven regional revenue` v1.7.0 passed 14/14 checks and `Quarterly revenue report` v1.11.0 passed 10/10. Both runtime identities are current. Exact policies, learning evidence and resolutions, all 17 prior release rows/packages, 18 prior program rows, seven assets, six snapshots, fifteen exports, two examples and 23 jobs were preserved. No model calls were needed. Evidence is in `output/evolution-validation/final-main-upgrade-summary.json`.

### Evidence index and limits

Generated evidence remains local under ignored `output/evolution-validation/`; the source fixture matrix, validator, independent checks and regressions are versioned. The live directory contains `summary.json`, frozen fixture hashes, synthetic request packets, captured receipts, generated reports, exports, `independent-review.json`, `independent-chain-audit.json`, and the export continuation. The original chain audit describes the completed live run before the twelve documented continuation exports; its baseline counts should not be confused with the subsequently extended workspace.

This supports reproducible, automatic draft generation from later data under three reviewed policies in one report family. It does not establish arbitrary report-template recovery, new metric/source-policy synthesis, automatic source discovery or scheduling, semantic correctness for unseen customer narratives, or autonomous report acceptance. Period intervals and data completeness assumptions remain explicit inputs. Model review here is an independent agent assessment of these particular outputs, not a calibrated quality score.
