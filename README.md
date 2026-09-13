# Report Foundry

A working local reporting application built from `Periodic_Report_System_Architecture.docx`. It materializes one typed, immutable native report and exports that same revision to DOCX, XLSX, PDF and PPTX.

The registered regional revenue adapter can compare historical report/source pairs to distinguish three implemented selection policies. The included data and historical targets are synthetic. Optional model assistance through OpenAI or a local CLIProxyAPI instance proposes a policy or drafts fact-bound commentary; users review consequential decisions and every composed draft. This is bounded policy learning, not arbitrary reporting-program synthesis.

Registered Census and ONS profiles also reconstruct scoped monthly headlines from original public reports and published data. They preserve source vintages and units, generate later-month drafts, and export the same frozen facts. Full bulletins and arbitrary templates remain outside the supported scope; FMC quarter inspection exposes unresolved reconciliation blocks.

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
- Explicit Census/ONS source import and historical headline observation profiles, with independently checked monthly drafts. Source defects remain visible and block use; unknown report regions require scope review.
- Explicit current/comparison intervals, timezone and data cutoff. Exact decimal arithmetic, deterministic driver selection, missing-period blocking, distinct missing/zero states, row-level source references and fact dependency checks.
- A native report with fact-linked prose, a typed regional table, a chart, a pivot definition, an optional image and flow/grid/canvas presentations. Click facts to inspect their definitions and origins.
- Candidate versions within the same report type, policy decisions, independent synthetic regression evaluation, compare-and-swap publication, frozen source-code packages, and a pinned release for each run. The active release remains selected while its replacement is reviewed.
- Historical report/source pairs, independent target observations, a region coverage ledger, competing policy hypotheses and reconstruction evaluation. Reserved pair contents are withheld from authoring and ordinary asset access until explicitly revealed as development evidence.
- Editable commentary creates a new immutable revision. Computed facts and prose are locked. Review acceptance creates an audited revision; it preserves earlier warnings and review findings in the acceptance history.
- Optional policy proposals and commentary composition through a bounded Responses provider. Commentary uses frozen fact references and selected qualitative evidence, with deterministic checks, one repair attempt and mandatory human review. Live checks and their limited scope are recorded in `docs/VALIDATION.md`.
- Persisted jobs with idempotency conflict detection, worker leases, heartbeats, stale-result fencing and cancellation. The deterministic local jobs restart safely as a unit after a crash; stages record progress, not invented percentages.
- Four actual export adapters with per-component coverage and fidelity manifests. Exporting does not call source discovery, preparation or language generation.

## Format boundaries

| Export | Implemented behavior | Boundary |
| --- | --- | --- |
| DOCX | Editable prose/tables, named styles, explicit indent, repeated headers, static chart/pivot and embedded image | Office pagination remains dependent on the target engine/fonts |
| XLSX | Materialized values, native chart, actual flat-source pivot definition/cache/records and an optional Images sheet | Pivot structure is independently parsed; target-application interaction is not certified. Strict native policy blocks |
| PDF | Native flow rendered by ReportLab, including the frozen image and its description | Word pagination equivalence and tagged-PDF accessibility are not certified |
| PPTX | Native text/tables/chart and an optional dedicated image slide, with complete canvas coverage | PowerPoint text layout/editing still requires target-app certification |

Compatible exports disclose permitted static representations and pending certification. Required unsupported features block. Exported chart/pivot data uses declared aggregate or series columns; unrelated source data is excluded. Office exports are downstream derivatives: editing them does not mutate the application report.

The executable evaluation fixture combines prose, table, chart, pivot and a real image in all four exports. Image placement preserves aspect ratio without cropping, stretching or upscaling. Office files contain image objects with description/decorative metadata; the raster pixels are not editable diagram elements. PDF descriptions are visible and recorded in the manifest, but tagged-PDF accessibility is not certified.

## Revenue source contract

CSV uses UTF-8, comma delimiter, and exactly these columns:

```csv
transaction_id,date,region,status,amount,currency
example-1,2026-01-15,North,posted,500.00,EUR
```

Dates are ISO local business dates. Status is `posted` or `cancelled`; currency is EUR; amounts are finite nonnegative decimals with at most two fractional digits. Transaction IDs are unique. The source must include posted records in both requested intervals. Absent regions within those assumed-complete, nonempty intervals become zero; an absent whole period blocks. A timestamp or formula-derived source requires an explicitly implemented adapter.

