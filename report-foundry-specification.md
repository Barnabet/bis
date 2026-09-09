# Report Foundry — Complete design specification

Revision 0.1 · 8 September 2026

Proposed architecture; see the worked example for the exact tested boundary.

# 01 — Product and architecture

## 1. Product definition

A report type is a repeatable reporting policy. A period is an execution parameter, not an instruction to reconstruct that policy again.

The product has two operations:

```text
learn(historical_examples, explicit_requirements) -> candidate_program
run(published_program, period, input_snapshot, editorial_inputs) -> report_run
```

`learn` may produce unresolved questions as well as working components. `run` produces a document and an audit bundle, or a specific explanation of why a valid document cannot be produced.

A historical example consists of the report, its period definition, and the information available when that report was authored. Inputs may include spreadsheets, exports, source documents, images, or management commentary. Multiple files can serve one input role, and one file can contain several periods.

### Success means more than numerical agreement

A successful report has the right facts, calculations, entities, selection of topics, mandatory wording, conditional sections, narrative interpretation, and presentation. Its important claims are traceable to supplied evidence. It does not silently discard a difficult section.

A report is not necessarily a deterministic function of numeric source files. Editorial choices and external explanations may be necessary inputs. The input contract must expose those dependencies instead of treating their absence as a model-quality problem.

### The guarantee we should offer

Given a published program, supported inputs, and its declared editorial parameters, the system either produces a report satisfying the configured acceptance checks or exposes a failure/review state. Automated checks do not establish universal correctness of unrestricted prose.

Do not promise exact recovery of a hidden policy from any finite collection of examples. Multiple policies may explain the same observations; example-based program synthesis explicitly encounters this ambiguity [R2]. The product must manage it.

## 2. First shippable scope

The architecture should not bake in a business domain. The first release should nevertheless have a deliberately bounded format envelope:

- Reference reports: DOCX and digitally generated PDF; retain both structural extraction and rendered-page access.
- Period inputs: CSV/XLSX plus text-bearing PDF/DOCX commentary.
- Output: editable DOCX with a preview generated from that exact DOCX.
- Content: fixed prose, computed prose, tables, static/generated figures, conditional sections, and evidence-grounded narrative.

Scanned documents, unusual spreadsheet layouts, complex diagrams, and publication-grade page reconstruction are explicit capability extensions. Detect unsupported material and surface it; never claim successful full coverage after flattening it away.

“Any number of examples” means there is no hard-coded small example count. It does not mean every example enters every model context or every example costs a full end-to-end investigation. Corpus size is handled by storage, indexing, incremental comparison, and selective work.

This initial scope is an implementation choice. The underlying contracts allow new ingestion and rendering adapters without redesigning the learning process.

## 3. The architecture I would build

### A. The application

A Python application owns users, artifacts, report types, jobs, permissions, lifecycle transitions, and billing/cost limits. It invokes models through a thin provider adapter.

There are three execution environments, not three collaborating agent personalities:

| Environment | Can inspect | Can change | Cannot do |
|---|---|---|---|
| Authoring sandbox | Allowed historical examples; candidate package; public regression failures | Candidate code, evidence notes, task status | Publish; alter protected expectations; see reserved reports |
| Evaluation environment | Candidate outputs and independent expected observations | Evaluation results | Rewrite the candidate to make a test pass |
| Production runtime | Published package; current permitted input snapshot | Run artifacts only | Edit policy; browse arbitrary sources; change code |

The evaluator is primarily ordinary code. A separate model call may review narrative, but it is not an autonomous manager or the authority for numeric correctness.

### B. One program-authoring agent

The agent's job is to author and maintain the complete reporting program. Its normal work unit is a coherent component: a table and associated commentary, a section, or a shared computation.

Within one work unit, the same agent reads the example, investigates candidate inputs, writes code, executes it, and reviews discrepancies. This avoids a mandatory translation boundary between “understanding” and “implementation.” Whether it improves outcomes is an experimental question, not an assumed theorem.

A fresh model context can take over a later work unit. Continuity comes from committed artifacts, not a giant uninterrupted conversation. The agent starts with the program map, relevant evidence, known decisions, and the current task—not the whole history.

### C. A constrained recurring runtime

The runtime binds inputs, performs declared extraction, executes the reporting program, asks a model for bounded prose, validates, and renders. The composing model receives no shell and no general filesystem or internet access.

A new source format or broken formula returns work to authoring in a separate candidate version. Generation does not fix itself by mutating its dependencies.

## 4. The reporting program

The central product artifact is a package with these responsibilities:

```text
program/
  manifest.json          # Input roles, entrypoint, component index, policies
  editorial.md           # Voice, section objectives, narrative constraints
  prepare.py             # Adapters, computations, selection, document plan
  extraction/            # Optional declared qualitative extraction tasks
  presentation/          # Trusted template and visual assets
  evidence/              # Observations, hypotheses, decisions, coverage
  regression/            # Read-only references to approved expectations
  environment.lock       # Reproducible dependency specification
```

Platform-owned evaluation fixtures live outside the writable package. The package may contain references to them and additional candidate-authored unit tests.

A publish operation freezes a content digest covering code, policies, template, prompts, dependencies, and relevant decisions. A version label is useful to humans; the digest identifies actual content.

### Do not introduce a universal business-rule language

Use Python for calculations, grouping, filtering, threshold logic, and selection. Use a small document model for structure. Use natural language for editorial intent. The combination is the reporting program.

Do not express the same calculation separately in YAML, prose, and Python. Record its meaning in evidence, but make one executable implementation authoritative.

Likewise, do not normalize every customer's data into one giant universal business schema. Each package has a small internal vocabulary suited to its report type. The platform standardizes interfaces and provenance, not the meaning of every possible metric.

## 5. Model freedom is a publication-time decision

Each document block is one of:

**Literal:** approved text or an approved presentation asset. No model call.

**Computed:** the program determines the content, including exact prose and tables. No model call.

**Narrative:** a model may compose within a declared evidence set, scope, and output contract.

A narrative block also has an assurance policy. For strict numerical sentences, the program can own the sentence completely. For explanatory prose, the model can use prepared facts and attributed source statements. For genuinely open-ended synthesis, the package can permit broader selection from a scoped qualitative corpus, with corresponding review requirements.

Do not force all narrative into slots. Do not force every exact sentence through a model. The package decides where variability is useful.

These modes are not separate sections: one section can contain all three.

## 6. Human interaction

The system asks a user only when an unresolved choice materially changes future outputs and cannot be resolved from accessible examples or declared policy.

A useful question shows the alternatives and their consequences: “Should commentary highlight the largest absolute changes or the largest percentage changes? These would select different regions in March.” A useless question asks the user to explain a whole report.

Users can approve a rule, supply additional commentary, mark an observed historical error, or keep a component draft-only. Approvals are versioned policy inputs, not hidden chat memory.

Human review is concentrated on ambiguous reporting policy and release acceptance. It should not become a substitute for writing validators for every routine table cell.

## 7. Operational shape

Start with one deployable application, PostgreSQL for metadata/jobs, an object store for immutable files, and separate isolated workers for untrusted code. Do not start with a multi-service agent platform.

Use a database-backed work queue with short transactions, leases, and idempotent result publication. PostgreSQL documents `SKIP LOCKED` as useful for avoiding contention among consumers of a queue-like table [R8]. That primitive does not by itself provide exactly-once execution.

Start with sequential authoring. Add parallel investigations only for measured bottlenecks and disjoint artifact ownership. Production prose blocks can run concurrently when their dependencies are complete.

## 8. Explicit non-goals

The first release does not autonomously discover inaccessible external data, infer undocumented causality, guarantee pixel-identical reconstruction of arbitrary PDFs, fine-tune a model for each customer, or mutate a published program during generation.

It also does not introduce a manager agent, a voting committee for every field, a vector database solely because examples exist, or a visual agent workflow builder. These are possible later tools, not prerequisites.


---

# 02 — Learning a report

