import pytest

from packages.contracts.models import FiscalYear


def test_fiscal_year_only_accepts_supported_values() -> None:
    assert FiscalYear(2025).value == 2025
    assert FiscalYear(2026).value == 2026
    with pytest.raises(ValueError):
        FiscalYear(2024)
