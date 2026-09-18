from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.contracts.models import ReleaseInfo

RELEASE_ID = UUID("00000000-0000-4000-8000-000000000010")
SNAPSHOT_HASH = "a" * 64


def test_release_info_is_immutable_release_metadata() -> None:
    released_at = datetime(2026, 1, 15, 10, 30, tzinfo=UTC)
    release = ReleaseInfo(
        release_id=RELEASE_ID,
        version="2026.1",
        released_at=released_at,
        fiscal_year=2026,  # type: ignore[arg-type]
        source_snapshot_hash=SNAPSHOT_HASH,
    )

    assert release.release_id == RELEASE_ID
    assert release.released_at == released_at
    assert release.source_snapshot_hash == SNAPSHOT_HASH

    with pytest.raises(ValidationError):
        release.version = "2026.2"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ReleaseInfo(
            release_id=RELEASE_ID,
            version="1",
            released_at=released_at,
            fiscal_year=2026,  # type: ignore[arg-type]
            source_snapshot_hash=SNAPSHOT_HASH,
            extra="x",
        )  # type: ignore[call-arg]


def test_release_info_accepts_supported_year_from_json_shape() -> None:
    release = ReleaseInfo(
        release_id=RELEASE_ID,
        version="2026.1",
        released_at=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
        fiscal_year=2026,  # type: ignore[arg-type]
        source_snapshot_hash=SNAPSHOT_HASH,
    )
    restored = ReleaseInfo.model_validate_json(release.model_dump_json())

    assert release.fiscal_year.value == 2026
    assert restored == release


def test_release_id_is_a_uuid() -> None:
    with pytest.raises(ValidationError):
        ReleaseInfo(
            release_id="release-2026-01",  # type: ignore[arg-type]
            version="2026.1",
            released_at=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
            fiscal_year=2026,  # type: ignore[arg-type]
            source_snapshot_hash=SNAPSHOT_HASH,
        )

    release = ReleaseInfo(
        release_id=RELEASE_ID,
        version="2026.1",
        released_at=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
        fiscal_year=2026,  # type: ignore[arg-type]
        source_snapshot_hash=SNAPSHOT_HASH,
    )
    assert release.release_id == RELEASE_ID
