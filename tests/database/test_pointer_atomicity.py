from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.database.support import seed_release


def test_publishing_a_new_release_replaces_pointer_atomically(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as connection:
        first = seed_release(connection, version="pointer-1")
        connection.execute(
            text("SELECT budget_validate_release(:release_id, :validator)"),
            {"release_id": first.release_id, "validator": "test"},
        )
        connection.execute(
            text("SELECT budget_publish_release(:release_id)"),
            {"release_id": first.release_id},
        )

    with postgres_engine.begin() as connection:
        second = seed_release(connection, version="pointer-2")
        connection.execute(
            text("SELECT budget_validate_release(:release_id, :validator)"),
            {"release_id": second.release_id, "validator": "test"},
        )
        connection.execute(
            text("SELECT budget_publish_release(:release_id)"),
            {"release_id": second.release_id},
        )
        pointer_release_id = connection.execute(
            text(
                """
                SELECT release_id
                FROM published_releases
                WHERE fiscal_year = :fiscal_year AND legal_stage = :legal_stage
                """
            ),
            {"fiscal_year": 2026, "legal_stage": "PLF"},
        ).scalar_one()
        published_count = connection.execute(
            text(
                """
                SELECT count(*)
                FROM releases
                WHERE fiscal_year = 2026 AND legal_stage = 'PLF' AND status = 'published'
                """
            )
        ).scalar_one()

    with postgres_engine.begin() as connection, pytest.raises(DBAPIError):
        connection.execute(
            text(
                """
                UPDATE published_releases
                SET published_at = now()
                WHERE fiscal_year = 2026 AND legal_stage = 'PLF'
                """
            )
        )

    assert pointer_release_id == second.release_id
    assert published_count == 2