The cutoff identifies the bound snapshot. There is no revision-timestamp column, so historical restatement filtering cannot be reconstructed. The app discloses this limitation.

## Learn a supported selection policy

Attach a historical DOCX/PDF report, one distinct CSV/XLSX transaction source and an explicit period to a report type. Assign its corpus role before learning. The current observation adapter recognizes explicit English EUR/percentage labels, supported regional tables, selected-region wording and the registered exact disclosure. Other regions remain visible and require a mapping implementation or an explicit scope exclusion with a reason. PDF page text, drawings, notes and complex layouts are not silently treated as reconstructed components.

The deterministic learning job runs three registered Python policies against permitted authoring/development examples: largest absolute revenue change, largest absolute percentage change, and largest current-period revenue. It records their actual predictions and located discrepancies. Percentage selection excludes undefined ratios and blocks if every regional ratio is undefined. All policies use stable normalized-region tie breaks.

Try the independently authored pairs in `fixtures/learning/ambiguous` and `fixtures/learning/discriminating`. Each contains an actual `report.docx`, `transactions.csv` and `period.json`. The first target selects North under all three policies, so the system retains the ambiguity. Adding the second pair distinguishes South by absolute change from North by current revenue and East by percentage change. Adding or revealing examples requires a fresh learning/evaluation basis before publication.

Review the selection decision and any unresolved regions, evaluate the exact candidate, then publish it. The chosen policy changes the driver facts, dependencies and computed wording for future periods. Contradictory or incorrect historical observations fail reconstruction; the application does not silently select the nearest answer. The adapter's posted-EUR source semantics, missing-region assumption and core presentation remain explicitly bounded.

Reserved targets and paired sources are withheld by content digest, including duplicate-file aliases. Explicitly revealing a pair records its transition to development evidence. Reserved evaluation exposes a pass/fail gate without target details; this access policy is not itself evidence of unseen-period accuracy, particularly after repeated evaluations. The repository's public synthetic pairs are never blind holdouts.

## Optional model assistance

Set `OPENAI_API_KEY` and an account-supported `FOUNDRY_OPENAI_MODEL` in the server environment to enable direct OpenAI requests. To use the local CLIProxyAPI service instead:

```sh
export FOUNDRY_MODEL_PROVIDER=cliproxyapi
export FOUNDRY_MODEL_BASE_URL=http://127.0.0.1:8317/v1
export FOUNDRY_MODEL_NAME=claude-opus-5
export FOUNDRY_MODEL_API_KEY='<your local proxy client key>'
uv run foundry serve
```

Use the proxy's client key, not its management or upstream OAuth credentials. The proxy provider never falls back to `OPENAI_API_KEY`. Configuration files matching `.env.*` are ignored by Git; they are not automatically loaded, so explicitly source a trusted local file before starting the service. The workbench/API shows the provider, endpoint, protocol and model without returning the credential. Deterministic learning and reporting/export work without a key.

Model-assisted learning receives only the bounded hypotheses, permitted target-region evidence and explicit requirements. It proposes one implemented policy and unresolved questions; it cannot change source calculations, reference observations, publication gates or application code. The existing CLI/API engine value `openai` selects the configured model provider for backward compatibility.

Commentary drafting receives the frozen report facts and up to five selected qualitative source files, within a smaller excerpt budget. Historical target reports and reserved evidence cannot be supplied as new-period commentary. The model has no tools and returns structured templates containing fact references. Successful drafting creates a new review-required snapshot; it never edits the original or accepts itself. Source identities, accepted structured responses, receipts and validation attempts are retained. Exporting that revision reuses its captured wording.

The provider uses `/v1/responses`, no tools, 2,048 output tokens and 45 seconds per request. Direct OpenAI uses its fixed HTTPS origin; CLIProxyAPI URLs are restricted to loopback HTTP(S), with no redirects or protocol/model fallback. Endpoint, protocol and model participate in queued-request and captured-response identity. A proxy response reporting a different model is rejected. Its reported model is not an independent attestation of the upstream service.

Some proxies accept `text.format` without enforcing its schema. Proxy requests therefore include explicit JSON-only/schema instructions; fenced or malformed JSON still fails, and application validation remains mandatory. `store:false` is sent as a request preference, not a guarantee about proxy or upstream retention. Composition permits at most two attempts total. Numeric-reference, exact-quotation and wording checks do not establish semantic truth; independent model grading and calibrated narrative-quality evaluation remain future work.

To repeat the opt-in synthetic live validation with the configuration above:

```sh
uv run python scripts/validate_live_model.py --run-live
```

