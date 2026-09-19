from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID, uuid5

import httpx
import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.connection import create_database_engine
from database.models import (
    AmountSourceFragment,
    BudgetAmount,
    BudgetNode,
    Release,
    ReleaseSourceDocument,
    SourceDocument,
    SourceFragment,
)
from database.repository import ReleaseRepository
from database.settings import DatabaseSettings

SOURCE_URLS = {
    2025: "https://www.budget.gouv.fr/documentation/file-download/25307",
    2026: "https://www.budget.gouv.fr/documentation/file-download/31618",
}
SOURCE_VERSIONS = {
    2025: "plf-2025-20241011",
    2026: "plf-2026-20251024",
}
SOURCE_PUBLICATION_DATES = {
    2025: date(2024, 10, 11),
    2026: date(2025, 10, 24),
}

NodeKey = tuple[str, ...]


@dataclass(frozen=True)
class BudgetRecord:
    node_type: Literal["mission", "programme", "action"]
    key: NodeKey
    parent_key: NodeKey | None
    code: str
    name: str
    ae: Decimal
    cp: Decimal


def aggregate_budget_rows(rows: list[dict[str, object]]) -> list[BudgetRecord]:
    """Aggregate official action rows into a reconciled three-level hierarchy."""

    records: dict[NodeKey, BudgetRecord] = {}
    for row in rows:
        if _text(row.get("type_mission")) != "BG":
            continue
        mission_code = _text(row.get("mission_code"))
        mission_name = _text(row.get("mission"))
        programme_code = _text(row.get("programme_code"))
        programme_name = _text(row.get("programme_name"))
        action_code = _text(row.get("action_code"))
        action_name = _text(row.get("action_name"))
        if not all(
            (mission_code, mission_name, programme_code, programme_name, action_code, action_name)
        ):
            continue

        amount_ae = _amount(row.get("ae"))
        amount_cp = _amount(row.get("cp"))
        levels = (
            ("mission", ("mission", mission_code), None, mission_code, mission_name),
            (
                "programme",
                ("programme", mission_code, programme_code),
                ("mission", mission_code),
                programme_code,
                programme_name,
            ),
            (
                "action",
                ("action", mission_code, programme_code, action_code),
                ("programme", mission_code, programme_code),
                action_code,
                action_name,
            ),
        )
        for node_type, key, parent_key, code, name in levels:
            current = records.get(key)
            if current is None:
                records[key] = BudgetRecord(
                    node_type=node_type,  # type: ignore[arg-type]
                    key=key,
                    parent_key=parent_key,
                    code=code,
                    name=name,
                    ae=amount_ae,
                    cp=amount_cp,
                )
            else:
                records[key] = BudgetRecord(
                    node_type=current.node_type,
                    key=current.key,
                    parent_key=current.parent_key,
                    code=current.code,
                    name=current.name,
                    ae=current.ae + amount_ae,
                    cp=current.cp + amount_cp,
                )

    order = {"mission": 0, "programme": 1, "action": 2}
    return sorted(
        records.values(),
        key=lambda record: (
            order[record.node_type],
            record.parent_key or (),
            record.code,
            record.name,
            record.key,
        ),
    )


def load_official_rows(payload: bytes) -> list[dict[str, object]]:
    """Read the first worksheet of an official XLS workbook into canonical rows."""

    with tempfile.NamedTemporaryFile(suffix=".xls") as temporary:
        temporary.write(payload)
        temporary.flush()
        dataframe = pl.read_excel(temporary.name, sheet_id=1)
    columns = _resolve_columns(dataframe.columns)
    rows: list[dict[str, object]] = []
    for row in dataframe.iter_rows(named=True):
        rows.append({name: row[column] for name, column in columns.items()})
    return rows


