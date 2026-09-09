import { useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Database,
  FileSpreadsheet,
  FileText,
  Fingerprint,
  FolderOpen,
  GitBranch,
  Play,
  Plus,
  Search,
  ShieldCheck,
  Upload,
  XCircle,
} from "lucide-react";
import type { Asset, Bootstrap, Program, SnapshotSummary } from "./types";
import { api, messageOf, post } from "./api";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  ExternalLink,
  KeyValue,
  Modal,
  pretty,
  shortDate,
  Spinner,
} from "./ui";

export function ReportsPage({
  data,
  onOpen,
  onCreate,
  onRun,
}: {
  data: Bootstrap;
  onOpen: (id: string) => void;
  onCreate: () => void;
  onRun: (id?: string) => void;
}) {
  const [query, setQuery] = useState("");
  const reports = data.snapshots.filter((report) =>
    `${report.title} ${typeof report.period === "string" ? report.period : report.period.label}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const latest = Object.values(
    reports.reduce<Record<string, SnapshotSummary>>((acc, item) => {
      const key = `${item.report_type_id}:${typeof item.period === "string" ? item.period : item.period.label}`;
      if (
        !acc[key] ||
        acc[key].created_at < item.created_at ||
        (acc[key].created_at === item.created_at &&
          acc[key].revision < item.revision)
      )
        acc[key] = item;
      return acc;
    }, {}),
  );
  const history = [...reports].sort(
    (a, b) =>
      Date.parse(b.created_at) - Date.parse(a.created_at) ||
      b.revision - a.revision ||
      a.id.localeCompare(b.id),
  );
  const historyDate = new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "medium",
  });
  return (
    <div className="library-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">YOUR WORKSPACE</span>
          <h1>Reports</h1>
          <p>From trusted inputs to a report you can stand behind.</p>
        </div>
        <button className="button primary" onClick={onCreate}>
          <Plus size={16} />
          New report type
        </button>
      </div>
      <div className="library-toolbar">
        <div>
          <h2>
            Latest reports <span>{latest.length}</span>
          </h2>
        </div>
        <label className="search-field">
          <Search size={15} />
          <input
            aria-label="Search reports"
            placeholder="Find a report…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button className="small-text-button" onClick={() => setQuery("")}>
              Clear
            </button>
          )}
        </label>
      </div>
      {latest.length ? (
        <div className="report-list">
          {latest.map((report, i) => (
            <button
              className="report-list-row"
              onClick={() => onOpen(report.id)}
              key={report.id}
            >
              <span className="report-row-icon">
                <FileText size={23} strokeWidth={1.5} />
              </span>
              <span className="report-row-title">
                <strong>{report.title}</strong>
                <span>
                  {typeof report.period === "string"
                    ? report.period
                    : report.period.label}{" "}
                  <b>·</b> Revision {report.revision}
                </span>
              </span>
              <Badge status={report.status} />
              <span className="report-row-date">
                {shortDate(report.created_at)}
              </span>
              <span className="report-row-number">
                {String(i + 1).padStart(2, "0")}
              </span>
              <ArrowUpRight size={18} />
            </button>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<FileText size={27} />}
          title={
            query ? "No matching reports" : "Your first report starts here"
          }
          text={
            query
              ? "Try a different report name or period."
              : "Create a report type, bind a source, and run a published program."
          }
          action={
            !query && (
              <button className="button primary" onClick={onCreate}>
                <Plus size={16} />
                Create report type
              </button>
            )
          }
        />
      )}
      {history.length > 0 && (
        <details className="technical-details report-history">
          <summary>
            <Clock3 size={15} />
            All runs &amp; revisions <span>({history.length})</span>
          </summary>
          <div className="table-scroll">
            <table className="data-table">
              <caption className="sr-only">
                All matching report snapshots, newest first
              </caption>
              <thead>
                <tr>
                  <th scope="col">Report &amp; period</th>
                  <th scope="col">Revision</th>
                  <th scope="col">Status</th>
                  <th scope="col">Created · local time</th>
                  <th scope="col">
                    <span className="sr-only">Open report snapshot</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {history.map((report) => {
                  const period =
                    typeof report.period === "string"
                      ? report.period
                      : report.period.label;
                  const created = historyDate.format(
                    new Date(report.created_at),
                  );
                  return (
                    <tr key={report.id}>
                      <td>
                        <strong>{report.title}</strong>
                        <span className="muted-small">{period}</span>
                      </td>
                      <td>{report.revision}</td>
                      <td>
                        <Badge status={report.status} />
                      </td>
                      <td>
                        <time dateTime={report.created_at}>{created}</time>
                      </td>
                      <td>
                        <button
                          className="small-text-button"
                          onClick={() => onOpen(report.id)}
                          aria-label={`Open ${report.title}, ${period}, revision ${report.revision}, created ${created}`}
                        >
                          Open <ArrowUpRight size={14} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      )}
      <div className="section-heading spaced">
        <div>
          <h2>Reporting programs</h2>
          <p>Repeatable reporting policies, ready for a new period.</p>
        </div>
        <span className="subtle-label">
          {data.report_types.length} REPORT TYPES
        </span>
      </div>
      <div className="type-list">
        {data.report_types.map((type) => {
          const program = data.programs.find(
            (p) => p.report_type_id === type.id,
          );
          return (
            <div className="type-row" key={type.id}>
              <div className="type-symbol">
                <GitBranch size={19} />
              </div>
              <div>
                <h3>{type.name}</h3>
                <p>
                  {type.description || "Regional revenue reporting program"}
                </p>
              </div>
              <Badge status={program?.state ?? "candidate"} />
              <button
                className="button secondary small"
                onClick={() => onRun(type.id)}
                disabled={program?.state !== "published"}
              >
                New run
                <ArrowRight size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
export function SourcesPage({
  data,
  onOpen,
  onRefresh,
}: {
  data: Bootstrap;
  onOpen: (id: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  async function upload(file?: File) {
    if (!file || uploading) return;
    setUploading(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const asset = await api<Asset>("/assets", { method: "POST", body });
      await onRefresh();
      onOpen(asset.id);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }
  return (
    <div className="library-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">EVIDENCE LIBRARY</span>
          <h1>Sources</h1>
          <p>Original files, preserved with their source identity.</p>
        </div>
        <button
          className="button primary"
          onClick={() => input.current?.click()}
          disabled={uploading}
        >
          <Upload size={16} />
          Upload source
        </button>
      </div>
      <input
        ref={input}
        className="sr-only"
        type="file"
        accept=".csv,.xlsx,.docx,.pdf"
        aria-label="Upload source file"
        onChange={(e) => void upload(e.target.files?.[0])}
      />
      <button
        className={`upload-zone${dragging ? " dragging" : ""}`}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void upload(e.dataTransfer.files[0]);
        }}
        disabled={uploading}
      >
        {uploading ? (
          <Spinner label="Inspecting and preserving your source…" />
        ) : (
          <>
            <span className="upload-icon">
              <Upload size={22} strokeWidth={1.5} />
            </span>
            <strong>Drop a source here, or browse files</strong>
            <span>
              CSV, XLSX, DOCX or PDF · Source inspection runs automatically
            </span>
          </>
        )}
      </button>
      {error && <ErrorNotice message={error} />}
      <div className="library-toolbar">
        <h2>
          Source library <span>{data.assets.length}</span>
        </h2>
        <span className="muted-small">Immutable originals</span>
      </div>
      {data.assets.length ? (
        <div className="source-list">
          {data.assets.map((asset) => (
            <button
              key={asset.id}
              className="source-row"
              onClick={() => onOpen(asset.id)}
            >
              <span className={`file-icon ${asset.filename.split(".").pop()}`}>
                {/\.csv$|\.xlsx$/i.test(asset.filename) ? (
                  <FileSpreadsheet size={22} />
                ) : (
                  <FileText size={22} />
                )}
              </span>
              <span className="source-name">
                <strong>{asset.filename}</strong>
                <span>
                  {String(
                    asset.profile?.format ?? asset.filename.split(".").pop(),
                  ).toUpperCase()}{" "}
                  <b>·</b>{" "}
                  {typeof asset.profile?.row_count === "number"
                    ? `${asset.profile.row_count} rows`
                    : "Document source"}
                  {asset.demo === true && <em>Synthetic demo</em>}
                </span>
              </span>
              <Badge status={String(asset.status ?? "usable")} />
              <span className="source-date">{shortDate(asset.created_at)}</span>
              <ChevronRight size={16} />
            </button>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<FolderOpen size={28} />}
          title="A home for your evidence"
          text="Upload a source to inspect its structure and make it available to a reporting program."
        />
      )}
      <div className="source-policy">
        <Fingerprint size={23} strokeWidth={1.5} />
        <div>
          <h3>Every file has a lasting identity.</h3>
          <p>
            Source files are stored with a content digest. Updated files become
            new sources, so earlier reports remain traceable.
          </p>
        </div>
      </div>
    </div>
  );
}
export function SourceDetail({
  asset,
  onClose,
}: {
  asset: Asset;
  onClose: () => void;
}) {
  const profile = asset.profile ?? {};
  const rows = Array.isArray(profile.sample_rows)
    ? (profile.sample_rows as Record<string, unknown>[])
    : [];
  const columns = Array.isArray(profile.columns)
    ? profile.columns.map((c) =>
        typeof c === "string"
          ? c
          : String(
              (c as Record<string, unknown>).name ??
                (c as Record<string, unknown>).id,
            ),
      )
    : rows[0]
      ? Object.keys(rows[0])
      : [];
  const warnings = Array.isArray(profile.warnings) ? profile.warnings : [];
  return (
    <Modal
      title={asset.filename}
      eyebrow="SOURCE INSPECTION"
      onClose={onClose}
      wide
    >
      <div className="modal-body">
        <div className="source-detail-summary">
          <span className="large-file-icon">
            <FileSpreadsheet size={32} strokeWidth={1.5} />
          </span>
          <div>
            <Badge status={String(asset.status ?? "usable")} />
            {asset.demo === true && (
              <p className="muted-small">Synthetic demonstration data</p>
            )}
          </div>
          <ExternalLink href={`/api/assets/${asset.id}/download`}>
            Download original
          </ExternalLink>
        </div>
        <dl className="source-properties">
          <KeyValue label="Format">
            {String(profile.format ?? asset.media_type ?? "Document")}
          </KeyValue>
          <KeyValue label="Rows">
            {String(profile.row_count ?? "Not tabular")}
          </KeyValue>
          <KeyValue label="Added">{shortDate(asset.created_at)}</KeyValue>
          <KeyValue label="Eligible roles">
            {Array.isArray(profile.eligible_roles)
              ? profile.eligible_roles.join(", ") || "Reference only"
              : "Reference only"}
          </KeyValue>
        </dl>
        {warnings.map((warning, i) => (
          <div className="notice warning" key={i}>
            {pretty(warning)}
          </div>
        ))}
        <h3 className="detail-subheading">Content preview</h3>
        {rows.length ? (
          <div className="table-scroll source-preview">
            <table className="data-table">
              <thead>
                <tr>
                  {columns.map((col) => (
                    <th key={col}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i}>
                    {columns.map((col) => (
                      <td key={col}>{String(row[col] ?? "—")}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted-small">
            This source has no tabular preview. Download the preserved original
            to inspect its content.
          </p>
        )}
        <details className="technical-details">
          <summary>
            <Fingerprint size={14} />
            Source identity and full inspection
          </summary>
          <dl>
            <KeyValue label="Content digest" mono>
              {asset.digest ?? asset.sha256 ?? "Unavailable"}
            </KeyValue>
            <KeyValue label="Asset identifier" mono>
              {asset.id}
            </KeyValue>
          </dl>
          <pre>{pretty(profile)}</pre>
        </details>
      </div>
      <footer className="modal-footer">
        <span className="muted-small">
          Source upload does not generate a report.
        </span>
        <button className="button secondary" onClick={onClose}>
          Done
        </button>
      </footer>
    </Modal>
  );
}
export function ProgramsPage({
  programs,
  onRefresh,
}: {
  programs: Program[];
  onRefresh: () => Promise<void>;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const program = programs.find((p) => p.id === selected) ?? programs[0];
  async function act(action: string, extra: Record<string, unknown> = {}) {
    if (!program) return;
    setBusy(action);
    setError(null);
    try {
      await post(`/programs/${program.id}/${action}`, {
        expected_digest: program.digest,
        ...extra,
      });
      await onRefresh();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="library-page programs-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">REPEATABLE BY DESIGN</span>
          <h1>Programs</h1>
          <p>
            The policy behind your reports, with visible checks and decisions.
          </p>
        </div>
      </div>
      {programs.length === 0 ? (
        <EmptyState
          icon={<GitBranch size={28} />}
          title="No programs yet"
          text="Create a report type to begin with a candidate reporting program."
        />
      ) : (
        <>
          <div
            className="program-selector"
            role="tablist"
            aria-label="Reporting programs"
          >
            {programs.map((p) => (
              <button
                role="tab"
                aria-selected={program?.id === p.id}
                className={program?.id === p.id ? "active" : ""}
                key={p.id}
                onClick={() => {
                  setSelected(p.id);
                  setError(null);
                }}
              >
                <GitBranch size={15} />
                {p.name ?? "Revenue program"}
                <Badge status={p.state} />
              </button>
            ))}
          </div>
          {error && <ErrorNotice message={error} />}
          {program && (
            <>
              <div className="program-banner">
                <div>
                  <span className="eyebrow">
                    REPORTING PROGRAM · V{program.version}
                  </span>
                  <h2>{program.name}</h2>
                  <p>
                    {program.state === "published"
                      ? "Published policy is frozen. Every run records this exact version."
                      : "Resolve policy decisions, evaluate the candidate, then publish."}
                  </p>
                </div>
                <div className="program-actions">
                  <button
                    className="button secondary"
                    disabled={Boolean(busy)}
                    onClick={() => void act("evaluate")}
                  >
                    {busy === "evaluate" ? (
                      <Spinner label="Evaluating…" />
                    ) : (
                      <>
                        <Play size={14} />
                        Run evaluation
                      </>
                    )}
                  </button>
                  {program.state !== "published" && (
                    <button
                      className="button primary"
                      disabled={
                        Boolean(busy) ||
                        !program.evaluation?.passed ||
                        program.decisions.some((d) => !d.resolution)
                      }
                      onClick={() => void act("publish")}
                    >
                      {busy === "publish" ? (
                        <Spinner label="Publishing…" />
                      ) : (
                        <>
                          <ShieldCheck size={15} />
                          Publish program
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>
              <div className="program-grid">
                <section className="program-section">
                  <div className="section-heading">
                    <h2>Coverage ledger</h2>
                    <span className="muted-small">
                      {
                        program.coverage.filter((c) => c.status === "verified")
                          .length
                      }{" "}
                      / {program.coverage.length} verified
                    </span>
                  </div>
                  <div className="coverage-list">
                    {program.coverage.map((component) => (
                      <div key={component.id}>
                        <span className={`coverage-icon ${component.status}`}>
                          {component.status === "verified" ? (
                            <Check size={14} />
                          ) : (
                            <Clock3 size={14} />
                          )}
                        </span>
                        <span>
                          <strong>{component.label}</strong>
                          <small>{component.kind.replaceAll("_", " ")}</small>
                        </span>
                        <Badge status={component.status} />
                      </div>
                    ))}
                  </div>
                </section>
                <section className="program-section">
                  <div className="section-heading">
                    <h2>Independent evaluation</h2>
                    {program.evaluation && (
                      <Badge
                        status={
                          program.evaluation.passed ? "verified" : "blocked"
                        }
                      >
                        {program.evaluation.passed ? "Passed" : "Needs repair"}
                      </Badge>
                    )}
                  </div>
                  {program.evaluation ? (
                    <>
                      <p className="muted-small">
                        Recorded {shortDate(program.evaluation.created_at)}{" "}
                        against this program digest.
                      </p>
                      <div className="evaluation-list">
                        {program.evaluation.checks.map((check, i) => (
                          <div key={i}>
                            {check.passed ? (
                              <CheckCircle2 size={17} />
                            ) : (
                              <XCircle size={17} />
                            )}
                            <span>
                              <strong>{check.name}</strong>
                              <small>{check.detail}</small>
                            </span>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="evaluation-empty">
                      <ShieldCheck size={28} strokeWidth={1.4} />
                      <h3>Ready to be checked</h3>
                      <p>
                        Evaluation records whether this candidate satisfies the
                        independent fixture checks.
                      </p>
                    </div>
                  )}
                </section>
              </div>
              <section className="program-section decisions-section">
                <div className="section-heading">
                  <h2>Policy decisions</h2>
                  <span className="muted-small">
                    Versioned, explicit choices
                  </span>
                </div>
                {program.decisions.length ? (
                  program.decisions.map((decision) => (
                    <div className="decision" key={decision.id}>
                      <div className="decision-heading">
                        <h3>{decision.question}</h3>
                        <Badge
                          status={
                            decision.resolution ? "accepted" : "needs_decision"
                          }
                        >
                          {decision.resolution ? "Resolved" : "Needs decision"}
                        </Badge>
                      </div>
                      <div className="decision-alternatives">
                        {decision.alternatives.map((option) => (
                          <label
                            key={option.value}
                            className={
                              (decisions[decision.id] ??
                                decision.resolution) === option.value
                                ? "selected"
                                : ""
                            }
                          >
                            <input
                              type="radio"
                              name={decision.id}
                              value={option.value}
                              checked={
                                (decisions[decision.id] ??
                                  decision.resolution) === option.value
                              }
                              disabled={program.state === "published"}
                              onChange={() =>
                                setDecisions((d) => ({
                                  ...d,
                                  [decision.id]: option.value,
                                }))
                              }
                            />
                            <span>
                              <strong>{option.label}</strong>
                              <small>{option.consequence}</small>
                            </span>
                          </label>
                        ))}
                      </div>
                      {program.state !== "published" && (
                        <button
                          className="button secondary small"
                          disabled={
                            Boolean(busy) ||
                            !decisions[decision.id] ||
                            decisions[decision.id] === decision.resolution
                          }
                          onClick={() =>
                            void act("decisions", {
                              decision_id: decision.id,
                              resolution: decisions[decision.id],
                            })
                          }
                        >
                          Record decision
                          <ArrowRight size={14} />
                        </button>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="muted-small">
                    No unresolved policy choices are recorded for this program.
                  </p>
                )}
              </section>
              <section className="program-section">
                <h2>Declared scope</h2>
                <ul className="limitations">
                  {program.limitations.map((limitation, i) => (
                    <li key={i}>{limitation}</li>
                  ))}
                </ul>
                <details className="technical-details">
                  <summary>
                    <Database size={14} />
                    Input contract and package identity
                  </summary>
                  <pre>{pretty(program.input_contract)}</pre>
                  <dl>
                    <KeyValue label="Program digest" mono>
                      {program.digest}
                    </KeyValue>
                  </dl>
                </details>
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}
