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

- Source upload and inspection for CSV, XLSX, DOCX and text-bearing PDF. Original bytes are content-addressed and integrity-checked. Only an unambiguous, value-only CSV/XLSX transaction source can feed this revenue program.
- Explicit current/comparison intervals, timezone and data cutoff. Exact decimal arithmetic, deterministic driver selection, missing-period blocking, distinct missing/zero states, row-level source references and fact dependency checks.
- A native report with fact-linked prose, a typed regional table, a chart, a pivot definition and flow/grid/canvas presentations. Click facts to inspect their definitions and origins.
- Candidate policy decisions, independent synthetic regression evaluation, compare-and-swap publication, frozen source-code packages, and a pinned release for each run.
- Editable commentary creates a new immutable revision. Computed facts and prose are locked. Review acceptance creates an audited revision; it preserves earlier warnings and review findings in the acceptance history.
- Persisted jobs with idempotency conflict detection, worker leases, heartbeats, stale-result fencing and cancellation. The deterministic local jobs restart safely as a unit after a crash; stages record progress, not invented percentages.
- Four actual export adapters with per-component coverage and fidelity manifests. Exporting does not call source discovery, preparation or language generation.

## Format boundaries

| Export | Implemented behavior | Boundary |
| --- | --- | --- |
| DOCX | Editable prose/tables, named styles, explicit indent, repeated headers, static chart/pivot | Office pagination remains dependent on the target engine/fonts |
| XLSX | Materialized values, native chart, actual flat-source pivot definition/cache/records | Pivot structure is independently parsed; target-application interaction is not certified. Strict native policy blocks |
| PDF | Native flow rendered by ReportLab | A native-report PDF, not a claim of exact Word pagination |
| PPTX | Native text/tables/chart, complete canvas coverage with declared layout limits | PowerPoint text layout/editing still requires target-app certification |

Compatible exports disclose permitted static representations and pending certification. Required unsupported features block. Exported chart/pivot data uses approved regional aggregates, not original transaction identifiers. Office exports are downstream derivatives: editing them does not mutate the application report.

The native core also defines an image node. Arbitrary image ingestion and image-node exporting are not yet certified and are rejected rather than omitted. The executable fixture covers prose, table, chart and pivot; it does not complete the architecture's entire mixed-image milestone.

## Source contract

CSV uses UTF-8, comma delimiter, and exactly these columns:

```csv
transaction_id,date,region,status,amount,currency
example-1,2026-01-15,North,posted,500.00,EUR
```

Dates are ISO local business dates. Status is `posted` or `cancelled`; currency is EUR; amounts are finite nonnegative decimals with at most two fractional digits. Transaction IDs are unique. The source must include posted records in both requested intervals. Absent regions within those assumed-complete, nonempty intervals become zero; an absent whole period blocks. A timestamp or formula-derived source requires an explicitly implemented adapter.

The cutoff identifies the bound snapshot. There is no revision-timestamp column, so historical restatement filtering cannot be reconstructed. The app discloses this limitation.

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

A period JSON example is available in the runtime's `default_period()` and the native contract documentation. `foundry status` returns the persisted catalog. Reusing a request key with different inputs returns a conflict. Published runtime code drift blocks a new run; existing frozen snapshots remain exportable. Each release retains its source-code package and dependency lock for restoration.

After changing the backend, restore the archived release code or create and evaluate a new report type. Candidate versioning within an existing report type is not implemented yet. To try updated code with a fresh synthetic demo while preserving the earlier installation:

```sh
uv run foundry --data-dir .foundry-new seed-demo
uv run foundry --data-dir .foundry-new serve
```

Stop the existing server before starting another on the same port. Running `seed-demo` again in the original data directory does not upgrade its published program.

## Validation

```sh
uv run pytest
npm --prefix web run build
```

Tests cover independent expected results, source corruption, interval boundaries, cancellation, duplicate requests, missing periods, source drift, normalized region ties, provenance and graph cycles, immutable revisions, publication gates, unsupported prose, export coverage and actual Office structures. All example periods are exposed synthetic regression evidence; none is represented as an unseen holdout.

## Deliberately unfinished architecture work

Automated learning, model-backed composition/review, execution of untrusted program code, arbitrary Office template recovery, advanced pivot features, parser isolation, PostgreSQL/object-store deployment, multi-user authentication/authorization, protected holdout access and production service limits remain future milestones. Historical documents can be catalogued and attached through the API, but the app does not pretend an upload has learned a program.

This installation is a single-user, loopback-only development application. Do not expose it as a network service. Host/origin checks are defense in depth, not tenant authentication or a production sandbox.

See [implementation decisions](docs/IMPLEMENTATION.md), [native contracts](docs/native-contract.md), and [API contract](docs/api-contract.md). The three original brief files are preserved unchanged.