This creates a fresh workspace under ignored `output/cliproxyapi-live/`, runs one learning job and two commentary jobs with exactly `claude-opus-5`, then exports DOCX/XLSX/PDF/PPTX without additional model calls. It allows at most five outbound requests including repairs. The saved summary includes receipts, synthetic request bodies, retry/cache checks, prose and artifacts; it excludes credentials and headers. Passing structural checks leaves the commentary pending semantic and visual review. The script neither accepts reports nor changes the main workspace. It requires explicit opt-in and is separate from the offline test suite.

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

Tests cover independent expected results, source corruption, interval boundaries, cancellation, duplicate requests, missing periods, source drift, normalized region ties, provenance and graph cycles, immutable revisions, publication gates, unsupported prose, export coverage and actual Office structures. Image tests exercise normalization and frozen identity. Learning tests inspect real DOCX targets, preserve ambiguity, reject contradictions and compare values, display precision, table membership/order and exact disclosure text. Provider/composition tests cover response failures and fact/evidence constraints without claiming live-model quality. See the [validation record](docs/VALIDATION.md) for the current automated and visual evidence.

The broader [historical-to-future experiment](docs/EVOLUTION_VALIDATION.md) uses three independent synthetic corpora, six historical report/source pairs and twelve later periods. It checks full expected reports, 48 source transformations and all four export formats. Repeat its deterministic or explicitly opted-in live route with:

```sh
uv run python scripts/validate_evolution.py --offline
# Configure the local CLIProxyAPI environment above before the live route.
uv run python scripts/validate_evolution.py --run-live
```

Live mode uses exact `claude-opus-5` for three policy proposals and twelve commentaries, capped at 27 requests including repairs. It creates a separate workspace under ignored `output/evolution-validation/`, preserves failures, and leaves reports awaiting review. The earlier 13 September milestone passed all twelve periods using 16 real requests and 485 regression tests. This validates automatic later-period drafts within the registered revenue policies after explicit policy review and period selection.

The [public report/data benchmark](docs/PUBLIC_CORPUS_VALIDATION.md) contains twelve real Census, ONS and FMC period pairs with 21 original-file hashes. The original generic-import baseline remains reproducible with `uv run python scripts/validate_public_corpus.py --fetch`. Explicit **Census and ONS headline profiles** now support original-source import, independently observed historical targets, candidate learning/evaluation, later-month drafts and all four exports. They reconstruct eight Census or seven ONS headline measures; full bulletin prose, appendices, uncertainty and publisher layout remain outside that scope. FMC quarter inspection retains unresolved totals, image-report and unit blocks.

Select the same public family when creating a program and importing its report/data files in Sources. CLI equivalents are `foundry create-type "Retail headlines" --family census_marts` and `foundry ingest source.xlsx --public-family census_marts`. Public periods must be exact calendar months with the immediately preceding month as comparison. Release checks have calendar-day precision; intraday availability is not certified. Scope decisions and report acceptance remain explicit.

```sh
uv run python scripts/validate_public_workflows.py --offline
# Uses the configured local CLIProxyAPI and exact claude-opus-5; at most ten calls.
uv run python scripts/validate_public_workflows.py --run-live
# Read-only quarter inspection; does not certify an FMC report.
foundry inspect-fmc output/public-corpus-cache/fmc-cfs-2025-source.xlsx --period 2025-Q1
```

The public workflow experiment uses the first two pairs per family for authoring and four later months for draft/evaluation jobs, with counterfactual and invalid-input cases. All public answers were previously researched, and later ONS observer failures were repaired as development regressions. These are **exposed regression checks, not untouched holdouts or proof of arbitrary report automation**. See the validation record for actual receipts, results and limitations.

## Deliberately unfinished architecture work

Arbitrary Python program synthesis/execution, broader metric and source-policy learning, calibrated semantic model review, image OCR or fact inference, imported Office template recovery, advanced pivot features, parser isolation, PostgreSQL/object-store deployment, multi-user authentication/authorization, retention controls and measured production service limits remain future milestones. Archived runtime packages are evidence and restoration artifacts, not independently executable environments. The implemented hypothesis search and optional composition do not complete the broader architecture.

This installation is a single-user, loopback-only development application. Do not expose it as a network service. Host/origin checks are defense in depth, not tenant authentication or a production sandbox.

See [implementation decisions](docs/IMPLEMENTATION.md), [native contracts](docs/native-contract.md), and [API contract](docs/api-contract.md). The three original brief files are preserved unchanged.
