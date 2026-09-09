import type { ReportNode, Snapshot } from "./types";
import { getNodes } from "./types";

export type ViewGroup = {
  name: string;
  node_ids: string[];
  dataset_id?: string;
};

export function nodesForView(snapshot: Snapshot, viewId: string): ReportNode[] {
  const nodes = getNodes(snapshot);
  const view = snapshot.views.find((item) => item.id === viewId);
  return view
    ? view.node_ids
        .map((id) => nodes.find((node) => node.id === id))
        .filter((node): node is ReportNode => Boolean(node))
    : nodes.filter((node) => node.kind !== "section");
}

export function viewGroups(
  snapshot: Snapshot,
  viewId: "workbook" | "presentation",
): ViewGroup[] {
  const view = snapshot.views.find((item) => item.id === viewId);
  const recipe =
    view?.recipe && typeof view.recipe === "object"
      ? (view.recipe as Record<string, unknown>)
      : {};
  const entries = recipe[viewId === "workbook" ? "sheets" : "slides"];
  const nodes = nodesForView(snapshot, viewId);
  const allowed = new Set(nodes.map((node) => node.id));
  if (Array.isArray(entries) && entries.length) {
    const groups = entries.flatMap((entry, index): ViewGroup[] => {
      if (!entry || typeof entry !== "object") return [];
      const group = entry as Record<string, unknown>;
      if (!Array.isArray(group.node_ids)) return [];
      return [
        {
          name: String(
            group.name ??
              group.title ??
              `${viewId === "workbook" ? "Sheet" : "Slide"} ${index + 1}`,
          ),
          node_ids: group.node_ids.filter(
            (id): id is string => typeof id === "string" && allowed.has(id),
          ),
        },
      ];
    });
    if (groups.length) return groups;
  }
  const imageIds = nodes
    .filter((node) => node.kind === "image")
    .map((node) => node.id);
  return [
    {
      name: viewId === "workbook" ? "Overview" : "Performance overview",
      node_ids: nodes
        .filter((node) => ["rich_text", "table"].includes(node.kind))
        .map((node) => node.id),
    },
    {
      name: viewId === "workbook" ? "Analysis" : "Regional analysis",
      node_ids: nodes
        .filter((node) => ["chart", "pivot"].includes(node.kind))
        .map((node) => node.id),
    },
    ...(imageIds.length
      ? [
          {
            name: viewId === "workbook" ? "Images" : "Report image",
            node_ids: imageIds,
          },
        ]
      : []),
  ];
}
