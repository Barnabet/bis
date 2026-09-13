import assert from "node:assert/strict";
import { test } from "node:test";
import { File } from "node:buffer";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const server = await createServer({ root: fileURLToPath(new URL("../", import.meta.url)), server: { middlewareMode: true }, appType: "custom" });
const helpers = await server.ssrLoadModule("/src/publicReports.ts");
const views = await server.ssrLoadModule("/src/ReportView.tsx");
const dialogs = await server.ssrLoadModule("/src/Dialogs.tsx");
const library = await server.ssrLoadModule("/src/LibraryPages.tsx");

const noOp = () => {};
const ons = { id: "ons-program", report_type_id: "ons-type", state: "published", version: "1.0.0", input_contract: { role: "public_source:ons_retail" } };
const census = { ...ons, id: "census-program", input_contract: { role: "public_source:census_marts" } };
const revenue = { ...ons, id: "revenue-program", input_contract: { role: "transactions" } };
const assets = [
  { id: "eur", filename: "ledger.csv", status: "usable", profile: { eligible_roles: ["transactions"] } },
  { id: "ons", filename: "drsi-june.csv", status: "usable", profile: { eligible_roles: ["public_source:ons_retail"], public_family: "ons_retail", period: "2025-06", vintage: "2025-07-25" } },
  { id: "census", filename: "census.xlsx", status: "usable", profile: { eligible_roles: ["public_source:census_marts"], public_family: "census_marts", period: "2025-06", vintage: "2025-07-17" } },
  { id: "blocked", filename: "blocked.csv", status: "blocked", profile: { eligible_roles: ["public_source:ons_retail"] } },
  { id: "reserved", filename: "reserved.csv", reserved: true, profile: { eligible_roles: ["public_source:ons_retail"] } },
];
const data = { report_types: [{ id: "ons-type", name: "ONS report", active_program_id: "ons-program" }], programs: [ons], assets, snapshots: [], jobs: [], capabilities: {} };

await test("source eligibility uses the exact declared input role and excludes blocked/reserved assets", () => {
  assert.deepEqual(helpers.eligibleSources(assets, ons).map((a) => a.id), ["ons"]);
  assert.deepEqual(helpers.eligibleSources(assets, census).map((a) => a.id), ["census"]);
  assert.deepEqual(helpers.eligibleSources(assets, revenue).map((a) => a.id), ["eur"]);
});

await test("historical targets retain family boundaries and PDF-only public scope", () => {
  const targets = [
    { id: "generic", filename: "report.pdf", profile: { eligible_roles: ["historical_target"] } },
    { id: "ons", filename: "ons.pdf", profile: { eligible_roles: ["historical_target"], public_family: "ons_retail" } },
    { id: "census", filename: "census.pdf", profile: { eligible_roles: ["historical_target"], public_family: "census_marts" } },
    { id: "docx", filename: "report.docx", profile: { eligible_roles: ["historical_target"] } },
  ];
  assert.deepEqual(helpers.eligibleTargets(targets, ons).map((a) => a.id), ["generic", "ons"]);
  assert.deepEqual(helpers.eligibleTargets(targets, revenue).map((a) => a.id), ["generic", "docx"]);
});

await test("public period derives month boundaries, previous month and source vintage", () => {
  assert.deepEqual(helpers.monthlySourcePeriod(assets[1], "ons_retail"), {
    label: "June 2025", start: "2025-06-01", end_exclusive: "2025-07-01",
    comparison: { start: "2025-05-01", end_exclusive: "2025-06-01" },
    timezone: "UTC", as_of: "2025-07-25T23:59:59+00:00",
  });
  const january = { ...assets[1], profile: { ...assets[1].profile, period: "2025-01", vintage: "2025-02-20" } };
  assert.equal(helpers.monthlySourcePeriod(january, "ons_retail").comparison.start, "2024-12-01");
  const leap = { ...assets[1], profile: { ...assets[1].profile, period: "2024-02", vintage: "2024-03-20" } };
  assert.equal(helpers.monthlySourcePeriod(leap, "ons_retail").end_exclusive, "2024-03-01");
});

await test("missing, invalid or wrong-family metadata never supplies a guessed public period", () => {
  assert.equal(helpers.monthlySourcePeriod(assets[1], "census_marts"), null);
  for (const profile of [{ period: "2025-13", vintage: "2026-01-01" }, { period: "2025-06", vintage: "2025-07-32" }, { period: "2025-06", vintage: "2025-06-01" }, {}]) {
    assert.equal(helpers.monthlySourcePeriod({ profile: { public_family: "ons_retail", ...profile } }, "ons_retail"), null);
  }
});

