from decimal import Decimal

from scripts.ingest_budget import aggregate_budget_rows


def test_aggregate_budget_rows_builds_reconciled_mission_programme_action_totals() -> None:
    rows = [
        {
            "type_mission": "BG",
            "mission": "Justice",
            "mission_code": "JA",
            "programme_code": "101",
            "programme_name": "Accès au droit",
            "action_code": "01",
            "action_name": "Aide juridictionnelle",
            "ae": "100",
            "cp": "90",
        },
        {
            "type_mission": "BG",
            "mission": "Justice",
            "mission_code": "JA",
            "programme_code": "101",
            "programme_name": "Accès au droit",
            "action_code": "01",
            "action_name": "Aide juridictionnelle",
            "ae": "25",
            "cp": "30",
        },
        {
            "type_mission": "BA",
            "mission": "Ignorée",
            "mission_code": "BA",
            "programme_code": "999",
            "programme_name": "Hors BG",
            "action_code": "01",
            "action_name": "Hors BG",
            "ae": "999",
            "cp": "999",
        },
    ]

    records = aggregate_budget_rows(rows)

    assert [(record.node_type, record.code, record.ae, record.cp) for record in records] == [
        ("mission", "JA", Decimal("125"), Decimal("120")),
        ("programme", "101", Decimal("125"), Decimal("120")),
        ("action", "01", Decimal("125"), Decimal("120")),
    ]
    assert records[1].parent_key == ("mission", "JA")
    assert records[2].parent_key == ("programme", "JA", "101")
