import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import IntEnum, StrEnum
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    WithJsonSchema,
    field_validator,
    model_validator,
)


def _parse_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("amount must be a finite decimal")
        return value
    if isinstance(value, str):
        if not _DECIMAL_PATTERN.fullmatch(value):
            raise ValueError("amount must be a canonical decimal string")
        try:
            return Decimal(value)
        except InvalidOperation as error:
            raise ValueError("amount must be a valid decimal") from error
    raise ValueError("amount must be a Decimal or canonical decimal string")


def _serialize_decimal(value: Decimal) -> str:
    return format(value, "f")


def _as_immutable_tuple(value: object) -> object:
    """Convert JSON arrays before strict tuple validation."""

    if isinstance(value, list):
        return tuple(value)
    return value


def _require_utc_timestamp(value: object, field_name: str) -> object:
    """Normalize UTC datetimes and require the canonical JSON ``Z`` suffix."""

    if isinstance(value, str):
        if not value.endswith("Z"):
            raise ValueError(f"{field_name} must use a UTC timestamp ending in Z")
        try:
            value = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError:
            return value
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return value.astimezone(UTC)


TREE_NODE_HIERARCHY_RULES: list[dict[str, Any]] = [
    {
        "if": {"properties": {"node_type": {"const": "mission"}}},
        "then": {
            "properties": {
                "children": {"items": {"properties": {"node_type": {"const": "programme"}}}}
            }
        },
    },
    {
        "if": {"properties": {"node_type": {"const": "programme"}}},
        "then": {
            "properties": {
                "children": {"items": {"properties": {"node_type": {"const": "action"}}}}
            }
        },
    },
    {
        "if": {"properties": {"node_type": {"const": "action"}}},
        "then": {"properties": {"children": {"maxItems": 0}}},
    },
]


NODE_DETAIL_RELATION_RULES: list[dict[str, Any]] = [
    {
        "if": {"properties": {"node_type": {"const": "mission"}}},
        "then": {"properties": {"parent": {"type": "null"}}},
    },
    {
        "if": {"properties": {"node_type": {"const": "programme"}}},
        "then": {
            "required": ["parent"],
            "properties": {
                "parent": {
                    "allOf": [
                        {"type": "object"},
                        {"properties": {"node_type": {"const": "mission"}}},
                    ]
                }
            },
        },
    },
    {
        "if": {"properties": {"node_type": {"const": "action"}}},
        "then": {
            "required": ["parent"],
            "properties": {
                "parent": {
                    "allOf": [
                        {"type": "object"},
                        {"properties": {"node_type": {"const": "programme"}}},
                    ]
                }
            },
        },
    },
]


ANOMALY_SCHEMA_RULES: list[dict[str, Any]] = [
    {
        "if": {"properties": {"severity": {"enum": ["error", "critical"]}}},
        "then": {"required": ["blocked"], "properties": {"blocked": {"const": True}}},
    }
]


HTTP_URL_PATTERN = (
    r"^https?://"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:[/?#][^\s]*)?$"
)
_HTTP_URL_PATTERN = re.compile(HTTP_URL_PATTERN)


DECIMAL_PATTERN = r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"
_DECIMAL_PATTERN = re.compile(DECIMAL_PATTERN)


DecimalString = Annotated[
    Decimal,
    BeforeValidator(_parse_decimal),
    PlainSerializer(_serialize_decimal, return_type=str, when_used="json"),
    WithJsonSchema(
        {"type": "string", "pattern": DECIMAL_PATTERN},
        mode="serialization",
    ),
]


class ContractModel(BaseModel):
    """Base configuration shared by every public contract model."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")


class FiscalYear(IntEnum):
    """Fiscal years covered by the MVP contracts."""

    Y2025 = 2025
    Y2026 = 2026


class NodeType(StrEnum):
    """The three levels of the budget tree."""

    MISSION = "mission"
    PROGRAMME = "programme"
    ACTION = "action"


class MatchKind(StrEnum):
    """How a search hit matched the query."""

    EXACT = "exact"
    LEXICAL = "lexical"
    SEMANTIC = "semantic"


class ReleaseInfo(ContractModel):
    """Metadata identifying an immutable published release."""

    release_id: UUID
    version: str = Field(min_length=1)
    released_at: datetime = Field(json_schema_extra={"pattern": "Z$"})
    fiscal_year: FiscalYear
    source_snapshot_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-fA-F]{64}$",
    )

    @field_validator("released_at", mode="before")
    @classmethod
    def _require_released_at_utc(cls, value: object) -> object:
        return _require_utc_timestamp(value, "released_at")

    @field_validator("fiscal_year", mode="before")
    @classmethod
    def _coerce_year_from_wire(cls, value: object) -> object:
        if value is None or isinstance(value, FiscalYear):
            return value
        if type(value) is int:
            try:
                return FiscalYear(value)
            except ValueError:
                return value
        return value


class Money(ContractModel):
    """A euro amount serialized as a decimal string on the wire."""

    amount: DecimalString
    currency: Literal["EUR"] = "EUR"


class BudgetValue(ContractModel):
    """Separated authorisations (AE) and payment credits (CP)."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        json_schema_extra={
            "anyOf": [
                {
                    "required": ["ae"],
                    "properties": {
                        "ae": {"type": "string", "pattern": DECIMAL_PATTERN},
                    },
                },
                {
                    "required": ["cp"],
                    "properties": {
                        "cp": {"type": "string", "pattern": DECIMAL_PATTERN},
                    },
                },
            ],
        },
    )

    ae: DecimalString | None = None
    cp: DecimalString | None = None
    currency: Literal["EUR"] = "EUR"

    @model_validator(mode="after")
    def _require_one_measure(self) -> "BudgetValue":
        if self.ae is None and self.cp is None:
            raise ValueError("at least one of ae or cp is required")
        return self


