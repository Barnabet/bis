import { useCallback, useState } from "react";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Clock3,
  Database,
  GitBranch,
  History,
  Info,
  Play,
  Plus,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react";
import type { Program, ReportType } from "./types";
import { programLifecycle } from "./types";
import { messageOf, post } from "./api";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  KeyValue,
  Modal,
  pretty,
  shortDate,
  Spinner,
} from "./ui";

type LifecycleAction = { kind: "candidates" | "discard"; program: Program };

function ProgramActionDialog({
  action,
  onClose,
  onComplete,
}: {
  action: LifecycleAction;
  onClose: () => void;
  onComplete: (program: Program, message: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const creating = action.kind === "candidates";
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await post<Program>(
        `/programs/${action.program.id}/${action.kind}`,
        {
          expected_digest: action.program.digest,
          reason: reason.trim(),
        },
      );
      await onComplete(
        result,
        creating
          ? `Candidate v${result.version} created. Review its inherited policy decisions.`
          : `Candidate v${result.version} discarded and retained in history.`,
      );
      onClose();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={creating ? "Prepare a program update" : "Discard this candidate"}
      eyebrow={`${creating ? "SUCCESSOR TO" : "CANDIDATE"} V${action.program.version}`}
      onClose={onClose}
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          <p className="dialog-intro">
            {creating
              ? "Create a separate candidate from this active release. The release stays active while you review decisions and evaluate the update."
              : "This candidate will leave the review workflow and remain in version history. Its active release and earlier report snapshots are preserved."}
          </p>
          <label className="field">
            {creating ? "Reason for this update" : "Reason for discarding"}
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={4}
              maxLength={1000}
              placeholder={
                creating
                  ? "Describe the change this version should address."
                  : "Explain why this candidate is no longer needed."
              }
              required
              disabled={busy}
            />
          </label>
          {creating && (
            <div className="notice info">
              <Info size={17} />
              <p>
                Prior decisions are kept as context. Each choice must be
                reviewed again, and the candidate needs a fresh passing
                evaluation before publication.
              </p>
            </div>
          )}
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
            className={`button ${creating ? "primary" : "danger"}`}
            disabled={busy || !reason.trim()}
          >
            {busy ? (
              <Spinner label={creating ? "Creating…" : "Discarding…"} />
            ) : creating ? (
              <>
                <Plus size={15} />
                Create candidate
              </>
            ) : (
              <>
                <Trash2 size={15} />
                Discard candidate
              </>
            )}
          </button>
        </footer>
      </form>
    </Modal>
  );
}

const lifecycleLabel = (status: string) =>
  ({
    active: "Active release",
    candidate: "Candidate",
    historical: "Historical release",
    discarded: "Discarded candidate",
  })[status] ?? status;

export function ProgramsPage({
  programs,
  reportTypes,
  onRefresh,
}: {
  programs: Program[];
  reportTypes: ReportType[];
  onRefresh: () => Promise<void>;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [action, setAction] = useState<LifecycleAction | null>(null);
  const closeAction = useCallback(() => setAction(null), []);
  const activePrograms = programs.filter(
    (p) => programLifecycle(p, reportTypes) === "active",
  );
  const candidates = programs.filter(
    (p) => programLifecycle(p, reportTypes) === "candidate",
  );
  const history = programs.filter((p) =>
    ["historical", "discarded"].includes(programLifecycle(p, reportTypes)),
  );
  const program =
    programs.find((p) => p.id === selected) ??
    activePrograms[0] ??
    candidates[0] ??
    history[0];
  const lifecycle = program ? programLifecycle(program, reportTypes) : "";
  const candidate = lifecycle === "candidate";
  const active = lifecycle === "active";
  const readOnly = lifecycle === "historical" || lifecycle === "discarded";
  const restartRequired = program?.runtime_status === "restart_required";
  const codeChanged = program?.runtime_status === "code_changed";
  const canReview = candidate && !restartRequired && !codeChanged;
  const existingCandidate = candidates.find(
    (p) => p.report_type_id === program?.report_type_id,
  );
  const parent = programs.find(
    (p) => p.id === program?.lineage?.parent_program_id,
  );
  const activeRelease = activePrograms.find(
    (p) => p.report_type_id === program?.report_type_id,
  );
  const evaluationCurrent = Boolean(
    program?.evaluation && program.evaluation.digest === program.digest,
  );
  const change = program?.change_summary;
  function selectProgram(id: string) {
    setSelected(id);
    setError(null);
    setSuccess(null);
  }
  async function complete(result: Program, message: string) {
    await onRefresh();
    setSelected(result.id);
    setSuccess(message);
    setError(null);
  }
  async function act(
    name: "evaluate" | "publish" | "decisions",
    extra: Record<string, unknown> = {},
  ) {
    if (!program || !canReview) return;
    setBusy(name);
    setError(null);
    setSuccess(null);
    try {
      const result = await post<Program>(`/programs/${program.id}/${name}`, {
        expected_digest: program.digest,
        ...extra,
      });
      await complete(
        result,
        name === "publish"
          ? `Version ${result.version} is now active for new runs. Earlier report snapshots keep their original release.`
          : name === "evaluate"
            ? "Evaluation recorded for this candidate."
            : "Policy decision recorded. Run a fresh evaluation before publication.",
      );
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(null);
    }
  }
  function programButtons(items: Program[]) {
    return (
      <div className="program-selector" aria-label="Choose a program version">
        {items.map((item) => (
          <button
            type="button"
            aria-pressed={program?.id === item.id}
            className={program?.id === item.id ? "active" : ""}
            key={item.id}
            disabled={Boolean(busy)}
            onClick={() => selectProgram(item.id)}
          >
            <GitBranch size={15} />
            <span>
              {item.name ?? "Revenue program"}
              <strong>v{item.version}</strong>
            </span>
            <Badge
              status={
                programLifecycle(item, reportTypes) === "active"
                  ? "published"
                  : programLifecycle(item, reportTypes)
              }
            >
              {lifecycleLabel(programLifecycle(item, reportTypes))}
            </Badge>
          </button>
        ))}
      </div>
    );
  }
  return (
    <div className="library-page programs-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">REPEATABLE BY DESIGN</span>
          <h1>Programs</h1>
          <p>
            The active policy, its next version, and the decisions behind both.
          </p>
        </div>
      </div>
      {!program ? (
        <EmptyState
          icon={<GitBranch size={28} />}
          title="No programs yet"
          text="Create a report type to begin with a candidate reporting program."
        />
      ) : (
        <>
          <div className="program-version-navigation">
            {activePrograms.length > 0 && (
              <section aria-label="Active releases">
                <h2>Active releases</h2>
                {programButtons(activePrograms)}
              </section>
            )}
            {candidates.length > 0 && (
              <section aria-label="Candidates in review">
                <h2>Candidates in review</h2>
                {programButtons(candidates)}
              </section>
            )}
            {history.length > 0 && (
              <details
                className="technical-details program-history"
                open={readOnly || undefined}
              >
                <summary>
                  <History size={15} />
                  Version history <span>({history.length})</span>
                </summary>
                {programButtons(history)}
              </details>
            )}
          </div>
          {error && (
            <ErrorNotice
              message={error}
              onRetry={() =>
                void onRefresh().catch((err) => setError(messageOf(err)))
              }
            />
          )}
          {success && (
            <div className="program-success" role="status">
              <CheckCircle2 size={17} />
              <span>{success}</span>
            </div>
          )}
          <div className="program-banner">
            <div>
              <div className="program-release-label">
                <span className="eyebrow">
                  REPORTING PROGRAM · V{program.version}
                </span>
                <Badge status={active ? "published" : lifecycle}>
                  {lifecycleLabel(lifecycle)}
                </Badge>
              </div>
              <h2>{program.name}</h2>
              <p>
                {active
                  ? "New report runs use this release. Every snapshot keeps the exact version that produced it."
                  : candidate
                    ? "Review the policy decisions, evaluate this candidate, then publish it as the active release."
                    : lifecycle === "discarded"
                      ? "This candidate was discarded. Its recorded policy and evidence remain available for inspection."
                      : "This release has been superseded. Its report snapshots and recorded review remain available."}
              </p>
            </div>
            <div className="program-actions">
              {active &&
                (existingCandidate ? (
                  <button
                    className="button primary"
                    onClick={() => selectProgram(existingCandidate.id)}
                  >
                    <GitBranch size={15} />
                    Open candidate v{existingCandidate.version}
                  </button>
                ) : (
                  <button
                    className="button primary"
                    disabled={Boolean(busy) || restartRequired}
                    onClick={() => setAction({ kind: "candidates", program })}
                  >
                    <Plus size={15} />
                    Create update
                  </button>
                ))}
              {candidate && (
                <>
                  <button
                    className="button secondary"
                    disabled={Boolean(busy) || !canReview}
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
                  <button
                    className="button primary"
                    disabled={
                      Boolean(busy) ||
                      !canReview ||
                      !evaluationCurrent ||
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
                  {program.lineage?.parent_program_id && (
                    <button
                      className="small-text-button discard-program"
                      disabled={Boolean(busy) || restartRequired}
                      onClick={() => setAction({ kind: "discard", program })}
                    >
                      <Trash2 size={14} />
                      Discard candidate
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
          {!readOnly && restartRequired && (
            <div className="notice warning">
              <Info size={18} />
              <p>
                The local application changed while this service was running.
                Restart Report Foundry before creating, reviewing, or publishing
                a program update. Existing snapshots and exports remain
                available.
              </p>
            </div>
          )}
          {!readOnly && !restartRequired && codeChanged && (
            <div className="notice warning">
              <GitBranch size={18} />
              <p>
                {active
                  ? "The installed runtime differs from this frozen release. Create and review a program update before starting another report run."
                  : program.lineage?.parent_program_id
                    ? "The installed runtime differs from this candidate. Discard it and create a new update from the active release before reviewing it."
                    : "The installed runtime differs from this initial candidate. Restore its matching application version before continuing review."}
              </p>
            </div>
          )}
          {candidate && activeRelease && (
            <div className="program-active-note">
              <ShieldCheck size={16} />
              <span>
                Active release:{" "}
                <button
                  className="small-text-button"
                  onClick={() => selectProgram(activeRelease.id)}
                >
                  v{activeRelease.version}
                </button>
                . This candidate becomes active only after publication.
              </span>
            </div>
          )}
          {program.lineage && (
            <section className="program-section program-lineage">
              <div className="section-heading">
                <h2>What this version updates</h2>
                <GitBranch size={17} />
              </div>
              <div className="lineage-version">
                <span>{parent ? `v${parent.version}` : "Parent release"}</span>
                <ArrowRight size={16} />
                <strong>v{program.version}</strong>
              </div>
              <p className="update-reason">{program.lineage.reason}</p>
              {parent && (
                <button
                  className="small-text-button"
                  onClick={() => selectProgram(parent.id)}
                >
                  Inspect parent release <ArrowRight size={14} />
                </button>
              )}
              {change && (
                <>
                  <div className="change-summary">
                    <span>
                      <strong>{change.added_files.length}</strong> files added
                    </span>
                    <span>
                      <strong>{change.changed_files.length}</strong> files
                      changed
                    </span>
                    <span>
                      <strong>{change.removed_files.length}</strong> files
                      removed
                    </span>
                  </div>
                  <p className="muted-small">
                    {change.python_changed
                      ? "Python version changed. "
                      : "Python version unchanged. "}
                    {change.policy_changed
                      ? "Reporting policy changed. "
                      : "Reporting policy unchanged. "}
                    {change.decision_review_required
                      ? "Policy choices require fresh review."
                      : "Policy review requirements are recorded below."}
                  </p>
                  {[
                    ...change.added_files,
                    ...change.changed_files,
                    ...change.removed_files,
                  ].length > 0 && (
                    <details className="technical-details">
                      <summary>Changed package files</summary>
                      <ul className="changed-file-list">
                        {(
                          [
                            ["Added", change.added_files],
                            ["Changed", change.changed_files],
                            ["Removed", change.removed_files],
                          ] as const
                        ).flatMap(([label, files]) =>
                          files.map((file) => (
                            <li key={`${label}:${file}`}>
                              <span>{label}</span>
                              <code>{file}</code>
                            </li>
                          )),
                        )}
                      </ul>
                    </details>
                  )}
                </>
              )}
              <details className="technical-details">
                <summary>Parent release identity</summary>
                <dl>
                  <KeyValue label="Program ID" mono>
                    {program.lineage.parent_program_id}
                  </KeyValue>
                  <KeyValue label="Frozen digest" mono>
                    {program.lineage.parent_program_digest}
                  </KeyValue>
                </dl>
              </details>
            </section>
          )}
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
                      !evaluationCurrent
                        ? "review_required"
                        : program.evaluation.passed
                          ? "verified"
                          : "blocked"
                    }
                  >
                    {!evaluationCurrent
                      ? "Out of date"
                      : program.evaluation.passed
                        ? "Passed"
                        : "Needs repair"}
                  </Badge>
                )}
              </div>
              {program.evaluation ? (
                <>
                  <p className="muted-small">
                    Recorded {shortDate(program.evaluation.created_at)}
                    {evaluationCurrent
                      ? " against this program digest."
                      : ". The program has changed since this evaluation."}
                  </p>
                  <div className="evaluation-list">
                    {program.evaluation.checks.map((check, index) => (
                      <div key={index}>
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
                  <h3>
                    {candidate
                      ? "Fresh evaluation required"
                      : "No evaluation recorded"}
                  </h3>
                  <p>
                    {candidate
                      ? "This version needs its own independent checks before it can become active."
                      : "This version has no recorded evaluation results."}
                  </p>
                </div>
              )}
            </section>
          </div>
          <section className="program-section decisions-section">
            <div className="section-heading">
              <h2>Policy decisions</h2>
              <span className="muted-small">Versioned, explicit choices</span>
            </div>
            {program.decisions.length ? (
              program.decisions.map((decision) => {
                const key = `${program.id}:${decision.id}`;
                const chosen = decisions[key] ?? decision.resolution;
                const prior = decision.alternatives.find(
                  (option) => option.value === decision.prior_resolution,
                );
                return (
                  <div className="decision" key={decision.id}>
                    <div className="decision-heading">
                      <h3>{decision.question}</h3>
                      <Badge
                        status={
                          decision.resolution ? "accepted" : "needs_decision"
                        }
                      >
                        {decision.resolution
                          ? "Resolved"
                          : decision.prior_resolution
                            ? "Review inherited choice"
                            : "Needs decision"}
                      </Badge>
                    </div>
                    {decision.prior_resolution && (
                      <div className="prior-decision">
                        <History size={15} />
                        <p>
                          Previous release chose{" "}
                          <strong>
                            {prior?.label ?? decision.prior_resolution}
                          </strong>
                          .
                          {candidate && !decision.resolution
                            ? " Choose and record the policy for this version."
                            : " This is retained as review context."}
                        </p>
                      </div>
                    )}
                    <div className="decision-alternatives">
                      {decision.alternatives.map((option) => (
                        <label
                          key={option.value}
                          className={chosen === option.value ? "selected" : ""}
                        >
                          <input
                            type="radio"
                            name={key}
                            value={option.value}
                            checked={chosen === option.value}
                            disabled={!canReview || Boolean(busy)}
                            onChange={() =>
                              setDecisions((previous) => ({
                                ...previous,
                                [key]: option.value,
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
                    {candidate && (
                      <button
                        className="button secondary small"
                        disabled={
                          Boolean(busy) ||
                          !canReview ||
                          !decisions[key] ||
                          decisions[key] === decision.resolution
                        }
                        onClick={() =>
                          void act("decisions", {
                            decision_id: decision.id,
                            resolution: decisions[key],
                          })
                        }
                      >
                        Record decision
                        <ArrowRight size={14} />
                      </button>
                    )}
                  </div>
                );
              })
            ) : (
              <p className="muted-small">
                No policy choices are recorded for this program.
              </p>
            )}
          </section>
          <section className="program-section">
            <h2>Declared scope</h2>
            <ul className="limitations">
              {program.limitations.map((limitation, index) => (
                <li key={index}>{limitation}</li>
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
                <KeyValue label="Lifecycle">
                  {lifecycleLabel(lifecycle)}
                </KeyValue>
                <KeyValue label="Runtime">
                  {program.runtime_status?.replaceAll("_", " ") ??
                    "Not reported"}
                </KeyValue>
              </dl>
            </details>
            {program.state === "published" &&
              program.package_artifact_digest && (
                <div className="program-package-download">
                  <a
                    className="small-text-button"
                    href={`/api/programs/${program.id}/package`}
                    download
                  >
                    Download source package <ArrowRight size={14} />
                  </a>
                  <p className="muted-small">
                    The frozen package is retained for evidence and restoration.
                    Downloading it does not change the installed runtime.
                  </p>
                </div>
              )}
          </section>
        </>
      )}
      {action && (
        <ProgramActionDialog
          action={action}
          onClose={closeAction}
          onComplete={complete}
        />
      )}
    </div>
  );
}
