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
  Image as ImageIcon,
  ImageOff,
  Layers3,
  Link2,
  LockKeyhole,
  Pencil,
  PenLine,
  ShieldCheck,
  Table2,
  X,
} from "lucide-react";
import type { Dataset, Fact, ReportNode, Snapshot } from "./types";
import { getNodes } from "./types";
import { ImagePreview } from "./ImagePreview";
import { nodesForView, viewGroups } from "./viewLayouts";
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
  onSource: (id: string) => void;
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
  props: Shared & {
    onEdit: (node: ReportNode) => void;
    onDraft: () => void;
    actionsDisabled?: boolean;
  },
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
                  <div className="commentary-actions">
                    <button
                      className="small-text-button"
                      onClick={() => props.onEdit(node)}
                      disabled={props.actionsDisabled}
                    >
                      <Pencil size={12} />
                      Revise commentary
                    </button>
                    <button
                      className="small-text-button"
                      onClick={props.onDraft}
                      disabled={props.actionsDisabled}
                    >
                      <PenLine size={13} />
                      Draft with AI
                    </button>
                  </div>
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
            <SnapshotImage
              {...props}
              node={node}
              key={`${snapshot.id}:${node.id}`}
            />
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
function SnapshotImage({
  snapshot,
  node,
  onSource,
}: Shared & { node: ReportNode }) {
  const source = snapshot.source_assets.find(
    (asset) => asset.id === node.asset_id,
  );
  return (
    <figure className="snapshot-image">
      {node.render_digest ? (
        <ImagePreview
          src={`/api/report-snapshots/${encodeURIComponent(snapshot.id)}/images/${encodeURIComponent(node.id)}`}
          alt={node.decorative ? "" : (node.alt_text ?? node.title)}
          className="snapshot-image-preview"
          onInspect={node.asset_id ? () => onSource(node.asset_id!) : undefined}
          inspectLabel={`Inspect source for ${node.title}`}
        />
      ) : (
        <div className="legacy-image-unavailable" role="status">
          <ImageOff size={22} />
          <p>
            This legacy snapshot has no preserved image bytes. Its image preview
            is unavailable.
          </p>
        </div>
      )}
      <figcaption>
        <div className="snapshot-image-caption">
          <strong>{node.title}</strong>
          {!node.decorative && node.alt_text && <p>{node.alt_text}</p>}
        </div>
        <div className="image-source-meta">
          <span>
            {node.width_px && node.height_px
              ? `${node.width_px} × ${node.height_px} px`
              : "Image dimensions not recorded"}
            {node.decorative ? " · Decorative" : ""}
          </span>
          {node.asset_id && (
            <button
              type="button"
              className="small-text-button"
              onClick={() => onSource(node.asset_id!)}
            >
              Inspect image source <ArrowUpRight size={14} />
            </button>
          )}
        </div>
        <details className="technical-details">
          <summary>Image provenance</summary>
          <dl>
            <KeyValue label="Source">
              {source?.filename ?? node.asset_id}
            </KeyValue>
            <KeyValue label="Original digest" mono>
              {source?.digest ?? "Not recorded"}
            </KeyValue>
            <KeyValue label="Frozen image digest" mono>
              {node.render_digest ?? "Not recorded in this legacy snapshot"}
            </KeyValue>
          </dl>
        </details>
      </figcaption>
    </figure>
  );
}

function PreparedViewNode(
  props: Shared & { node: ReportNode; family: "grid" | "canvas" },
) {
  const { snapshot, node, family } = props;
  if (node.kind === "image")
    return <SnapshotImage {...props} key={`${snapshot.id}:${node.id}`} />;
  if (node.kind === "rich_text")
    return (
      <div className={family === "grid" ? "sheet-prose" : "slide-prose"}>
        <h3>{node.title}</h3>
        <p>
          <RichText {...props} node={node} />
        </p>
      </div>
    );
  const dataset =
    snapshot.datasets[node.materialized_dataset_id ?? node.dataset_id ?? ""];
  if (node.kind === "chart" && dataset)
    return (
      <section className={family === "grid" ? "sheet-chart" : "slide-chart"}>
        <h3 className="view-node-heading">{node.title}</h3>
        <RevenueChart {...props} dataset={dataset} />
      </section>
    );
  if ((node.kind === "table" || node.kind === "pivot") && dataset)
    return (
      <section className={family === "grid" ? "sheet-data" : "slide-table"}>
        <h3 className="view-node-heading">{node.title}</h3>
        <DataTable {...props} dataset={dataset} pivot={node.kind === "pivot"} />
        {node.kind === "pivot" && (
          <p className="slide-note">
            <Layers3 size={13} />
            Materialized pivot aggregates
          </p>
        )}
      </section>
    );
  return null;
}