## 1. Learning is a build process with a visible coverage ledger

The system must account for every meaningful observed document region. Before interpreting formulas, create a document map and a coverage ledger.

Each region is marked `uninvestigated`, `mapped`, `implemented`, `verified`, `needs_decision`, or `out_of_scope`. A component can be implemented without yet being verified. A report cannot become publishable by simply losing uninvestigated regions during extraction.

Regions include footnotes, captions, conditional-looking pages, chart labels, and tables—not only body paragraphs. Decorative elements can be classified as presentation-only.

## 2. Ingest and preserve the evidence

Store original report/input bytes, media type, digest, upload provenance, period metadata, and corpus assignment. Never overwrite an earlier snapshot with an updated source file.

Extract a structural document representation and retain references back to the original. Docling offers a representation with hierarchy, text, tables, pictures, layout where available, and provenance [R5]. I would evaluate it as an ingestion adapter, not treat its output as unquestionable truth.

For native DOCX, also inspect styles, tables, headers, footers, and embedded assets directly. For PDFs, keep page images for ambiguous tables and visual structure. Preserve spreadsheet formulas, cached values, sheet names, merged cells, and displayed number formats as distinct information.

A source locator must say what it actually identifies. PDF page/bounding-box references, DOCX structural paths, and spreadsheet cell addresses are different locator types. Do not invent page coordinates for formats that did not provide them.

### Independent observations

Extract important expected values and structural observations before allowing the candidate program to influence them. Each expectation stores a source location and extraction method. High-impact ambiguous extraction requires source inspection or confirmation.

These observations are the test oracle, not the candidate program's output. Candidate-authored tests are useful for internal logic, but cannot independently certify that the program reproduces a historical report.

## 3. Establish corpus roles before learning

Assign examples to authoring, development evaluation, or reserved evaluation. Assignment is enforced by storage permissions and tool access, not merely an instruction in a prompt.

When data is scarce, use all available examples for authoring if necessary and say that no unseen-period evidence exists. A single example can support a provisional program; it cannot demonstrate unseen-period generalization.

Once an evaluation failure is exposed to authoring, that example is development/regression evidence. Do not keep reporting it as untouched holdout performance.

Report versions may correspond to different policy eras. Before reconciling incompatible observations, check whether the reporting requirements changed. Do not average distinct policies into one confused rule.

## 4. Bootstrap a candidate

One initial authoring call receives the document map, small source-file profiles, and explicit user requirements. It produces:

- A component map and shared semantic vocabulary.
- A first input-role proposal.
- A prioritized list of unresolved work.
- A package skeleton with explicit unimplemented components.

It does not have to correctly explain the whole report in one pass. It must not fill missing implementations with plausible text to make a preview look complete.

Choose one representative connected slice first. Prefer a slice containing a source dependency, a calculation, a selection decision, a narrative obligation, and a visible output. Prove the whole path before implementing dozens of isolated metrics.

## 5. The authoring work loop

The application selects an eligible task whose upstream dependencies are stable. The agent may propose tasks or explain why another component must be handled first, but the application owns status and scheduling.

```text
load compact task context
  -> inspect relevant report regions and source profiles
  -> formulate or compare candidate rules
  -> execute small probes
  -> update candidate implementation
  -> run focused regression and behavior checks
  -> submit patch, evidence, and remaining questions
  -> application checks and commits, or rejects the patch
```

The agent uses ordinary Python files. It is not required to express every intermediate thought as schema-valid JSON. A final task result has a small structured envelope: task ID, changed files, evidence references, test references, proposed status, and remaining blockers.

### Tool surface

Expose a small set of capabilities:

| Capability | Result |
|---|---|
| `inspect_sources(scope, query)` | File profiles, selected rows/cells, document regions, or previews |
| `read_artifact(id, range)` | Relevant package/evidence content |
| `execute_python(task_id, files)` | Sandboxed execution with artifact references and capped logs |
| `evaluate(candidate, components, corpus_role)` | Focused machine-readable discrepancies |
| `submit_patch(task_id, base_digest, changes)` | Candidate patch proposal; application-controlled commit |
| `propose_decision(component, alternatives, impact)` | A user-facing policy decision record |

Implementation can combine these into fewer tools. Keep tool results compact and retrievable rather than returning full datasets by default. Tool documentation should include failure behavior, permissions, and examples [R9].

### Starting budgets

Start with a maximum of 20 tool actions per authoring task and at most two unsuccessful repair rounds after a stable failure is identified. These are configurable initial settings, not measured optimal values.

A task that is too large should be split with a preserved dependency map. A task blocked on information should stop. A task whose repair attempts repeat the same failure should escalate with the best available candidate and evidence. Do not reinitialize the same vague prompt indefinitely.

## 6. Evidence is an annotation on the program, not a separate teaching product

For each material rule, store a short record:

```text
Rule: regional_driver_selection
Meaning: identify regions discussed in the movement paragraph
Observed: example_A section 2 mentions North and South
Candidates: largest absolute change; largest percentage change
Evidence: probe_17; source observations obs_A_21 and obs_A_22
State: unresolved
Implementation: program.py::select_drivers (provisional)
Impact: commentary could discuss different regions in unseen periods
Next action: find or request a distinguishing example
```

Machine-stable fields are ID, component, evidence references, state, implementation reference, and decision reference. Explanations remain text. Do not require a universal formal hypothesis language or arbitrary numeric confidence estimates.

Accepted states are `observed`, `supported`, `approved`, `assumed`, `contradicted`, and `unresolved`. These describe different evidence relationships; they are not a single increasing confidence scale. An explicit approved rule may intentionally supersede a historical observation.

## 7. Recover semantics before overfitting values

For every important quantity, determine or expose:

Its source role and population; its unit and scale; the time window and comparison basis; exclusion and missing-data rules; the calculation; rounding/display conventions; and the conditions under which it appears.

For selected content, also investigate ranking criteria, thresholds, ties, minimum sample sizes, stable ordering, and whether human discretion is an input.

For explanatory prose, distinguish mathematical contribution from causal explanation. An input table may establish that one region accounts for most of a change. It may not establish that a marketing campaign caused that change.

When source information is absent, add an explicit editorial input or mark the claim unsupported. Do not search for ever-more-elaborate correlations simply to imitate the historical sentence.

## 8. Generalization procedure

For a candidate rule:

**Reproduce the observed outputs.** Match values, table membership/order, section presence, and mandatory wording with their actual display conventions.

**Compare plausible alternatives where the rule is underdetermined.** Focus on alternatives that would materially change new reports. It is unnecessary to enumerate every mathematically possible program.

**Look for a distinguishing existing example.** Use inexpensive profiles or targeted probes across the corpus to identify periods where candidate outputs differ.

**Ask a targeted question only when necessary.** Present the alternatives with their consequences and support.

**Add behavioral tests derived from the accepted rule.** These test implementation consistency, not the truth of the original inference.

**Evaluate unseen periods where available.** Keep their reference reports out of the authoring environment until the reserved evaluation has been recorded.

### Helpful behavioral checks

Row permutation should not change an order-insensitive aggregation. A transaction beyond the period boundary should not change a period-filtered metric. A new region must participate according to the stated population rule. Ties must produce the declared stable order. A zero denominator must produce the declared undefined state, not infinity or fabricated growth.

Counterfactual cases must remain within the rule's validity assumptions. A perturbation that makes a dataset semantically impossible is a robustness test, not evidence about normal business behavior.

## 9. Incremental learning from more examples

For each new example, first parse and fingerprint its structure, profile inputs, and execute the current candidate. Compare outputs with independently observed expectations.

If the example is explained, attach evidence and stop. If it introduces a new condition, add a scoped task. If it contradicts a rule, investigate input revisions, extraction mistakes, policy changes, and historical errors before modifying code.

Only affected components and their dependents need an authoring revisit. Full corpus checks can run at publication, while interactive work uses focused checks.

