from dogs_scraper.utils.dates import combine_local
from dogs_scraper.utils.text import (
    clean, distance_m, normalise_dog_name, to_float, to_int,
)


def test_clean_collapses_whitespace_and_nbsp():
    assert clean("  One Hot   Chance \n") == "One Hot Chance"
    assert clean("   ") is None
    assert clean(None) is None


def test_numeric_parsers():
    assert to_int("Box 4") == 4
    assert to_float("29.10kg") == 29.10
    assert to_float("$1.80") == 1.80
    assert to_int(None) is None


def test_distance_parsing():
    assert distance_m("350m") == 350
    assert distance_m("Race 4 - 440m Heat") == 440
    assert distance_m(None) is None


def test_dog_name_normalisation_matches_our_fields():
    assert normalise_dog_name("One Hot Chance") == "ONE HOT CHANCE"
    assert normalise_dog_name("O'Reilly's Boy") == "OREILLYS BOY"


def test_combine_local_produces_offset_aware_iso():
    from datetime import date
    result = combine_local(date(2026, 8, 28), "12:34")
    assert result is not None
    assert result.startswith("2026-08-28T12:34")
    assert result.endswith("+10:00")
    assert combine_local(date(2026, 8, 28), "not a time") is None
