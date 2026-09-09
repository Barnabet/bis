# Implementation decisions

The workspace supplies two architectural proposals and no executable reference pack. This build follows `Periodic_Report_System_Architecture.docx` for the native snapshot and four-format export design. The earlier Markdown remains useful for period, evidence, and publication contracts.

## First executable scope

Build the DOCX specification's deterministic milestones first: a typed native snapshot, exact period-based revenue computation, fact-linked prose, table/chart/pivot content, three views, and independent DOCX/XLSX/PDF/PPTX exports. Add a local workbench, source inspection, persisted jobs, publication gates, report review, and immutable editorial revisions around that working core.

The built-in regional revenue package and fixtures are manually authored synthetic examples. There are no customer examples, hidden holdouts, or model-quality claims. Arbitrary automatic policy learning and execution of uploaded/generated Python are outside this release. Uploaded historical reports are catalogued as evidence, never used as new-period numbers.

## Architecture

- Python modular monolith: FastAPI API, CLI, local worker, contracts, runtime, ingestion, storage, exporters.
- SQLite with WAL and transactional job leasing for a single-user local installation. Content-addressed immutable files live outside the relational records. PostgreSQL/object storage and hardened tenant isolation remain deployment work.
- React/TypeScript native workbench served by the same local API after a production build.
- Published program digests cover the registered runtime, contracts, export code, dependency lock, policy and decisions. Runs pin this version. Code drift blocks future execution of that release instead of silently substituting a newer runtime.
- Existing report types can create and discard replacement candidates. One candidate is open at a time; automatically allocated versions include discarded history. Publication compares the evaluated candidate digest and its expected active release before atomically updating the active pointer.
- Exports only read a frozen snapshot. They cannot bind sources, recompute business facts, compose prose, or modify a snapshot.
- Presentation and editability capabilities are reported separately. A native pivot is structurally verified; certification in a target Office application is a separate gate. A compatible export may disclose pending certification; strict export blocks it.

## Program upgrades

A candidate starts from a published base and captures the installed code identity. It retains prior policy answers as review context but resets current decisions, evaluation and publication approval. The active release is independent of this draft. Creation retries with the same base and reason reuse the open candidate; discarding a candidate records the reason without deleting history or changing the active pointer.

Publication does not rewrite older release records, package artifacts, report snapshots or exports. Read models derive `active` and `historical` status from the report type's active pointer; stored publication evidence remains intact. An existing run request keeps its first resolved release even after a newer release becomes active.

Runtime identity distinguishes a process that must restart after on-disk changes from a published program whose registered code differs from the installed runtime. A restart loads the new host code; a newly evaluated candidate adopts it for future reports. Archived source-code packages and locks remain restoration evidence, not an automatically executable version store. Jobs pinned to incompatible historical code fail explicitly, and a draft update does not silently repair them.

## Trust boundary

This is a loopback-only, single-user application. It has no authentication or tenant boundary and must not be exposed as a hosted service. The API accepts only the registered reporting program, not arbitrary Python or template execution. Parsers reject active/external Office relationships, archive traversal/oversized expansion and unsupported formula-derived inputs. This does not constitute a production parser sandbox.

## Validation

Use independent expected values plus behavioral mutations: explicit windows, missing comparison, zero denominator, row order, excluded transactions, new regions, invalid decimals and provenance cycles. Verify revision immutability, idempotency conflicts, publication compare-and-swap, stale worker fencing, cancellation, artifact integrity and export coverage. Open actual exported Office/PDF files independently. Visual verification and target-application certification are recorded with their actual limits.
