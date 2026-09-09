import { useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  BarChart3,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Database,
  FileCheck2,
  FileText,
  Fingerprint,
  GitBranch,
  Info,
  Layers3,
  Link2,
  LockKeyhole,
  Pencil,
  ShieldCheck,
  Table2,
  X,
} from "lucide-react";
import type { Dataset, Fact, ReportNode, Snapshot } from "./types";
import { getNodes } from "./types";
import {
  Badge,
  IconButton,
  KeyValue,
  money,
  number,
  pretty,
  shortDate,
} from "./ui";

type Shared = {
  snapshot: Snapshot;
  onFact: (id: string) => void;
  selectedFact: string | null;
};
export function RichText({
  node,
  snapshot,
  onFact,
  selectedFact,
}: Shared & { node: ReportNode }) {
  return (
    <>
      {node.runs?.map((run, i) =>
        run.type === "text" ? (
          <span key={i}>{run.text}</span>
        ) : (
          <button
            key={i}
            className={`fact-inline${selectedFact === run.fact_id ? " selected" : ""}`}
            onClick={() => onFact(run.fact_id)}
            title={`Inspect evidence: ${snapshot.facts[run.fact_id]?.definition ?? run.fact_id}`}
          >
            {snapshot.facts[run.fact_id]?.display ?? `[${run.fact_id}]`}
          </button>
        ),
      )}
    </>
  );
}
function displayValue(
  value: string | number | null,
  unit?: string,
  key?: string,
) {
  if (unit === "EUR") return money(value);
  if (unit === "ratio" || key === "growth") return number(value, true);
  return value ?? "—";
}
// The registered revenue adapter owns these exact fact definitions. Resolve
// labels through them instead of guessing from date-window scope or reformatting values.
function regionalFact(snapshot: Snapshot, region: unknown, field: string) {
  const label = String(region);
  const definitions: Record<string, string> = {
    current: `Sum of posted revenue in ${label}.`,
    comparison: `Sum of posted revenue in ${label}.`,
    change: `Current minus comparison posted revenue for ${label}.`,
    growth: `Revenue movement divided by comparison revenue for ${label};`,
  };
  return Object.values(snapshot.facts).find(
    (f) =>
      f.id.startsWith("region.") &&
      f.id.endsWith(`.${field}`) &&
      Boolean(definitions[field]) &&
      f.definition.startsWith(definitions[field]),
  );
}
function compareExactDecimal(a: string | number, b: string | number) {
  const left = String(a).split("."),
    right = String(b).split(".");
  const scale = Math.max(left[1]?.length ?? 0, right[1]?.length ?? 0);
  const integer = (parts: string[]) =>
    BigInt(parts[0] + (parts[1] ?? "").padEnd(scale, "0"));
  const x = integer(left),
    y = integer(right);
  return x < y ? -1 : x > y ? 1 : 0;
}
export function DataTable({
  dataset,
  snapshot,
  onFact,
  selectedFact,
  pivot = false,
}: Shared & { dataset: Dataset; pivot?: boolean }) {
  const [sort, setSort] = useState<{ column: string; descending: boolean }>({
    column: dataset.columns[0]?.id ?? "",
    descending: false,
  });
  const columns = pivot
    ? dataset.columns.filter((col) =>
        ["region", "comparison", "current", "change"].includes(col.id),
      )
    : dataset.columns;
  const rows = useMemo(
    () =>
      [...dataset.rows].sort((a, b) => {
        const column = dataset.columns.find((c) => c.id === sort.column);
        const numeric =
          column?.type === "decimal" || column?.type === "integer";
        const av = a[sort.column];
        const bv = b[sort.column];
        if (av == null || bv == null)
          return av == null ? (bv == null ? 0 : 1) : -1;
        const comparison = numeric
          ? compareExactDecimal(av, bv)
          : String(av).localeCompare(String(bv));
        return comparison * (sort.descending ? -1 : 1);
      }),
    [dataset, sort],
  );
  return (
    <div className="table-scroll">
      <table className={`data-table${pivot ? " pivot-table" : ""}`}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.id}
                className={col.type !== "text" ? "numeric" : ""}
                aria-sort={
                  sort.column === col.id
                    ? sort.descending
                      ? "descending"
                      : "ascending"
                    : "none"
                }
              >
                <button
                  onClick={() =>
                    setSort({
                      column: col.id,
                      descending:
                        sort.column === col.id
                          ? !sort.descending
                          : col.type !== "text",
                    })
                  }
                >
                  {col.label}
                  {sort.column === col.id ? (
                    sort.descending ? (
                      <ArrowDown size={11} />
                    ) : (
                      <ArrowUp size={11} />
                    )
                  ) : (
                    <span className="sort-placeholder" />
                  )}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={`${row.region ?? ""}-${i}`}>
              {columns.map((col) => {
                const fact = regionalFact(snapshot, row.region, col.id);
                const value = fact
                  ? fact.display
                  : displayValue(row[col.id], col.unit, col.id);
                return (
                  <td
                    key={col.id}
                    className={`${col.type !== "text" ? "numeric " : ""}${col.id === "growth" || col.id === "change" ? (Number(row[col.id]) > 0 ? "positive" : Number(row[col.id]) < 0 ? "negative" : "") : ""}`}
                  >
                    {fact ? (
                      <button
                        className={`table-fact${selectedFact === fact.id ? " selected" : ""}`}
                        title={`Inspect ${fact.definition}`}
                        onClick={() => onFact(fact.id)}
                      >
                        {value}
                      </button>
                    ) : (
                      value
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
        {dataset.id === "regional_totals" && (
          <tfoot>
            <tr>
              {columns.map((col) => (
                <td
                  key={col.id}
                  className={col.type !== "text" ? "numeric" : ""}
                >
                  {col.id === "region" ? (
                    "Total"
                  ) : snapshot.facts[`revenue.${col.id}`] ? (
                    <button
                      className="table-fact"
                      onClick={() => onFact(`revenue.${col.id}`)}
                    >
                      {snapshot.facts[`revenue.${col.id}`].display}
                    </button>
                  ) : (
                    "—"
                  )}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
export function RevenueChart({
  dataset,
  onFact,
  snapshot,
  selectedFact,
}: Shared & { dataset: Dataset }) {
  const max = Math.max(
    ...dataset.rows.flatMap((row) => [
      Number(row.current),
      Number(row.comparison),
    ]),
    1,
  );
  const axisMax = Math.ceil(max / 100) * 100;
  return (
    <div
      className="revenue-chart"
      role="figure"
      aria-label="Regional revenue comparison. Exact values are available in the regional breakdown table."
    >
      <div className="chart-legend">
        <span>
          <i className="current-dot" />
          Current period
        </span>
        <span>
          <i className="comparison-dot" />
          Comparison period
        </span>
      </div>
      <div className="chart-body">
        <div className="chart-grid" aria-hidden="true">
          {[0, 1, 2, 3, 4].map((tick) => (
            <div key={tick} style={{ left: `${tick * 25}%` }}>
              <span>{money((axisMax * tick) / 4).replace(".00", "")}</span>
            </div>
          ))}
        </div>
        {dataset.rows.map((row) => {
          const fact = regionalFact(snapshot, row.region, "current");
          const comparisonFact = regionalFact(
            snapshot,
            row.region,
            "comparison",
          );
          return (
            <div className="chart-row" key={String(row.region)}>
              <div className="chart-label">{row.region}</div>
              <div className="chart-bars">
                <button
                  className={`chart-bar current${fact?.id === selectedFact ? " selected" : ""}`}
                  style={{ width: `${(Number(row.current) / axisMax) * 100}%` }}
                  title={`${row.region}, current: ${fact?.display ?? money(row.current)}`}
                  aria-label={`${row.region}, current revenue ${fact?.display ?? money(row.current)}. Inspect evidence.`}
                  onClick={() => fact && onFact(fact.id)}
                />
                <div
                  className="chart-bar comparison"
                  style={{
                    width: `${(Number(row.comparison) / axisMax) * 100}%`,
                  }}
                  title={`${row.region}, comparison: ${comparisonFact?.display ?? money(row.comparison)}`}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
function Metrics(props: Shared) {
  return (
    <div className="report-metrics">
      {[
        {
          id: "revenue.current",
          label: "TOTAL REVENUE",
          caption: "Current period",
        },
        {
          id: "revenue.comparison",
          label: "COMPARISON",
          caption: "Previous comparison period",
        },
        {
          id: "revenue.growth",
          label: "PERIOD GROWTH",
          caption: "Relative revenue change",
        },
      ].map(({ id, label, caption }) => (
        <button
          key={id}
          className={`metric${id.endsWith("growth") ? " growth" : ""}${props.selectedFact === id ? " selected" : ""}`}
          onClick={() => props.onFact(id)}
        >
          <span className="metric-label">
            {label}
            <ArrowUpRight size={13} />
          </span>
          <strong>{props.snapshot.facts[id]?.display ?? "—"}</strong>
          <span className="metric-caption">{caption}</span>
        </button>
      ))}
    </div>
  );
}
export function ReportDocument(
  props: Shared & { onEdit: (node: ReportNode) => void },
) {
  const nodes = getNodes(props.snapshot);
  const snapshot = props.snapshot;
  const view = snapshot.views.find((v) => v.id === "document");
  const ordered = view
    ? view.node_ids
        .map((id) => nodes.find((n) => n.id === id))
        .filter((n): n is ReportNode => Boolean(n))
    : nodes.filter((n) => n.kind !== "section");
  return (
    <article className="report-paper">
      <div className="paper-topline">
        <span className="eyebrow">FINANCIAL PERFORMANCE</span>
        <span className="paper-number">
          REPORT / {String(snapshot.revision).padStart(2, "0")}
        </span>
      </div>
      <div className="paper-title">
        <h2>{snapshot.title}</h2>
        <span>{snapshot.period.label}</span>
      </div>
      <div className="paper-meta">
        <span>
          {shortDate(snapshot.period.start)} —{" "}
          {shortDate(
            new Date(
              new Date(snapshot.period.end_exclusive).getTime() - 86400000,
            ).toISOString(),
          )}
        </span>
        <span>All figures in EUR</span>
      </div>
      <Metrics {...props} />
      {ordered.map((node) => {
        if (node.kind === "rich_text")
          return (
            <section
              key={node.id}
              className={`report-section${node.editable ? " commentary-section" : ""}`}
            >
              <div className="section-title-row">
                <h3>{node.title}</h3>
                {node.editable ? (
                  <button
                    className="small-text-button"
                    onClick={() => props.onEdit(node)}
                  >
                    <Pencil size={12} />
                    Revise commentary
                  </button>
                ) : (
                  <span className="subtle-label">
                    <LockKeyhole size={11} />
                    Computed
                  </span>
                )}
              </div>
              <p className={node.editable ? "editorial-text" : "summary-text"}>
                <RichText {...props} node={node} />
              </p>
            </section>
          );
        if (
          node.kind === "chart" &&
          node.dataset_id &&
          snapshot.datasets[node.dataset_id]
        )
          return (
            <section className="report-section chart-section" key={node.id}>
              <div className="section-title-row">
                <h3>{node.title}</h3>
                <span className="subtle-label">BY REGION</span>
              </div>
              <RevenueChart
                {...props}
                dataset={snapshot.datasets[node.dataset_id]}
              />
            </section>
          );
        if (
          (node.kind === "table" || node.kind === "pivot") &&
          snapshot.datasets[
            node.materialized_dataset_id ?? node.dataset_id ?? ""
          ]
        )
          return (
            <section
              className={`report-section${node.kind === "pivot" ? " pivot-section" : ""}`}
              key={node.id}
            >
              <div className="section-title-row">
                <h3>{node.title}</h3>
                <span className="subtle-label">
                  {node.kind === "pivot" ? (
                    <>
                      <Layers3 size={12} />
                      Aggregate view
                    </>
                  ) : (
                    `${snapshot.datasets[node.dataset_id!].rows.length} REGIONS`
                  )}
                </span>
              </div>
              <DataTable
                {...props}
                dataset={
                  snapshot.datasets[
                    node.materialized_dataset_id ?? node.dataset_id!
                  ]
                }
                pivot={node.kind === "pivot"}
              />
            </section>
          );
        if (node.kind === "image")
          return (
            <figure className="report-image" key={node.id}>
              <img
                src={`/api/assets/${node.asset_id}/download`}
                alt={node.decorative ? "" : (node.alt_text ?? node.title)}
              />
            </figure>
          );
        return null;
      })}
      <footer className="paper-footer">
        <span>
          <ShieldCheck size={13} />
          One snapshot. Every figure connected.
        </span>
        <span>
          {snapshot.period.label} · Revision {snapshot.revision}
        </span>
      </footer>
    </article>
  );
}
export function WorkbookView(props: Shared) {
  const [sheet, setSheet] = useState("Overview");
  const nodes = getNodes(props.snapshot);
  const dataset =
    props.snapshot.datasets[
      sheet === "Source aggregates" ? "pivot_source" : "regional_totals"
    ];
  return (
    <div className="workbook-view">
      <div className="workbook-formula">
        <span className="cell-reference">
          {sheet === "Overview"
            ? "Overview"
            : sheet === "Analysis"
              ? "Analysis"
              : "Source aggregates"}
        </span>
        <span className="formula-label">ƒx</span>
        <span>
          Values from revision {props.snapshot.revision} ·{" "}
          {props.snapshot.period.label}
        </span>
      </div>
      <div className="workbook-canvas">
        <div className="sheet-heading">
          <Table2 size={22} />
          <div>
            <h2>
              {sheet === "Analysis"
                ? "Regional analysis"
                : sheet === "Source aggregates"
                  ? "Approved source aggregates"
                  : props.snapshot.title}
            </h2>
            <p>
              {sheet === "Analysis"
                ? "Materialized pivot and chart. Export to inspect workbook capabilities."
                : sheet === "Source aggregates"
                  ? "Approved aggregate records behind the pivot. Transaction IDs are excluded."
                  : "Shared report facts, presented as a workbook."}
            </p>
          </div>
        </div>
        {sheet === "Overview" && (
          <>
            <Metrics {...props} />
            {nodes
              .filter((n) => n.kind === "rich_text")
              .map((node) => (
                <div className="sheet-prose" key={node.id}>
                  <h3>{node.title}</h3>
                  <RichText {...props} node={node} />
                </div>
              ))}
          </>
        )}
        {dataset && (
          <DataTable
            {...props}
            dataset={dataset}
            pivot={sheet === "Analysis"}
          />
        )}
        {sheet === "Analysis" && (
          <div className="sheet-chart">
            <RevenueChart
              {...props}
              dataset={props.snapshot.datasets.regional_totals}
            />
          </div>
        )}
        {sheet === "Overview" &&
          nodes
            .filter((n) => n.kind === "image")
            .map((n) => (
              <figure className="report-image" key={n.id}>
                <img
                  src={`/api/assets/${n.asset_id}/download`}
                  alt={n.decorative ? "" : (n.alt_text ?? n.title)}
                />
              </figure>
            ))}
      </div>
      <div className="sheet-tabs">
        <div className="sheet-controls">
          <ChevronLeft size={14} />
          <ChevronRight size={14} />
        </div>
        {["Overview", "Analysis", "Source aggregates"].map((name) => (
          <button
            className={sheet === name ? "active" : ""}
            key={name}
            onClick={() => setSheet(name)}
          >
            {name}
          </button>
        ))}
        <span>3 sheets</span>
      </div>
    </div>
  );
}
export function PresentationView(props: Shared) {
  const [slide, setSlide] = useState(0);
  const nodes = getNodes(props.snapshot);
  return (
    <div className="presentation-view">
      <div className="slide-navigation">
        <span className="eyebrow">PRESENTATION</span>
        <div>
          <IconButton
            label="Previous slide"
            onClick={() => setSlide((s) => Math.max(0, s - 1))}
          >
            <ChevronLeft size={16} />
          </IconButton>
          <span>{slide + 1} / 2</span>
          <IconButton
            label="Next slide"
            onClick={() => setSlide((s) => Math.min(1, s + 1))}
          >
            <ChevronRight size={16} />
          </IconButton>
        </div>
      </div>
      <div className="slide-canvas">
        <div className="slide-top">
          <span>REPORT FOUNDRY</span>
          <span>{props.snapshot.period.label}</span>
        </div>
        <h2>{slide === 0 ? props.snapshot.title : "The regional picture"}</h2>
        {slide === 0 ? (
          <>
            <Metrics {...props} />
            {nodes
              .filter((n) => n.kind === "rich_text")
              .map((node) => (
                <div className="slide-prose" key={node.id}>
                  <span className="eyebrow">{node.title}</span>
                  <p>
                    <RichText {...props} node={node} />
                  </p>
                </div>
              ))}
          </>
        ) : (
          <>
            <RevenueChart
              {...props}
              dataset={props.snapshot.datasets.regional_totals}
            />
            <div className="slide-table">
              <DataTable
                {...props}
                dataset={props.snapshot.datasets.regional_totals}
              />
            </div>
            <p className="slide-note">
              <Layers3 size={12} />
              Regional pivot is represented by these materialized aggregates.
            </p>
          </>
        )}
        <footer>
          <span>
            {slide === 0 ? "Performance overview" : "Regional analysis"} ·
            Revision {props.snapshot.revision}
          </span>
          {nodes
            .filter((n) => n.kind === "image")
            .map((n) => (
              <img
                key={n.id}
                src={`/api/assets/${n.asset_id}/download`}
                alt={n.decorative ? "" : (n.alt_text ?? n.title)}
              />
            ))}
          <strong>{String(slide + 1).padStart(2, "0")}</strong>
        </footer>
      </div>
      <div className="slide-thumbnails">
        {[0, 1].map((i) => (
          <button
            className={slide === i ? "active" : ""}
            key={i}
            onClick={() => setSlide(i)}
          >
            <span>{String(i + 1).padStart(2, "0")}</span>
            {i === 0 ? <FileText size={28} /> : <BarChart3 size={28} />}
            <strong>
              {i === 0 ? "Performance overview" : "Regional analysis"}
            </strong>
          </button>
        ))}
      </div>
    </div>
  );
}
export function EvidencePanel({
  snapshot,
  selectedFact,
  onFact,
  onClose,
  onSource,
}: Shared & { onClose: () => void; onSource: (id: string) => void }) {
  const fact: Fact | undefined = selectedFact
    ? snapshot.facts[selectedFact]
    : undefined;
  return (
    <aside className="evidence-panel">
      <header>
        <div>
          <Link2 size={16} />
          <h2>Evidence & lineage</h2>
        </div>
        <IconButton label="Close evidence panel" onClick={onClose}>
          <X size={15} />
        </IconButton>
      </header>
      {fact ? (
        <>
          <div className="evidence-section">
            <button className="small-text-button" onClick={() => onFact("")}>
              <ChevronLeft size={12} />
              All report evidence
            </button>
            <span className="eyebrow fact-eyebrow">SELECTED FACT</span>
            <h3 className="fact-value">{fact.display}</h3>
            <p className="fact-definition">{fact.definition}</p>
            <Badge status={fact.status} />
            <dl>
              <KeyValue label="Fact identifier" mono>
                {fact.id}
              </KeyValue>
              <KeyValue label="Scope">{fact.scope}</KeyValue>
              <KeyValue label="Exact value" mono>
                {fact.value === null ? "Undefined" : fact.value}
                {fact.unit && ` ${fact.unit}`}
              </KeyValue>
            </dl>
          </div>
          {fact.inputs.length > 0 && (
            <div className="evidence-section">
              <h3>
                <GitBranch size={14} />
                Derived from
              </h3>
              <div className="fact-dependencies">
                {fact.inputs.map((id) => (
                  <button key={id} onClick={() => onFact(id)}>
                    <span>{snapshot.facts[id]?.definition ?? id}</span>
                    <strong>{snapshot.facts[id]?.display ?? id}</strong>
                    <ChevronRight size={13} />
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="evidence-section">
            <h3>
              <Database size={14} />
              Source locations
            </h3>
            {fact.sources.length ? (
              fact.sources.map((source, i) => (
                <div className="source-locator" key={i}>
                  <button
                    className="text-button"
                    onClick={() => onSource(source.asset_id)}
                  >
                    {snapshot.source_assets.find(
                      (s) => s.id === source.asset_id,
                    )?.filename ?? source.asset_id}
                    <ArrowUpRight size={12} />
                  </button>
                  <p>{pretty(source.locator)}</p>
                  <code title={source.artifact_sha256}>
                    {source.artifact_sha256.slice(0, 16)}…
                  </code>
                </div>
              ))
            ) : (
              <p className="muted-small">
                Follow the upstream facts to their original source locations.
              </p>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="evidence-intro">
            <span className="evidence-symbol">
              <Fingerprint size={27} strokeWidth={1.4} />
            </span>
            <h3>Built on evidence.</h3>
            <p>
              Select any highlighted figure to see its definition, calculation,
              and source.
            </p>
          </div>
          <div className="evidence-section">
            <h3>Snapshot at a glance</h3>
            <div className="evidence-stats">
              <div>
                <strong>{Object.keys(snapshot.facts).length}</strong>
                <span>Shared facts</span>
              </div>
              <div>
                <strong>{snapshot.source_assets.length}</strong>
                <span>Bound sources</span>
              </div>
              <div>
                <strong>{snapshot.views.length}</strong>
                <span>Native views</span>
              </div>
            </div>
          </div>
          <div className="evidence-section">
            <h3>
              <FileCheck2 size={14} />
              Validation
            </h3>
            {snapshot.findings.length === 0 ? (
              <div className="validation-good">
                <CheckCheck size={17} />
                <span>No validation findings</span>
              </div>
            ) : (
              snapshot.findings.map((f) => (
                <div className={`finding ${f.severity}`} key={f.id}>
                  <span>
                    {f.severity === "review"
                      ? "Review required"
                      : f.severity === "block"
                        ? "Blocked"
                        : "Note"}
                  </span>
                  <p>{f.message}</p>
                </div>
              ))
            )}
          </div>
          <div className="evidence-section">
            <h3>
              <Database size={14} />
              Bound sources
            </h3>
            {snapshot.source_assets.map((asset) => (
              <button
                className="evidence-source"
                key={asset.id}
                onClick={() => onSource(asset.id)}
              >
                <FileText size={15} />
                <span>
                  {asset.filename}
                  <small>Immutable source</small>
                </span>
                <ArrowUpRight size={13} />
              </button>
            ))}
          </div>
        </>
      )}
      <div className="evidence-section">
        <h3>
          <GitBranch size={14} />
          Snapshot identity
        </h3>
        <dl>
          <KeyValue label="Revision">
            {snapshot.revision}
            {snapshot.parent_id
              ? " · follows a prior revision"
              : " · original run"}
          </KeyValue>
          <KeyValue label="Program">v{snapshot.program.version}</KeyValue>
          <KeyValue label="Program digest" mono>
            <span title={snapshot.program.digest}>
              {snapshot.program.digest.slice(0, 18)}…
            </span>
          </KeyValue>
          <KeyValue label="Created">{shortDate(snapshot.created_at)}</KeyValue>
        </dl>
        <a
          className="small-text-button"
          href={`/api/report-snapshots/${snapshot.id}/audit`}
          download
        >
          Download audit bundle <ArrowUpRight size={13} />
        </a>
      </div>
      <div className="evidence-disclosure">
        <Info size={14} />
        <p>
          All views share this snapshot. Editorial changes create a new
          revision.
        </p>
      </div>
    </aside>
  );
}