def download_source(url: str) -> bytes:
    headers = {
        "Accept": (
            "application/vnd.ms-excel, "
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        "User-Agent": "budget-france-ingestion/0.1 (+https://github.com/RKANOTAI/budget-france)",
    }
    with httpx.Client(follow_redirects=True, timeout=120, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
    payload = response.content
    if payload.lstrip().lower().startswith(b"<html"):
        raise RuntimeError("official source returned an HTML block page instead of the workbook")
    return payload


def ingest_release(
    *,
    fiscal_year: int,
    source_url: str,
    source_version: str,
    publication_date: date,
) -> tuple[UUID, int]:
    payload = download_source(source_url)
    snapshot_hash = hashlib.sha256(payload).hexdigest()
    rows = load_official_rows(payload)
    records = aggregate_budget_rows(rows)
    if not records:
        raise RuntimeError("official source did not produce any Budget général records")

    collected_at = datetime.now(UTC)
    engine = create_database_engine(DatabaseSettings())
    try:
        with Session(engine) as session, session.begin():
            existing = session.scalar(
                select(Release).where(
                    Release.fiscal_year == fiscal_year,
                    Release.legal_stage == "PLF",
                    Release.version == source_version,
                )
            )
            if existing is not None:
                raise RuntimeError(f"release {source_version} already exists")

            release = Release(
                fiscal_year=fiscal_year,
                legal_stage="PLF",
                version=source_version,
                source_snapshot_hash=snapshot_hash,
                created_at=collected_at,
            )
            document = SourceDocument(
                url=source_url,
                document_type="XLS",
                legal_stage="PLF",
                fiscal_year=fiscal_year,
                source_version=source_version,
                collected_at=collected_at,
                sha256=snapshot_hash,
                publication_date=publication_date,
                media_type="application/vnd.ms-excel",
                media_metadata={"source_row_count": len(rows), "budget_node_count": len(records)},
            )
            session.add_all([release, document])
            session.flush()
            session.add(
                ReleaseSourceDocument(release_id=release.id, source_document_id=document.id)
            )

            node_ids = {
                record.key: uuid5(release.id, "node:" + "/".join(record.key)) for record in records
            }
            for record in records:
                session.add(
                    BudgetNode(
                        id=node_ids[record.key],
                        release_id=release.id,
                        parent_id=(
                            node_ids[record.parent_key] if record.parent_key is not None else None
                        ),
                        node_type=record.node_type,
                        code=record.code,
                        slug=_slug(record.key, record.name),
                        name=record.name,
                    )
                )
            session.flush()

            for record in records:
                content = json.dumps(
                    {
                        "node_type": record.node_type,
                        "code": record.code,
                        "name": record.name,
                        "ae": format(record.ae, "f"),
                        "cp": format(record.cp, "f"),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                fragment = SourceFragment(
                    id=uuid5(release.id, "fragment:" + "/".join(record.key)),
                    source_document_id=document.id,
                    fragment_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    locator="/".join(f"{key}={value}" for key, value in _locator(record)),
                    content=content,
                )
                session.add(fragment)
                for metric, amount in (("AE", record.ae), ("CP", record.cp)):
                    amount_row = BudgetAmount(
                        id=uuid5(release.id, f"amount:{'/'.join(record.key)}:{metric}"),
                        node_id=node_ids[record.key],
                        metric=metric,
                        amount=amount,
                        unit="EUR",
                        aggregation="sum_of_source_rows",
                    )
                    session.add(amount_row)
                    session.add(
                        AmountSourceFragment(
                            amount_id=amount_row.id,
                            source_fragment_id=fragment.id,
                        )
                    )
            session.flush()
            repository = ReleaseRepository(session)
            repository.validate_release(release.id, validator="official-budget-ingestion")
            repository.publish_release(release.id)
            return release.id, len(records)
    finally:
        engine.dispose()


def _resolve_columns(columns: list[str]) -> dict[str, str]:
    normalized = {_header_key(column): column for column in columns}
    aliases = {
        "type_mission": ("type mission",),
        "mission": ("mission",),
        "mission_code": ("code mission",),
        "programme_code": ("programme",),
        "programme_name": ("libelle programme",),
        "action_code": ("action",),
        "action_name": ("libelle action",),
        "ae": ("ae plf", "ae plf 2026", "ae plf 2025"),
        "cp": ("cp plf", "cp plf 2026", "cp plf 2025"),
    }
    resolved: dict[str, str] = {}
    for target, candidates in aliases.items():
        for candidate in candidates:
            if candidate in normalized:
                resolved[target] = normalized[candidate]
                break
        if target not in resolved:
            raise ValueError(f"official workbook is missing required column: {target}")
    return resolved


def _header_key(value: str) -> str:
    return " ".join(str(value).replace("\xa0", " ").split()).casefold()


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _amount(value: object) -> Decimal:
    text = _text(value).replace("\u202f", "").replace(" ", "").replace(",", "")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"invalid budget amount: {value!r}") from error


def _slug(key: NodeKey, name: str) -> str:
    raw = unicodedata.normalize("NFKD", f"{'-'.join(key)}-{name}")
    ascii_text = raw.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return slug or "budget-node"


def _locator(record: BudgetRecord) -> tuple[tuple[str, str], ...]:
    if record.node_type == "mission":
        return (("mission", record.code),)
    if record.node_type == "programme":
        return (("mission", record.key[1]), ("programme", record.code))
    return (
        ("mission", record.key[1]),
        ("programme", record.key[2]),
        ("action", record.code),
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fiscal-year", type=int, choices=(2025, 2026), required=True)
    parser.add_argument("--url")
    parser.add_argument("--version")
    parser.add_argument("--publication-date")
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    fiscal_year = arguments.fiscal_year
    publication_date = (
        date.fromisoformat(arguments.publication_date)
        if arguments.publication_date
        else SOURCE_PUBLICATION_DATES[fiscal_year]
    )
    release_id, node_count = ingest_release(
        fiscal_year=fiscal_year,
        source_url=arguments.url or SOURCE_URLS[fiscal_year],
        source_version=arguments.version or SOURCE_VERSIONS[fiscal_year],
        publication_date=publication_date,
    )
    print(f"published release {release_id} with {node_count} budget nodes")


if __name__ == "__main__":
    main()
