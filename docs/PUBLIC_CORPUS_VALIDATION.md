# Public report and data benchmark

Captured 13 September 2026. We downloaded **12 real periodic reports and their matching published data from three official publishers**: 21 distinct original files, 19,377,266 bytes. The source URLs, exact hashes, release dates, unit caveats and independently located observations are recorded in [`fixtures/public-corpus/manifest.json`](../fixtures/public-corpus/manifest.json).

The first application baseline found **zero transaction-eligible periods and zero completed reporting workflows**. Public-source acquisition and the documented source checks are complete; FMC discrepancies remain unexplained, and general reporting support remains unimplemented. The earlier 485-test synthetic suite validates the implemented EUR revenue family and does not establish robustness across these new report families.

## Acquired sources

| Official source | Captured periods and files | Useful challenges |
| --- | --- | --- |
| [US Census Advance Monthly Retail Trade](https://www.census.gov/retail/marts/historic_releases.html) | May–August 2025; four seven-page PDFs and four corresponding archived XLSX workbooks | USD scaling, month/year comparisons, overlapping industry categories, suppressed values, uncertainty and release revisions |
| [ONS Retail Sales](https://www.ons.gov.uk/businessindustryandtrade/retailindustry/datasets/retailsales/current) | June–September 2025; four bulletin PDFs and full release-vintage CSV versions v117–v120 | 621 series, mixed annual/quarterly/monthly rows, value versus volume, seasonal adjustment, corrections and index rebasing |
| [FMC Containerized Freight Statistics](https://www.fmc.gov/databases-and-publications/containerized-freight-statistics/) | Q1–Q4 2025; four quarterly PDFs and one shared annual XLSX | Image-based tables, port/carrier dimensions, container and tonnage measures, inconsistent published totals and annual-file leakage |

These are published aggregates and estimates, not confidential business survey responses or individual shipment records. They can test reconstruction from published source data; they cannot prove reproduction of the agencies' underlying collection, estimation or seasonal-adjustment procedures. The [Census methodology](https://www.census.gov/retail/marts/how_surveys_are_collected.html) and [FMC publication scope](https://www.fmc.gov/articles/federal-maritime-commission-begins-publishing-carrier-submitted-containerized-freight-statistics-data/) describe those boundaries.

### Source checks and real complications

For Census, 32 headline observations match the paired workbooks. Twenty-eight also recompute from level cells with independent decimal arithmetic; four rolling-three-month figures are checked against published change cells because a single workbook does not contain all necessary level months. The June advance figure is USD 720,106 million in its July release and USD 722,571 million in the following vintage. A past report must be paired with its own vintage, not the latest revised time series. The exact reports and data are linked from the [historical archive](https://www.census.gov/retail/marts/historic_releases.html).

For ONS, 32 selected report claims match stable CDID series in the exact archived CSV versions. All 621 series in each CSV carry the expected internal release date. The archive dates mean **date superseded**, so publication and archive-row dates must not be conflated. The [July 2025 bulletin](https://www.ons.gov.uk/businessindustryandtrade/retailindustry/bulletins/retailsales/july2025) documents corrections: June monthly volume growth changes from +0.9% to +0.3% between vintages. The [August release](https://www.ons.gov.uk/businessindustryandtrade/retailindustry/bulletins/retailsales/august2025) changes the index reference from 2022=100 to 2023=100, without changing growth rates through that rebasing alone. Comparing index levels across the boundary without reconciling the base would be invalid. Retailer anecdotes in the bulletins are not derivable from the numeric CSV.

For FMC, 32 separately transcribed PDF table cells agree with the workbook. Quarterly port and carrier tonnage sums agree with the printed totals, but container grand totals do not: sums of integer port cells exceed printed totals by 10–19 units; carrier sums differ by 11–15. The exact discrepancies remain recorded. We have not assumed a rounding explanation or invented a tolerance. All retrieved files belong to an August 2026 revised publication batch, so this is a retrospective 2025 corpus, not an original quarterly-vintage benchmark. The annual workbook includes future quarters that must be withheld during any later learning experiment. The official scope identifies TEUs; the precise tonnage standard is not specified in the retrieved tables. [FMC source and revision notice](https://www.fmc.gov/databases-and-publications/containerized-freight-statistics/)

## Actual current application baseline

Original bytes were passed through the real `inspect_asset` and `inspect_target` functions with model generation and both provider transports disabled. Descriptive cache filenames preserve the original file formats and exact bytes; no data was rescaled into EUR, flattened or rewritten to force compatibility. The isolated evidence is under `output/public-corpus-validation/`; the main application and its stored reports were not changed.

| Corpus | Source admission | Report observations |
| --- | --- | --- |
| Census, four pairs | All XLSX files rejected with `ACTIVE_CONTENT` | PDFs retained as evidence; zero mapped observations |
| ONS, four pairs | All wide CSV files rejected with `INPUT_DRIFT` because the generic transaction importer requires unique nonempty headers | June/August/September PDFs retained with zero mapped observations; July's 104 pages exceed the declared 100-page limit |
| FMC, four pairs | Workbook catalogued with no eligible transaction sheet | All four PDFs have image-based tables; zero mapped observations and four unresolved page regions each |

The Census rejection is a genuine external-workbook boundary. Each workbook contains an `externalLinkPath` relationship to a legacy workbook, eight hidden defined names and cached external cells. There are no worksheet formulas, macros, embedded executable objects or ordinary hyperlink relationships in these samples. Public availability does not justify silently resolving external paths or discarding their provenance. A reviewed static-cell extraction capability could preserve the original and bind a separately identified derivative without resolving links; the aggregate-data adapter would still be required.

The current PDF admission status means that text was retained as evidence. It does not mean that tables, figures, footnotes or report structure have been reconstructed. The ONS PDFs contain large statistical appendices: 99, 104, 100 and 98 pages. This research checked relevant content and source identities, not every-page visual fidelity.

## Reproduce the baseline

```sh
# Use already downloaded, hash-verified originals without network access.
uv run python scripts/validate_public_corpus.py

# Explicitly permit downloading missing originals from the recorded official URLs.
uv run python scripts/validate_public_corpus.py --fetch
```

The cache is `output/public-corpus-cache/`. Every invocation creates a new evidence directory and never overwrites a previous summary. A changed download hash fails rather than updating the expected artifact silently. The manifest, application and both validation scripts have captured identities and are checked for changes during a run. Provider generation and network transports are guarded against model dispatch. The command's successful completion means the capability baseline was recorded; its counts explicitly distinguish source consistency, input admission and complete reporting runs.

Original publications and large data files remain in ignored local storage; the repository contains source attribution, hashes, observations and the reproducible harness. ONS identifies its Open Government Licence; Census attribution and usage policies are linked in the manifest. FMC downloads are public, but this search did not establish an explicit redistribution licence for every publication element. ONS initially returned HTTP 429 for later downloads; a paced retry succeeded, and that access history remains in the research evidence.

The final integrated execution is `output/public-corpus-validation/20260913T101308Z-ff8614/summary.json`: all 21 original hashes verified before and after checking, 96/96 report numeric controls, 28/28 independent arithmetic checks, 42 retained FMC reconciliation findings, and zero model calls or complete reporting runs. The 42 findings include overlapping category/subtotal/grand-total comparisons and are not 42 independent failing reports. All 18 deliberate changes to copies of sources were detected, including changed values, periods, comparison levels, CDIDs, units, vintage metadata, missing values, category identities and formula text. Mutation evidence is in `output/public-corpus-research/source-value-mutation-checks.json`. A real 33,955-byte Census workbook download also exercised the fetch helper and matched its frozen hash. Cached-hash tampering and cache-path traversal probes were rejected.

The first import-only summary and the subsequent control-check summary are retained alongside the final run. No application runtime code or production dependencies changed, so the earlier 485-test application result is kept as its own milestone; these public-source checks are reported separately.

## Next implementation and evaluation

Start with Census, where native spreadsheet cells and searchable reports make the numerical contract clearest. Add reusable aggregate-table bindings, typed units, period and vintage identities, missing-value states and independently located report observations. Extend those mechanisms for ONS time series and rebasing, then FMC image tables and unresolved aggregation rules. Keep domain mappings and unsupported regions visible instead of treating successful file parsing as full report understanding.

For the next evaluation, use the first two periods of each family for development, freeze the implementation, and evaluate the later two without exposing their report answers to authoring. That is a proposed protocol, not an established blind holdout: this acquisition manifest exposes every expected answer and the FMC workbook contains all four quarters. A separate authoring manifest must exclude later reports and oracle entries, and FMC inputs must be explicitly limited to the permitted quarters. Additional untouched publishers and formats should follow. Public reports may already be in a model's training data, so include independently computed counterfactual data variants that change values, winners, missingness and periods; a model repeating memorized prose must fail. Test wrong-vintage inputs, adjusted/unadjusted swaps, index-base changes, suppressed-as-zero errors, duplicate subtotals and conflicting source totals explicitly.

For any subsequent model-assisted runs, retain the configured local CLIProxyAPI and exact `claude-opus-5`. Score numerical correctness, provenance, content coverage, refusal behavior, narrative faithfulness and export fidelity separately. A missing adapter, blocked run or unsupported report region is an explicit result, not a passing robustness case. These public corpora now make that next stage concrete; no live public-corpus generation or automatic report acceptance is claimed here.
