from decimal import Decimal

import pytest
from pydantic import ValidationError

from packages.contracts.models import Money


def test_money_is_strict_frozen_and_json_serializes_decimal_as_string() -> None:
    money = Money(amount=Decimal("123.40"))
    restored = Money.model_validate_json(money.model_dump_json())

    assert money.model_dump_json() == '{"amount":"123.40","currency":"EUR"}'
    assert restored == money

    with pytest.raises(ValidationError):
        Money(amount=123.4)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Money(amount=Decimal("1"), unexpected="field")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        money.amount = Decimal("2")  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Money(amount=Decimal("NaN"))
    with pytest.raises(ValidationError):
        Money(amount=Decimal("Infinity"))
