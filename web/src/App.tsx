import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Database,
  FileText,
  GitBranch,
  Layers3,
  Link2,
  Menu,
  MoreHorizontal,
  Plus,
  Presentation,
  ShieldCheck,
  Table2,
  X,
} from "lucide-react";
import type {
  Asset,
  Bootstrap,
  ExportRecord,
  Job,
  ReportNode,
  Snapshot,
} from "./types";
import { activeProgramFor, canRunProgram } from "./types";
import { api, messageOf, post } from "./api";
import {
  AcceptDialog,
  CreateTypeDialog,
  ExportDialog,
  RevisionDialog,
  RunDialog,
} from "./Dialogs";
import {
  ProgramsPage,
  ReportsPage,
  SourceDetail,
  SourcesPage,
} from "./LibraryPages";
import {
  EvidencePanel,
  PresentationView,
  ReportDocument,
  WorkbookView,
} from "./ReportView";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  IconButton,
  Modal,
  Spinner,
} from "./ui";

type Page = "report" | "reports" | "sources" | "programs";
type Dialog =
  | {
      kind: "create" | "run" | "export" | "accept" | "help";
      reportTypeId?: string;
    }
  | { kind: "revision"; node: ReportNode }
  | null;
const emptyData: Bootstrap = {
  report_types: [],
  snapshots: [],
  assets: [],
  programs: [],
  jobs: [],
  capabilities: {},
};
function readRoute(): { page: Page; id: string | null } {
  const parts = window.location.hash.replace(/^#\/?/, "").split("/");
  return {
    page:
      parts[0] === "reports" && parts[1]
        ? "report"
        : ["reports", "sources", "programs"].includes(parts[0])
          ? (parts[0] as Page)
          : "report",
    id: parts[0] === "reports" ? (parts[1] ?? null) : null,
  };
}

export default function App() {
  const initial = useRef(readRoute());
  const [data, setData] = useState<Bootstrap>(emptyData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<Page>(initial.current.page);
  const [snapshotId, setSnapshotId] = useState<string | null>(
    initial.current.id,
  );
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [view, setView] = useState("document");
  const [evidence, setEvidence] = useState(window.innerWidth > 1100);
  const [fact, setFact] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [source, setSource] = useState<Asset | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const [mobileNav, setMobileNav] = useState(false);
  const completedJobs = useRef(new Set<string>());
  const initialized = useRef(false);
  const notify = useCallback((message: string) => setToast(message), []);
  const navigate = useCallback((target: Page, id?: string) => {
    window.location.hash =
      target === "report" && id ? `/reports/${id}` : `/${target}`;
    setPage(target);
    if (id) setSnapshotId(id);
    setMobileNav(false);
  }, []);
  const refresh = useCallback(async () => {
    const next = await api<Bootstrap>("/bootstrap");
    setData(next);
    if (!initialized.current) {
      initialized.current = true;
      if (!initial.current.id && initial.current.page === "report") {
        const latest = [...next.snapshots].sort(
          (a, b) =>
            b.created_at.localeCompare(a.created_at) || b.revision - a.revision,
        )[0];
        if (latest) navigate("report", latest.id);
        else navigate("reports");
      }
    }
  }, [navigate]);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await refresh();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setLoading(false);
    }
  }, [refresh]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    const listener = () => {
      const next = readRoute();
      setPage(next.page);
      if (next.id) setSnapshotId(next.id);
    };
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);
  const loadSnapshot = useCallback(async (id: string) => {
    setSnapshotLoading(true);
    setSnapshotError(null);
    try {
      const result = await api<Snapshot>(`/report-snapshots/${id}`);
      setSnapshot(result);
      setFact(null);
    } catch (err) {
      setSnapshotError(messageOf(err));
    } finally {
      setSnapshotLoading(false);
    }
  }, []);
  useEffect(() => {
    if (snapshotId) void loadSnapshot(snapshotId);
  }, [snapshotId, loadSnapshot]);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 5500);
    return () => window.clearTimeout(timer);
  }, [toast]);
  const refreshExports = useCallback(async (id: string) => {
    try {
      setExports(
        await api<ExportRecord[]>(
          `/exports?snapshot_id=${encodeURIComponent(id)}`,
        ),
      );
    } catch (err) {
      setJobError(messageOf(err));
    }
  }, []);
  useEffect(() => {
    if (snapshot?.id) void refreshExports(snapshot.id);
  }, [snapshot?.id, refreshExports]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    let disposed = false;
    let timer: number;
    async function poll() {
      try {
        const next = await api<Job>(`/jobs/${job!.id}`);
        if (disposed) return;
        setJob(next);
        setJobError(null);
        if (["queued", "running"].includes(next.status))
          timer = window.setTimeout(() => void poll(), 900);
      } catch (err) {
        if (!disposed) {
          setJobError(messageOf(err));
          timer = window.setTimeout(() => void poll(), 2500);
        }
      }
    }
    timer = window.setTimeout(() => void poll(), 450);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [job?.id, job?.status]);
  useEffect(() => {
    if (
      !job ||
      !["completed", "failed", "blocked", "cancelled"].includes(job.status) ||
      completedJobs.current.has(job.id)
    )
      return;
    completedJobs.current.add(job.id);
    void refresh().catch((err) => setError(messageOf(err)));
    if (job.status === "completed") {
      const id = String(job.result?.snapshot_id ?? job.snapshot_id ?? "");
      if (id) {
        navigate("report", id);
        setDialog((current) => (current?.kind === "run" ? null : current));
        notify("Report generated. Your new snapshot is ready.");
      } else {
        if (snapshot?.id) void refreshExports(snapshot.id);
        notify("Export ready. Download it from the export dialog.");
      }
    } else if (job.status === "cancelled") notify("Job cancelled.");
  }, [job, navigate, notify, refresh, snapshot?.id, refreshExports]);
  const closeDialog = useCallback(() => setDialog(null), []);
  const closeSource = useCallback(() => setSource(null), []);
  const beginRun = useCallback(
    (reportTypeId?: string) => {
      if (job && ["queued", "running"].includes(job.status)) {
        notify(
          "A job is already running. Its progress is shown at the top of your workspace.",
        );
        return;
      }
      setJob(null);
      setJobError(null);
      setDialog({ kind: "run", reportTypeId });
    },
    [job, notify],
  );
  const beginExport = () => {
    if (
      job?.kind !== "export" ||
      !["queued", "running", "completed"].includes(job.status)
    )
      setJob(null);
    setJobError(null);
    setDialog({ kind: "export" });
  };
  const openSource = async (id: string) => {
    setSourceLoading(true);
    try {
      setSource(await api<Asset>(`/assets/${id}`));
    } catch (err) {
      notify(messageOf(err));
    } finally {
      setSourceLoading(false);
    }
  };
  const saveSnapshot = (result: Snapshot) => {
    setSnapshot(result);
    navigate("report", result.id);
    void refresh().catch((err) => setError(messageOf(err)));
    notify(
      result.status === "accepted"
        ? "Report accepted. A new revision records your review."
        : `Revision ${result.revision} saved.`,
    );
  };
  const selectFact = (id: string) => {
    setFact(id || null);
    setEvidence(true);
  };
  const cancelJob = async () => {
    if (!job) return;
    try {
      setJob(await post<Job>(`/jobs/${job.id}/cancel`, {}));
    } catch (err) {
      setJobError(messageOf(err));
    }
  };
  const activeJob = job && ["queued", "running"].includes(job.status);
  const shared = snapshot
    ? { snapshot, onFact: selectFact, selectedFact: fact }
    : null;
  const activeProgram = activeProgramFor(
    data.report_types.find((type) => type.id === snapshot?.report_type_id),
    data.programs,
  );
  const published = canRunProgram(activeProgram);

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      {mobileNav && (
        <div className="sidebar-scrim" onClick={() => setMobileNav(false)} />
      )}
      <aside className={`sidebar${mobileNav ? " mobile-open" : ""}`}>
        <button
          className="brand"
          onClick={() => navigate("reports")}
          aria-label="Report Foundry home"
        >
          <span className="brand-mark">
            <i />
            <i />
            <i />
          </span>
          <span>
            report<span>foundry</span>
          </span>
        </button>
        <div className="workspace-switch">
          <span className="workspace-avatar">W</span>
          <div>
            My workspace<small>Local edition</small>
          </div>
          <ChevronDown size={13} />
        </div>
        <span className="nav-label">WORKSPACE</span>
        <nav aria-label="Main navigation">
          {[
            { id: "reports" as const, icon: FileText, label: "Reports" },
            { id: "sources" as const, icon: Database, label: "Sources" },
            { id: "programs" as const, icon: GitBranch, label: "Programs" },
          ].map((item) => (
            <button
              className={
                page === item.id || (page === "report" && item.id === "reports")
                  ? "active"
                  : ""
              }
              key={item.id}
              onClick={() => navigate(item.id)}
            >
              <item.icon size={18} strokeWidth={1.6} />
              <span>{item.label}</span>
              {item.id === "reports" && data.snapshots.length > 0 && (
                <span className="nav-count">
                  {new Set(data.snapshots.map((s) => s.report_type_id)).size}
                </span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-recent">
          <div className="nav-label">
            RECENT REPORTS
            <button
              title="New report type"
              aria-label="Create report type"
              onClick={() => setDialog({ kind: "create" })}
            >
              <Plus size={14} />
            </button>
          </div>
          {Object.values(
            data.snapshots.reduce<
              Record<string, (typeof data.snapshots)[number]>
            >((acc, item) => {
              if (
                !acc[item.report_type_id] ||
                acc[item.report_type_id].created_at < item.created_at
              )
                acc[item.report_type_id] = item;
              return acc;
            }, {}),
          )
            .slice(0, 4)
            .map((report) => (
              <button
                className={
                  snapshot?.report_type_id === report.report_type_id &&
                  page === "report"
                    ? "selected"
                    : ""
                }
                key={report.id}
                onClick={() => navigate("report", report.id)}
              >
                <span className="recent-dot" />
                <span>{report.title}</span>
              </button>
            ))}
        </div>
        <div className="sidebar-bottom">
          <div className="workspace-note">
            <span className="note-symbol">
              <Layers3 size={20} strokeWidth={1.5} />
            </span>
            <strong>One report. Every format.</strong>
            <p>Connected facts, from your source to your final document.</p>
          </div>
          <button
            className="sidebar-help"
            onClick={() => setDialog({ kind: "help" })}
          >
            <CircleHelp size={17} />
            About this workspace
            <ArrowRight size={14} />
          </button>
          <div className="sidebar-profile">
            <span className="profile-avatar">L</span>
            <div>
              Local workspace
              <small>
                <i />
                Files stay on this machine
              </small>
            </div>
            <MoreHorizontal size={17} />
          </div>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="app-topbar">
          <div className="breadcrumb">
            <button
              className="mobile-menu icon-button"
              onClick={() => setMobileNav(true)}
              aria-label="Open navigation"
            >
              <Menu size={19} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <button
              onClick={() => navigate(page === "report" ? "reports" : page)}
            >
              {page === "report"
                ? "Reports"
                : page.charAt(0).toUpperCase() + page.slice(1)}
            </button>
            {page === "report" && snapshot && (
              <>
                <ChevronRight size={13} />
                <strong>{snapshot.period.label}</strong>
              </>
            )}
          </div>
          <div className="topbar-right">
            {data.demo && (
              <span className="demo-label">
                <span />
                Synthetic demo
              </span>
            )}
            <span className="topbar-divider" />
            <span className="workspace-status">LOCAL WORKSPACE</span>
          </div>
        </header>
        {activeJob && (
          <div className="background-job">
            <Spinner label={(job.stage ?? job.status).replaceAll("_", " ")} />
            <span>
              {job.kind === "export"
                ? "Preparing your export"
                : "Preparing a report snapshot"}
            </span>
            <button
              className="text-button"
              onClick={() =>
                setDialog({ kind: job.kind === "export" ? "export" : "run" })
              }
            >
              View progress
              <ArrowRight size={13} />
            </button>
          </div>
        )}
        {jobError && (
          <div className="top-notice">
            <ErrorNotice message={jobError} />
          </div>
        )}
        <main id="main-content" tabIndex={-1}>
          {loading ? (
            <div className="workspace-loading">
              <div className="loading-mark">
                <Layers3 size={32} strokeWidth={1.3} />
              </div>
              <Spinner label="Opening your workspace…" />
            </div>
          ) : error ? (
            <div className="load-error">
              <EmptyState
                icon={<Database size={30} />}
                title="Let’s reconnect your workspace"
                text="The interface is ready, but the local report service could not be reached."
              />
              <ErrorNotice message={error} onRetry={() => void load()} />
            </div>
          ) : page === "reports" ? (
            <ReportsPage
              data={data}
              onOpen={(id) => navigate("report", id)}
              onCreate={() => setDialog({ kind: "create" })}
              onRun={beginRun}
            />
          ) : page === "sources" ? (
            <SourcesPage
              data={data}
              onOpen={(id) => void openSource(id)}
              onRefresh={refresh}
            />
          ) : page === "programs" ? (
            <ProgramsPage
              programs={data.programs}
              reportTypes={data.report_types}
              onRefresh={refresh}
            />
          ) : (
            <>
              {snapshotLoading ? (
                <div className="workspace-loading">
                  <Spinner label="Opening report snapshot…" />
                </div>
              ) : snapshotError ? (
                <div className="load-error">
                  <ErrorNotice
                    message={snapshotError}
                    onRetry={() => snapshotId && void loadSnapshot(snapshotId)}
                  />
                </div>
              ) : snapshot && shared ? (
                <>
                  <div className="report-heading">
                    <div>
                      <button
                        className="back-label"
                        onClick={() => navigate("reports")}
                      >
                        <ArrowLeft size={12} />
                        ALL REPORTS
                      </button>
                      <h1>{snapshot.title}</h1>
                      <div className="report-heading-meta">
                        <span>{snapshot.period.label}</span>
                        <span className="meta-dot">·</span>
                        <span>Revision {snapshot.revision}</span>
                        <Badge status={snapshot.status} />
                      </div>
                    </div>
                    <div className="report-actions">
                      {snapshot.status !== "accepted" && (
                        <button
                          className="button secondary accept-button"
                          onClick={() => setDialog({ kind: "accept" })}
                          disabled={snapshot.status === "blocked"}
                        >
                          <ShieldCheck size={15} />
                          Accept report
                        </button>
                      )}
                      <button
                        className="button secondary"
                        onClick={() => beginRun()}
                        disabled={!published || Boolean(activeJob)}
                        title={
                          activeProgram?.runtime_status === "code_changed"
                            ? "The active release needs an update. Open Programs to review it."
                            : activeProgram?.runtime_status ===
                                "restart_required"
                              ? "Restart the local service before creating a new run."
                              : undefined
                        }
                      >
                        <Plus size={16} />
                        New run
                      </button>
                      <button className="button primary" onClick={beginExport}>
                        <ArrowDownToLine size={16} />
                        Export
                        <ChevronDown size={13} />
                      </button>
                    </div>
                  </div>
                  <div className="view-bar">
                    <div
                      className="view-tabs"
                      role="tablist"
                      aria-label="Report view"
                    >
                      {[
                        { id: "document", label: "Report", icon: FileText },
                        { id: "workbook", label: "Workbook", icon: Table2 },
                        {
                          id: "presentation",
                          label: "Presentation",
                          icon: Presentation,
                        },
                      ].map((tab, index, all) => (
                        <button
                          id={`tab-${tab.id}`}
                          type="button"
                          role="tab"
                          tabIndex={view === tab.id ? 0 : -1}
                          aria-selected={view === tab.id}
                          aria-controls="report-content"
                          key={tab.id}
                          className={view === tab.id ? "active" : ""}
                          onClick={() => setView(tab.id)}
                          onKeyDown={(e) => {
                            if (
                              e.key === "ArrowRight" ||
                              e.key === "ArrowLeft"
                            ) {
                              e.preventDefault();
                              const next =
                                all[
                                  (index +
                                    (e.key === "ArrowRight" ? 1 : -1) +
                                    all.length) %
                                    all.length
                                ];
                              setView(next.id);
                              document
                                .getElementById(`tab-${next.id}`)
                                ?.focus();
                            }
                          }}
                        >
                          <tab.icon size={15} />
                          {tab.label}
                        </button>
                      ))}
                    </div>
                    <div className="view-tools">
                      <span className="shared-facts-note">
                        <Link2 size={12} />
                        Shared facts, three views
                      </span>
                      <button
                        className={`evidence-toggle${evidence ? " active" : ""}`}
                        onClick={() => setEvidence(!evidence)}
                        aria-pressed={evidence}
                      >
                        <Link2 size={14} />
                        <span>Evidence</span>
                      </button>
                    </div>
                  </div>
                  <div
                    className={`report-workspace${evidence ? " with-evidence" : ""}`}
                  >
                    <div
                      className={`report-surface ${view}`}
                      id="report-content"
                      role="tabpanel"
                      aria-labelledby={`tab-${view}`}
                    >
                      {view === "document" ? (
                        <ReportDocument
                          {...shared}
                          onEdit={(node) =>
                            setDialog({ kind: "revision", node })
                          }
                        />
                      ) : view === "workbook" ? (
                        <WorkbookView {...shared} />
                      ) : (
                        <PresentationView {...shared} />
                      )}
                      <div className="surface-footer">
                        <span>
                          <Check size={12} />
                          Native snapshot preview
                        </span>
                        <span>
                          {Object.keys(snapshot.facts).length} facts ·{" "}
                          {snapshot.views.length} views ·{" "}
                          {snapshot.source_assets.length} sources
                        </span>
                      </div>
                    </div>
                    {evidence && (
                      <EvidencePanel
                        {...shared}
                        onClose={() => setEvidence(false)}
                        onSource={(id) => void openSource(id)}
                      />
                    )}
                  </div>
                </>
              ) : (
                <EmptyState
                  icon={<FileText size={30} />}
                  title="No report is open"
                  text="Choose a report from your workspace to explore its facts and evidence."
                  action={
                    <button
                      className="button primary"
                      onClick={() => navigate("reports")}
                    >
                      Browse reports
                      <ArrowRight size={15} />
                    </button>
                  }
                />
              )}
            </>
          )}
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <Check size={16} />
          <span>{toast}</span>
          <IconButton
            label="Dismiss notification"
            onClick={() => setToast(null)}
          >
            <X size={14} />
          </IconButton>
        </div>
      )}
      {sourceLoading && (
        <div className="source-loading-toast" role="status">
          <Spinner label="Opening source…" />
        </div>
      )}
      {dialog?.kind === "create" && (
        <CreateTypeDialog
          onClose={closeDialog}
          onCreated={async () => {
            await refresh();
            navigate("programs");
            notify("Report type created. Review its candidate program.");
          }}
        />
      )}
      {dialog?.kind === "run" && (
        <RunDialog
          data={data}
          snapshot={snapshot}
          reportTypeId={dialog.reportTypeId}
          job={job?.kind === "export" ? null : job}
          onJob={setJob}
          onCancel={() => void cancelJob()}
          onClose={closeDialog}
        />
      )}
      {dialog?.kind === "revision" && snapshot && (
        <RevisionDialog
          snapshot={snapshot}
          node={dialog.node}
          onClose={closeDialog}
          onSaved={saveSnapshot}
        />
      )}
      {dialog?.kind === "accept" && snapshot && (
        <AcceptDialog
          snapshot={snapshot}
          onClose={closeDialog}
          onSaved={saveSnapshot}
        />
      )}
      {dialog?.kind === "export" && snapshot && (
        <ExportDialog
          snapshot={snapshot}
          capabilities={data.capabilities}
          job={job?.kind === "export" ? job : null}
          exports={exports}
          onJob={setJob}
          onCancel={() => void cancelJob()}
          onClose={closeDialog}
        />
      )}
      {source && <SourceDetail asset={source} onClose={closeSource} />}
      {dialog?.kind === "help" && (
        <Modal
          title="A workspace for trusted reports."
          eyebrow="REPORT FOUNDRY · LOCAL EDITION"
          onClose={closeDialog}
        >
          <div className="modal-body">
            <p className="dialog-intro">
              Report Foundry turns supported source data and a published
              reporting policy into one native snapshot, with document,
              workbook, and presentation views.
            </p>
            <div className="help-steps">
              <div>
                <Database size={20} />
                <span>
                  <strong>Start with evidence</strong>Upload and inspect
                  original files in Sources.
                </span>
              </div>
              <div>
                <GitBranch size={20} />
                <span>
                  <strong>Make the policy explicit</strong>Resolve decisions,
                  evaluate, and publish a Program.
                </span>
              </div>
              <div>
                <FileText size={20} />
                <span>
                  <strong>Review the actual report</strong>Run a period, trace
                  facts, revise commentary, then export.
                </span>
              </div>
            </div>
            <div className="notice info">
              The included example is synthetic. This local edition uses a
              bounded, authored revenue program; it does not claim automated
              policy learning or production isolation.
            </div>
          </div>
          <footer className="modal-footer">
            <button className="button primary" onClick={closeDialog}>
              Back to the workspace
              <ArrowRight size={15} />
            </button>
          </footer>
        </Modal>
      )}
    </div>
  );
}
