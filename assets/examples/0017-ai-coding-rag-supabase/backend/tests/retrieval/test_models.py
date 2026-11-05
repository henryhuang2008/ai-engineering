import pytest
from pydantic import ValidationError

from app.retrieval.models import SearchFilters, validate_query


def test_search_filters_normalize_ticker_and_form() -> None:
    filters = SearchFilters(ticker=" googl ", fiscal_year=2025, filing_type=" 10-k ")

    assert filters.ticker == "GOOGL"
    assert filters.fiscal_year == 2025
    assert filters.filing_type == "10-K"


@pytest.mark.parametrize("value", ["", "  "])
def test_search_filters_reject_empty_text_values(value: str) -> None:
    with pytest.raises(ValidationError):
        SearchFilters(ticker=value)


def test_search_filters_reject_out_of_range_year() -> None:
    with pytest.raises(ValidationError):
        SearchFilters(fiscal_year=1800)


def test_validate_query_trims_and_bounds_search_text() -> None:
    assert validate_query("  annual revenue  ") == "annual revenue"
    with pytest.raises(ValueError, match="must not be empty"):
        validate_query(" \t ")
    with pytest.raises(ValueError, match="2000"):
        validate_query("x" * 2_001)
