import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  CheckCircle2,
  FileText,
  Info,
  LockKeyhole,
  Play,
  Plus,
  Search,
  XCircle,
} from "lucide-react";
import type {
  Asset,
  HistoricalExample,
  Job,
  LearningCoverage,
  ModelStatus,
  Period,
  Program,
} from "./types";
import { api, identifier, messageOf, post } from "./api";
import { Badge, ErrorNotice, KeyValue, Modal, pretty, Spinner } from "./ui";
import { JobProgress } from "./Dialogs";
import { ModelConfiguration } from "./ModelConfiguration";

const exampleLabel = (example: HistoricalExample) =>
  example.label || example.period.label || example.report_filename;
const roleLabel = (role: string) =>
  ({
    authoring: "Available to learning",
    development: "Development / regression",
    reserved: "Reserved for evaluation",
  })[role] ?? role;

function AddExampleDialog({
  reportTypeId,
  assets,
  onClose,
  onSaved,
}: {
  reportTypeId: string;
  assets: Asset[];
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const targets = assets.filter(
    (asset) =>
      !asset.reserved &&
      asset.status !== "blocked" &&
      Array.isArray(asset.profile?.eligible_roles) &&
      asset.profile.eligible_roles.includes("historical_target") &&
      /\.(docx|pdf)$/i.test(asset.filename),
  );
  const sources = assets.filter(
    (asset) =>
      !asset.reserved &&
      asset.status !== "blocked" &&
      Array.isArray(asset.profile?.eligible_roles) &&
      asset.profile.eligible_roles.includes("transactions"),
  );
  const [target, setTarget] = useState("");
  const [source, setSource] = useState("");
  const [label, setLabel] = useState("");
  const [caveats, setCaveats] = useState("");
  const [role, setRole] =
    useState<HistoricalExample["corpus_role"]>("authoring");
  const [period, setPeriod] = useState<Period>({
    label: "",
    start: "",
    end_exclusive: "",
    comparison: { start: "", end_exclusive: "" },
    timezone: "Europe/Paris",
    as_of: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (
      period.end_exclusive <= period.start ||
      period.comparison.end_exclusive <= period.comparison.start
    ) {
      setError("Each end date must fall after its start date.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await post(`/report-types/${reportTypeId}/examples`, {
        report_asset_id: target,
        source_asset_ids: [source],
        period,
        corpus_role: role,
        ...(label.trim() ? { label: label.trim() } : {}),
        ...(caveats.trim() ? { caveats: caveats.trim() } : {}),
      });
      await onSaved();
      onClose();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Pair a report with its sources"
      eyebrow="HISTORICAL EXAMPLE"
      onClose={onClose}
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          <p className="dialog-intro">
            Connect a historical DOCX or PDF to the transaction data behind it.
            Its target values are evidence for learning, never inputs to a new
            report period.
          </p>
          <label className="field">
            Example label <span className="optional">Optional</span>
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              maxLength={100}
              placeholder="e.g. Approved first-quarter report"
            />
          </label>
          <label className="field">
            Historical report
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              required
            >
              <option value="" disabled>
                Choose a DOCX or PDF target
              </option>
              {targets.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.filename}
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
                Choose the CSV or XLSX behind the report
              </option>
              {sources.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.filename}
                </option>
              ))}
            </select>
          </label>
          {(!targets.length || !sources.length) && (
            <div className="notice info">
              <Info size={17} />
              <p>
                Upload the historical report and one compatible transaction
                source in Sources, then return here to pair them.
              </p>
            </div>
          )}
          <label className="field">
            Historical period label
            <input
              value={period.label}
              onChange={(e) =>
                setPeriod((p) => ({ ...p, label: e.target.value }))
              }
              required
              placeholder="e.g. Q1 2025"
            />
          </label>
          <fieldset className="period-fieldset">
            <legend>Reported period</legend>
            <div className="field-row">
              <label className="field">
                Start date
                <input
                  type="date"
                  value={period.start}
                  onChange={(e) =>
                    setPeriod((p) => ({ ...p, start: e.target.value }))
                  }
                  required
                />
              </label>
              <label className="field">
                End date <span className="optional">Exclusive</span>
                <input
                  type="date"
                  value={period.end_exclusive}
                  onChange={(e) =>
                    setPeriod((p) => ({ ...p, end_exclusive: e.target.value }))
                  }
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
                  value={period.comparison.start}
                  onChange={(e) =>
                    setPeriod((p) => ({
                      ...p,
                      comparison: { ...p.comparison, start: e.target.value },
                    }))
                  }
                  required
                />
              </label>
              <label className="field">
                End date <span className="optional">Exclusive</span>
                <input
                  type="date"
                  value={period.comparison.end_exclusive}
                  onChange={(e) =>
                    setPeriod((p) => ({
                      ...p,
                      comparison: {
                        ...p.comparison,
                        end_exclusive: e.target.value,
                      },
                    }))
                  }
                  required
                />
              </label>
            </div>
          </fieldset>
          <div className="example-time-fields">
            <label className="field">
              Business time zone
              <input
                value={period.timezone}
                onChange={(e) =>
                  setPeriod((p) => ({ ...p, timezone: e.target.value }))
                }
                required
              />
            </label>
            <label className="field">
              Source availability cutoff
              <input
                value={period.as_of}
                onChange={(e) =>
                  setPeriod((p) => ({ ...p, as_of: e.target.value }))
                }
                placeholder="2025-04-01T00:00:00+02:00"
                required
              />
              <span className="field-help">
                ISO date and time with a time zone.
              </span>
            </label>
          </div>
          <label className="field">
            How may this example be used?
            <select
              value={role}
              onChange={(e) =>
                setRole(e.target.value as HistoricalExample["corpus_role"])
              }
            >
              <option value="authoring">
                Authoring — available to learning
              </option>
              <option value="development">
                Development — regression evidence
              </option>
              <option value="reserved">
                Reserved — keep the target out of learning
              </option>
            </select>
          </label>
          {role === "reserved" && (
            <div className="notice info">
              <LockKeyhole size={17} />
              <p>
                The target stays hidden from learning and source previews.
                Revealing it later permanently makes it development evidence and
                records the reason.
              </p>
            </div>
          )}
          <label className="field">
            Caveats <span className="optional">Optional</span>
            <textarea
              value={caveats}
              onChange={(e) => setCaveats(e.target.value)}
              maxLength={2000}
              rows={3}
              placeholder="Record known historical errors, missing context, or policy exceptions."
            />
          </label>
          {error && <ErrorNotice message={error} />}
        </div>
        <footer className="modal-footer">
          <button
            type="button"
            className="button secondary"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            className="button primary"
            disabled={busy || !target || !source}
          >
            {busy ? (
              <Spinner label="Inspecting example…" />
            ) : (
              <>
                Add example
                <ArrowRight size={15} />
              </>
            )}
          </button>
        </footer>
      </form>
    </Modal>
  );
}

