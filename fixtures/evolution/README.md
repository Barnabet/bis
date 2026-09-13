# Independent period evolution fixtures

This synthetic corpus tests the supported posted EUR regional revenue report
family across three reporting policies. It contains six historical report/data
pairs and twelve later-period report/data pairs. Every pair includes an actual
DOCX report, CSV source, explicit period parameters, and an independent JSON
oracle. No Foundry runtime, exporter, model response, or generated snapshot was
used to author these expectations.

`build_fixtures.py` retains the manually declared regional amounts, totals,
changes, exact growth fractions, rounded displays, and selected region. Before
writing any artifact it checks these declarations with Python `Fraction`
arithmetic, checks display rounding with `Decimal`, and independently verifies
the declared winner. `arithmetic-check.json` records every case and all three
policy winners. This is an arithmetic consistency check, not evidence that the
application passed the experiment.

The manifest uses paths relative to this directory. Each corpus has two
`history` pairs and four `future` pairs. Upload only the historical pairs during
learning, review, evaluation, and publication. Future sources, reports, expected
JSON, and canary labels must remain outside the authoring/model context until
the program is published. The future report and expected JSON are evaluation
artifacts; only its CSV and explicit period parameters are generation inputs.

## Historical discrimination

All first historical cases are deliberately ambiguous: each of the registered
policies selects the same region. In every second historical case all three
policies select different regions. Together the two observed reports support
exactly one policy within the registered three-policy family.

| Corpus | Expected policy | Q3 2025 selected region | Q4 2025 selected region | Future-only region |
| --- | --- | --- | --- | --- |
| `current_revenue` | Largest current revenue | Atrium | Atrium | Dune Canary |
| `absolute_change` | Largest absolute change | Harbor | Juniper | Orchard Canary |
| `percentage_change` | Largest absolute percentage change | Maple | Willow | Zephyr Canary |

Historical targets use explicit EUR totals, overall growth, a selected-region
label, a native regional table, and the registered disclosure. They do not
declare the selection policy in prose. The source contract remains explicit:
posted transactions in EUR, nonnegative currency amounts, local business dates,
inclusive starts, and exclusive ends.

## Future periods

Each corpus progresses through Q1, Q2, Q3, and Q4 2026 using year-on-year
comparisons. For Q3 and Q4, the comparison amounts match the corresponding
historical 2025 current amounts by region. The CSV transaction identifiers are
distinct per case. The periods are explicit experimental inputs; the experiment
does not test automatic calendar scheduling or external data collection.

| Period | Cases deliberately covered |
| --- | --- |
| Q1 2026 | Overall revenue decline and a selected region with a negative movement. Percentage selection is tested when every region declines. |
| Q2 2026 | An exact tie under the approved policy, broken by normalized region key. The source spells the first tied region with mixed case and surrounding whitespace. Absolute and percentage ties have opposite signs. |
| Q3 2026 | A new future-only region, a disappeared region, undefined growth for a zero comparison, and defined overall growth. Percentage selection must exclude the new region's undefined ratio and can select a disappeared region's negative movement. |
| Q4 2026 | Fractional currency and aggregation across split transactions. The percentage winner's exact magnitude exceeds another region although both displayed magnitudes round to 50.0%. |

Every source splits each nonzero regional period amount across two records,
placed on the inclusive first date and final included date. Large cancelled
records and records exactly on both exclusive end dates must not contribute.
Absent regional records are genuinely absent, not zero placeholders; each
whole period remains nonempty and is treated as complete under the approved
source assumption. Zero-activity whole periods, missing required fields, and
contradictory target values belong in the separate failure matrix.

All expected DOCX tables contain current, comparison, change, and growth,
including the literal `Not defined` when comparison revenue is zero. Expected
JSON retains the full corresponding values. Growth is stored both as an exact
rational `growth_fraction` and a 40-significant-digit decimal `growth_value`
matching the documented calculation precision; monetary strings are exact and
must be compared numerically rather than by trailing-zero spelling.

## Freeze and limits

`frozen-sha256.json` contains hashes of all 72 report, CSV, period, and expected
JSON files. Verify it before learning and after evaluation. These values were
declared before the live experiment and must not be changed to match a failing
candidate. The builder can reproduce the fixture design for review, but the
experiment uses the committed frozen artifacts. DOCX ZIP timestamps can vary
if the builder is rerun, so regeneration requires a deliberate new freeze.

All 18 DOCX fixtures were rendered with the bundled LibreOffice and checked as
single-page reports; internal render evidence lives under the ignored
`output/evolution-fixture-qa/` directory.

This corpus tests independent calculations, registered-policy recovery,
chronological reuse, boundary exclusions, and report content. It does not prove
arbitrary report discovery, arbitrary source schemas, template reconstruction,
causal narrative correctness, or production generalization to customer data.