class SourceRef(ContractModel):
    """A verifiable reference to a source document fragment."""

    source_fragment_id: UUID
    url: AnyHttpUrl = Field(json_schema_extra={"pattern": HTTP_URL_PATTERN})
    sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-fA-F]{64}$",
    )
    locator: str = Field(min_length=1)
    legal_stage: Literal["PLF", "LFI"]
    document_type: str = Field(min_length=1)
    retrieved_at: datetime = Field(json_schema_extra={"pattern": "Z$"})
    source_version: str = Field(min_length=1)
    publication_date: date | None = None

    @field_validator("url")
    @classmethod
    def _require_http_scheme(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if not _HTTP_URL_PATTERN.fullmatch(str(value)):
            raise ValueError("url must use HTTP or HTTPS with a non-empty hostname")
        return value

    @field_validator("retrieved_at", mode="before")
    @classmethod
    def _require_utc(cls, value: object) -> object:
        return _require_utc_timestamp(value, "retrieved_at")


class Explanation(ContractModel):
    """Source-grounded prose; limitations must state when context is unavailable."""

    summary: str = Field(min_length=1)
    what_it_funds: str = Field(min_length=1)
    main_changes: str = Field(min_length=1)
    limitations: str = Field(min_length=1)
    source_fragment_ids: Annotated[tuple[UUID, ...], BeforeValidator(_as_immutable_tuple)] = Field(
        min_length=1,
    )


class TreeNode(ContractModel):
    """One node of the Mission → Programme → Action tree."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        json_schema_extra=cast(Any, {"allOf": TREE_NODE_HIERARCHY_RULES}),
    )

    id: UUID
    node_type: NodeType
    name: str = Field(min_length=1)
    code: str | None = Field(default=None, min_length=1)
    budget: BudgetValue
    children: Annotated[tuple["TreeNode", ...], BeforeValidator(_as_immutable_tuple)] = ()
    source_refs: Annotated[tuple[SourceRef, ...], BeforeValidator(_as_immutable_tuple)] = Field(
        min_length=1,
    )

    @field_validator("node_type", mode="before")
    @classmethod
    def _coerce_node_type_from_wire(cls, value: object) -> object:
        if isinstance(value, NodeType):
            return value
        if type(value) is str:
            try:
                return NodeType(value)
            except ValueError:
                return value
        return value

    @model_validator(mode="after")
    def _validate_children(self) -> "TreeNode":
        expected_child_type = {
            NodeType.MISSION: NodeType.PROGRAMME,
            NodeType.PROGRAMME: NodeType.ACTION,
            NodeType.ACTION: None,
        }[self.node_type]
        for child in self.children:
            if expected_child_type is None or child.node_type != expected_child_type:
                raise ValueError("tree node children must follow Mission → Programme → Action")
        return self


class TreeResponse(ContractModel):
    """Published tree root together with the release that produced it."""

    release: ReleaseInfo
    root: TreeNode

    @model_validator(mode="after")
    def _validate_unique_node_ids(self) -> "TreeResponse":
        seen_ids: set[UUID] = set()
        pending = [self.root]
        while pending:
            node = pending.pop()
            if node.id in seen_ids:
                raise ValueError("tree response node UUIDs must be unique")
            seen_ids.add(node.id)
            pending.extend(node.children)
        return self


class TreeCollection(ContractModel):
    """All published Mission roots for one release."""

    release: ReleaseInfo
    roots: Annotated[tuple[TreeNode, ...], BeforeValidator(_as_immutable_tuple)] = Field(
        min_length=1,
    )

    @model_validator(mode="after")
    def _validate_unique_node_ids(self) -> "TreeCollection":
        seen_ids: set[UUID] = set()
        pending = list(self.roots)
        while pending:
            node = pending.pop()
            if node.id in seen_ids:
                raise ValueError("tree response node UUIDs must be unique")
            seen_ids.add(node.id)
            pending.extend(node.children)
        return self


class HistoryPoint(ContractModel):
    """One fiscal-year budget value in a node's history."""

    year: FiscalYear
    budget: BudgetValue
    provenance: Annotated[tuple[SourceRef, ...], BeforeValidator(_as_immutable_tuple)] = Field(
        min_length=1,
    )

    @field_validator("year", mode="before")
    @classmethod
    def _coerce_year_from_wire(cls, value: object) -> object:
        if isinstance(value, FiscalYear):
            return value
        if type(value) is int:
            try:
                return FiscalYear(value)
            except ValueError:
                return value
        return value


HistoricalValue = HistoryPoint


class NodeDetail(ContractModel):
    """Detailed node view with release, history, provenance, and explanation."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        json_schema_extra=cast(
            Any,
            {"allOf": TREE_NODE_HIERARCHY_RULES + NODE_DETAIL_RELATION_RULES},
        ),
    )

    id: UUID
    release: ReleaseInfo
    node_type: NodeType
    name: str = Field(min_length=1)
    code: str | None = Field(default=None, min_length=1)
    budget: BudgetValue
    description: str | None = Field(default=None, min_length=1)
    parent: TreeNode | None = None
    children: Annotated[tuple[TreeNode, ...], BeforeValidator(_as_immutable_tuple)] = ()
    history: Annotated[tuple[HistoryPoint, ...], BeforeValidator(_as_immutable_tuple)] = ()
    provenance: Annotated[tuple[SourceRef, ...], BeforeValidator(_as_immutable_tuple)] = Field(
        min_length=1,
    )
    explanation: Explanation | None = None

    @field_validator("node_type", mode="before")
    @classmethod
    def _coerce_node_type_from_wire(cls, value: object) -> object:
        if isinstance(value, NodeType):
            return value
        if type(value) is str:
            try:
                return NodeType(value)
            except ValueError:
                return value
        return value

    @model_validator(mode="after")
    def _validate_relationships(self) -> "NodeDetail":
        expected_parent_type = {
            NodeType.MISSION: None,
            NodeType.PROGRAMME: NodeType.MISSION,
            NodeType.ACTION: NodeType.PROGRAMME,
        }[self.node_type]
        if expected_parent_type is None:
            if self.parent is not None:
                raise ValueError("mission node detail cannot have a parent")
        elif self.parent is None or self.parent.node_type != expected_parent_type:
            raise ValueError("node detail parent must be the preceding budget level")

        expected_child_type = {
            NodeType.MISSION: NodeType.PROGRAMME,
            NodeType.PROGRAMME: NodeType.ACTION,
            NodeType.ACTION: None,
        }[self.node_type]
        for child in self.children:
            if expected_child_type is None or child.node_type != expected_child_type:
                raise ValueError("node detail children must follow Mission → Programme → Action")
        return self


class SearchHit(ContractModel):
    """A deterministic search result, never an explanation."""

    node_id: UUID
    node_type: NodeType
    name: str = Field(min_length=1)
    code: str | None = Field(default=None, min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    match_kind: MatchKind = Field(
        description=(
            "exact or lexical is a direct match; semantic is a reconstruction, not an exact result"
        )
    )

    @field_validator("node_type", mode="before")
    @classmethod
    def _coerce_node_type_from_wire(cls, value: object) -> object:
        if isinstance(value, NodeType):
            return value
        if type(value) is str:
            try:
                return NodeType(value)
            except ValueError:
                return value
        return value

    @field_validator("match_kind", mode="before")
    @classmethod
    def _coerce_match_kind_from_wire(cls, value: object) -> object:
        if isinstance(value, MatchKind):
            return value
        if type(value) is str:
            try:
                return MatchKind(value)
            except ValueError:
                return value
        return value


class SearchResponse(ContractModel):
    """Search hits tied to the immutable release queried."""

    query: str = Field(min_length=1)
    hits: Annotated[tuple[SearchHit, ...], BeforeValidator(_as_immutable_tuple)] = ()
    total: int = Field(ge=0)
    release: ReleaseInfo


class AnomalySummary(ContractModel):
    """A publication-review finding emitted by validation."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        json_schema_extra=cast(Any, {"allOf": ANOMALY_SCHEMA_RULES}),
    )

    code: str = Field(min_length=1)
    severity: Literal["info", "warning", "error", "critical"]
    message: str = Field(min_length=1)
    node_id: UUID | None = None
    blocked: bool = False
    details: Annotated[tuple[str, ...], BeforeValidator(_as_immutable_tuple)] = ()

    @model_validator(mode="after")
    def _require_blocking_for_publication_risk(self) -> "AnomalySummary":
        if self.severity in {"error", "critical"} and not self.blocked:
            raise ValueError("error and critical anomalies must be blocked")
        return self


class ApiResponse[T](ContractModel):
    """Successful API envelope carrying a typed payload."""

    data: T
    request_id: UUID | None = None


class TreeApiResponse(ApiResponse[TreeResponse]):
    """API envelope for a published budget tree."""


class TreeCollectionApiResponse(ApiResponse[TreeCollection]):
    """API envelope for all published budget tree roots."""


class NodeApiResponse(ApiResponse[NodeDetail]):
    """API envelope for a detailed budget node."""


class SearchApiResponse(ApiResponse[SearchResponse]):
    """API envelope for search results."""


class ProblemDetails(ContractModel):
    """RFC 7807 problem detail document."""

    type: str = Field(default="about:blank", min_length=1)
    title: str = Field(min_length=1)
    status: int = Field(ge=100, le=599)
    detail: str | None = Field(default=None, min_length=1)
    instance: str | None = Field(default=None, min_length=1)