Do not repeatedly feed all reports to the model. Maintain an index of component-to-example mappings and retrieve the most relevant evidence. Selective retrieval and external persistent notes are established context-management techniques [R10]; the exact selection policy should be evaluated on this product's corpus.

## 10. Publication request

Authoring may request publication when coverage is complete, declared checks pass, and material unknowns have an allowed resolution. The application independently verifies those conditions.

The release record contains corpus exposure, supported input shapes, policy decisions, known limitations, test outcomes, template validation, package digest, and model/prompt metadata. A polished preview is not a publication gate.


---

# 03 — Contracts and report program

## 1. What gets a schema

Structure the artifacts that cross an execution boundary or control application behavior. Do not structure every exploratory observation or require an agent to serialize its reasoning.

The four main boundaries are the example bundle, package manifest, prepared report, and composed fragments. Source references and period semantics are shared types. A validation finding has a small separate result envelope.

The executable schemas in `contracts/` cover the reference subset: period, prepared report, composed fragments, and shared source/fact types. Example bundles and package manifests below are normative interface descriptions for the application build; their full validation implementation is a subsequent milestone. Do not mistake an illustrative API field list for implemented server code.

Schema conformance establishes shape, not truth. Structured-output documentation explicitly warns that valid structured responses can still contain mistakes [R3]. Apply semantic and provenance checks separately.

## 2. Example bundle

An example bundle has an immutable ID, report artifact references, period definition, input-role bindings, optional editorial inputs, and corpus role.

```json
{
  "example_id": "example_2025_02",
  "report_artifact_ids": ["artifact_report_2025_02"],
  "period_id": "period_2025_02",
  "bindings": {
    "deliveries": ["artifact_delivery_export_2025_02"],
    "management_commentary": ["artifact_notes_2025_02"]
  },
  "corpus_role": "authoring"
}
```

Artifact IDs resolve through the application's authorization layer. They are not arbitrary filesystem paths supplied to a privileged reader. Bindings can initially be proposed; ambiguous bindings require resolution before they become a published input contract.

A missing expected source can be recorded explicitly. It must not become an empty but apparently valid dataset.

## 3. Period semantics

The executable `period.schema.json` includes a human label, local start date, exclusive end date, an explicit comparison window, an IANA timezone string, and a timezone-aware data cutoff.

```json
{
  "label": "March 2025",
  "start": "2025-03-01",
  "end_exclusive": "2025-04-01",
  "comparison": {
    "start": "2025-02-01",
    "end_exclusive": "2025-03-01"
  },
  "timezone": "Europe/Paris",
  "as_of": "2025-04-03T12:00:00+02:00"
}
```

The host verifies that windows have positive duration and that timezone identifiers exist. Date-only source records are interpreted as local business dates. Timestamped sources require explicit timezone conversion before filtering; do not assume that UTC midnight equals the local reporting boundary.

The program must declare how it uses `as_of`. If source records have revision timestamps, apply the declared revision policy. If they do not, bind an immutable snapshot captured by that cutoff and disclose that later revision filtering cannot be reconstructed from those files.

The demonstration uses date-only CSV data and treats `as_of` as snapshot metadata. It does not implement historical revision selection or fiscal-calendar inference.

Comparison windows are explicit because “previous period” may not mean the preceding calendar month. Fiscal calendars, year-to-date reporting, rolling periods, and prior-year comparisons belong in the period policy, not in the model's interpretation of a label.

## 4. Package manifest

The production manifest must define these fields:

| Field | Meaning |
|---|---|
| `schema_version` | Manifest contract revision |
| `report_type_id`, `version` | Human identity and release label |
| `prepare_entrypoint` | Approved Python entrypoint within the package |
| `input_roles` | Required/optional roles, accepted shapes, matching rules, validation |
| `period_policy` | Calendar/comparison/cutoff semantics |
| `parameters` | Declared editorial or operational inputs |
| `components` | Stable component IDs, dependencies, modes, assurance requirements |
| `extraction_tasks` | Optional declared model-assisted extraction contracts |
| `editorial_artifact` | Package-relative writing instructions |
| `presentation_artifact` | Trusted template/assets |
| `failure_policy` | Which omissions, disclosures, and fallbacks are authorized |
| `evaluation_policy` | Required checks and approval conditions |

The host creates the release digest from canonical file content and stores release approval separately. A package cannot make itself approved by setting a boolean in its own manifest.

Input-role contracts specify schema, units, allowed file multiplicity, required comparisons, and drift behavior. An alias mapping such as `Net Sales -> revenue_net` is permissible only when supported or explicitly approved. Fuzzy matching is a candidate-binding aid, not a silent production decision.

## 5. Preparation interface

The production entrypoint is conceptually:

```python

def prepare(context: PreparationContext) -> PreparedReport:
    """Return facts, evidence, and a complete document plan.

    Inputs are immutable and explicitly bound. No model calls, network reads,
    undeclared filesystem reads, or writes to the published package.
    """
```

`PreparationContext` contains the period, bound local artifacts, any validated extraction results, approved parameters, and run-local output locations for generated tables/figures.

A report program can use ordinary helper modules. The platform does not require a separate workflow node per formula. Shared computations should execute once and feed multiple components.

All unknowns must be represented as missing/undefined states or findings. Exceptions remain useful for fatal input/schema errors. Numeric zero is never a substitute for missing information.

### Optional extraction precedes pure preparation

For unstructured inputs, the host runs declared extraction tasks first. Each task identifies source scope, extraction instructions, output schema, expected provenance, and missing/contradictory-evidence behavior.

Extraction output is a captured model result, not a deterministic calculation. Validate and store it, then pass it into `prepare`. Do not hide model calls inside a supposedly deterministic Python function.

For a qualitative-only report, preparation may mostly bind validated excerpts, structure the narrative work, and establish obligations. The architecture does not require numeric facts to be useful.

## 6. Prepared report

`PreparedReport` is the sole input to production composition and rendering, aside from pinned editorial/presentation assets. It has:

- Package and input-snapshot digests, report type, and period.
- A fact registry and qualitative evidence registry.
- An ordered document plan containing literal, table, narrative, and figure blocks.
- References to assets generated during preparation.

The reference schemas use direct literal text, table rows made of fact IDs, narrative block contracts, and digest-identified figures. The reference renderer demonstrates literal/table/narrative only and rejects unsupported blocks.

### Facts

A fact has an ID, kind, raw value, unit, display string, status, provenance, and dependency references. IDs are stable semantic identifiers, not display labels.

```json
{
  "kind": "number",
  "value": "0.15",
  "unit": "ratio",
  "display": "+15.0%",
  "status": "known",
  "sources": [],
  "inputs": ["deliveries.current", "deliveries.comparison"]
}
```

This illustrates a derived fact; its parents must exist and have traceable provenance. Reference validation rejects cycles and unknown parents. A fact may instead point directly to source locations.

Serialize precision-sensitive numbers as decimal strings and calculate with an explicit decimal or integer policy. Store the raw value separately from its displayed representation. Specify whether percentages are ratios or percentage values, and distinguish percentage change from percentage-point change.

A fact's display string is owned by the program. A composing model cannot change `+15.0%` into `15.0 percentage points` by editing the referenced value, although surrounding prose can still introduce that semantic error and requires checking.

Known numeric facts must contain finite decimal values. Undefined and missing numeric facts have `null` values and explicit display conventions. `NaN`, infinity, and blank-as-zero are not accepted.

### Provenance

A source reference contains the artifact SHA-256 digest and a locator. For example:

```json
{
  "artifact_sha256": "<64 lowercase hexadecimal characters>",
  "locator": "sheet=Deliveries;cell=G42"
}
```

The locator is intentionally format-specific text in the reference contract. Production ingestion should use typed locator variants once adapters are implemented.

Derived facts reference upstream facts and, where practical, an executable lineage artifact containing filters, grouping keys, formula version, and included source row IDs. Do not put millions of row references in model context. The reference code uses aggregate input locators rather than implementing full row-level lineage.

Provenance says where a claim came from. It does not certify that a source statement is true. Distinguish source assertion, computed result, and inferred interpretation in the production evidence model.

