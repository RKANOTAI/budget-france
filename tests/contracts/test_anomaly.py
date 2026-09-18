from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.contracts.models import AnomalySummary

NODE_ID = UUID("00000000-0000-4000-8000-000000000031")


def test_anomaly_summary_can_block_unverified_publication() -> None:
    anomaly = AnomalySummary(
        code="MISSING_SOURCE",
        severity="critical",
        message="Le nœud n'a pas de provenance exploitable.",
        node_id=NODE_ID,
        blocked=True,
        details=("source absent",),
    )
    restored = AnomalySummary.model_validate_json(anomaly.model_dump_json())

    assert anomaly.blocked is True
    assert anomaly.severity == "critical"
    assert isinstance(restored.details, tuple)
    assert restored == anomaly

    with pytest.raises(ValidationError):
        AnomalySummary(
            code="UNKNOWN",
            severity="fatal",  # type: ignore[arg-type]
            message="Niveau non prévu.",
            blocked=False,
        )
    with pytest.raises(ValidationError):
        AnomalySummary(code="UNKNOWN", severity="warning", message="x", extra="x")  # type: ignore[call-arg]


def test_error_and_critical_anomalies_must_block_publication() -> None:
    for severity in ("error", "critical"):
        with pytest.raises(ValidationError):
            AnomalySummary(code="UNSAFE", severity=severity, message="x", blocked=False)


def test_anomaly_node_id_is_a_uuid_when_present() -> None:
    with pytest.raises(ValidationError):
        AnomalySummary(
            code="MISSING_SOURCE",
            severity="critical",
            message="x",
            node_id="action-1",  # type: ignore[arg-type]
            blocked=True,
        )

    anomaly = AnomalySummary(
        code="MISSING_SOURCE",
        severity="critical",
        message="x",
        node_id=NODE_ID,
        blocked=True,
    )
    assert anomaly.node_id is not None
    assert anomaly.node_id.version == 4