function ReasonDialog({
  title,
  eyebrow,
  explanation,
  actionLabel,
  submit,
  onClose,
}: {
  title: string;
  eyebrow: string;
  explanation: string;
  actionLabel: string;
  submit: (reason: string) => Promise<void>;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await submit(reason.trim());
      onClose();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title={title} eyebrow={eyebrow} onClose={onClose}>
      <form onSubmit={save}>
        <div className="modal-body">
          <p className="dialog-intro">{explanation}</p>
          <label className="field">
            Reason
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={1000}
              rows={4}
              required
              disabled={busy}
            />
          </label>
          {error && <ErrorNotice message={error} />}
        </div>
        <footer className="modal-footer">
          <button
            type="button"
            className="button secondary"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button className="button primary" disabled={busy || !reason.trim()}>
            {busy ? <Spinner label="Recording…" /> : actionLabel}
          </button>
        </footer>
      </form>
    </Modal>
  );
}

function ExampleDetails({
  example,
  onClose,
  onSource,
  onReveal,
  editable,
}: {
  example: HistoricalExample;
  onClose: () => void;
  onSource: (id: string) => void;
  onReveal: () => void;
  editable: boolean;
}) {
  const reserved =
    (example.effective_role ?? example.corpus_role) === "reserved";
  return (
    <Modal
      title={exampleLabel(example)}
      eyebrow="HISTORICAL EXAMPLE"
      onClose={onClose}
      wide
    >
      <div className="modal-body">
        <div className="example-detail-status">
          <Badge status={example.state} />
          <Badge status={reserved ? "reserved" : "known"}>
            {roleLabel(example.effective_role ?? example.corpus_role)}
          </Badge>
          {example.exposed && (
            <span className="muted-small">Exposure recorded</span>
          )}
        </div>
        <dl className="source-properties">
          <KeyValue label="Period">{example.period.label}</KeyValue>
          <KeyValue label="Reported window">
            {example.period.start} → {example.period.end_exclusive} (exclusive)
          </KeyValue>
          <KeyValue label="Comparison">
            {example.period.comparison.start} →{" "}
            {example.period.comparison.end_exclusive} (exclusive)
          </KeyValue>
          <KeyValue label="Cutoff">{example.period.as_of}</KeyValue>
        </dl>
        <div className="example-bound-files">
          <h3>Paired files</h3>
          <button
            className="text-button"
            onClick={() => {
              onClose();
              onSource(example.report_asset_id);
            }}
          >
            <FileText size={15} />
            {example.report_filename}
            <ArrowUpRight size={14} />
          </button>
          {example.source_asset_ids.map((id, index) => (
            <button
              className="text-button"
              key={id}
              onClick={() => {
                onClose();
                onSource(id);
              }}
            >
              <FileText size={15} />
              {example.source_filenames[index] ?? id}
              <ArrowUpRight size={14} />
            </button>
          ))}
        </div>
        {example.caveats && (
          <div className="example-caveats">
            <h3>Declared caveats</h3>
            <p>{example.caveats}</p>
          </div>
        )}
        {reserved ? (
          <div className="reserved-example-notice">
            <LockKeyhole size={23} />
            <div>
              <h3>Target reserved for evaluation</h3>
              <p>
                Its extracted regions and observations are hidden. Revealing the
                target makes this example development evidence; it can no longer
                be described as an untouched reserved case.
              </p>
              {editable && (
                <button className="button secondary small" onClick={onReveal}>
                  Reveal for development
                  <ArrowRight size={14} />
                </button>
              )}
            </div>
          </div>
        ) : example.inspection ? (
          <>
            {example.inspection.issues.length > 0 && (
              <section className="example-inspection">
                <h3>Inspection issues</h3>
                {example.inspection.issues.map((issue, index) => (
                  <div className="notice warning" key={index}>
                    {pretty(issue)}
                  </div>
                ))}
              </section>
            )}
            <section className="example-inspection">
              <h3>
                Target regions <span>{example.inspection.regions.length}</span>
              </h3>
              {example.inspection.regions.length ? (
                example.inspection.regions.map((region, index) => (
                  <details className="technical-details" key={index}>
                    <summary>
                      Region {index + 1}
                      {region && typeof region === "object" && "kind" in region
                        ? ` · ${String(region.kind)}`
                        : ""}
                    </summary>
                    <pre>{pretty(region)}</pre>
                  </details>
                ))
              ) : (
                <p className="muted-small">
                  No regions were extracted from this target.
                </p>
              )}
            </section>
            <section className="example-inspection">
              <h3>Independent observations</h3>
              {example.inspection.observations.length ? (
                <pre className="inspection-observations">
                  {pretty(example.inspection.observations)}
                </pre>
              ) : (
                <p className="muted-small">
                  No independently extracted observations were recorded.
                </p>
              )}
            </section>
          </>
        ) : (
          <p className="muted-small">
            This example has no inspection result yet.
          </p>
        )}
        <details className="technical-details">
          <summary>Example identity</summary>
          <dl>
            <KeyValue label="Example ID" mono>
              {example.id}
            </KeyValue>
            <KeyValue label="Digest" mono>
              {example.digest}
            </KeyValue>
          </dl>
        </details>
      </div>
      <footer className="modal-footer">
        <button className="button secondary" onClick={onClose}>
          Close
        </button>
      </footer>
    </Modal>
  );
}

