from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.database.support import seed_release


def test_validation_rejects_a_release_without_any_amount(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="v1", with_amount=False)
        try:
            connection.execute(
                text("SELECT budget_validate_release(:release_id, :validator)"),
                {"release_id": release.release_id, "validator": "test"},
            )
        except DBAPIError as error:
            assert "has no budget amounts" in str(error)
        else:
            raise AssertionError("a release without amounts must fail closed")


def test_validation_rejects_an_unsourced_amount(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="v2", with_source=False)
        try:
            connection.execute(
                text("SELECT budget_validate_release(:release_id, :validator)"),
                {"release_id": release.release_id, "validator": "test"},
            )
        except DBAPIError as error:
            assert "unsourced budget amount" in str(error)
        else:
            raise AssertionError("an unsourced amount must fail closed")


def test_validation_rejects_a_blocking_anomaly(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="v3")
        connection.execute(
            text(
                """
                INSERT INTO anomalies (release_id, code, severity, message, blocked)
                VALUES (:release_id, 'MISSING_SOURCE', 'critical', 'blocked', true)
                """
            ),
            {"release_id": release.release_id},
        )
        try:
            connection.execute(
                text("SELECT budget_validate_release(:release_id, :validator)"),
                {"release_id": release.release_id, "validator": "test"},
            )
        except DBAPIError as error:
            assert "blocking anomaly" in str(error)
        else:
            raise AssertionError("a blocking anomaly must prevent validation")


def test_validated_release_publishes_and_updates_year_stage_pointer(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="v4")
        connection.execute(
            text("SELECT budget_validate_release(:release_id, :validator)"),
            {"release_id": release.release_id, "validator": "test"},
        )
        published_id = connection.execute(
            text("SELECT budget_publish_release(:release_id)"),
            {"release_id": release.release_id},
        ).scalar_one()
        status = connection.execute(
            text("SELECT status FROM releases WHERE id = :release_id"),
            {"release_id": release.release_id},
        ).scalar_one()
        pointer = connection.execute(
            text(
                """
                SELECT release_id
                FROM published_releases
                WHERE fiscal_year = 2026 AND legal_stage = 'PLF'
                """
            )
        ).scalar_one()

    assert published_id == release.release_id
    assert status == "published"
    assert pointer == release.release_id