export function WorkbookView(props: Shared) {
  const [selectedSheet, setSelectedSheet] = useState("");
  const nodes = nodesForView(props.snapshot, "workbook");
  const groups = viewGroups(props.snapshot, "workbook");
  const sheets =
    props.snapshot.datasets.pivot_source &&
    !groups.some((group) => group.name === "Source aggregates")
      ? [
          ...groups,
          {
            name: "Source aggregates",
            node_ids: [],
            dataset_id: "pivot_source",
          },
        ]
      : groups;
  const sheet = sheets.find((item) => item.name === selectedSheet) ?? sheets[0];
  const sheetNodes = (sheet?.node_ids ?? [])
    .map((id) => nodes.find((node) => node.id === id))
    .filter((node): node is ReportNode => Boolean(node));
  const onlyImages =
    sheetNodes.length > 0 && sheetNodes.every((node) => node.kind === "image");
  return (
    <div className="workbook-view">
      <div className="workbook-formula">
        <span className="cell-reference">{sheet?.name}</span>
        <span className="formula-label">ƒx</span>
        <span>
          Values from revision {props.snapshot.revision} ·{" "}
          {props.snapshot.period.label}
        </span>
      </div>
      <div
        className="workbook-canvas"
        id="workbook-sheet-content"
        role="tabpanel"
        aria-label={sheet?.name}
      >
        <div className="sheet-heading">
          {onlyImages ? <ImageIcon size={22} /> : <Table2 size={22} />}
          <div>
            <h2>
              {sheet?.dataset_id
                ? "Approved source aggregates"
                : onlyImages
                  ? "Report images"
                  : sheet?.name === "Overview"
                    ? props.snapshot.title
                    : sheet?.name}
            </h2>
            <p>
              {sheet?.dataset_id
                ? "Approved aggregate records behind the pivot. Transaction IDs are excluded."
                : onlyImages
                  ? "The image bytes and source identity preserved in this report snapshot."
                  : "Shared report nodes, arranged by this snapshot’s workbook recipe."}
            </p>
          </div>
        </div>
        {sheet === sheets[0] && !onlyImages && <Metrics {...props} />}
        {sheetNodes.map((node) => (
          <PreparedViewNode
            {...props}
            node={node}
            family="grid"
            key={`${props.snapshot.id}:${node.id}`}
          />
        ))}
        {sheet?.dataset_id && props.snapshot.datasets[sheet.dataset_id] && (
          <DataTable
            {...props}
            dataset={props.snapshot.datasets[sheet.dataset_id]}
          />
        )}
      </div>
      <div className="sheet-tabs" role="tablist" aria-label="Workbook sheets">
        {sheets.map((item, index) => (
          <button
            type="button"
            role="tab"
            aria-selected={sheet?.name === item.name}
            aria-controls="workbook-sheet-content"
            tabIndex={sheet?.name === item.name ? 0 : -1}
            className={sheet?.name === item.name ? "active" : ""}
            key={item.name}
            onClick={() => setSelectedSheet(item.name)}
            onKeyDown={(event) => {
              if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
                event.preventDefault();
                const next =
                  (index +
                    (event.key === "ArrowRight" ? 1 : -1) +
                    sheets.length) %
                  sheets.length;
                setSelectedSheet(sheets[next].name);
                const buttons =
                  event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>(
                    'button[role="tab"]',
                  );
                buttons?.[next]?.focus();
              }
            }}
          >
            {item.name}
          </button>
        ))}
        <span>{sheets.length} sheets</span>
      </div>
    </div>
  );
}

export function PresentationView(props: Shared) {
  const [selectedSlide, setSelectedSlide] = useState(0);
  const nodes = nodesForView(props.snapshot, "presentation");
  const slides = viewGroups(props.snapshot, "presentation");
  const index = Math.min(selectedSlide, Math.max(0, slides.length - 1));
  const slide = slides[index];
  const slideNodes = (slide?.node_ids ?? [])
    .map((id) => nodes.find((node) => node.id === id))
    .filter((node): node is ReportNode => Boolean(node));
  const onlyImages =
    slideNodes.length > 0 && slideNodes.every((node) => node.kind === "image");
  return (
    <div className="presentation-view">
      <div className="slide-navigation">
        <span className="eyebrow">PRESENTATION</span>
        <div>
          <button
            type="button"
            className="icon-button"
            aria-label="Previous slide"
            disabled={index === 0}
            onClick={() =>
              setSelectedSlide((current) => Math.max(0, current - 1))
            }
          >
            <ChevronLeft size={16} />
          </button>
          <span aria-live="polite">
            {index + 1} / {slides.length}
          </span>
          <button
            type="button"
            className="icon-button"
            aria-label="Next slide"
            disabled={index >= slides.length - 1}
            onClick={() =>
              setSelectedSlide((current) =>
                Math.min(slides.length - 1, current + 1),
              )
            }
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
      <div
        className={`slide-canvas${onlyImages ? " image-slide" : ""}`}
        aria-label={`Slide ${index + 1}: ${slide?.name}`}
      >
        <div className="slide-top">
          <span>REPORT FOUNDRY</span>
          <span>{props.snapshot.period.label}</span>
        </div>
        <h2>{slide?.name}</h2>
        {index === 0 && !onlyImages && <Metrics {...props} />}
        {slideNodes.map((node) => (
          <PreparedViewNode
            {...props}
            node={node}
            family="canvas"
            key={`${props.snapshot.id}:${node.id}`}
          />
        ))}
        <footer>
          <span>
            {slide?.name} · Revision {props.snapshot.revision}
          </span>
          <strong>{String(index + 1).padStart(2, "0")}</strong>
        </footer>
      </div>
      <div className="slide-thumbnails" aria-label="Choose a slide">
        {slides.map((item, itemIndex) => {
          const imageSlide =
            item.node_ids.some(
              (id) => nodes.find((node) => node.id === id)?.kind === "image",
            ) &&
            item.node_ids.every(
              (id) => nodes.find((node) => node.id === id)?.kind === "image",
            );
          return (
            <button
              type="button"
              className={index === itemIndex ? "active" : ""}
              key={`${item.name}:${itemIndex}`}
              aria-pressed={index === itemIndex}
              aria-label={`Slide ${itemIndex + 1}: ${item.name}`}
              onClick={() => setSelectedSlide(itemIndex)}
            >
              <span>{String(itemIndex + 1).padStart(2, "0")}</span>
              {imageSlide ? (
                <ImageIcon size={28} />
              ) : itemIndex === 0 ? (
                <FileText size={28} />
              ) : (
                <BarChart3 size={28} />
              )}
              <strong>{item.name}</strong>
            </button>
          );
        })}
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