### Narrative blocks

Each narrative block names its allowed facts/evidence, required references, objective, word limit, and authorized fallback.

```json
{
  "id": "movement_commentary",
  "kind": "narrative",
  "instructions": "Describe the period movement and selected regions. Do not infer causes.",
  "allowed_fact_ids": ["deliveries.current", "deliveries.growth"],
  "required_fact_ids": ["deliveries.current", "deliveries.growth"],
  "allowed_evidence_ids": [],
  "max_words": 100,
  "fallback_text": null
}
```

The package can authorize deliberate flexibility in emphasis. Where exact selection is part of the reporting policy, preparation selects the candidates first. Where selection is editorial, preparation supplies the evidence pool and the block's obligations explicitly.

## 7. Composed fragments

The model returns a block ID and paragraphs represented as inline spans. A span is either text or a reference to a prepared fact. Paragraphs may list qualitative evidence IDs.

```json
{
  "block_id": "movement_commentary",
  "paragraphs": [
    {
      "spans": [
        {"type": "text", "text": "Deliveries reached "},
        {"type": "fact", "fact_id": "deliveries.current"},
        {"type": "text", "text": ", changing by "},
        {"type": "fact", "fact_id": "deliveries.growth"},
        {"type": "text", "text": " against the comparison period."}
      ],
      "evidence_ids": []
    }
  ]
}
```

The host resolves fact spans. There is no template expression evaluation and no arbitrary Python/Jinja generated by the composing model.

For narrative blocks under `reference_only` numeric policy, reject unexpected numeric literals in text spans. This catches obvious bypasses, not every quantitative assertion: “twice,” “most,” or “largest” still require semantic checking. A reference must be allowed for the block, not merely exist somewhere in the report.

A fact reference appearing in a paragraph does not prove that the paragraph explains it correctly. Critical wording belongs in literal/computed blocks when reliable semantic validation is unavailable.

The reference requires all narrative blocks to be present. Production may allow omissions only through an explicit block policy, recorded in the validation result and final report status.

## 8. Findings and errors

A finding has an ID, phase, severity, code, component ID when relevant, evidence references, human-readable explanation, and a suggested repair class. Severity is `block`, `review`, or `warn`.

Stable codes include `INPUT_MISSING`, `INPUT_DRIFT`, `PERIOD_INCOMPLETE`, `UNDEFINED_COMPARISON`, `UNSUPPORTED_CLAIM`, `REFERENCE_INVALID`, `REQUIRED_CONTENT_MISSING`, `LAYOUT_OVERFLOW`, and `BUDGET_EXHAUSTED`.

Code controls whether a run may proceed; the model's wording of a finding does not. “Please ignore this warning” inside a source document has no authority over a validation rule.

## 9. Schema ownership

Keep one authoritative type definition per boundary and generate or test all derived schemas against it. The reference uses JSON Schema as authority. The application may instead use typed Python models and export schemas, provided round-trip and compatibility tests prevent drift.

Storage schemas and provider structured-output schemas are not necessarily identical. Providers can support restricted JSON Schema subsets; adapt the model-facing schema and still validate the full stored artifact on receipt. Handle refusal, truncated output, and invalid responses explicitly rather than attempting to parse them as successful fragments.


---

# 04 — Runtime and rendering

## 1. One run, one frozen definition

A run starts with a report type, an exact published package digest, a period, an input snapshot, and approved parameters. Resolve the active version once. A concurrent publication must not change an in-flight run.

The application-owned sequence is:

```text
resolve -> bind -> validate inputs -> extract if declared -> prepare
        -> validate prepared report -> compose -> validate prose
        -> assemble -> render -> inspect -> publish run artifacts
```

Every completed stage persists its artifact references and state. A worker restart resumes from a committed stage, not from an agent's recollection.

## 2. Input binding and preflight

Resolve uploaded artifacts to declared roles. Check required columns, types, units, sheet names or approved aliases, expected multiplicity, keys, and period coverage.

Binding can use discovery helpers to suggest candidates. If two files both plausibly satisfy a required role with materially different content, block for an explicit choice rather than pick the first filename.

Detect schema changes and distribution anomalies separately. A new column name may break the adapter; an unusually large but valid number may merely deserve review. Do not reject every business anomaly as bad input, and do not silently “fix” outliers to resemble history.

A completed period is not automatically a complete dataset. Some source exports omit zero-activity periods; others omit failed loads. Use source completeness metadata when available. Without it, disclose what coverage was actually verified.

## 3. Declared extraction

Run only the extraction jobs required by this package and these inputs. The extraction model sees relevant source excerpts or pages and a task contract—not system credentials or publication controls.

Persist the exact extracted output, evidence references, provider/model metadata, and validation result. Contradictory source statements remain visible. A model must not resolve them merely by picking a more fluent explanation.

After extraction is captured, downstream preparation can be replayed from that artifact. Calling the same model again is a new stochastic attempt, not a deterministic replay.

## 4. Deterministic preparation

Execute the package in a sandbox with its pinned environment and read-only input mounts. Write only run-local output artifacts.

Preparation computes the facts, table rows, chart data, conditional blocks, selected narrative candidates, and unresolved-input findings. It should be independent of wall-clock time except for explicitly supplied parameters.

The prepared document plan is complete: even a missing optional component has a recorded decision. The composing model is not expected to discover a missing appendix from an old example.

Ordinary Python functions are sufficient initially. Avoid an elaborate task graph for every intermediate value. Record meaningful block dependencies and use conservative recomputation when dependency tracking is uncertain.

## 5. Composition

Each call receives a bounded group of related narrative blocks, relevant prepared facts/evidence, and approved style instructions. It does not receive the entire historical corpus.

Start with one call per coherent section, grouping short tightly related paragraphs. Split unusually large sections at semantic boundaries. Independent sections can run concurrently after their dependencies are ready.

Use a shared glossary, naming conventions, and package-wide tone instructions. An executive summary depends on the finished section content, so compose it after those sections are accepted. Avoid repeatedly regenerating it while body sections are still changing.

The model may select emphasis only where the block contract permits it. It must not invent causes, new source facts, comparison definitions, or table membership.

### Data access when narrative is genuinely open-ended

Some reports require synthesis across a larger qualitative corpus. The published package may authorize a read-only search tool scoped to designated artifacts, with a retrieval budget and evidence requirements. This is an explicit capability extension—not arbitrary internet browsing or access to the learning workspace.

Start with preparation-selected excerpts. Add bounded retrieval only after testing demonstrates that the preselected context fails to capture relevant information.

## 6. Validation and local repair

First check syntax, block IDs, required references, allowed evidence, numeric-literal policy, word limits, and completeness. Then review substantive support, comparison language, causality, omissions, and contradictions.

Repair only the failed block and downstream dependents. The repair input includes the original block contract, original evidence, previous text, and specific failures. Do not ask for an unconstrained “improved version.”

Starting production budget: one initial composition and at most two repair attempts per block. This is a tunable design default, not a promised quality/latency optimum.

An authorized deterministic fallback can be used after failures, but only if the package declares it adequate for that block's obligations. The run records the fallback. A required analysis paragraph cannot silently turn into an empty string while the run is marked successful.

A factual/preparation failure cannot be repaired by prose. A policy or code defect creates a new authoring task against a candidate version. The production run remains blocked or draft-only.

## 7. Document rendering

Use a trusted template built during authoring, not layout code written every period. Bind the prepared document tree and validated prose into it.

For DOCX output, I would start with a small renderer over `python-docx` and/or `docxtpl`, selected by prototype fidelity tests. `docxtpl` supports templates but has run/paragraph/table tag-placement restrictions [R6]. Those constraints belong in template compilation and validation, not in a prompt asking the model to “preserve formatting.”

The renderer must handle table repetition, header rows, column widths, number alignment, figures, captions, page breaks, conditional sections, and cross-references. A template can include stable visual styles without making every page position fixed.

### Fidelity policy

