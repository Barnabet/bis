# Report Foundry

A working local reporting application built from `Periodic_Report_System_Architecture.docx`. It materializes one typed, immutable native report and exports that same revision to DOCX, XLSX, PDF and PPTX.

The included regional revenue program is manually authored and the data is synthetic. It demonstrates the deterministic reporting and export foundation described in the brief. It does not claim to learn arbitrary reporting policies from uploaded examples.

## Run locally

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node.js 22+.

```sh
uv sync --extra dev
npm --prefix web ci
npm --prefix web run build
uv run foundry seed-demo
uv run foundry serve
```

Open [Report Foundry](http://127.0.0.1:8741). `seed-demo` is idempotent: it preserves an existing demo. Source artifacts and the SQLite catalog persist in `.foundry/`. Use `--data-dir PATH` before a CLI command to create a separate installation.

Office-to-PDF precision previews additionally require LibreOffice on `PATH`, or an explicit executable set before serving: `FOUNDRY_SOFFICE=/path/to/soffice uv run foundry serve`. All four export downloads work without LibreOffice; unavailable previews are disclosed. On this Codex host, use its bundled `dependencies/bin/override/soffice` runtime.

For frontend development, run `npm --prefix web run dev` alongside the API. Vite proxies `/api` to port 8741. Interactive API documentation is at `/docs`.

## What works

- Source upload and inspection for CSV, XLSX, DOCX, text-bearing PDF, PNG and JPEG. Original bytes are content-addressed and integrity-checked. Only an unambiguous, value-only CSV/XLSX transaction source can feed this revenue program.
- Explicit current/comparison intervals, timezone and data cutoff. Exact decimal arithmetic, deterministic driver selection, missing-period blocking, distinct missing/zero states, row-level source references and fact dependency checks.
- A native report with fact-linked prose, a typed regional table, a chart, a pivot definition, an optional image and flow/grid/canvas presentations. Click facts to inspect their definitions and origins.
- Candidate versions within the same report type, policy decisions, independent synthetic regression evaluation, compare-and-swap publication, frozen source-code packages, and a pinned release for each run. The active release remains selected while its replacement is reviewed.
- Editable commentary creates a new immutable revision. Computed facts and prose are locked. Review acceptance creates an audited revision; it preserves earlier warnings and review findings in the acceptance history.
- Persisted jobs with idempotency conflict detection, worker leases, heartbeats, stale-result fencing and cancellation. The deterministic local jobs restart safely as a unit after a crash; stages record progress, not invented percentages.
- Four actual export adapters with per-component coverage and fidelity manifests. Exporting does not call source discovery, preparation or language generation.

## Format boundaries

| Export | Implemented behavior | Boundary |
| --- | --- | --- |
| DOCX | Editable prose/tables, named styles, explicit indent, repeated headers, static chart/pivot and embedded image | Office pagination remains dependent on the target engine/fonts |
| XLSX | Materialized values, native chart, actual flat-source pivot definition/cache/records and an optional Images sheet | Pivot structure is independently parsed; target-application interaction is not certified. Strict native policy blocks |
| PDF | Native flow rendered by ReportLab, including the frozen image and its description | Word pagination equivalence and tagged-PDF accessibility are not certified |
| PPTX | Native text/tables/chart and an optional dedicated image slide, with complete canvas coverage | PowerPoint text layout/editing still requires target-app certification |

Compatible exports disclose permitted static representations and pending certification. Required unsupported features block. Exported chart/pivot data uses approved regional aggregates, not original transaction identifiers. Office exports are downstream derivatives: editing them does not mutate the application report.

The executable evaluation fixture combines prose, table, chart, pivot and a real image in all four exports. Image placement preserves aspect ratio without cropping, stretching or upscaling. Office files contain image objects with description/decorative metadata; the raster pixels are not editable diagram elements. PDF descriptions are visible and recorded in the manifest, but tagged-PDF accessibility is not certified.

## Source contract

CSV uses UTF-8, comma delimiter, and exactly these columns:

```csv
transaction_id,date,region,status,amount,currency
example-1,2026-01-15,North,posted,500.00,EUR
```

Dates are ISO local business dates. Status is `posted` or `cancelled`; currency is EUR; amounts are finite nonnegative decimals with at most two fractional digits. Transaction IDs are unique. The source must include posted records in both requested intervals. Absent regions within those assumed-complete, nonempty intervals become zero; an absent whole period blocks. A timestamp or formula-derived source requires an explicitly implemented adapter.

The cutoff identifies the bound snapshot. There is no revision-timestamp column, so historical restatement filtering cannot be reconstructed. The app discloses this limitation.

## Optional report image

Upload one still PNG or JPEG (`.png`, `.jpg`, `.jpeg`) and select it when creating a report. The input and normalized PNG must each fit within 20 MiB (20,971,520 bytes); dimensions are limited to 8,192 pixels per side and 16 million pixels in total. Animated images, mismatched extensions, truncated files and invalid embedded color profiles are rejected.

The original upload remains immutable evidence. Inspection applies EXIF orientation, converts an embedded color profile to sRGB, preserves transparency and strips metadata into a separate frozen PNG. Reports pin that PNG's hash, dimensions and original source identity. Previewing or exporting an existing snapshot uses those frozen bytes without normalizing the original again.

Provide a meaningful description of at most 500 characters, or explicitly mark the image decorative. Non-decorative images require human review of the image and its description. The application does not perform image OCR or infer report facts from pixels. Image selection, description and decorative status participate in request identity; changing them requires a new request key and creates a new report. Commentary revisions preserve the existing image binding.

## CLI workflow

```sh
uv run foundry ingest path/to/transactions.csv
uv run foundry create-type 'Regional revenue'
uv run foundry resolve PROGRAM_ID selection largest_absolute_change
uv run foundry resolve PROGRAM_ID completeness assumed_complete
uv run foundry resolve PROGRAM_ID template compatible_reviewed
uv run foundry evaluate PROGRAM_ID
uv run foundry publish PROGRAM_ID
uv run foundry run TYPE_ID ASSET_ID --period period.json --key period-request-1
uv run foundry export SNAPSHOT_ID docx --key word-export-1 --output output/report.docx
uv run foundry worker
```

To include an image, ingest it first and use its returned asset ID:

```sh
uv run foundry ingest path/to/report-image.png
uv run foundry run TYPE_ID ASSET_ID --period period.json --key image-request-1 \
  --image-asset IMAGE_ASSET_ID --image-alt 'Regional offices shown on a map.'
```

For a decorative image, use `--image-decorative` with `--image-asset`; its description may be empty. The API uses `POST /api/assets`, then the optional `image:{asset_id,alt_text,decorative}` field on `POST /api/report-runs`. Image inspection previews are available at `/api/assets/{id}/preview`; a report's pinned image is at `/api/report-snapshots/{id}/images/{node_id}`.

A period JSON example is available in the runtime's `default_period()` and the native contract documentation. `foundry status` returns the persisted catalog. Reusing a request key with different inputs returns a conflict. Retrying the same request after publication returns its original job and pinned program; a new request uses the active release.

## Upgrade a reporting program

After installing backend changes, restart the server before creating or evaluating a candidate. A running process whose code files changed reports `restart_required`; a published program that differs from the installed runtime reports `code_changed`. Existing snapshots and export artifacts retain their original identities. Archived source-code packages and dependency locks provide audit and restoration evidence; the application does not execute archived runtimes automatically.

In the workbench, create a new candidate from the active program, review its changes and policy decisions, evaluate it, and publish it. The report type, source assets and historical reports stay in place. Creating a candidate captures the installed code and preserves the old policy answers as context; new decisions, evaluation and release approval are required. The old release remains active until publication, although code drift can prevent new runs against it.

The equivalent CLI workflow uses the new candidate ID returned by the first command:

```sh
uv run foundry create-candidate ACTIVE_PROGRAM_ID --reason 'Update the installed revenue runtime'
uv run foundry resolve CANDIDATE_ID selection largest_absolute_change
uv run foundry resolve CANDIDATE_ID completeness assumed_complete
uv run foundry resolve CANDIDATE_ID template compatible_reviewed
uv run foundry evaluate CANDIDATE_ID
uv run foundry publish CANDIDATE_ID
```

Only one candidate can be open per report type. Retrying creation from the same base with the same reason returns that candidate. To abandon a replacement candidate, use `uv run foundry discard-candidate CANDIDATE_ID --reason 'Defer this update'`; discarding retains its history and leaves the active release unchanged. The initial candidate must be retained until its report type has a published release. Automatically assigned version numbers account for discarded candidates and are not reused. Published versions offer a source-package download in the workbench.

Publication checks both the evaluated candidate digest and its expected active release. It cannot overwrite a newer release. In-flight jobs keep their original program pin and never silently switch to the replacement. They may block if that pinned runtime is no longer installed.

Running `seed-demo` again preserves the existing demo; use the candidate workflow to upgrade its program. Programs published before image support must follow this workflow before generating image-bearing reports. Existing snapshots remain unchanged. A fresh demo includes the mixed-content image fixture; a separate `--data-dir` remains available for independent installations.

## Validation

```sh
uv run pytest
npm --prefix web run build
```

Tests cover independent expected results, source corruption, interval boundaries, cancellation, duplicate requests, missing periods, source drift, normalized region ties, provenance and graph cycles, immutable revisions, publication gates, unsupported prose, export coverage and actual Office structures. Image tests exercise normalization, bounds, frozen-byte integrity, descriptions, image-aware idempotency and export without re-reading original pixels. All example periods are exposed synthetic regression evidence; none is represented as an unseen holdout. See the [validation record](docs/VALIDATION.md) for the current automated and visual evidence.

## Deliberately unfinished architecture work

Automated learning, model-backed composition/review, image OCR or fact inference, execution of untrusted program code, arbitrary Office template recovery, advanced pivot features, parser isolation, PostgreSQL/object-store deployment, multi-user authentication/authorization, protected holdout access and production service limits remain future milestones. Historical documents can be catalogued and attached through the API, but the app does not pretend an upload has learned a program.

This installation is a single-user, loopback-only development application. Do not expose it as a network service. Host/origin checks are defense in depth, not tenant authentication or a production sandbox.

See [implementation decisions](docs/IMPLEMENTATION.md), [native contracts](docs/native-contract.md), and [API contract](docs/api-contract.md). The three original brief files are preserved unchanged.
