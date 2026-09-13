# Implementation decisions

The workspace supplies two architectural proposals and no executable reference pack. This build follows `Periodic_Report_System_Architecture.docx` for the native snapshot and four-format export design. The earlier Markdown remains useful for period, evidence, and publication contracts.

## First executable scope

The implemented deterministic foundation comprises a typed native snapshot, exact period-based revenue computation, fact-linked prose, table/chart/pivot content, an optional supplied image, three views, and independent DOCX/XLSX/PDF/PPTX exports. A local workbench, source inspection, persisted jobs, publication gates, report review, and immutable editorial revisions surround that core.

The built-in Python adapter and fixtures are manually authored. Bounded learning now compares three registered selection policies against independently inspected historical report/source pairs; optional model assistance proposes decisions within that envelope. Synthetic live checks are recorded separately in `VALIDATION.md`; there are no customer examples or hidden benchmark holdouts. Arbitrary reporting-policy synthesis and execution of uploaded/generated Python remain outside this release. Historical report values are evaluation observations, never production source inputs.

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

## Supplied images

The current image milestone accepts one optional still PNG/JPEG per report through the workbench, API or CLI. Both original and normalized files are bounded to 20 MiB (20,971,520 bytes); dimensions are bounded to 8,192 pixels per side and 16,000,000 total pixels. Format mismatches, animation, truncation and invalid embedded color profiles fail inspection. This bounded raster path does not perform OCR, infer facts, recover arbitrary diagrams or learn reporting policy from an image.

Ingestion preserves original bytes as immutable evidence and creates a separate PNG derivative: EXIF orientation is applied, embedded profiles are converted to sRGB, transparency is retained, and metadata is stripped. Asset inspection records both identities. The run freezes the selected asset, render hash, dimensions, description and decorative status; these fields participate in source snapshot identity and request idempotency. The description has a 500-character limit and must be nonempty unless the user marks the image decorative. Non-decorative images add a human review finding; their pixels never change revenue facts.

Generation verifies the bound original evidence and derivative. Existing snapshot previews and exports resolve only the frozen PNG, so they do not re-normalize older uploads under changed code. Missing or corrupt frozen bytes block; a legacy image without a render hash is never silently upgraded. Editorial and acceptance revisions retain image bindings. Existing published programs adopt image support through a newly reviewed and evaluated candidate.

The image appears in native flow, an Images worksheet and a dedicated canvas slide, with coverage in DOCX, XLSX, PDF and PPTX. Export placement preserves aspect ratio without cropping, stretching or upscaling. Office outputs contain native image objects with description/decorative metadata, while their pixels remain raster content. PDF descriptions and manifest disclosure do not constitute certified tagged-PDF accessibility. Image export support does not remove the pending Microsoft Excel native pivot interaction gate.

Candidate evaluation now uses `fixtures/report-image.png` alongside synthetic revenue observations, checks its frozen identity and complete view coverage, and smoke-tests all four mixed-content exports. Evaluation records original fixture and render digests. This is exposed development evidence, not a protected holdout or target-application certification.

## Trust boundary

This is a loopback-only, single-user application. It has no authentication or tenant boundary and must not be exposed as a hosted service. The API accepts only the registered reporting program, not arbitrary Python or template execution. Parsers reject active/external Office relationships, archive traversal/oversized expansion and unsupported formula-derived inputs. This does not constitute a production parser sandbox.

## Paired examples and bounded authoring

An immutable example binds one historical target, one distinct transaction source, explicit period, label/caveats and corpus role. DOCX inspection inventories ordered body regions and unsupported structural material so the learner cannot gain apparent completeness by omitting a region. The observation adapter independently reads explicit EUR/percentage labels, regional table cells and ordered membership, selected-region prose and the registered exact disclosure. It stores original target identity, locators, extraction methods and displayed precision. Unsupported notation, units, prose and region kinds remain unresolved.