Define fidelity per package: semantic structure, brand/style fidelity, or strict approved layout. Do not imply that a flattened PDF can always be turned into an exactly equivalent editable template.

Prefer the original editable template where available. Otherwise, reconstruct a template and show a one-time preview for approval. Missing fonts or unsupported visual elements become explicit limitations.

For tables that grow, specify overflow behavior before publication: continue across pages with repeated headers, change approved orientation, split into approved sub-tables, or move rows to an appendix. Do not shrink text indefinitely to make it fit.

### Rendering inspection

Produce the preview from the actual DOCX to be delivered, using a pinned conversion environment. Inspect for missing assets, blank pages, clipped text, table overflow, unresolved field codes, and broken cross-references. Compare layout using tolerances, not byte-for-byte ZIP equality.

For high-assurance templates, stress-test long headings, negative numbers, large figures, long lists, and minimum/maximum table sizes. Runtime inspection still matters because new combinations can break layout.

The supplied reference emits Markdown only. The DOCX/render-inspection path is specified here but is not implemented in the demonstration.

## 8. Caching

Cache keys must include everything that can change a stage's output and be scoped to the tenant/authorization boundary.

```text
parse_key = digest(source_bytes, parser_version, parser_configuration)
prepare_key = digest(package_content, input_snapshot, period, parameters,
                     extraction_outputs, execution_environment)
compose_key = digest(block_contract, selected_context, editorial_version,
                     provider_model, generation_settings)
render_key = digest(assembled_document, template, renderer_environment)
```

Hash canonical representations. Do not use filenames, run labels, or “same month” as cache identity. A revised input must invalidate affected results.

An exact validated prose artifact can be reused when its entire dependency key matches. This reuses a prior result; it does not prove the model is deterministic. Keep a bypass option for repeated-generation evaluation.

Use conservative package-wide invalidation first. Optimize to component-level invalidation only after dependency tests are reliable. Incorrect reuse is worse than an extra calculation.

## 9. Durability, retries, and idempotency

Assume job execution may occur more than once. Store a unique logical stage key, an attempt number, a lease/fencing token, and output digests.

Claim work in a short transaction. Execute outside the transaction. Publish a result only if the lease token is still current. A stale worker may finish, but cannot overwrite the accepted output.

Use an idempotency key on run creation, scoped to the caller/report type. Store the original request digest and reject reuse of the same key with different inputs. External model calls can still be duplicated after failures; exactly-once billing is not guaranteed by local job deduplication.

Cancellation sets persisted state and prevents new downstream work. Terminate cancellable sandbox work and ignore late results unless the lease remains valid.

## 10. Final run states

`ready` means all mandatory checks passed under the package's policy. It is not a universal claim of truth.

`needs_review` means a renderable draft exists but at least one unresolved review requirement remains. Clearly mark it as a draft in the UI and delivery metadata.

`blocked` means required information, policy, or correctness conditions are missing. A partial preview can exist but must not masquerade as the final report.

`failed` indicates an execution/infrastructure failure. `cancelled` indicates explicit cancellation. Keep these distinct from valid source data containing no activity.

A completed run stores the exact package, period, input/extraction snapshots, prepared facts, composed fragments, validation findings, final document/preview, and provenance references. This is the unit of reproducibility.


---

# 05 — Evaluation and security

## 1. The acceptance unit is the whole report

Track whole-report acceptance without manual corrections, critical factual failures, required-content omissions, unsupported substantive claims, and render defects. Also measure authoring effort, recurring runtime, model/tool consumption, and review burden separately.

Do not let a high average section score conceal a materially wrong executive summary. A report can have many correct cells and still be unacceptable because its selection policy is wrong.

Keep numerical/structural correctness separate from stylistic similarity. Historical prose is not necessarily the only acceptable prose. Mandatory exact text should use exact checks; open narration should use explicit obligations and support checks.

## 2. Independent evaluation ownership

The application owns approved expectations, release gates, corpus assignments, and the evaluation implementation. The authoring sandbox can read public regression failures but cannot overwrite independent fixtures or weaken publication thresholds.

An agent may challenge an apparent historical error. A separate review records the proposed correction, source evidence, and approval. Do not silently rewrite the oracle to match the candidate.

Expected report observations are also fallible. Track extraction method and disputed values. A test is not authoritative merely because it exists in a JSON file.

## 3. Checks by boundary

| Boundary | Mandatory checks | Action on failure |
|---|---|---|
| Ingestion | File identity, parse coverage, format support, provenance | Correct extraction or mark unsupported material |
| Candidate patch | Syntax, allowed writes, declared imports, focused regression | Reject patch or return specific failures |
| Package publication | Coverage, supported input shapes, policy decisions, independent regression, render tests | Do not publish |
| Period preparation | Bindings, schema, date/unit semantics, reconciliations, completeness evidence | Block or request review according to policy |
| Narrative | Valid references, obligations, support, contradictions, permitted numeric forms | Local repair, authorized fallback, or review |
| Final artifact | Required elements, resolved fields, figure/table presence, layout | Re-render with approved rules or block |

Do not require an exploratory Python probe to pass a complete production schema. Validate its durable outputs before they become program dependencies.

## 4. Tests to implement

### Historical reconstruction

Compare independently extracted expected numbers using the original display rules. For rounded figures, compare the resulting display value or the implied acceptable interval. Match table membership and order separately from cell values.

Check exact mandatory wording, expected section presence, units, captions, and period labels. Treat layout differences according to the package's fidelity policy.

### Behavioral tests

Exercise accepted-rule properties: permutation invariance, excluded-period isolation, deterministic tie handling, zero denominators, negative movement, missing comparisons, empty valid populations, new categories, renamed inputs, and corrupted numeric cells.

Construct tests for both presence and absence of conditional sections. A system that always includes every possible warning is not correctly implementing conditional behavior.

### Unseen periods and policy regimes

Reserve full example/report pairs before authoring when possible. Test data-shape shifts as well as ordinary chronological progression. Do not use a later policy regime as a test of an earlier policy without stating the intended expected behavior.

Keep development evaluations distinct from a final reserved evaluation. Record which information was exposed and when. Repeatedly tuning on a “holdout” makes it development data.

### Deliberate failure injection

Inject wrong-but-plausible candidate formulas, missing exclusions, reversed signs, and wrong top-k selection. The checks should fail. An evaluation harness that rejects invalid JSON but accepts incorrect business logic is not ready.

Inject unsupported causal prose and a false comparison expressed with entirely valid fact references. Deterministic reference checking should pass the reference syntax; semantic review should detect the substantive problem. This distinction is intentional.

## 5. Narrative evaluation

Use deterministic checks for what can be decided reliably by code. Use a narrowly prompted reviewer for semantic support, omissions, and contradictions, with source evidence and block obligations visible.

Do not show the reviewer the author's self-assessment. Grade the output, not the confidence of its explanation. The reviewer emits specific findings and evidence references rather than an unexplained “8/10.”

Model-based grading needs calibration against human judgments and is not a deterministic oracle [R4]. Maintain reviewed good/bad examples, including subtle numerical-language and causality errors. Measure reviewer misses and false alarms.

A second model is optional, not automatically superior. Test same-model independent review versus another model. For critical prose, deterministic construction or human approval may remain the appropriate policy.

## 6. Repeated reliability experiments

Run two distinct experiments:

**Authoring stability:** reset the candidate workspace and author from the same examples multiple times. Compare inferred behavior on fixed test inputs, not source-code textual similarity.

**Runtime stability:** pin one package and input snapshot, bypass prose caches, and repeat composition/rendering. Measure whole-report acceptance and error types.

Also repeat the deterministic runtime without bypassing its stable artifacts to verify reproducibility. Different DOCX ZIP metadata does not necessarily mean different report content.

Agent evaluations distinguish finding at least one successful attempt from passing consistently across attempts [R4]. Report first-attempt success, all-attempt success for a stated repeat count, and distribution across report types. Do not report only the best generated example.

