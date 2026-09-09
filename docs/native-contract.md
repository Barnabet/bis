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
    image_asset=None,             # optional SourceAsset for the small brand image
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
| image | `asset_id`, `alt_text`, `width_px`, `height_px`, `decorative` |

Stable leaf IDs: `summary`, `commentary`, `regional_table`, `regional_chart`, `regional_pivot`, and optional `report_mark`. Root is `root`.

Stable dataset `regional_totals`: columns `region` (text), `current` (decimal EUR), `comparison` (decimal EUR), `change` (decimal EUR), `growth` (decimal ratio, nullable). Row order alphabetical by normalized region. `pivot_source`: `region` (text), `period` (text: current/comparison), `revenue` (decimal EUR). Only these approved aggregate columns are embedded in pivot caches; transaction IDs must never be embedded.

Core facts: `revenue.current`, `revenue.comparison`, `revenue.change`, `revenue.growth`, `driver.region`, `driver.change`, `region.<key>.current`, `.comparison`, `.change`, `.growth`. Summary references current, growth, selected driver name/change, and total change. Reference formatting belongs to the fact registry.

## Views

Views: `{id,family,title,node_ids,coverage,recipe}`. Families flow/grid/canvas. IDs `document`, `workbook`, `presentation`. `node_ids` contain leaves in intended order. Coverage is `{scope:'complete'|'executive',required_node_ids:[...],omitted_node_ids:[...]}`. Complete views must include every leaf; executive omissions must be explicit. Structural containers do not require a rendered location.

Recipes contain family-specific placement data. The built-in flow declares a precision style and permits static pivots. Grid places summary/table on Overview and pivot/chart on Analysis, with a native pivot required. Canvas uses two slides. Renderers must produce a fidelity manifest and honestly distinguish static pivot renderings from native workbook functionality.

## Accepted source policy

CSV headers: `transaction_id,date,region,status,amount,currency`. `_line` may be supplied by the parser; otherwise record positions imply CSV lines starting at 2. An optional `_locator` string preserves native provenance such as `sheet=Transactions;row=2`; when present this is used exactly instead of fabricating CSV coordinates. Dates are local business dates; amount is a finite nonnegative decimal with at most two fractional digits; currency is EUR. `status` is posted/cancelled. Duplicate transaction IDs block. Normalize region with Unicode NFKC, collapsed whitespace, and casefold; merge equivalent spellings under deterministic title-cased display. Use stable safe IDs based on a readable key plus digest when needed.

Both current and comparison must contain posted rows. Missing regions within these assumed-complete nonempty periods are zero. Sum posted rows inside explicit intervals. Rank drivers by descending absolute revenue movement, then normalized key. Relative growth with zero comparison is null/undefined. Formatting uses half-up rounding. Exact precision is retained in raw fact strings. Source locators identify included CSV lines; derived facts link upstream.
