import { useEffect, useState } from "react";
import { ArrowRight, FileText, Info, PenLine } from "lucide-react";
import type {
  Bootstrap,
  HistoricalExample,
  Job,
  ModelStatus,
  Snapshot,
} from "./types";
import { api, identifier, messageOf, post } from "./api";
import { Badge, ErrorNotice, Modal, Spinner } from "./ui";
import { JobProgress } from "./Dialogs";
import { ModelConfiguration } from "./ModelConfiguration";

export function CompositionDialog({
  data,
  model,
  snapshot,
  job,
  onJob,
  onCancel,
  onClose,
}: {
  data: Bootstrap;
  model: ModelStatus | undefined;
  snapshot: Snapshot;
  job: Job | null;
  onJob: (job: Job) => void;
  onCancel: () => void;
  onClose: () => void;
}) {
  const [objective, setObjective] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [targetIds, setTargetIds] = useState<string[]>(
    data.historical_target_asset_ids ?? [],
  );
  const [checkingSources, setCheckingSources] = useState(
    data.historical_target_asset_ids === undefined,
  );
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (data.historical_target_asset_ids !== undefined) {
      setTargetIds(data.historical_target_asset_ids);
      setCheckingSources(false);
      return;
    }
    let disposed = false;
    setCheckingSources(true);
    Promise.all(
      data.report_types.map((type) =>
        api<HistoricalExample[] | { examples: HistoricalExample[] }>(
          `/report-types/${type.id}/examples`,
        ),
      ),
    )
      .then((lists) => {
        if (!disposed)
          setTargetIds(
            lists.flatMap((list) =>
              (Array.isArray(list) ? list : list.examples).map(
                (example) => example.report_asset_id,
              ),
            ),
          );
      })
      .catch((err) => {
        if (!disposed) setSourcesError(messageOf(err));
      })
      .finally(() => {
        if (!disposed) setCheckingSources(false);
      });
    return () => {
      disposed = true;
    };
  }, [data.historical_target_asset_ids, data.report_types]);
  const sources = sourcesError
    ? []
    : data.assets.filter(
        (asset) =>
          !asset.reserved &&
          asset.status !== "blocked" &&
          !targetIds.includes(asset.id) &&
          /\.(docx|pdf)$/i.test(asset.filename) &&
          Array.isArray(asset.profile?.eligible_roles) &&
          asset.profile.eligible_roles.includes("commentary"),
      );
  const active =
    busy || Boolean(job && ["queued", "running"].includes(job.status));
  const validSelection = selected.filter((id) =>
    sources.some((source) => source.id === id),
  );
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onJob(
        await post<Job>(`/report-snapshots/${snapshot.id}/compose`, {
          expected_revision: snapshot.revision,
          source_asset_ids: validSelection,
          objective: objective.trim(),
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
      title="Draft commentary with AI"
      eyebrow="EVIDENCE-GROUNDED DRAFT"
      onClose={onClose}
    >
      <form onSubmit={submit}>
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
            Prepare editorial commentary from this snapshot’s approved facts and
            any selected source notes. The result becomes a new revision for
            your review.
          </p>
          <ModelConfiguration model={model} />
          <label className="field">
            What should the commentary address?
            <textarea
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
              maxLength={1000}
              rows={4}
              required
              disabled={active}
              placeholder="Summarize the selected region and period results, distinguishing evidence from interpretation."
            />
          </label>
          <fieldset className="composition-source-fieldset">
            <legend>
              Commentary sources <span>Optional</span>
            </legend>
            <p className="muted-small">
              Choose up to five DOCX or PDF notes. Historical target reports and
              reserved sources are excluded.
            </p>
            {checkingSources ? (
              <Spinner label="Checking source eligibility…" />
            ) : sources.length ? (
              <div className="composition-source-list">
                {sources.map((asset) => (
                  <label key={asset.id}>
                    <input
                      type="checkbox"
                      checked={validSelection.includes(asset.id)}
                      disabled={
                        active ||
                        (validSelection.length >= 5 &&
                          !validSelection.includes(asset.id))
                      }
                      onChange={(event) =>
                        setSelected((previous) =>
                          event.target.checked
                            ? [...previous, asset.id]
                            : previous.filter((id) => id !== asset.id),
                        )
                      }
                    />
                    <FileText size={17} />
                    <span>
                      {asset.filename}
                      <small>
                        {String(
                          asset.profile?.format ??
                            asset.filename.split(".").pop(),
                        ).toUpperCase()}{" "}
                        · Immutable source
                      </small>
                    </span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="composition-empty-sources">
                No eligible commentary notes are available. You can draft from
                the snapshot’s facts only, or upload notes in Sources first.
              </p>
            )}
            {sourcesError && (
              <ErrorNotice
                message={`Source eligibility could not be verified. Source selection is unavailable; facts-only drafting remains possible. ${sourcesError}`}
              />
            )}
            <p className="composition-selection-summary">
              {validSelection.length
                ? `${validSelection.length} source${validSelection.length === 1 ? "" : "s"} selected.`
                : "No sources selected — use approved snapshot facts only."}
            </p>
          </fieldset>
          <div className="notice info">
            <Info size={17} />
            <p>
              Computed facts stay locked. AI wording and explanations require
              review; this action does not accept the report or publish a future
              reporting rule.
            </p>
          </div>
          {error && <ErrorNotice message={error} />}
          {job && <JobProgress job={job} onCancel={onCancel} />}
        </div>
        <footer className="modal-footer">
          <button type="button" className="button secondary" onClick={onClose}>
            {active ? "Continue in background" : "Cancel"}
          </button>
          <button
            className="button primary"
            disabled={
              active ||
              !model?.configured ||
              !objective.trim() ||
              checkingSources
            }
          >
            {active ? (
              <Spinner label="Drafting…" />
            ) : (
              <>
                <PenLine size={15} />
                Create AI draft
                <ArrowRight size={15} />
              </>
            )}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
