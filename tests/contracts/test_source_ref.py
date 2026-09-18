from datetime import UTC, date, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.contracts.models import SourceRef

SHA256 = "a" * 64
SOURCE_ID = UUID("00000000-0000-4000-8000-000000000001")


def _source(**overrides: object) -> SourceRef:
    values: dict[str, object] = {
        "source_fragment_id": SOURCE_ID,
        "url": "https://www.budget.gouv.fr/documentation/file-download/32270",
        "sha256": SHA256,
        "locator": "page=12;table=3",
        "legal_stage": "LFI",
        "document_type": "LFI",
        "retrieved_at": datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
        "source_version": "2026.1",
    }
    values.update(overrides)
    return SourceRef(**values)  # type: ignore[arg-type]


def test_source_ref_requires_canonical_complete_provenance() -> None:
    source = _source(publication_date=date(2025, 12, 20))
    restored = SourceRef.model_validate_json(source.model_dump_json())

    assert source.source_fragment_id == SOURCE_ID
    assert source.sha256 == SHA256
    assert source.legal_stage == "LFI"
    assert source.retrieved_at.tzinfo is UTC
    assert source.publication_date == date(2025, 12, 20)
    assert '"sha256"' in source.model_dump_json()
    assert '"hash"' not in source.model_dump_json()
    assert restored == source

    retrieved_at_schema = SourceRef.model_json_schema()["properties"]["retrieved_at"]
    assert retrieved_at_schema["pattern"] == "Z$"


def test_source_ref_rejects_missing_or_invalid_provenance() -> None:
    with pytest.raises(ValidationError):
        SourceRef(
            url="https://example.test/source",  # type: ignore[arg-type]
            sha256=SHA256,
            locator="page=1",
            legal_stage="PLF",
            document_type="PAP",
            retrieved_at=datetime(2026, 1, 15, tzinfo=UTC),
            source_version="2026.1",
        )  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        _source(url="not-a-url")
    with pytest.raises(ValidationError):
        _source(sha256="bad")
    with pytest.raises(ValidationError):
        _source(retrieved_at=datetime(2026, 1, 15))
    with pytest.raises(ValidationError):
        _source(retrieved_at=datetime(2026, 1, 15, tzinfo=timezone(timedelta(hours=1))))
    with pytest.raises(ValidationError):
        SourceRef(**{**_source().model_dump(), "extra": "x"})


def test_source_ref_rejects_undocumented_provenance_aliases() -> None:
    with pytest.raises(ValidationError):
        SourceRef(
            url="https://example.test/source",  # type: ignore[arg-type]
            hash=SHA256,
            localisateur="cellule=B12",
        )  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        SourceRef(
            url="https://example.test/source",  # type: ignore[arg-type]
            sha256=SHA256,
            localisateur="cellule=B12",
        )  # type: ignore[call-arg]