All measured results must include dataset size and limitations. No numeric performance target in this design is evidence that the target has been reached.

## 7. Initial publication policy

For a release candidate, require all mandatory observed components to be accounted for; all approved critical numeric/structural expectations to pass; no unresolved material policy ambiguity except an explicitly allowed review-only path; defined missing-data behavior; and a validated rendering template.

Passing all current tests is necessary, not proof of universal correctness. A package learned from one example should carry an evidence-limited status. Publication can allow review-required operation without advertising unattended readiness.

Runtime `ready` is permitted only when the release policy and current-run checks both pass. A user clicking “approve draft” creates an audit record; it does not retroactively transform the original model output into a clean automated success.

## 8. Threat model

Treat uploaded reports, spreadsheets, comments, templates, archive members, and model-generated Python as untrusted. A source document can contain instructions designed to redirect an agent; prompt-injection guidance recommends limiting the access and consequences available to a manipulated model [R7].

The likely impact is not limited to a wrong sentence. Risks include reading another tenant's files, sending data outside approved boundaries, overwriting fixtures, invoking host tools, consuming unlimited resources, and rendering malicious or externally linked content.

### Required controls

Authoring code runs outside the API process in a sandbox. Mount only the permitted task inputs and candidate files. Disable network access by default, provide no host secrets, and enforce CPU, memory, process, wall-clock, and output-size limits.

Use a stronger isolation boundary for production multi-tenant untrusted code rather than assuming an ordinary container is sufficient. I would start by evaluating gVisor or an equivalent managed isolation layer. gVisor's security model still permits operations made available inside a sandbox, so mounts and network policy remain essential [R11].

Pin dependency environments. Do not let a model run unrestricted package installation against the internet during a production job. New dependencies go through an approved build step.

Prevent path traversal, archive bombs, symlink escapes, macro execution, and external-resource fetching in document parsers/renderers. Validate package-relative output paths and copy final artifacts through the host's controlled export boundary.

Use authorization checks on every artifact resolution, including cache reads. Scope caches and logs to tenants. Do not leak sensitive raw text through traces or analytics. Apply explicit retention and deletion behavior to raw inputs, extracted text, and derived artifacts.

Keep prompt text separate from source text. Never interpolate uploaded document contents into privileged instructions. Structured output restricts shape; it does not sanitize arbitrary text fields or solve prompt injection by itself.

## 9. Minimal observability

Record the run/package/task IDs; stage and attempt; input/output artifact digests; model and prompt identity; tool calls and capped logs; tokens/cost where available; stage duration; validation codes; and final disposition.

Store source-sensitive traces under the same access controls as source documents. The normal UI should show understandable component progress and blockers, not dump tool logs.

A useful failure view answers: which component failed, at what boundary, against which evidence, and whether the repair belongs to source binding, program logic, narrative, or presentation.


---

# 06 — Implementation plan

## 1. Build the runtime before asking an agent to author it

The first implementation should prove that one manually authored package can produce the desired report from raw inputs under the exact contracts the learning system will later target.

This is not retreating from automated learning. It establishes an executable target and a trustworthy test harness. Otherwise, failures in inference, runtime contracts, and document rendering become indistinguishable.

Do not begin with an elaborate agent conversation and hope that its output will eventually be runnable.

## 2. Starting stack

Use a Python modular monolith, PostgreSQL, an object store, and isolated execution workers. Keep the model provider behind a small interface for structured responses, tool calls, usage metadata, and cancellation where supported.

Use ordinary Python for report-specific data processing; choose tabular libraries based on actual source size and transformations. Do not couple the platform contract to a particular dataframe library.

Evaluate Docling/native-format readers for ingestion and a trusted DOCX renderer for output. Pin versions once compatibility tests pass. The reference code does not make untested installation/version promises about these components.

A web UI can be added without changing core contracts. The first engineering interface should be a CLI that can ingest an example, build a candidate, run checks, and generate a report artifact.

## 3. Suggested application modules

```text
app/
  api/                # Authentication, report types, uploads, runs, decisions
  artifacts/          # Immutable storage, authorization, hashes, provenance
  ingestion/          # Parser adapters, profiles, document maps, source locators
  contracts/          # Authoritative interfaces and semantic validation
  authoring/          # Task loop, context loading, patch proposals, checkpoints
  packages/           # Candidate snapshots, diffs, release publication
  runtime/            # Binding, extraction, preparation, composition, assembly
  rendering/          # Trusted document renderer and preview inspection
  evaluation/         # Independent oracles, tests, narrative review, reports
  jobs/               # Claims, leases, fencing, retry policy, cancellation
  observability/      # Stage metrics, controlled traces, cost accounting
```

These are code modules, not separate services. Isolation workers are a security boundary; the other modules do not require independent deployments.

## 4. Core persisted entities

| Entity | Key fields |
|---|---|
| `report_types` | tenant ID, type ID, name, active release ID |
| `artifacts` | tenant ID, artifact ID, digest, storage key, media type, metadata |
| `example_bundles` | tenant/type IDs, report artifacts, period, bindings, corpus role |
| `candidates` | tenant/type IDs, base release, current digest, state |
| `authoring_tasks` | candidate ID, component, dependencies, status, checkpoint artifacts |
| `decisions` | candidate/component, question, alternatives, resolution, actor, timestamp |
| `releases` | type ID, immutable package digest, approval/evaluation references |
| `runs` | release ID, period, input snapshot, parameters, idempotency key, status |
| `jobs` | logical stage key, payload ref, attempt, lease token, expiry, status |
| `evaluations` | candidate/run reference, corpus exposure, findings, evaluator version |

Artifact bytes live in object storage; these records contain references and access-control metadata. Small JSON contracts can also be stored in the database, but preserve their canonical artifact representation for hashing.

Enforce tenant consistency with foreign keys or equivalent application/database constraints. A globally unique ID does not replace authorization. Unique run-idempotency constraints include the tenant and report type.

Publication should atomically record the immutable release and, when authorized, update the active-release pointer. No file mutation is permitted after release publication.

## 5. API contract sketch

| Operation | Request/result |
|---|---|
| `POST /report-types` | Create type; return type ID |
| `POST /artifacts` | Register/upload authorized artifact; return immutable artifact ID |
| `POST /report-types/{id}/examples` | Attach report/period/input bundle |
| `POST /report-types/{id}/candidates` | Start candidate from examples or an existing release |
| `GET /candidates/{id}` | Coverage, progress, blockers, artifacts |
| `POST /decisions/{id}/resolve` | Record an authorized policy decision |
| `POST /candidates/{id}/evaluate` | Schedule protected evaluation |
| `POST /candidates/{id}/publish` | Request publication; server enforces gate |
| `POST /report-types/{id}/runs` | Resolve/pin release and create period run |
| `GET /runs/{id}` | Status, checks, outputs, audit references |
| `POST /runs/{id}/cancel` | Persist cancellation |

Long operations return a job/run resource, not a request kept open for the whole agent session. The application UI streams or polls persisted stage updates. This is application design, not a promise that the assistant delivering these docs is doing background work.

Reject unsupported fields and malformed IDs at the boundary. Report `409` for conflicting version/idempotency updates and use a structured error body for domain-specific input failures.

## 6. Authoring context contract

For each task, construct context from the task objective, component map, shared definitions relevant to that component, source-region references, selected evidence, current implementation, focused failures, and previous checkpoint.

Do not include all prior transcripts. Persist useful conclusions into package artifacts and keep full traces only for authorized debugging.

The application verifies patch preconditions against the candidate base digest. If another accepted patch changed a dependency, the task must rebase/re-evaluate rather than silently overwrite it.

Start with one authoring task running per candidate. Later, parallelize read-only evidence collection or disjoint components only after the patch-merging behavior is tested.

## 7. Build milestones and completion tests

### Milestone A — Fixture and deterministic runtime

Implement immutable inputs, period contracts, fact references, preparation, validation, and a basic renderer. Manually author one realistic package and independently record expected outputs.