The learner receives compact authoring/development cases without a Store or filesystem tool. It executes only the registered Python adapter under three selection options, comparing every candidate against the independent observations. It preserves multiple compatible hypotheses and contradictory examples instead of guessing a winner. The program's accepted selection changes computation, driver provenance and wording. No universal business-rule language or arbitrary Python executor was introduced.

An optional call to the configured model provider sees the bounded analysis and requirements, proposes an implemented option and explains remaining questions. The host validates its response and stores a receipt. Proposed choices never resolve their own consequential decisions. Every target region remains mapped, unresolved or explicitly out of scope with a reason and author. Region review does not claim template fidelity or validate an unknown numerical rule.

Learning jobs freeze candidate and corpus identities. Their final transaction checks both identities and the worker lease before writing candidate evidence and completing the job together. New decisions, changed examples, scope reviews and package changes invalidate evaluation. Publication additionally binds reference fixture identities and current corpus membership/exposure state. Public reconstruction reports located discrepancies; reserved evaluation reports only its gate result.

Reserved pairs are withheld by original content digest across asset aliases, ordinary previews/downloads, learning and production bindings. A pair cannot be retroactively reserved after example reuse, report use or durable generation/composition work has pinned its contents. Explicit reveal appends exposure history and changes its effective role to development. This is an application access boundary for the local workflow, not tenant authorization or a claim that repeatedly queried reserved gates remain statistically untouched.

## Captured model composition

The provider adapter uses the Responses protocol with requested JSON schema, tools disabled and `store:false`. Direct OpenAI retains its fixed HTTPS origin. Explicit CLIProxyAPI configuration accepts only loopback HTTP(S) endpoints and uses a separate local client credential; it never borrows the direct OpenAI key. No redirects, protocol fallback or proxy-reported model substitution are accepted. Proxy requests include a JSON-only/schema instruction because compatibility translation may omit enforcement of `text.format`; strict JSON parsing and host validation remain in force. `store:false` does not attest to downstream retention.

Credentials stay in the server environment. Provider, canonical endpoint, protocol, model and hard budgets are pinned in job input and cache identity. Request/schema/output digests, requested/proxy-reported model, response ID and usage appear in receipts. Deterministic tests inject transport responses; separate opt-in live validation uses the real configured proxy. Results are recorded with their scope in `docs/VALIDATION.md`.

Composition is a separate explicit job against a frozen report. It receives available facts and at most five selected qualitative source files, bounded further to twelve excerpts, 6,000 characters per excerpt and 24,000 characters overall. Historical targets and reserved sources are excluded by digest. The proposal permits one to three English paragraphs, eight to 150 words, and typed fact placeholders. It must reference the current total and selected region. Numeric literals, unsupported rankings, invalid references, hidden text, links and unverified quotations are rejected. Causal wording is restricted to attributed exact quotations from cited evidence and still requires review.

The host permits two composition attempts total. It captures validated provider result envelopes as immutable objects keyed by logical job/request identity, allowing a retried stage to reuse a recorded response. A crash or cancellation during an unrecorded network call can still leave uncertainty about remote work; no exactly-once billing guarantee is made. Successful composition creates a new review-required revision with frozen evidence, model receipt and attempt findings. Lease fencing and a check for newer sibling revisions protect the final commit. The original facts and snapshot remain unchanged, and exports never call the provider.

Deterministic checks and human acceptance are the present assurance boundary. There is no independent model semantic grader, calibrated reviewer accuracy, broad qualitative retrieval or automatic production narration hidden inside preparation. Archived program files still require restoration into a compatible installed runtime; they are not separately executable per-version environments.

## Validation

Use independent expected values plus behavioral mutations: explicit windows, missing comparison, zero denominator, row order, excluded transactions, new regions, invalid decimals and provenance cycles. Verify revision immutability, idempotency conflicts, publication compare-and-swap, stale worker fencing, cancellation, artifact integrity and export coverage. Image checks exercise normalization, safety bounds, descriptions, immutable bindings and export from frozen bytes without the original upload. Open actual exported Office/PDF files independently. Visual verification and target-application certification are recorded with their actual limits in `docs/VALIDATION.md`.
