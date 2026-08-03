from datetime import datetime

from donnietts.formatting import (
    date_to_words,
    number_to_words,
    percent_to_words,
    time_to_words,
    wind_to_words,
)


def test_number_to_words() -> None:
    assert number_to_words(0) == "zero"
    assert number_to_words(7) == "seven"
    assert number_to_words(19) == "nineteen"
    assert number_to_words(42) == "forty two"
    assert number_to_words(60) == "sixty"
    assert number_to_words(100) == "one hundred"
    assert number_to_words(117) == "one hundred seventeen"
    assert number_to_words(-3) == "minus three"


def test_time_to_words() -> None:
    assert time_to_words(datetime(2026, 1, 2, 9, 0)) == "nine o'clock A M"
    assert time_to_words(datetime(2026, 1, 2, 9, 5)) == "nine oh five A M"
    assert time_to_words(datetime(2026, 1, 2, 14, 15)) == "two fifteen P M"
    assert time_to_words(datetime(2026, 1, 2, 0, 0)) == "twelve o'clock A M"
    assert time_to_words(datetime(2026, 1, 2, 23, 59)) == "eleven fifty nine P M"


def test_date_to_words() -> None:
    assert date_to_words(datetime(2026, 1, 2)) == "January second"
    assert date_to_words(datetime(2026, 3, 21)) == "March twenty first"
    assert date_to_words(datetime(2026, 12, 31)) == "December thirty first"


def test_percent_and_wind() -> None:
    assert percent_to_words(20) == "twenty percent"
    assert percent_to_words(0) == "zero percent"
    assert wind_to_words(0) == "calm wind"
    assert wind_to_words(5) == "light wind"
    assert wind_to_words(20) == "breezy conditions"
    assert wind_to_words(40) == "strong wind"