**Done when:** the package reproduces its expected numeric/structural behavior, invalid inputs are rejected, a changed input invalidates cached output, and a rerun cannot mutate package files. The included reference exercises part of this milestone, not all of it.

### Milestone B — Production document rendering

Implement the actual DOCX template path, preview conversion, and stress cases for variable tables and text. Keep the facts and prose deterministic for this milestone.

**Done when:** the delivered DOCX and its preview contain the same intended content; required layout rules pass; overflow has an explicit handling policy. Have a person approve the first template.

### Milestone C — Bounded narration

Add the composition interface, structured fragments, deterministic reference checks, semantic review, and local repair. Keep source binding and policy manually defined.

**Done when:** repeated runs are measured, intentionally unsupported claims are rejected or flagged, numeric-reference violations fail, and exhausted repair budgets produce explicit review/block states.

### Milestone D — Single-component automated authoring

Give the authoring agent one historical component and its permitted source files. Require it to create a candidate implementation using the same runtime contracts. Expose focused oracle discrepancies without allowing oracle edits.

**Done when:** multiple fresh authoring trials are evaluated; successful candidates work on counterfactual inputs; ambiguous rules produce a decision instead of a hidden guess. Include a deliberately ambiguous example, not just an easy sum.

### Milestone E — Whole-report learning

Add document maps, the coverage ledger, shared dependencies, component work selection, and durable checkpoints. Learn a report containing fixed, computed, and narrative content.

**Done when:** every source-report region is accounted for, no component disappears silently, and the full document is evaluated beyond isolated unit tests.

### Milestone F — Multiple examples and safe updates

Add incremental comparison, policy-era handling, selective investigation, corpus exposure tracking, and release versioning.

**Done when:** a new example that agrees adds evidence without a full relearn; a contradiction produces a scoped task; adding a release leaves old runs reproducible; a reserved evaluation stays inaccessible to authoring.

### Milestone G — Production hardening

Add multi-tenant sandbox isolation, authorization tests, resource budgets, crash recovery, lease fencing, safe cancellation, audit controls, and retention.

**Done when:** a stale worker cannot publish, malicious input cannot access disallowed artifacts, a crash resumes without corrupting a release, and all failure states are visible to the user.

## 8. Architecture experiments

Benchmark the proposed single-authoring-agent loop against a staged specialist pipeline only after the same fixtures, runtime contracts, and evaluation harness exist.

Hold models, allowed evidence, total token/tool budgets, and publication criteria comparable. Measure full-report quality, authoring stability, runtime stability, and total cost—not just whether a task was eventually completed.

Then test component granularity, context retrieval, prose grouping, review policy, and model choice one change at a time. A smaller model is an optimization only after it meets the quality threshold on the intended work.

No particular model is embedded in this design. Current model rankings and prices change; select and pin providers using this product's tests rather than a generic leaderboard.

## 9. What I would deliberately defer

Defer per-customer fine-tuning, automatic visual workflow editing, autonomous general web research, a universal metrics ontology, vector infrastructure without demonstrated retrieval need, and multi-agent voting by default.

Also defer full arbitrary-document pixel reconstruction. Ship declared format/fidelity capabilities and increase them with tests. Do not hide an unsupported feature behind a vague agent instruction.

## 10. First practical engineering task

Take one difficult real report component and its original raw files. Manually implement its intended behavior behind the preparation contract and encode independent expected observations. Then ask the authoring agent to reproduce that implementation's behavior from the examples without exposing the solution.

This experiment separates failures of the architecture from failures of policy inference. It should be the first serious benchmark, before investing in a large orchestration layer.


---

# 07 — Worked example

## 1. A deliberately small report

Consider a monthly deliveries report with a regional table and a movement paragraph. The supplied source rows represent all delivery activity in this synthetic example. The desired report compares a month with the preceding month.

This is a teaching fixture, not a customer dataset or measured demonstration of automatic policy inference.

| Region | January | February | March |
|---|---:|---:|---:|
| North | 100 | 120 | 132 |
| South | 50 | 55 | 85 |
| East | 10 | 10 | 20 |
| West | 40 | 41 | 42 |
| Total | 200 | 226 | 279 |

The historical February narrative mentions North and South as the regions to discuss. Two candidate rules explain that observation:

**Rule A:** discuss the two largest absolute changes in delivery count.

**Rule B:** discuss the two largest percentage increases.

In February, North increases by 20 deliveries / 20%, while South increases by 5 deliveries / 10%. Both rules select North and South. Reproducing February does not distinguish the rules.

In March, the rules disagree:

| Region | Absolute change | Percentage change |
|---|---:|---:|
| North | +12 | +10.0% |
| South | +30 | +54.5% |
| East | +10 | +100.0% |
| West | +1 | +2.4% |

Rule A selects South then North. Rule B selects East then South.

The learning system should discover this disagreement, inspect a distinguishing report if one exists, or ask a targeted question. It should not call whichever rule it guessed first “generalized.”

## 2. The accepted policy for the reference

For the runnable demonstration, the policy is **manually specified**:

Sum delivery counts in explicit current/comparison date windows. Select up to two regions by descending absolute change. Break ties by normalized region key. The source contract says that missing regions inside an assumed-complete, nonempty period have zero deliveries. A period with no rows is rejected because completeness cannot be established by this reference.

Counts must be nonnegative integers. A zero comparison total makes relative growth undefined. Dates use inclusive starts and exclusive ends. Regional table order is alphabetical and is independent of narrative driver order.

The code does not infer these rules. It executes them so the learning stage has an exact target interface to produce.

## 3. What the program prepares

For March, the prepared output contains a current total of 279 and comparison total of 226. The relative change is `(279 - 226) / 226`, displayed as `+23.5%` under one-decimal half-up rounding.

The table includes all four regions. The narrative contract requires the current total, growth, and the selected South/North names and changes. It does not allow the model to choose East merely because its percentage growth looks dramatic.

Facts are connected to source locators or upstream fact IDs. The program stores exact decimal strings separately from display values. The composing response refers to fact IDs; rendering substitutes the controlled display strings.

The resulting paragraph is:

> Deliveries reached 279, a change of +23.5% against the comparison period. The largest absolute regional changes were in South (+30) and North (+12). These figures describe movements, not their causes.

This paragraph is an authored fixture standing in for a model response. No LLM produced or evaluated it during this demonstration.

## 4. Run it

From the bundle root:

```bash
python -m pip install -r reference/requirements.txt
python reference/run_example.py
python -m unittest discover -s reference -p 'test_*.py' -v
```

The example writes `reference/generated/prepared-report.json`, `prose.json`, and `report.md`. The bundle also contains the test log from execution in the authoring environment.

The reference requires Python 3.11 or newer, `jsonschema`, and its installed dependencies. It uses the standard-library timezone database interface; an environment without IANA timezone data needs a system timezone database or the `tzdata` package. The requirements file includes `tzdata` for portability.

## 5. What was checked

**38 automated tests passed when this bundle was assembled.** These are local deterministic tests, not evidence of end-to-end AI report quality.

They check independent expected values and driver selection, February reconstruction, period boundaries, row-order invariance, deterministic ties, zero comparison behavior, new regions under the declared zero policy, negative movement, input drift, missing periods, bad numeric/date inputs, provenance-reference structure, cycles, table shape, narrative completeness, fact/evidence permissions, word limits, and renderer capability failures.

The tests also include a deliberately revealing case: appending “A marketing campaign caused the increase” still passes the deterministic reference checks. That statement uses no invalid fact IDs or numeric literals. It needs semantic review or a restrictive wording policy. The test passes by confirming this known boundary, not by declaring the claim correct.

## 6. What is not implemented

The demonstration does not learn from reports, parse DOCX/PDF/XLSX, run a model, judge semantic support, render DOCX, verify layout, implement a job queue, enforce tenant authorization, create a production sandbox, perform historical revision selection, or guarantee source completeness.

Its source locators are aggregate descriptions, not a full executable row-level lineage engine. Schema validation checks the digest format but does not independently prove artifact integrity against a remote store. A production host must resolve and verify those artifacts.

