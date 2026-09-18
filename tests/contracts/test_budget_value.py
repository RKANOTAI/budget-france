import json
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from packages.contracts.models import BudgetValue


def test_budget_value_keeps_ae_and_cp_separate_as_decimal_strings() -> None:
    value = BudgetValue(ae=Decimal("10.50"), cp=Decimal("9.25"))

    assert value.model_dump_json() == '{"ae":"10.50","cp":"9.25","currency":"EUR"}'
    assert BudgetValue.model_validate_json('{"ae":"10.50","cp":"9.25"}') == value

    with pytest.raises(ValidationError):
        BudgetValue(ae=1.5, cp=Decimal("1"))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        BudgetValue(ae=Decimal("1"), cp=Decimal("1"), unexpected="field")  # type: ignore[call-arg]


def test_decimal_wire_values_reject_exponents_and_publish_a_canonical_pattern() -> None:
    schema = BudgetValue.model_json_schema(mode="serialization")
    decimal_schemas = (
        schema["properties"]["ae"]["anyOf"],
        schema["properties"]["cp"]["anyOf"],
    )

    for alternatives in decimal_schemas:
        assert alternatives[0]["pattern"] == r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"

    with pytest.raises(ValidationError):
        BudgetValue.model_validate_json('{"ae":"1e3"}')


def test_budget_value_schema_requires_ae_or_cp() -> None:
    schema = BudgetValue.model_json_schema(mode="serialization")

    assert {tuple(item["required"]) for item in schema["anyOf"]} == {("ae",), ("cp",)}


def test_exported_budget_schema_rejects_empty_object_with_jsonschema() -> None:
    schema_path = Path(__file__).parents[2] / "packages/contracts/schemas/budget_value.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    validator = Draft202012Validator(schema)

    with pytest.raises(JsonSchemaValidationError):
        validator.validate({})
    with pytest.raises(JsonSchemaValidationError):
        validator.validate({"ae": None})
    with pytest.raises(JsonSchemaValidationError):
        validator.validate({"cp": None})
    validator.validate({"ae": "1.00"})
