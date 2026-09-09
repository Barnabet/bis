export type Run =
  | { type: "text"; text: string }
  | { type: "fact"; fact_id: string };
export type Fact = {
  id: string;
  kind: string;
  value: string | null;
  unit: string;
  display: string;
  status: string;
  definition: string;
  scope: string;
  inputs: string[];
  sources: { asset_id: string; artifact_sha256: string; locator: unknown }[];
};
export type Dataset = {
  id: string;
  columns: { id: string; label: string; type: string; unit?: string }[];
  rows: Record<string, string | number | null>[];
};
export type ReportNode = {
  id: string;
  kind: string;
  title: string;
  runs?: Run[];
  editable?: boolean;
  mode?: string;
  children?: string[];
  dataset_id?: string;
  materialized_dataset_id?: string;
  asset_id?: string;
  render_digest?: string;
  media_type?: string;
  width_px?: number;
  height_px?: number;
  alt_text?: string;
  decorative?: boolean;
  category_column?: string;
  series?: { column_id: string; label: string }[];
  axis_unit?: string;
};
export type Finding = {
  id: string;
  phase: string;
  severity: string;
  code: string;
  component_id: string;
  evidence_refs: string[];
  message: string;
  repair_class: string;
};
export type Period = {
  label: string;
  start: string;
  end_exclusive: string;
  comparison: { start: string; end_exclusive: string };
  timezone: string;
  as_of: string;
};
export type Snapshot = {
  id: string;
  title: string;
  report_type_id: string;
  revision: number;
  parent_id: string | null;
  period: Period;
  program: { id: string; version: string; digest: string };
  source_snapshot_digest: string;
  source_assets: { id: string; digest: string; filename: string }[];
  facts: Record<string, Fact>;
  datasets: Record<string, Dataset>;
  nodes: ReportNode[] | Record<string, ReportNode>;
  views: {
    id: string;
    family: string;
    title: string;
    node_ids: string[];
    coverage: {
      scope: string;
      required_node_ids: string[];
      omitted_node_ids: string[];
    };
    recipe: unknown;
  }[];
  findings: Finding[];
  metadata: Record<string, unknown>;
  status: string;
  created_at: string;
  acceptance?: { accepted_at: string; actor: string };
};
export type SnapshotSummary = {
  id: string;
  title: string;
  report_type_id: string;
  revision: number;
  period: Period | string;
  status: string;
  created_at: string;
  accepted_at?: string;
};
export type ReportType = {
  id: string;
  name: string;
  description?: string;
  program_id?: string;
  active_program_id?: string | null;
  created_at?: string;
};
export type Asset = {
  id: string;
  filename: string;
  digest?: string;
  sha256?: string;
  media_type?: string;
  size_bytes?: number;
  created_at?: string;
  synthetic?: boolean;
  role?: string;
  reserved?: boolean;
  access_reason?: string;
  profile?: Record<string, unknown>;
  extraction?: Record<string, unknown>;
  [key: string]: unknown;
};
export type ImageProfile = {
  width_px: number;
  height_px: number;
  render_digest: string;
  media_type: string;
  normalization: string;
};
export const getImageProfile = (
  asset: Asset | undefined,
): ImageProfile | undefined => {
  if (asset?.reserved) return undefined;
  const image = asset?.profile?.image;
  if (!image || typeof image !== "object") return undefined;
  const profile = image as Record<string, unknown>;
  return typeof profile.width_px === "number" &&
    typeof profile.height_px === "number" &&
    typeof profile.render_digest === "string"
    ? (image as ImageProfile)
    : undefined;
};
export type Program = {
  id: string;
  report_type_id: string;
  name?: string;
  title?: string;
  version: string;
  digest: string;
  state: string;
  runtime_status?: "current" | "code_changed" | "restart_required";
  lifecycle_status?: "active" | "historical" | "candidate" | "discarded";
  active_program_id?: string | null;
  lineage?: {
    parent_program_id: string;
    parent_program_digest: string;
    reason: string;
  } | null;
  package_artifact_digest?: string | null;
  change_summary?: {
    added_files: string[];
    changed_files: string[];
    removed_files: string[];
    python_changed: boolean;
    policy_changed: boolean;
    decision_review_required: boolean;
  } | null;
  description?: string;
  coverage: { id: string; label: string; kind: string; status: string }[];
  decisions: {
    id: string;
    question: string;
    alternatives: { value: string; label: string; consequence: string }[];
    resolution: string | null;
    prior_resolution?: string | null;
    inherited_from?: {
      program_id: string;
      program_digest: string;
      resolved_at?: string;
    } | null;
  }[];
  evaluation: null | {
    passed: boolean;
    checks: { name: string; passed: boolean; detail: string }[];
    digest: string;
    created_at: string;
  };
  limitations: string[];
  input_contract: unknown;
  learning?: ProgramLearning | null;
  [key: string]: unknown;
};
export type Job = {
  id: string;
  kind?: string;
  status: string;
  stage?: string;
  stages?: unknown;
  message?: string;
  error?: unknown;
  result?: Record<string, unknown>;
  snapshot_id?: string;
  export_id?: string;
  created_at?: string;
  [key: string]: unknown;
};
export type ExportRecord = {
  id: string;
  format: string;
  status: string;
  snapshot_id: string;
  filename?: string;
  fidelity?: unknown;
  [key: string]: unknown;
};
export type Bootstrap = {
  report_types: ReportType[];
  snapshots: SnapshotSummary[];
  assets: Asset[];
  programs: Program[];
  jobs: Job[];
  capabilities: Record<string, unknown> | unknown[];
  demo?: boolean;
  historical_target_asset_ids?: string[];
};