export function LearningPanel({
  program,
  assets,
  model,
  editable,
  busyElsewhere,
  job,
  onJob,
  onCancel,
  onRefresh,
  onSource,
}: {
  program: Program;
  assets: Asset[];
  model: ModelStatus | undefined;
  editable: boolean;
  busyElsewhere: boolean;
  job: Job | null;
  onJob: (job: Job) => void;
  onCancel: () => void;
  onRefresh: () => Promise<void>;
  onSource: (id: string) => void;
}) {
  const [examples, setExamples] = useState<HistoricalExample[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [requirements, setRequirements] = useState(
    program.learning?.requirements ?? "",
  );
  const [engine, setEngine] = useState<"deterministic" | "openai">(
    "deterministic",
  );
  const [starting, setStarting] = useState(false);
  const [inspectBusy, setInspectBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [modal, setModal] = useState<
    | { kind: "add" }
    | { kind: "example"; example: HistoricalExample }
    | { kind: "reveal"; example: HistoricalExample }
    | { kind: "coverage"; coverage: LearningCoverage }
    | null
  >(null);
  const closeModal = useCallback(() => setModal(null), []);
  const learning = program.learning;
  const loadExamples = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api<
        HistoricalExample[] | { examples: HistoricalExample[] }
      >(`/report-types/${program.report_type_id}/examples`);
      setExamples(Array.isArray(result) ? result : result.examples);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setLoading(false);
    }
  }, [program.report_type_id]);
  useEffect(() => {
    void loadExamples();
  }, [loadExamples, learning?.corpus_digest]);
  useEffect(() => {
    setRequirements(program.learning?.requirements ?? "");
  }, [program.learning?.requirements]);
  const available = examples.filter(
    (example) =>
      (example.effective_role ?? example.corpus_role) !== "reserved" &&
      example.state !== "blocked",
  );
  const reserved = examples.filter(
    (example) => (example.effective_role ?? example.corpus_role) === "reserved",
  );
  const filtered = examples.filter((example) =>
    `${exampleLabel(example)} ${example.report_filename} ${example.source_filenames.join(" ")}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const active =
    starting ||
    busyElsewhere ||
    Boolean(job && ["queued", "running"].includes(job.status));
  async function inspect(id: string) {
    setInspectBusy(true);
    setError(null);
    try {
      setModal({
        kind: "example",
        example: await api<HistoricalExample>(`/examples/${id}`),
      });
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setInspectBusy(false);
    }
  }
  async function learn(event: React.FormEvent) {
    event.preventDefault();
    setStarting(true);
    setError(null);
    setNotice(null);
    try {
      onJob(
        await post<Job>(`/programs/${program.id}/learn`, {
          expected_digest: program.digest,
          idempotency_key: identifier(),
          requirements: requirements.trim(),
          engine,
        }),
      );
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setStarting(false);
    }
  }
  return (
    <section
      className="program-section learning-panel"
      aria-labelledby={`learning-heading-${program.id}`}
    >
      <div className="section-heading">
        <div>
          <h2 id={`learning-heading-${program.id}`}>Examples &amp; learning</h2>
          <p>
            Historical evidence and explicit requirements for this report type.
          </p>
        </div>
        {editable && (
          <button
            className="button secondary small"
            disabled={active}
            onClick={() => setModal({ kind: "add" })}
          >
            <Plus size={15} />
            Add example
          </button>
        )}
      </div>
      {error && (
        <ErrorNotice message={error} onRetry={() => void loadExamples()} />
      )}
      {notice && (
        <div className="program-success" role="status">
          <CheckCircle2 size={17} />
          {notice}
        </div>
      )}
      {loading ? (
        <Spinner label="Loading historical examples…" />
      ) : (
        <>
          <div className="example-library-summary">
            <span>
              <strong>{available.length}</strong> available to learning
            </span>
            <span>
              <strong>{reserved.length}</strong> reserved
            </span>
            {learning && (
              <span>
                <strong>{learning.example_ids.length}</strong> used by this
                version
              </span>
            )}
          </div>
          {examples.length > 3 && (
            <label className="search-field example-search">
              <Search size={15} />
              <input
                aria-label="Search historical examples"
                placeholder="Find an example…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
          )}
          {filtered.length ? (
            <div className="example-list">
              {filtered.map((example) => (
                <div className="example-row" key={example.id}>
                  <span className="example-file-symbol">
                    {(example.effective_role ?? example.corpus_role) ===
                    "reserved" ? (
                      <LockKeyhole size={19} />
                    ) : (
                      <BookOpen size={19} />
                    )}
                  </span>
                  <div className="example-row-main">
                    <strong>{exampleLabel(example)}</strong>
                    <span>{example.report_filename}</span>
                    <small>{example.source_filenames.join(" · ")}</small>
                    <div>
                      <Badge status={example.state} />
                      <span className="muted-small">
                        {roleLabel(
                          example.effective_role ?? example.corpus_role,
                        )}
                      </span>
                      {learning?.example_ids.includes(example.id) && (
                        <span className="example-used">
                          Used by this version
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    className="small-text-button"
                    disabled={inspectBusy}
                    onClick={() => void inspect(example.id)}
                  >
                    Inspect
                    <ArrowUpRight size={14} />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="example-empty">
              <BookOpen size={25} />
              <h3>
                {query
                  ? "No matching examples"
                  : "Start with an approved historical report"}
              </h3>
              <p>
                {query
                  ? "Try another report name or source filename."
                  : "Pair the report with its source data to compare plausible policies and account for every target region."}
              </p>
            </div>
          )}
        </>
      )}
      {editable ? (
        <form className="learning-form" onSubmit={learn}>
          <label className="field">
            Explicit reporting requirements
            <span className="field-help">
              These instructions take precedence over inferred conventions.
            </span>
            <textarea
              value={requirements}
              onChange={(event) => setRequirements(event.target.value)}
              rows={4}
              maxLength={4000}
              disabled={active}
              placeholder="Describe mandatory content, selection rules, known exceptions, and the intended audience."
            />
          </label>
          <label className="field">
            Learning engine
            <select
              value={engine}
              onChange={(event) =>
                setEngine(event.target.value as "deterministic" | "openai")
              }
              disabled={active}
            >
              <option value="deterministic">
                Deterministic — compare supported policies
              </option>
              <option value="openai" disabled={!model?.configured}>
                OpenAI assisted{!model?.configured ? " — not configured" : ""}
              </option>
            </select>
          </label>
          <p className="learning-method-note">
            {engine === "deterministic"
              ? "Compares the supported revenue-selection policies against supplied historical observations. It retains every hypothesis that the evidence supports."
              : "Uses the configured model to assist analysis of supplied examples. Candidate evidence, coverage review, and independent evaluation still govern publication."}
          </p>
          {(!model?.configured || engine === "openai") && (
            <ModelConfiguration model={model} />
          )}
          <div className="learning-submit">
            <span className="muted-small">
              Reserved targets are excluded. Learning updates this candidate and
              invalidates its earlier evaluation.
            </span>
            <button
              className="button primary"
              disabled={
                active ||
                loading ||
                !available.length ||
                (engine === "openai" && !model?.configured)
              }
            >
              {active ? (
                <Spinner label="Working…" />
              ) : (
                <>
                  <Play size={15} />
                  Learn from examples
                </>
              )}
            </button>
          </div>
        </form>
      ) : (
        <div className="learning-readonly">
          <LockKeyhole size={15} />
          <p>
            {learning
              ? "This release preserves its learned evidence and requirements. Create an update to learn from additional examples."
              : "This program has no recorded example-learning result. Its existing authored policy and checks are shown below."}
          </p>
        </div>
      )}
      {job && <JobProgress job={job} onCancel={onCancel} />}
      {learning && (
        <div className="learning-results">
          <div className="section-heading">
            <h3>Recorded learning result</h3>
            <Badge status="known">
              {learning.engine.startsWith("openai")
                ? "OpenAI assisted"
                : "Deterministic analysis"}
            </Badge>
          </div>
          {learning.requirements && (
            <details className="technical-details">
              <summary>Requirements used by this version</summary>
              <p className="learning-requirements-record">
                {learning.requirements}
              </p>
            </details>
          )}
          {learning.model_proposal && (
            <div className="notice info model-proposal">
              <Info size={18} />
              <div>
                <strong>AI policy proposal · awaiting human decision</strong>
                <p>
                  Suggested policy:{" "}
                  {learning.hypotheses.find(
                    (hypothesis) =>
                      hypothesis.value === learning.model_proposal?.selection,
                  )?.label ?? learning.model_proposal.selection}
                </p>
                <p>{learning.model_proposal.rationale}</p>
                {learning.model_proposal.unresolved_questions.length > 0 && (
                  <>
                    <strong>Unresolved questions</strong>
                    <ul>
                      {learning.model_proposal.unresolved_questions.map(
                        (question, index) => (
                          <li key={index}>{question}</li>
                        ),
                      )}
                    </ul>
                  </>
                )}
                <p>
                  Review the evidence and explicitly resolve the policy decision
                  below. This proposal does not approve a policy.
                </p>
                {learning.model_receipt && (
                  <details className="technical-details">
                    <summary>Model execution receipt</summary>
                    <pre>{pretty(learning.model_receipt)}</pre>
                  </details>
                )}
              </div>
            </div>
          )}
          <h3 className="learning-subheading">Competing policy hypotheses</h3>
          <p className="muted-small">
            Agreement with supplied examples is evidence, not proof of
            generalization. Resolve any remaining policy ambiguity below.
          </p>
          <div className="hypothesis-list">
            {learning.hypotheses.map((hypothesis) => (
              <details className="hypothesis" key={hypothesis.value}>
                <summary>
                  <span>{hypothesis.label}</span>
                  <Badge status={hypothesis.supported ? "known" : "blocked"}>
                    {hypothesis.supported
                      ? "Supported by examples"
                      : "Not supported by examples"}
                  </Badge>
                  <small>
                    {hypothesis.checks.filter((check) => check.passed).length} /{" "}
                    {hypothesis.checks.length} checks
                  </small>
                </summary>
                <div className="table-scroll">
                  <table className="data-table hypothesis-checks">
                    <thead>
                      <tr>
                        <th>Example</th>
                        <th>Observed target</th>
                        <th>Policy result</th>
                        <th>Outcome</th>
                      </tr>
                    </thead>
                    <tbody>
                      {hypothesis.checks.map((check, index) => (
                        <tr key={index}>
                          <td>
                            {examples.find(
                              (example) => example.id === check.example_id,
                            )?.period.label ?? check.example_id}
                            <details className="technical-details">
                              <summary>Source location</summary>
                              <pre>{pretty(check.locator)}</pre>
                            </details>
                          </td>
                          <td>
                            <pre>{pretty(check.expected)}</pre>
                          </td>
                          <td>
                            <pre>{pretty(check.actual)}</pre>
                          </td>
                          <td>
                            {check.passed ? (
                              <CheckCircle2 size={17} aria-label="Passed" />
                            ) : (
                              <XCircle size={17} aria-label="Failed" />
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            ))}
          </div>
          <div className="section-heading learning-subheading">
            <h3>Historical target coverage</h3>
            <span className="muted-small">
              {
                learning.coverage.filter(
                  (row) => row.status === "needs_decision",
                ).length
              }{" "}
              regions need review
            </span>
          </div>
          <div className="learning-coverage">
            {learning.coverage.map((row) => (
              <article key={row.id} className="learning-coverage-row">
                <div className="coverage-row-heading">
                  <strong>{row.region_id}</strong>
                  <span>{row.kind}</span>
                  <Badge status={row.status}>
                    {row.status.replaceAll("_", " ")}
                  </Badge>
                </div>
                <p className="coverage-excerpt">
                  {row.text || "No text extracted from this region."}
                </p>
                <div className="coverage-row-context">
                  <span>
                    {examples.find((example) => example.id === row.example_id)
                      ?.period.label ?? row.example_id}
                  </span>
                  {row.component_id && (
                    <span>Component: {row.component_id}</span>
                  )}
                </div>
                {row.reason && <p className="coverage-reason">{row.reason}</p>}
                <details className="technical-details">
                  <summary>Original target location</summary>
                  <pre>{pretty(row.locator)}</pre>
                </details>
                {editable && row.status === "needs_decision" && (
                  <button
                    className="small-text-button"
                    disabled={active}
                    onClick={() =>
                      setModal({ kind: "coverage", coverage: row })
                    }
                  >
                    Exclude this region from scope
                    <ArrowRight size={14} />
                  </button>
                )}
              </article>
            ))}
          </div>
          {learning.assumptions.length > 0 && (
            <div className="learning-notes">
              <h3>Assumptions</h3>
              <ul>
                {learning.assumptions.map((item, index) => (
                  <li key={index}>{pretty(item)}</li>
                ))}
              </ul>
            </div>
          )}
          {learning.limitations.length > 0 && (
            <div className="learning-notes">
              <h3>Evidence limitations</h3>
              <ul>
                {learning.limitations.map((item, index) => (
                  <li key={index}>{pretty(item)}</li>
                ))}
              </ul>
            </div>
          )}
          <details className="technical-details">
            <summary>Learning corpus identity</summary>
            <dl>
              <KeyValue label="Corpus digest" mono>
                {learning.corpus_digest}
              </KeyValue>
              <KeyValue label="Bound examples">
                {learning.example_ids.join(", ")}
              </KeyValue>
            </dl>
          </details>
        </div>
      )}
      {modal?.kind === "add" && (
        <AddExampleDialog
          reportTypeId={program.report_type_id}
          assets={assets}
          onClose={closeModal}
          onSaved={async () => {
            await loadExamples();
            await onRefresh();
            setNotice(
              "Historical example added. Run learning to incorporate it into this candidate.",
            );
          }}
        />
      )}
      {modal?.kind === "example" && (
        <ExampleDetails
          example={modal.example}
          onClose={closeModal}
          onSource={onSource}
          editable={editable && !active}
          onReveal={() => setModal({ kind: "reveal", example: modal.example })}
        />
      )}
      {modal?.kind === "reveal" && (
        <ReasonDialog
          title="Reveal this reserved target"
          eyebrow="EXPOSURE DECISION"
          explanation="Revealing the target permanently promotes this example to development evidence. Its observations become available to learning, and the exposure is recorded. This cannot restore an untouched reserved case later."
          actionLabel="Reveal for development"
          onClose={closeModal}
          submit={async (reason) => {
            await post(`/examples/${modal.example.id}/reveal`, { reason });
            await loadExamples();
            await onRefresh();
            setNotice("Target revealed and promoted to development evidence.");
          }}
        />
      )}
      {modal?.kind === "coverage" && (
        <ReasonDialog
          title="Exclude this target region"
          eyebrow="EXPLICIT SCOPE DECISION"
          explanation={`Exclude “${modal.coverage.region_id}” only if it is intentionally outside this program’s supported output. It will not become implemented content. Record why this omission is acceptable for future reports.`}
          actionLabel="Record scope exclusion"
          onClose={closeModal}
          submit={async (reason) => {
            await post(`/programs/${program.id}/coverage`, {
              expected_digest: program.digest,
              coverage_id: modal.coverage.id,
              disposition: "out_of_scope",
              reason,
            });
            await onRefresh();
            setNotice(
              "Scope exclusion recorded. Evaluate the updated candidate before publication.",
            );
          }}
        />
      )}
    </section>
  );
}
