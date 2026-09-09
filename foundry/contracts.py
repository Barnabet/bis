"""Authoritative native report boundary; format adapters consume this model only."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Window(Contract):
    start: date
    end_exclusive: date

    @model_validator(mode="after")
    def ordered(self):
        if self.start >= self.end_exclusive:
            raise ValueError("Reporting windows must have positive duration")
        return self


class Period(Window):
    label: str = Field(min_length=1)
    comparison: Window
    timezone: str
    as_of: datetime

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a known IANA timezone") from exc
        return value

    @field_validator("as_of")
    @classmethod
    def aware_cutoff(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of requires an explicit timezone")
        return value


class Program(Contract):
    id: Identifier
    version: str = Field(min_length=1)
    digest: Digest


class SourceAsset(Contract):
    id: Identifier
    digest: Digest
    filename: str = Field(min_length=1)


class SourceReference(Contract):
    asset_id: Identifier
    artifact_sha256: Digest
    locator: str = Field(min_length=1)


class Fact(Contract):
    id: Identifier
    kind: Literal["number", "text"]
    value: str | None
    unit: str
    display: str
    status: Literal["known", "missing", "undefined", "not_applicable", "withheld"]
    definition: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    inputs: list[Identifier] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_value(self):
        if self.status == "known":
            if self.value is None:
                raise ValueError("Known facts require a value")
            if self.kind == "number":
                _decimal(self.value)
        elif self.value is not None:
            raise ValueError("Missing, undefined, withheld and inapplicable facts require null values")
        if not self.inputs and not self.sources:
            raise ValueError("Every fact requires source or upstream provenance")
        if len(self.inputs) != len(set(self.inputs)):
            raise ValueError("Duplicate fact dependencies")
        return self


def _decimal(value: Any) -> Decimal:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError("Exact decimals must be nonempty decimal strings")
    if not re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?", value):
        raise ValueError("Invalid decimal string syntax")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal string") from exc
    if not number.is_finite():
        raise ValueError("Numeric facts and cells must be finite")
    return number


class Column(Contract):
    id: Identifier
    label: str
    type: Literal["text", "decimal", "integer", "fact"]
    unit: str = ""


class Dataset(Contract):
    id: Identifier
    columns: list[Column] = Field(min_length=1)
    rows: list[dict[str, str | int | None]]

    @model_validator(mode="after")
    def rectangular_and_typed(self):
        columns = {c.id: c for c in self.columns}
        if len(columns) != len(self.columns):
            raise ValueError("Dataset column IDs must be unique")
        for row in self.rows:
            if set(row) != set(columns):
                raise ValueError("Dataset rows must contain exactly their declared columns")
            for key, value in row.items():
                if value is None:
                    continue
                kind = columns[key].type
                if kind == "decimal":
                    _decimal(value)
                elif kind == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                    raise ValueError("Integer column requires integer values")
                elif kind in {"text", "fact"} and not isinstance(value, str):
                    raise ValueError("Text and fact columns require strings")
        return self


class TextRun(Contract):
    type: Literal["text"] = "text"
    text: str


class FactRun(Contract):
    type: Literal["fact"] = "fact"
    fact_id: Identifier


Run = Annotated[TextRun | FactRun, Field(discriminator="type")]


class NodeBase(Contract):
    id: Identifier
    title: str


class Section(NodeBase):
    kind: Literal["section"] = "section"
    children: list[Identifier]


class RichText(NodeBase):
    kind: Literal["rich_text"] = "rich_text"
    runs: list[Run] = Field(min_length=1)
    editable: bool = False
    mode: Literal["literal", "computed", "composed"]


class Table(NodeBase):
    kind: Literal["table"] = "table"
    dataset_id: Identifier


class Measure(Contract):
    column_id: Identifier
    aggregation: Literal["sum"] = "sum"


class Pivot(NodeBase):
    kind: Literal["pivot"] = "pivot"
    dataset_id: Identifier
    materialized_dataset_id: Identifier
    row_dimensions: list[Identifier] = Field(min_length=1)
    column_dimensions: list[Identifier]
    measures: list[Measure] = Field(min_length=1)
    native_required_in: list[Literal["flow", "grid", "canvas"]] = Field(default_factory=lambda: ["grid"])


class Series(Contract):
    column_id: Identifier
    label: str


class Chart(NodeBase):
    kind: Literal["chart"] = "chart"
    dataset_id: Identifier
    chart_type: Literal["bar"] = "bar"
    category_column: Identifier
    series: list[Series] = Field(min_length=1)
    axis_unit: str


class Image(NodeBase):
    kind: Literal["image"] = "image"
    asset_id: Identifier
    alt_text: str = Field(max_length=500)
    width_px: int = Field(gt=0, le=8192)
    height_px: int = Field(gt=0, le=8192)
    decorative: bool = False
    render_digest: Digest | None = None
    media_type: Literal['image/png'] = 'image/png'

    @model_validator(mode='after')
    def image_identity(self):
        if not self.decorative and not self.alt_text.strip():
            raise ValueError('A non-decorative image requires descriptive alt text')
        if self.width_px * self.height_px > 16_000_000:
            raise ValueError('Image exceeds the supported pixel limit')
        return self


class ImageBinding(Contract):
    asset_id: Identifier
    alt_text: str = Field(default='', max_length=500)
    decorative: bool = False

    @field_validator('alt_text')
    @classmethod
    def trim_alt(cls, value):
        return value.strip()

    @model_validator(mode='after')
    def accessible_image(self):
        if not self.decorative and not self.alt_text:
            raise ValueError('Describe the image or explicitly mark it decorative')
        return self


Node = Annotated[Section | RichText | Table | Pivot | Chart | Image, Field(discriminator="kind")]


class Coverage(Contract):
    scope: Literal["complete", "executive"]
    required_node_ids: list[Identifier]
    omitted_node_ids: list[Identifier] = Field(default_factory=list)


class View(Contract):
    id: Identifier
    family: Literal["flow", "grid", "canvas"]
    title: str
    node_ids: list[Identifier]
    coverage: Coverage
    recipe: dict[str, Any] = Field(default_factory=dict)


class Finding(Contract):
    id: Identifier
    phase: str
    severity: Literal["block", "review", "warn"]
    code: str
    component_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    message: str
    repair_class: str


class Snapshot(Contract):
    schema_version: Literal["1.0"] = "1.0"
    id: Identifier
    revision: int = Field(ge=1)
    parent_id: Identifier | None = None
    title: str
    report_type_id: Identifier
    program: Program
    period: Period
    source_snapshot_digest: Digest
    source_assets: list[SourceAsset] = Field(min_length=1)
    facts: dict[str, Fact]
    datasets: dict[str, Dataset]
    nodes: list[Node] = Field(min_length=1)
    views: list[View] = Field(min_length=1)
    findings: list[Finding] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: Literal["accepted", "review_required", "blocked"]
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def aware_creation(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at requires an explicit timezone")
        return value

    @model_validator(mode="after")
    def reference_integrity(self):
        assets = {a.id: a for a in self.source_assets}
        nodes = {n.id: n for n in self.nodes}
        if len(assets) != len(self.source_assets) or len(nodes) != len(self.nodes):
            raise ValueError("Source asset and node IDs must be unique")
        if len({v.id for v in self.views}) != len(self.views):
            raise ValueError("View IDs must be unique")
        if (self.revision == 1) != (self.parent_id is None):
            raise ValueError("Revision one has no parent; later revisions require one")
        for key, fact in self.facts.items():
            if key != fact.id:
                raise ValueError("Fact registry key must match fact ID")
            if any(parent not in self.facts for parent in fact.inputs):
                raise ValueError("Unknown upstream fact reference")
            for source in fact.sources:
                if source.asset_id not in assets or assets[source.asset_id].digest != source.artifact_sha256:
                    raise ValueError("Fact source identity or digest does not match a bound source asset")
        _acyclic({f.id: f.inputs for f in self.facts.values()}, "fact")
        for key, dataset in self.datasets.items():
            if key != dataset.id:
                raise ValueError("Dataset registry key must match dataset ID")
            for column in dataset.columns:
                if column.type == "fact":
                    if any(row[column.id] not in self.facts for row in dataset.rows if row[column.id] is not None):
                        raise ValueError("Dataset has an unknown fact reference")
        children = {}
        for node in self.nodes:
            if isinstance(node, Section):
                if len(node.children) != len(set(node.children)) or any(child not in nodes for child in node.children):
                    raise ValueError("Section contains duplicate or unknown children")
                children[node.id] = node.children
            else:
                children[node.id] = []
            if isinstance(node, RichText):
                if any(isinstance(run, FactRun) and run.fact_id not in self.facts for run in node.runs):
                    raise ValueError("Rich text contains an unknown fact reference")
                if node.mode == "computed" and node.editable:
                    raise ValueError("Computed prose cannot be freely editable")
                if node.mode == "computed" and any(isinstance(run, TextRun) and re.search(r"\d|[%€$£]", run.text) for run in node.runs):
                    raise ValueError("Computed numeric prose must use controlled fact references")
            if isinstance(node, (Table, Pivot, Chart)):
                if node.dataset_id not in self.datasets:
                    raise ValueError("Node refers to an unknown dataset")
                columns = {c.id: c for c in self.datasets[node.dataset_id].columns}
                if isinstance(node, Pivot):
                    if node.materialized_dataset_id not in self.datasets:
                        raise ValueError("Pivot requires an existing materialized dataset")
                    dimensions = node.row_dimensions + node.column_dimensions
                    if len(dimensions) != len(set(dimensions)) or any(d not in columns for d in dimensions):
                        raise ValueError("Invalid pivot dimensions")
                    for measure in node.measures:
                        if measure.column_id not in columns or columns[measure.column_id].type not in {"decimal", "integer"}:
                            raise ValueError("Pivot measures must reference numeric columns")
                if isinstance(node, Chart):
                    if node.category_column not in columns:
                        raise ValueError("Unknown chart category column")
                    for series in node.series:
                        if series.column_id not in columns or columns[series.column_id].type not in {"decimal", "integer"}:
                            raise ValueError("Chart series must reference numeric columns")
            if isinstance(node, Image) and node.asset_id not in assets:
                raise ValueError("Image refers to an unknown bound asset")
        _acyclic(children, "content")
        roots = set(nodes) - {child for refs in children.values() for child in refs}
        if len(roots) != 1 or not isinstance(nodes[next(iter(roots))], Section):
            raise ValueError("Content must have one section root with no orphan nodes")
        leaves = {n.id for n in self.nodes if not isinstance(n, Section)}
        for view in self.views:
            included = set(view.node_ids)
            required = set(view.coverage.required_node_ids)
            omitted = set(view.coverage.omitted_node_ids)
            if len(included) != len(view.node_ids) or not included <= leaves:
                raise ValueError("Views require unique existing leaf IDs")
            if required != included or included & omitted or included | omitted != leaves:
                raise ValueError("View coverage must account for every leaf exactly once")
            if view.coverage.scope == "complete" and omitted:
                raise ValueError("Complete views cannot omit content")
        if self.status == "accepted" and any(f.severity in {"block", "review"} for f in self.findings):
            raise ValueError("Accepted snapshots cannot contain unresolved block/review findings")
        if self.status == "review_required" and any(f.severity == "block" for f in self.findings):
            raise ValueError("Blocking findings require blocked status")
        return self


def _acyclic(graph: dict[str, list[str]], label: str):
    visiting, visited = set(), set()

    def visit(key):
        if key in visiting:
            raise ValueError(f"Cycle in {label} references")
        if key in visited:
            return
        visiting.add(key)
        for parent in graph[key]:
            visit(parent)
        visiting.remove(key)
        visited.add(key)

    for key in graph:
        visit(key)
