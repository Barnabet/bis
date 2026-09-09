# Native core contract

The DOCX specification is the source of product requirements. Contract revision: `1.0`.

`foundry.contracts.Snapshot` is the authoritative Pydantic boundary. All models forbid extra fields. Its JSON representation uses strings for exact decimal values and dates; `facts` and `datasets` are dictionaries indexed by their stable IDs.

## Runtime integration

```python
from foundry.runtime import prepare, default_period, default_program

snapshot = prepare(
    rows,                         # list[dict], parsed records; optional _line integer / _locator string
    period,                       # Period or matching dict
    source_asset,                 # SourceAsset or {id,digest,filename}
    program=None,                 # Program or {id,version,digest}; built-in default
    snapshot_id=None,
    report_type_id="quarterly-revenue",
    revision=1,
    parent_id=None,
    created_at=None,              # supplied aware datetime/string or current time
    source_snapshot_digest=None,  # computed from bound source when omitted
    image_asset=None,             # optional original image SourceAsset
    image_metadata=None,          # validated binding and frozen PNG identity; see below
    reporting_policy=None,        # or {'selection': one registered policy}; no other keys
)
```

Returns a `Snapshot`; use `.model_dump(mode="json")` at boundaries. Fatal source issues raise `RuntimeBlocked` with a `.findings` list of Finding objects. No model calls or renderer calls occur here.

`default_period()` is Q1 2026 compared with Q1 2025, Europe/Paris, with explicit cutoff. `default_program()` returns the trusted built-in revenue package metadata. `render_runs(node.runs, snapshot.facts)` returns resolved text. `validate_commentary(text,node_id="commentary")` returns findings for unsupported numeric literals and common causal claims; these checks are intentionally conservative, never semantic proof. `revise_commentary(snapshot,text,expected_revision=...)` creates a revision and revalidates it without changing facts/datasets/program.

## Snapshot JSON

Top-level fields: `schema_version`, `id`, `revision`, `parent_id`, `title`, `report_type_id`, `program`, `period`, `source_snapshot_digest`, `source_assets`, `facts`, `datasets`, `nodes`, `views`, `findings`, `metadata`, `status`, `created_at`.

- `program`: `{id,version,digest}`.
- `period`: `{label,start,end_exclusive,comparison:{start,end_exclusive},timezone,as_of}`.
- `source_assets`: `[{id,digest,filename}]`; artifact lookup/authorization is a host responsibility.
- `facts`: stable ID → `{id,kind,value,unit,display,status,definition,scope,inputs,sources}`. `kind` is number/text; value is decimal string, text, or null. Status supports known/missing/undefined/not_applicable/withheld. `scope` is a string; `sources` contains `{asset_id,artifact_sha256,locator}`.
- `datasets`: ID → `{id,columns:[{id,label,type,unit}],rows:[{column_id:value}]}`. Column types are text/decimal/integer/fact; exact amounts are decimal strings. Every row has exactly its declared columns.
- `findings`: `[{id,phase,severity,code,component_id,evidence_refs,message,repair_class}]`; severity block/review/warn.
- `status`: accepted/review_required/blocked. Infrastructure run state belongs to the host, separately.
- `metadata`: records normalization, completeness/cutoff assumptions, deterministic runtime identity and included/excluded source-row counts.

## Nodes

All nodes have `id`, `kind`, and `title`.

| Kind | Additional fields |
| --- | --- |
| section | `children: [node_id]` |
| rich_text | `runs: [{type:'text',text} \| {type:'fact',fact_id}]`, `editable: bool`, `mode: 'literal'\|'computed'\|'composed'` |
| table | `dataset_id` |
| pivot | `dataset_id`, `materialized_dataset_id`, `row_dimensions`, `column_dimensions`, `measures:[{column_id,aggregation:'sum'}]`, `native_required_in:['grid']` |
| chart | `dataset_id`, `chart_type:'bar'`, `category_column`, `series:[{column_id,label}]`, `axis_unit` |
| image | `asset_id`, `alt_text`, `width_px`, `height_px`, `decorative`, `render_digest`, `media_type:'image/png'` |

Stable leaf IDs: `summary`, `commentary`, `regional_table`, `regional_chart`, `regional_pivot`, and optional `report_image`. Root is `root`. The legacy asset-only image fixture uses `report_mark` and has no exportable render identity.

