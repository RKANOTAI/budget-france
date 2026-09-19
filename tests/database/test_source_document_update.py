from __future__ import annotations

from sqlalchemy import Engine, text

from tests.database.support import seed_release


def test_authorized_draft_source_document_update_returns_new_row(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="source-update-1")
        connection.execute(
            text(
                """
                UPDATE source_documents
                SET media_type = 'application/json'
                WHERE id = :document_id
                """
            ),
            {"document_id": release.document_id},
        )
        media_type = connection.execute(
            text("SELECT media_type FROM source_documents WHERE id = :document_id"),
            {"document_id": release.document_id},
        ).scalar_one()
    assert media_type == "application/json"