The reference package digest covers the demonstration code and schemas. A production release digest must also cover prompts, policies, templates, dependencies, and approved decisions.

The figure block contract exists, but this renderer deliberately rejects figures rather than silently omit them. The full example-bundle and package-manifest server validators remain implementation work.

All synthetic periods and expected values are visible in the bundle. Consequently, there was no blind holdout evaluation here.

## 7. How to turn this into the first learning experiment

Create a fresh candidate directory without the authored reference implementation. Give the authoring agent the February report fragment, its source rows, the runtime contract, and a skeleton package. Hide the March report expectation and the manually chosen selection rule.

First measure whether it recognizes ambiguity rather than silently settling on one rule. Then provide a distinguishing example or an explicit user decision, and measure whether it implements the accepted rule and its edge cases.

Finally, evaluate on genuinely reserved examples that were not visible in this document or its fixtures. Do not use these publicly exposed synthetic examples to claim unseen-period performance.

That experiment tests the difficult part: recovering reporting behavior, not just emitting correct JSON or filling a known template.


---

# 08 — Decisions and sources

## 1. Architecture decisions

### ADR-001 — One authoring agent, not a permanent specialist chain

**Decision:** one agent owns investigation, implementation, and focused testing for a coherent component.

**Reason:** keep tightly coupled interpretation and coding in the same work loop. Control context size with component tasks and durable artifacts instead of separate agent personalities.

**Tradeoff:** the agent needs broad tools and can still make correlated mistakes. Independent evaluation, write restrictions, and an explicit coverage ledger address different parts of that risk.

**Revisit when:** controlled experiments show a specialist separation improves whole-report acceptance or cost under comparable budgets.

### ADR-002 — Application-owned lifecycle

**Decision:** ordinary code owns scheduling, budgets, artifact permissions, evaluation invocation, and publication.

**Reason:** these are product invariants, not open-ended reasoning tasks.

**Tradeoff:** the application needs explicit states and failure handling. That implementation cost is preferable to hiding them in prompts.

### ADR-003 — A thin report model plus ordinary Python

**Decision:** structure inputs, facts, blocks, references, and statuses. Keep formulas in Python and editorial instructions in text.

**Reason:** support precise and open-ended content without building a universal reporting language.

**Tradeoff:** Python is expressive enough to overfit or do unsafe things. Tests and sandbox controls are therefore necessary; schema validation alone is insufficient.

### ADR-004 — No production shell for narration

**Decision:** production composition consumes prepared context and emits bounded fragments.

**Reason:** new-period execution should not reinterpret data semantics or modify its own implementation.

**Tradeoff:** new input shapes can block a run. They are handled through an explicit candidate update rather than an invisible runtime repair.

### ADR-005 — Deterministic values, flexible prose where declared

**Decision:** fixed and computed content bypasses models. Narrative can vary within an approved contract.

**Reason:** exactness and expression have different failure modes.

**Tradeoff:** fact references prevent value substitution mistakes but not false surrounding claims. High-assurance content may require deterministic wording or human review.

### ADR-006 — Independent oracles

**Decision:** candidate code cannot edit approved reference observations or release criteria.

**Reason:** a program must not certify itself by redefining expected results.

**Tradeoff:** disputes need a separate correction workflow. Historical errors and extraction mistakes are possible and must remain contestable.

### ADR-007 — First release has an explicit format envelope

**Decision:** support a tested subset of input/output formats and fidelity levels first.

**Reason:** numerical correctness does not imply robust document reconstruction.

**Tradeoff:** unsupported material is visible rather than magically handled. Expand capabilities through adapters and fixtures.

### ADR-008 — Durable jobs without an initial workflow platform

**Decision:** start with database-backed jobs, stage artifacts, leases, and idempotent publication.

**Reason:** one application can implement the needed lifecycle without another orchestration service.

**Tradeoff:** leases, cancellation, and retry behavior must actually be implemented. Replace this with a durable workflow platform when operational needs justify it; do not implement a general workflow engine accidentally.

## 2. Evidence versus proposal

The architecture, component granularity, schemas, milestones, and initial budgets are original design recommendations for this application. The cited sources support narrower background facts and implementation capabilities. None validates this exact product architecture, its performance, or its suitability for a specific unseen corpus.

No live model evaluation, customer document trial, production load test, sandbox attack test, or DOCX fidelity test was performed while writing these docs. The bundled Python reference has its own explicit, limited test scope.

## 3. Primary sources

All sources below were consulted on **8 September 2026**. URLs are included as literal references so this documentation remains usable outside the chat.

### R1 — Agent versus workflow distinction

Anthropic, *Building effective agents*, originally published 19 December 2024; the current page notes that some tooling has changed.

`https://www.anthropic.com/engineering/building-effective-agents`

Used for the distinction between model-directed tool loops and predefined workflows, and the recommendation to add architectural complexity based on demonstrated need. Not evidence that a single agent is optimal for this application.

### R2 — Ambiguity in learning from examples

Microsoft Research / Sumit Gulwani, *Programming by Examples: Applications, Algorithms, and Ambiguity Resolution*, IJCAR 2016.

`https://www.microsoft.com/en-us/research/publication/programming-examples-applications-algorithms-ambiguity-resolution/`

Used for the fact that example-compatible programs can remain ambiguous and may need disambiguation. The product's particular evidence ledger and question workflow are proposed designs.

### R3 — Structured output is not semantic correctness

OpenAI, *Structured model outputs*, current documentation.

`https://developers.openai.com/api/docs/guides/structured-outputs`

Used for structured JSON output capabilities, the explicit warning that responses may still contain mistakes, and the importance of avoiding type/schema divergence. Provider-specific schema support must be checked during integration.

### R4 — Agent evaluation and repeated reliability

Anthropic, *Demystifying evals for AI agents*, current engineering article.

`https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents`

Used for deterministic/model/human grading distinctions, calibration, isolated trials, and the difference between occasional success and consistent success. It does not establish an acceptance threshold for this product.

### R5 — Structural document extraction

Docling, *Docling document*, project documentation.

`https://docling-project.github.io/docling/concepts/docling_document/`

Used for the representation's support for text, tables, pictures, hierarchy, layout where available, and provenance. This is a capability description, not a guarantee of extraction accuracy on arbitrary files.

### R6 — DOCX template restrictions

python-docx-template, current documentation.

`https://docxtpl.readthedocs.io/en/latest/`

Used for documented restrictions on ordinary tags across runs, paragraphs, and table rows. The chosen renderer still requires corpus-specific fidelity testing.

### R7 — Agent prompt-injection risks

OpenAI, *Safety in building agents*, current documentation.

`https://developers.openai.com/api/docs/guides/agent-builder-safety`

Used for untrusted-input and data-leakage risks, instruction separation, and limiting agent access. This is not an endorsement of every legacy product recommendation on that page.

### R8 — Database queue locking primitive

PostgreSQL, current *SELECT* documentation.

`https://www.postgresql.org/docs/current/sql-select.html`

Used specifically for the documented queue-like use of `SKIP LOCKED`. Leases, fencing, idempotency, and crash recovery are additional application responsibilities.

### R9 — Tool interface design

Anthropic, *Writing effective tools for agents*, 11 September 2025.

`https://www.anthropic.com/engineering/writing-tools-for-agents`

Used for making tools understandable and measuring tool usage, errors, and cost. The tool surface in this design is a starting proposal.

### R10 — Context management

Anthropic, *Effective context engineering for AI agents*, 29 September 2025.

`https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents`

Used for selective retrieval and persistent external notes as context-management techniques. It does not specify the right retrieval strategy for this report corpus.

### R11 — Sandbox threat boundary

gVisor, *Security Model*, project documentation.

`https://gvisor.dev/docs/architecture_guide/security/`

Used for isolation scope and the fact that sandboxed applications can still exercise the file/network permissions granted to them. A sandbox does not replace least privilege or source authorization.
