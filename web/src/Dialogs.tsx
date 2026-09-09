import { useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  FileSpreadsheet,
  Eye,
  FileText,
  Info,
  Layers3,
  LockKeyhole,
  Play,
  Presentation,
  ShieldCheck,
} from "lucide-react";
import type {
  Bootstrap,
  ExportRecord,
  Job,
  ReportNode,
  Snapshot,
} from "./types";
import { identifier, messageOf, post } from "./api";
import { Badge, CheckLine, ErrorNotice, Modal, pretty, Spinner } from "./ui";

export function JobProgress({
  job,
  onCancel,
}: {
  job: Job;
  onCancel?: () => void;
}) {
  const steps = Array.isArray(job.steps)
    ? (job.steps as { stage: string; at: string }[])
    : [];
  return (
    <div className="job-progress" aria-live="polite">
      <div className="job-current">
        {["queued", "running"].includes(job.status) ? (
          <Spinner label={(job.stage ?? job.status).replaceAll("_", " ")} />
        ) : (
          <Badge status={job.status} />
        )}
        <span className="muted-small">
          {job.kind === "export" ? "Export job" : "Report run"}
        </span>
      </div>
      {steps.length > 0 && (
        <ol className="job-steps">
          {steps.map((step, i) => (
            <li key={`${step.stage}-${i}`}>
              <span
                className={
                  i === steps.length - 1 && job.status === "running"
                    ? "current"
                    : ""
                }
              />
              <strong>{step.stage.replaceAll("_", " ")}</strong>
            </li>
          ))}
        </ol>
      )}
      {job.error != null && (
        <ErrorNotice
          message={
            typeof job.error === "object" && "message" in job.error
              ? String(job.error.message)
              : pretty(job.error)
          }
        />
      )}
      {["queued", "running"].includes(job.status) && onCancel && (
        <button className="small-text-button" onClick={onCancel}>
          Cancel job
        </button>
      )}
    </div>
  );
}
export function CreateTypeDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/report-types", {
        name: name.trim(),
        description: description.trim(),
      });
      await onCreated();
      onClose();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="A new reporting program"
      eyebrow="CREATE REPORT TYPE"
      onClose={onClose}
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          <p className="dialog-intro">
            Give this recurring report a name. You’ll review its policy and
            evaluation before the first run.
          </p>
          <label className="field">
            Report name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Quarterly revenue"
              maxLength={100}
              required
            />
          </label>
          <label className="field">
            Description <span className="optional">Optional</span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What should this report help you understand?"
              rows={3}
              maxLength={1000}
            />
          </label>
          <div className="notice info">
            <Info size={17} />
            <p>
              This local release supports a regional revenue program. Creating a
              report type starts a candidate using that adapter; it does not
              infer a policy from historical reports.
            </p>
          </div>
          {error && <ErrorNotice message={error} />}
        </div>
        <footer className="modal-footer">
          <button type="button" className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="button primary" disabled={busy || !name.trim()}>
            {busy ? (
              <Spinner label="Creating…" />
            ) : (
              <>
                Create report type
                <ArrowRight size={15} />
              </>
            )}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