export type ModelStatus = {
  configured: boolean;
  provider: string;
  model: string | null;
  limits?: Record<string, unknown>;
};
export type HistoricalExample = {
  id: string;
  report_type_id: string;
  label?: string;
  caveats?: string;
  period: Period;
  corpus_role: "authoring" | "development" | "reserved";
  effective_role: "authoring" | "development" | "reserved";
  report_asset_id: string;
  source_asset_ids: string[];
  report_filename: string;
  source_filenames: string[];
  digest: string;
  state: string;
  inspection: {
    regions: unknown[];
    observations: unknown[];
    issues: unknown[];
  } | null;
  exposed: boolean;
};
export type LearningCoverage = {
  id: string;
  example_id: string;
  region_id: string;
  locator: unknown;
  kind: string;
  text: string;
  component_id: string | null;
  status: "mapped" | "needs_decision" | "out_of_scope";
  reason: string;
};
export type ProgramLearning = {
  engine: string;
  model_proposal?: {
    selection: string;
    rationale: string;
    unresolved_questions: string[];
  };
  model_receipt?: Record<string, unknown>;
  requirements: string;
  corpus_digest: string;
  example_ids: string[];
  hypotheses: {
    value: string;
    label: string;
    supported: boolean;
    checks: {
      example_id: string;
      expected: unknown;
      actual: unknown;
      passed: boolean;
      locator: unknown;
    }[];
  }[];
  coverage: LearningCoverage[];
  assumptions: string[];
  limitations: string[];
};
export const getModelStatus = (
  capabilities: Bootstrap["capabilities"],
): ModelStatus | undefined => {
  if (Array.isArray(capabilities)) return undefined;
  const model = capabilities.model;
  return model &&
    typeof model === "object" &&
    typeof (model as Record<string, unknown>).configured === "boolean"
    ? (model as ModelStatus)
    : undefined;
};
export const getNodes = (snapshot: Snapshot) =>
  Array.isArray(snapshot.nodes)
    ? snapshot.nodes
    : Object.values(snapshot.nodes);

export const activeProgramFor = (
  reportType: ReportType | undefined,
  programs: Program[],
) =>
  reportType?.active_program_id
    ? programs.find((program) => program.id === reportType.active_program_id)
    : undefined;

export const canRunProgram = (program: Program | undefined) =>
  program?.state === "published" &&
  (!program.runtime_status || program.runtime_status === "current");

export const programLifecycle = (
  program: Program,
  reportTypes: ReportType[],
) => {
  if (program.lifecycle_status) return program.lifecycle_status;
  if (program.state === "candidate" || program.state === "discarded")
    return program.state;
  const activeId =
    reportTypes.find((type) => type.id === program.report_type_id)
      ?.active_program_id ?? program.active_program_id;
  return activeId === program.id ? "active" : "historical";
};
