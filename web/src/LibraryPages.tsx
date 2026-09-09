import { useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  ChevronRight,
  Clock3,
  FileSpreadsheet,
  FileText,
  Fingerprint,
  FolderOpen,
  GitBranch,
  Image as ImageIcon,
  Plus,
  Search,
  Upload,
} from "lucide-react";
import type { Asset, Bootstrap, SnapshotSummary } from "./types";
import { activeProgramFor, canRunProgram, getImageProfile } from "./types";
import { ImagePreview } from "./ImagePreview";
import { api, messageOf } from "./api";
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
          const program = activeProgramFor(type, data.programs);
          const candidate = data.programs.find(
            (p) => p.report_type_id === type.id && p.state === "candidate",
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
              <Badge status={program ? "published" : "candidate"}>
                {program
                  ? `Active · v${program.version}`
                  : "Awaiting publication"}
              </Badge>
              {candidate && program && (
                <span className="muted-small">Update in review</span>
              )}
              <button
                className="button secondary small"
                onClick={() => onRun(type.id)}
                disabled={!canRunProgram(program)}
                title={
                  program?.runtime_status === "code_changed"
                    ? "The active release needs a program update. Open Programs to review it."
                    : program?.runtime_status === "restart_required"
                      ? "Restart the local service before creating a new run."
                      : undefined
                }
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
        accept=".csv,.xlsx,.docx,.pdf,.png,.jpg,.jpeg"
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
              CSV, XLSX, DOCX, PDF, PNG or JPEG · Source inspection runs
              automatically
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
                {/\.(png|jpe?g)$/i.test(asset.filename) ? (
                  <ImageIcon size={22} />
                ) : /\.csv$|\.xlsx$/i.test(asset.filename) ? (
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
                  {getImageProfile(asset)
                    ? `${getImageProfile(asset)!.width_px} × ${getImageProfile(asset)!.height_px} px`
                    : typeof asset.profile?.row_count === "number"
                      ? `${asset.profile.row_count} rows`
                      : /\.(png|jpe?g)$/i.test(asset.filename)
                        ? "Image source"
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
  const imageProfile = getImageProfile(asset);
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
            {imageProfile ? (
              <ImageIcon size={32} strokeWidth={1.5} />
            ) : (
              <FileSpreadsheet size={32} strokeWidth={1.5} />
            )}
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
          <KeyValue label={imageProfile ? "Image dimensions" : "Rows"}>
            {imageProfile
              ? `${imageProfile.width_px} × ${imageProfile.height_px} px`
              : String(profile.row_count ?? "Not tabular")}
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
        <h3 className="detail-subheading">
          {imageProfile ? "Prepared report image" : "Content preview"}
        </h3>
        {imageProfile ? (
          <>
            <ImagePreview
              src={`/api/assets/${asset.id}/preview`}
              alt={`Prepared preview of ${asset.filename}`}
              className="source-image-preview"
            />
            <p className="image-normalization-note">
              The report uses an orientation-corrected PNG with image metadata
              removed. The immutable original is available separately above.
            </p>
            <dl className="source-properties">
              <KeyValue label="Report image format">
                {imageProfile.media_type}
              </KeyValue>
              <KeyValue label="Preparation">
                Orientation applied · metadata removed
              </KeyValue>
            </dl>
          </>
        ) : rows.length ? (
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
            {imageProfile && (
              <>
                <KeyValue label="Prepared image digest" mono>
                  {imageProfile.render_digest}
                </KeyValue>
                <KeyValue label="Preparation method" mono>
                  {imageProfile.normalization}
                </KeyValue>
              </>
            )}
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
export { ProgramsPage } from "./ProgramsPage";