Stable dataset `regional_totals`: columns `region` (text), `current` (decimal EUR), `comparison` (decimal EUR), `change` (decimal EUR), `growth` (decimal ratio, nullable). Row order alphabetical by normalized region. `pivot_source`: `region` (text), `period` (text: current/comparison), `revenue` (decimal EUR). Only these approved aggregate columns are embedded in pivot caches; transaction IDs must never be embedded.

Core facts: `revenue.current`, `revenue.comparison`, `revenue.change`, `revenue.growth`, `driver.region`, `driver.change`, `region.<key>.current`, `.comparison`, `.change`, `.growth`. Percentage selection additionally produces `driver.growth`; current-revenue selection produces `driver.current`. The summary's computed wording and references change with the selected rule. Reference formatting belongs to the fact registry. `metadata.reporting_policy.selection` records the applied rule.

## Views

Views: `{id,family,title,node_ids,coverage,recipe}`. Families flow/grid/canvas. IDs `document`, `workbook`, `presentation`. `node_ids` contain leaves in intended order. Coverage is `{scope:'complete'|'executive',required_node_ids:[...],omitted_node_ids:[...]}`. Complete views must include every leaf; executive omissions must be explicit. Structural containers do not require a rendered location.

Recipes contain family-specific placement data. The built-in flow declares a precision style and permits static pivots. Grid places summary/commentary/table on Overview and pivot/chart on Analysis, with a native pivot required. Canvas uses two slides. An optional image is included in every complete view: it follows the existing flow content, occupies an Images worksheet, and adds a dedicated third canvas slide. Renderers must produce a fidelity manifest and honestly distinguish static pivot renderings from native workbook functionality.

## Frozen image contract

The public revenue program supports zero or one still PNG/JPEG image per run. `ImageBinding` accepts only `{asset_id,alt_text,decorative}`. `decorative` defaults to false; `alt_text` is trimmed, limited to 500 characters, and must be nonempty unless the image is explicitly decorative. Validation cannot prove that the description is meaningful; non-decorative images add an `IMAGE_REVIEW_REQUIRED` finding linked to their original asset for human review. Pixels are never inputs to revenue facts or datasets, and no OCR or image interpretation runs.

Ingestion bounds the original and normalized files to 20 MiB (20,971,520 bytes), each side to 8,192 pixels, and total area to 16,000,000 pixels. It rejects format/extension mismatches, animation, truncation and invalid embedded color profiles. It applies EXIF orientation, converts embedded profiles to sRGB, preserves transparency, and writes a metadata-free RGB/RGBA PNG. Original upload bytes remain an immutable `SourceAsset`; normalization creates a separate immutable object.

The inspected asset's `profile.image` includes `{width_px,height_px,render_digest,media_type:'image/png',normalization:'exif_transpose_strip_metadata_png',color_conversion,original_format,original_width_px,original_height_px,has_alpha,render_size}`. `color_conversion` is `embedded_profile_to_srgb` or `rgb_without_embedded_profile`. The asset's `digest` identifies original evidence; `render_digest` identifies the exact normalized PNG used for display and export.

The service freezes `image_metadata:{asset_id,alt_text,decorative,render_digest,media_type,width_px,height_px}` before calling `prepare`, alongside the original `image_asset`. The source snapshot digest includes the asset identities and this binding. Changing the selected image, description or decorative flag changes that identity without changing revenue calculation. Editorial and acceptance revisions retain the same image node and original source reference.

Generation verifies the frozen derivative and original evidence identities. Snapshot preview and export resolve the image only through `render_digest`, verify the bytes and dimensions, and never re-normalize the original. Export adapters receive an `asset_resolver` that reads frozen objects by digest. Missing or corrupt render bytes block the operation; current asset metadata is never substituted for a historical snapshot binding. For schema compatibility, `render_digest` remains nullable and `media_type` defaults to `image/png`; legacy nodes lacking a frozen derivative remain readable but cannot preview or export an image.

All four adapters preserve aspect ratio without cropping, stretching or upscaling. Office image objects carry descriptions and decorative metadata; their raster pixels are not native editable diagrams. PDF descriptions are visible and included in the fidelity manifest, while tagged-PDF accessibility remains uncertified. These image capabilities do not certify native Excel pivot interaction.