await test("upload form sends explicit public family and leaves generic imports unchanged", () => {
  const file = new File(["original bytes"], "source.csv", { type: "text/csv" });
  const publicBody = helpers.sourceUploadBody(file, "ons_retail");
  assert.equal(publicBody.get("public_family"), "ons_retail");
  assert.equal(publicBody.get("file").name, "source.csv");
  assert.equal(helpers.sourceUploadBody(file, "").has("public_family"), false);
});

await test("new-program dialog presents scoped public families", () => {
  const html = renderToStaticMarkup(React.createElement(dialogs.CreateTypeDialog, { onClose: noOp, onCreated: async () => {} }));
  assert.match(html, /value="ons_retail"/);
  assert.match(html, /value="census_marts"/);
  assert.match(html, /Reporting family/);
});

await test("public run dialog initially selects only its matching source and monthly dates", () => {
  const html = renderToStaticMarkup(React.createElement(dialogs.RunDialog, { data, snapshot: null, reportTypeId: "ons-type", job: null, onJob: noOp, onCancel: noOp, onClose: noOp }));
  assert.match(html, /drsi-june\.csv/);
  assert.doesNotMatch(html, /ledger\.csv|census\.xlsx|blocked\.csv|reserved\.csv/);
  assert.match(html, /value="June 2025"/);
  assert.match(html, /value="2025-05-01"/);
  assert.match(html, /value="2025-07-25T23:59:59\+00:00"/);
  assert.match(html, /Published source data/);
  assert.doesNotMatch(html, /Report image/);
});

await test("sources page exposes an import family before choosing a file", () => {
  const html = renderToStaticMarkup(React.createElement(library.SourcesPage, { data, onOpen: noOp, onRefresh: async () => {} }));
  assert.match(html, /Import as/);
  assert.match(html, /value="ons_retail"/);
  assert.match(html, /value="census_marts"/);
});

function publicSnapshot() {
  const facts = Object.fromEntries([
    ["ons.J5EC", "0.9", "0.9%", "Volume: monthly change"],
    ["ons.J5EG", "-0.6", "-0.6%", "Volume: rolling change"],
    ["ons.MS6Y", "27.8", "27.8%", "Online share of retail"],
  ].map(([id, value, display, definition]) => [id, { id, value, display, definition, unit: "percent_points", status: "known", inputs: [], sources: [] }]));
  const rows = Object.values(facts).map((f) => ({ metric: f.definition, value: f.id }));
  const rates = rows.map((r) => ({ metric: r.metric, value: facts[r.value].value }));
  const nodes = [
    { id: "table", kind: "table", title: "Headline measures", dataset_id: "headlines" },
    { id: "chart", kind: "chart", title: "Published percentage figures", dataset_id: "rates", category_column: "metric", series: [{ column_id: "value", label: "Published figure" }], axis_unit: "percent_points" },
  ];
  return {
    id: "snapshot", title: "ONS monthly retail headlines", revision: 1, period: { label: "June 2025", start: "2025-06-01", end_exclusive: "2025-07-01" },
    facts, datasets: { headlines: { id: "headlines", columns: [{ id: "metric", label: "Measure", type: "text" }, { id: "value", label: "Published value", type: "fact" }], rows }, rates: { id: "rates", columns: [{ id: "metric", label: "Measure", type: "text" }, { id: "value", label: "Published value", type: "decimal", unit: "percent_points" }], rows: rates } },
    nodes, views: [{ id: "document", node_ids: ["table", "chart"] }], metadata: { source_vintage: "2025-07-25", adapter: "ons_retail" }, source_assets: [],
  };
}

await test("public table resolves fact references and percentages stay on the published scale", () => {
  const snapshot = publicSnapshot();
  const props = { snapshot, onFact: noOp, selectedFact: null, onSource: noOp };
  const html = renderToStaticMarkup(React.createElement(views.DataTable, { ...props, dataset: snapshot.datasets.headlines }));
  assert.match(html, />27\.8%<\/button>/);
  assert.match(html, />-0\.6%<\/button>/);
  assert.doesNotMatch(html, /2780|>ons\./);
  const raw = renderToStaticMarkup(React.createElement(views.DataTable, { ...props, dataset: snapshot.datasets.rates }));
  assert.match(raw, />27\.8%<\/td>/);
  assert.doesNotMatch(raw, /2780/);
});

await test("public report uses headline metrics and a signed percentage chart without EUR labels", () => {
  const snapshot = publicSnapshot();
  const html = renderToStaticMarkup(React.createElement(views.ReportDocument, { snapshot, onFact: noOp, selectedFact: null, onSource: noOp, onEdit: noOp, onDraft: noOp }));
  assert.match(html, /PUBLISHED HEADLINES/);
  assert.match(html, /Publication vintage 2025-07-25/);
  assert.match(html, /headline-chart-bar negative/);
  assert.match(html, />27\.8%<\/button>/);
  assert.doesNotMatch(html, /All figures in EUR|TOTAL REVENUE|width:-|NaN|2780/);
});
await server.close();
