export type Run =
  { type: "text"; text: string } | { type: "fact"; fact_id: string };
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
  profile?: Record<string, unknown>;
  extraction?: Record<string, unknown>;
  [key: string]: unknown;
};
export type Program = {
  id: string;
  report_type_id: string;
  name?: string;
  title?: string;
  version: string;
  digest: string;
  state: string;
  description?: string;
  coverage: { id: string; label: string; kind: string; status: string }[];
  decisions: {
    id: string;
    question: string;
    alternatives: { value: string; label: string; consequence: string }[];
    resolution: string | null;
  }[];
  evaluation: null | {
    passed: boolean;
    checks: { name: string; passed: boolean; detail: string }[];
    digest: string;
    created_at: string;
  };
  limitations: string[];
  input_contract: unknown;
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
};
export const getNodes = (snapshot: Snapshot) =>
  Array.isArray(snapshot.nodes)
    ? snapshot.nodes
    : Object.values(snapshot.nodes);