## Accepted source policy

CSV headers: `transaction_id,date,region,status,amount,currency`. `_line` may be supplied by the parser; otherwise record positions imply CSV lines starting at 2. An optional `_locator` string preserves native provenance such as `sheet=Transactions;row=2`; when present this is used exactly instead of fabricating CSV coordinates. Dates are local business dates; amount is a finite nonnegative decimal with at most two fractional digits; currency is EUR. `status` is posted/cancelled. Duplicate transaction IDs block. Normalize region with Unicode NFKC, collapsed whitespace, and casefold; merge equivalent spellings under deterministic title-cased display. Use stable safe IDs based on a readable key plus digest when needed.

Both current and comparison must contain posted rows. Missing regions within these assumed-complete nonempty periods are zero. Sum posted rows inside explicit intervals. The default selection ranks descending absolute revenue movement. The two other registered policies rank absolute percentage movement or current-period revenue. All break ties by normalized region key. Percentage selection excludes undefined ratios and raises `SELECTION_UNDEFINED` if none remain. Relative growth with zero comparison is null/undefined. Formatting uses half-up rounding. Exact precision is retained in raw fact strings. Source locators identify included CSV lines; derived facts link upstream.

`reporting_policy` accepts exactly one `selection` key and one of `largest_absolute_change`, `largest_percentage_change`, `largest_current_revenue`. `None` preserves the original default behavior. The driver-name fact depends on the regional change, growth or current facts used for its ranking. When callers provide a published `program`, its digest is the host's authority for the accepted policy. Direct fixture preparation without a program gives nondefault policies a distinct default program digest. This is a bounded registered Python adapter, not an expression evaluator or arbitrary program loader.

## Historical observations and component scope

`inspect_target(asset)` reads only the original target's inspected regions and identity. It returns `{asset_id,asset_digest,observations,regions,issues}`. An observation stores `{id,fact_id,value,locator,method,region_id,unit,display?,display_decimals?}`. Numeric expected values come from explicit historical labels/cells; they are never computed from candidate output. Supported special IDs are `regional_totals.region_order` for ordered table membership, `policy.selection` for explicit supported selection wording, and `node.commentary.text` for the exact registered disclosure.

`compare_snapshot(snapshot,inspection)` returns `{passed,checks,observation_count}`. It compares numeric values at their observed half-up display precision and separately checks table membership/order, selection wording and exact literal text. An empty observation set fails. Passing those comparisons does not account for unrecognized target regions: the historical coverage ledger separately preserves them as `needs_decision`, with explicit approved exclusions represented as `out_of_scope`. Native view coverage continues to account for the snapshot's leaves; it is not a substitute for historical target coverage.

`analyze_examples(cases)` accepts already authorized authoring/development cases and tests the three registered policies. Reserved cases are rejected before candidate execution. It returns competing hypotheses, located discrepancies, complete region coverage, assumptions and limitations. Contradictions and multiple compatible rules remain unresolved rather than being converted to a fabricated confidence score.

## Composed commentary revisions

Composition consumes one validated frozen snapshot and bounded qualitative `Evidence` records: `{id,asset_id,artifact_sha256,locator,text}`. The service verifies source identity and excludes historical targets and reserved evidence before the composing boundary. Model output has one to three paragraphs `{template,evidence_refs}`. `{{fact_id}}` placeholders are validated against available snapshot facts and become ordinary typed fact runs; literal text remains text runs. There is no template expression evaluation.

The implemented commentary contract requires references to `revenue.current` and `driver.region`, eight to 150 words and no unsupported numerical literals, rankings, links or hidden text. Quoted evidence must match a cited excerpt. Causal statements require exact attributed quotations and still receive a human-review finding. These checks do not prove semantic support; every usable proposal has `COMPOSITION_REVIEW_REQUIRED`.

Successful composition changes only editable commentary in a new snapshot ID/revision. Original facts and image bindings remain intact. Selected qualitative sources join `source_assets`; the source snapshot identity records their addition. `metadata.composition` retains objective, evidence, receipt, attempts, used evidence references and originating job. Accepted structured provider results are stored separately as immutable objects for retry reuse. Acceptance remains a separate audited revision; exports read only frozen content and assets.