export function RunDialog({
  data,
  snapshot,
  reportTypeId,
  job,
  onJob,
  onCancel,
  onClose,
}: {
  data: Bootstrap;
  snapshot: Snapshot | null;
  reportTypeId?: string;
  job: Job | null;
  onJob: (job: Job) => void;
  onCancel: () => void;
  onClose: () => void;
}) {
  const published = data.report_types.filter((t) =>
    data.programs.some(
      (p) => p.report_type_id === t.id && p.state === "published",
    ),
  );
  const usable = data.assets.filter(
    (a) =>
      Array.isArray(a.profile?.eligible_roles) &&
      a.profile.eligible_roles.includes("transactions") &&
      a.status !== "blocked",
  );
  const fallback = {
    label: "Q1 2026",
    start: "2026-01-01",
    end_exclusive: "2026-04-01",
    comparison: { start: "2025-01-01", end_exclusive: "2025-04-01" },
    timezone: "Europe/Paris",
    as_of: "2026-04-01T00:00:00+02:00",
  };
  const period = snapshot?.period ?? fallback;
  const [type, setType] = useState(
    reportTypeId ?? snapshot?.report_type_id ?? published[0]?.id ?? "",
  );
  const [source, setSource] = useState(
    usable.find((a) => snapshot?.source_assets.some((s) => s.id === a.id))
      ?.id ??
      usable[0]?.id ??
      "",
  );
  const [label, setLabel] = useState(period.label);
  const [start, setStart] = useState(period.start);
  const [end, setEnd] = useState(period.end_exclusive);
  const [comparisonStart, setComparisonStart] = useState(
    period.comparison.start,
  );
  const [comparisonEnd, setComparisonEnd] = useState(
    period.comparison.end_exclusive,
  );
  const [timezone, setTimezone] = useState(period.timezone);
  const [asOf, setAsOf] = useState(period.as_of);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active =
    busy || Boolean(job && ["queued", "running"].includes(job.status));
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (end <= start || comparisonEnd <= comparisonStart) {
      setError("Each end date must fall after its start date.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await post<Job>("/report-runs", {
        report_type_id: type,
        asset_id: source,
        period: {
          label,
          start,
          end_exclusive: end,
          comparison: { start: comparisonStart, end_exclusive: comparisonEnd },
          timezone,
          as_of: asOf,
        },
        idempotency_key: identifier(),
      });
      onJob(result);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="A new period. The same policy."
      eyebrow="NEW REPORT RUN"
      onClose={onClose}
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          <p className="dialog-intro">
            Bind a source and define both date windows. The published program
            prepares a fresh, traceable snapshot.
          </p>
          <label className="field">
            Reporting program
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              required
            >
              <option value="" disabled>
                Select a published program
              </option>
              {published.map((t) => (
                <option value={t.id} key={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Transaction source
            <select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              required
            >
              <option value="" disabled>
                Select an eligible source
              </option>
              {usable.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.filename}
                  {a.demo ? " · synthetic demo" : ""}
                </option>
              ))}
            </select>
          </label>
          {!usable.length && (
            <div className="notice warning">
              Upload a compatible CSV or XLSX transaction source in Sources
              first.
            </div>
          )}
          <label className="field">
            Period label
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              required
            />
          </label>
          <fieldset className="period-fieldset">
            <legend>Current period</legend>
            <div className="field-row">
              <label className="field">
                Start date
                <input
                  type="date"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                End date <span className="optional">Exclusive</span>
                <input
                  type="date"
                  value={end}
                  onChange={(e) => setEnd(e.target.value)}
                  required
                />
              </label>
            </div>
          </fieldset>
          <fieldset className="period-fieldset">
            <legend>Comparison period</legend>
            <div className="field-row">
              <label className="field">
                Start date
                <input
                  type="date"
                  value={comparisonStart}
                  onChange={(e) => setComparisonStart(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                End date <span className="optional">Exclusive</span>
                <input
                  type="date"
                  value={comparisonEnd}
                  onChange={(e) => setComparisonEnd(e.target.value)}
                  required
                />
              </label>
            </div>
          </fieldset>
          <details className="advanced-options">
            <summary>
              Time zone and source cutoff
              <ChevronRight size={13} />
            </summary>
            <label className="field">
              Business time zone
              <input
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                required
              />
            </label>
            <label className="field">
              Source cutoff{" "}
              <span className="optional">ISO date with time zone</span>
              <input
                value={asOf}
                onChange={(e) => setAsOf(e.target.value)}
                required
              />
            </label>
          </details>
          {error && <ErrorNotice message={error} />}
          {job && <JobProgress job={job} onCancel={onCancel} />}
        </div>
        <footer className="modal-footer">
          <button type="button" className="button secondary" onClick={onClose}>
            {active ? "Run in background" : "Cancel"}
          </button>
          <button
            className="button primary"
            disabled={active || !type || !source}
          >
            {active ? (
              <Spinner label="Running…" />
            ) : (
              <>
                <Play size={15} />
                Generate report
              </>
            )}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
export function RevisionDialog({
  snapshot,
  node,
  onClose,
  onSaved,
}: {
  snapshot: Snapshot;
  node: ReportNode;
  onClose: () => void;
  onSaved: (snapshot: Snapshot) => void;
}) {
  const original =
    node.runs
      ?.map((r) =>
        r.type === "text" ? r.text : (snapshot.facts[r.fact_id]?.display ?? ""),
      )
      .join("") ?? "";
  const [text, setText] = useState(original);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await post<Snapshot>(
        `/report-snapshots/${snapshot.id}/revisions`,
        {
          expected_revision: snapshot.revision,
          node_id: node.id,
          text,
          reason,
        },
      );
      onSaved(result);
      onClose();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Revise editorial commentary"
      eyebrow={`REVISION ${snapshot.revision} → ${snapshot.revision + 1}`}
      onClose={onClose}
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          <p className="dialog-intro">
            Add context in your own words. Your edit is saved as a new revision
            with the original facts and source identity.
          </p>
          <label className="field">
            Commentary
            <textarea
              className="commentary-input"
              rows={7}
              value={text}
              onChange={(e) => setText(e.target.value)}
              required
              maxLength={4000}
            />
          </label>
          <label className="field">
            Reason for revision
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Clarified the scope of the comparison"
              required
              maxLength={500}
            />
          </label>
          <div className="notice info">
            <LockKeyhole size={16} />
            <p>
              Computed text and facts are locked. Numerical or causal claims in
              commentary may require review.
            </p>
          </div>
          {error && <ErrorNotice message={error} />}
        </div>
        <footer className="modal-footer">
          <button type="button" className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="button primary"
            disabled={
              busy || !text.trim() || !reason.trim() || text === original
            }
          >
            {busy ? (
              <Spinner label="Saving…" />
            ) : (
              <>
                Create revision
                <ArrowRight size={15} />
              </>
            )}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
export function AcceptDialog({
  snapshot,
  onClose,
  onSaved,
}: {
  snapshot: Snapshot;
  onClose: () => void;
  onSaved: (snapshot: Snapshot) => void;
}) {
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function accept() {
    setBusy(true);
    setError(null);
    try {
      const result = await post<Snapshot>(
        `/report-snapshots/${snapshot.id}/accept`,
        { expected_revision: snapshot.revision },
      );
      onSaved(result);
      onClose();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Accept this report"
      eyebrow="RELEASE REVIEW"
      onClose={onClose}
    >
      <div className="modal-body">
        <div className="accept-symbol">
          <ShieldCheck size={31} strokeWidth={1.5} />
        </div>
        <p className="dialog-intro">
          Confirm your review of {snapshot.period.label}. Acceptance creates an
          immutable revision and records your decision in its audit history.
        </p>
        {snapshot.findings.length > 0 && (
          <div className="review-findings">
            {snapshot.findings.map((f) => (
              <div key={f.id}>
                <Badge
                  status={
                    f.severity === "block" ? "blocked" : "review_required"
                  }
                />
                <p>{f.message}</p>
              </div>
            ))}
          </div>
        )}
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
          />
          <span>
            I have reviewed the report, its commentary, and the evidence
            relevant to these findings.
          </span>
        </label>
        {error && <ErrorNotice message={error} />}
      </div>
      <footer className="modal-footer">
        <button className="button secondary" onClick={onClose}>
          Keep in review
        </button>
        <button
          className="button primary"
          disabled={!checked || busy || snapshot.status === "blocked"}
          onClick={() => void accept()}
        >
          {busy ? (
            <Spinner label="Accepting…" />
          ) : (
            <>
              <ShieldCheck size={15} />
              Accept report
            </>
          )}
        </button>
      </footer>
    </Modal>
  );
}
const formats = [
  {
    id: "docx",
    title: "Word document",
    label: "DOCX",
    detail: "Document flow",
    icon: FileText,
  },
  {
    id: "xlsx",
    title: "Excel workbook",
    label: "XLSX",
    detail: "Workbook grid",
    icon: FileSpreadsheet,
  },
  {
    id: "pdf",
    title: "PDF document",
    label: "PDF",
    detail: "Fixed pages",
    icon: FileText,
  },
  {
    id: "pptx",
    title: "PowerPoint deck",
    label: "PPTX",
    detail: "Slide canvas",
    icon: Presentation,
  },
];
export function ExportDialog({
  snapshot,
  capabilities,
  job,
  exports,
  onJob,
  onCancel,
  onClose,
}: {
  snapshot: Snapshot;
  capabilities: Bootstrap["capabilities"];
  job: Job | null;
  exports: ExportRecord[];
  onJob: (job: Job) => void;
  onCancel: () => void;
  onClose: () => void;
}) {
  const [format, setFormat] = useState("docx");
  const [policy, setPolicy] = useState("compatible");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active =
    busy || Boolean(job && ["queued", "running"].includes(job.status));
  const exportId = String(job?.result?.export_id ?? job?.export_id ?? "");
  const completed = exports.find((record) => record.id === exportId);
  async function generate() {
    setBusy(true);
    setError(null);
    try {
      onJob(
        await post<Job>("/exports", {
          snapshot_id: snapshot.id,
          format,
          policy,
          idempotency_key: identifier(),
        }),
      );
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Take your report with you."
      eyebrow="EXPORT SNAPSHOT"
      onClose={onClose}
    >
      <div className="modal-body">
        <div className="export-context">
          <span>
            <FileText size={16} />
            {snapshot.period.label}
          </span>
          <Badge status={snapshot.status} />
          <span>Revision {snapshot.revision}</span>
        </div>
        <p className="dialog-intro">
          Every format is generated from this exact snapshot. Exporting never
          recalculates your report.
        </p>
        <div
          className="format-options"
          role="radiogroup"
          aria-label="Export format"
        >
          {formats.map((item) => (
            <label
              className={format === item.id ? "selected" : ""}
              key={item.id}
            >
              <input
                type="radio"
                name="format"
                value={item.id}
                checked={format === item.id}
                onChange={() => setFormat(item.id)}
                disabled={active}
              />
              <item.icon size={25} strokeWidth={1.5} />
              <span>
                <strong>{item.title}</strong>
                <small>{item.detail}</small>
              </span>
              <em>{item.label}</em>
            </label>
          ))}
        </div>
        <label className="field">
          Fidelity policy
          <select
            value={policy}
            onChange={(e) => setPolicy(e.target.value)}
            disabled={active}
          >
            <option value="compatible">
              Compatible — allow declared static representations
            </option>
            <option value="strict">
              Strict — require certified native capabilities
            </option>
          </select>
        </label>
        <div className="notice info">
          <Layers3 size={17} />
          <p>
            {format === "xlsx"
              ? "Workbook native features are not certified in this release. Compatible export uses declared static representations; strict export is blocked."
              : "Pivots become static aggregates in this format. The fidelity manifest records how each report element is represented."}
          </p>
        </div>
        <div className="export-assurances">
          <CheckLine>
            Snapshot, source and program identities preserved
          </CheckLine>
          <CheckLine>Fidelity manifest included with every export</CheckLine>
        </div>
        {snapshot.status !== "accepted" && (
          <div className="notice warning">
            This report is in review. Its export is labelled as a draft.
          </div>
        )}
        {error && <ErrorNotice message={error} />}
        {job && <JobProgress job={job} onCancel={onCancel} />}
        {completed && (
          <div className="export-ready">
            <CheckCircle2 size={22} />
            <div>
              <strong>Your {completed.format.toUpperCase()} is ready</strong>
              <span>{completed.filename}</span>
              <a href={`/api/exports/${completed.id}/manifest`} download>
                View fidelity manifest
                <ArrowRight size={12} />
              </a>
              {(completed.preview_digest || completed.format === "pdf") && (
                <a
                  href={`/api/exports/${completed.id}/preview`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Preview export
                  <ArrowRight size={12} />
                </a>
              )}
            </div>
            <a
              className="button primary small"
              href={`/api/exports/${completed.id}/download`}
              download
            >
              <ArrowDownToLine size={15} />
              Download
            </a>
          </div>
        )}
        <details className="technical-details">
          <summary>
            Renderer capability details
            <ChevronRight size={13} />
          </summary>
          <pre>{pretty(capabilities)}</pre>
        </details>
        {exports.length > 0 && (
          <details className="technical-details">
            <summary>
              Previous exports <span>{exports.length}</span>
            </summary>
            <div className="past-exports">
              {exports.map((record) => (
                <div key={record.id}>
                  <span>
                    {record.format.toUpperCase()}
                    <small>{record.filename}</small>
                  </span>
                  {(record.preview_digest || record.format === "pdf") && (
                    <a
                      href={`/api/exports/${record.id}/preview`}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`Preview ${record.format.toUpperCase()} export`}
                      title="Preview actual export"
                    >
                      <Eye size={16} />
                    </a>
                  )}
                  <a
                    href={`/api/exports/${record.id}/manifest`}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={`${record.format.toUpperCase()} fidelity manifest`}
                    title="View fidelity manifest"
                  >
                    <FileText size={16} />
                  </a>
                  <a
                    href={`/api/exports/${record.id}/download`}
                    download
                    aria-label={`Download ${record.filename}`}
                  >
                    <ArrowDownToLine size={15} />
                  </a>
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
      <footer className="modal-footer">
        <button className="button secondary" onClick={onClose}>
          {active ? "Continue in background" : "Close"}
        </button>
        <button
          className="button primary"
          disabled={active || (policy === "strict" && format === "xlsx")}
          onClick={() => void generate()}
        >
          {active ? (
            <Spinner label="Exporting…" />
          ) : (
            <>
              Create {format.toUpperCase()}
              <ArrowRight size={15} />
            </>
          )}
        </button>
      </footer>
    </Modal>
  );
}
