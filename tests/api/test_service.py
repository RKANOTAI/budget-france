from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session

from api.service import DatabaseBudgetService
from tests.database.support import seed_release


def _publish(connection: Connection, release_id: object) -> None:
    connection.execute(
        text("SELECT budget_validate_release(:release_id, :validator)"),
        {"release_id": release_id, "validator": "api-test"},
    )
    connection.execute(
        text("SELECT budget_publish_release(:release_id)"),
        {"release_id": release_id},
    )


def test_database_service_returns_published_tree_and_node(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        release = seed_release(connection, version="api-service-1")
        _publish(connection, release.release_id)

    with Session(postgres_engine) as session:
        service = DatabaseBudgetService(session)
        tree = service.tree(fiscal_year=2026, legal_stage="PLF")
        node = service.node(
            node_id=release.node_id,
            fiscal_year=2026,
            legal_stage="PLF",
        )

    assert tree.release.version == "api-service-1"
    assert len(tree.roots) == 1
    assert tree.roots[0].id == release.node_id
    assert node.id == release.node_id
    assert node.provenance[0].locator == "row=1"
    assert node.budget.ae == 0
