from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.contracts.models import Explanation

FRAGMENT_1 = UUID("00000000-0000-4000-8000-000000000060")
FRAGMENT_2 = UUID("00000000-0000-4000-8000-000000000061")


def test_explanation_rejects_undocumented_source_fragment_id_alias() -> None:
    with pytest.raises(ValidationError):
        Explanation(
            summary="Résumé documenté.",
            what_it_funds="Périmètre financé.",
            main_changes="Évolution publiée.",
            limitations="Contexte limité.",
            source_fragment_id=FRAGMENT_1,
        )  # type: ignore[call-arg]


def test_explanation_is_textual_and_cites_source_fragments() -> None:
    explanation = Explanation(
        summary="Cette action finance un dispositif documenté.",
        what_it_funds="Le document décrit le périmètre de l'action.",
        main_changes="La nomenclature publiée est inchangée dans cet extrait.",
        limitations="La source ne permet pas d'expliquer toute variation.",
        source_fragment_ids=(FRAGMENT_1, FRAGMENT_2),
    )
    restored = Explanation.model_validate_json(explanation.model_dump_json())

    assert explanation.source_fragment_ids == (FRAGMENT_1, FRAGMENT_2)
    assert "amount" not in Explanation.model_fields
    assert "year" not in Explanation.model_fields
    assert isinstance(restored.source_fragment_ids, tuple)
    assert restored == explanation

    with pytest.raises(ValidationError):
        Explanation(
            summary="Sans citation",
            what_it_funds="Périmètre",
            main_changes="Évolution",
            limitations="Limites",
            source_fragment_ids=(),
        )
    with pytest.raises(ValidationError):
        Explanation(
            summary="Montant canonique",
            what_it_funds="Périmètre",
            main_changes="Évolution",
            limitations="Limites",
            source_fragment_ids=(FRAGMENT_1,),
            amount=10,
        )  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Explanation(
            summary="Alias",
            what_it_funds="Périmètre",
            main_changes="Évolution",
            limitations="Limites",
            source_fragment_ids=FRAGMENT_1,  # type: ignore[arg-type]
        )
