from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.database.support import seed_release


def test_release_status_transitions_are_database_controlled(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="status-1")
    with postgres_engine.begin() as connection, pytest.raises(DBAPIError):
        connection.execute(
            text("UPDATE releases SET status = 'validated' WHERE id = :release_id"),
            {"release_id": release.release_id},
        )
    with postgres_engine.begin() as connection:
        connection.execute(
            text("SELECT budget_reject_release(:release_id)"),
            {"release_id": release.release_id},
        )
        status = connection.execute(
            text("SELECT status FROM releases WHERE id = :release_id"),
            {"release_id": release.release_id},
        ).scalar_one()
    assert status == "rejected"
