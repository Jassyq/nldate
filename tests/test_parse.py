"""Test suite for nldate.parse().

All relative expressions are evaluated against TODAY, which is a Wednesday:

    November 2025
    Mo Tu We Th Fr Sa Su
                    1  2
     3  4  5  6  7  8  9
    10 11 12 13 14 15 16
    17 18 19 20 21 22 23
    24 25 26 27 28 29 30
"""

from datetime import date

import pytest

from nldate import parse

TODAY = date(2025, 11, 5)  # Wednesday


def p(s: str) -> date:
    return parse(s, today=TODAY)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("December 1st, 2025", date(2025, 12, 1)),
        ("December 1, 2025", date(2025, 12, 1)),
        ("Dec 1 2025", date(2025, 12, 1)),
        ("Dec. 1, 2025", date(2025, 12, 1)),
        ("1 December 2025", date(2025, 12, 1)),
        ("1st of December, 2025", date(2025, 12, 1)),
        ("the 25th of December 2025", date(2025, 12, 25)),
        ("December first, 2025", date(2025, 12, 1)),
        ("twenty-fifth of December 2025", date(2025, 12, 25)),
        ("Sept 3rd 2024", date(2024, 9, 3)),
        ("Monday, December 1st, 2025", date(2025, 12, 1)),
    ],
)
def test_written_out_dates(text: str, expected: date) -> None:
    assert p(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2025-12-01", date(2025, 12, 1)),
        ("2025/12/01", date(2025, 12, 1)),
        ("12/1/2025", date(2025, 12, 1)),
        ("12/01/25", date(2025, 12, 1)),
        ("12-1-2025", date(2025, 12, 1)),
        ("20251201", date(2025, 12, 1)),
        ("2025-12-01T10:30:00", date(2025, 12, 1)),
        ("25/12/2025", date(2025, 12, 25)),
    ],
)
def test_numeric_dates(text: str, expected: date) -> None:
    assert p(text) == expected


def test_year_defaults_to_current_year() -> None:
    assert p("July 4") == date(2025, 7, 4)
    assert p("4th of July") == date(2025, 7, 4)
    assert p("12/25") == date(2025, 12, 25)
    assert p("Christmas") == date(2025, 12, 25)
    assert p("Halloween 2027") == date(2027, 10, 31)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("today", date(2025, 11, 5)),
        ("now", date(2025, 11, 5)),
        ("tomorrow", date(2025, 11, 6)),
        ("yesterday", date(2025, 11, 4)),
        ("the day after tomorrow", date(2025, 11, 7)),
        ("the day before yesterday", date(2025, 11, 3)),
        ("TOMORROW", date(2025, 11, 6)),
        ("  tomorrow  ", date(2025, 11, 6)),
        ("tomorrow at 5pm", date(2025, 11, 6)),
    ],
)
def test_simple_anchors(text: str, expected: date) -> None:
    assert p(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Friday", date(2025, 11, 7)),
        ("Wednesday", date(2025, 11, 5)),  # today counts for a bare weekday
        ("Tuesday", date(2025, 11, 11)),
        ("next Tuesday", date(2025, 11, 11)),
        ("next Wednesday", date(2025, 11, 12)),  # strictly after today
        ("last Tuesday", date(2025, 11, 4)),
        ("last Wednesday", date(2025, 10, 29)),  # strictly before today
        ("this Monday", date(2025, 11, 3)),  # within the current Mon-Sun week
        ("this Friday", date(2025, 11, 7)),
        ("Friday next week", date(2025, 11, 14)),
        ("Monday last week", date(2025, 10, 27)),
        ("next week", date(2025, 11, 12)),
        ("last week", date(2025, 10, 29)),
        ("next month", date(2025, 12, 5)),
        ("last month", date(2025, 10, 5)),
        ("next year", date(2026, 11, 5)),
        ("last year", date(2024, 11, 5)),
    ],
)
def test_weekdays_and_periods(text: str, expected: date) -> None:
    assert p(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("in 3 days", date(2025, 11, 8)),
        ("in three days", date(2025, 11, 8)),
        ("in a week", date(2025, 11, 12)),
        ("in 2 weeks", date(2025, 11, 19)),
        ("3 days ago", date(2025, 11, 2)),
        ("a week ago", date(2025, 10, 29)),
        ("two weeks ago", date(2025, 10, 22)),
        ("10 days from now", date(2025, 11, 15)),
        ("a week from today", date(2025, 11, 12)),
        ("a fortnight from today", date(2025, 11, 19)),
        ("in 1 year and 2 months", date(2027, 1, 5)),
        ("3 months ago", date(2025, 8, 5)),
    ],
)
def test_offsets_from_today(text: str, expected: date) -> None:
    assert p(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5 days before December 1st, 2025", date(2025, 11, 26)),
        ("5 days after December 1st, 2025", date(2025, 12, 6)),
        ("1 year and 2 months after yesterday", date(2027, 1, 4)),
        ("two weeks from tomorrow", date(2025, 11, 20)),
        ("3 days after next Tuesday", date(2025, 11, 14)),
        ("2 weeks, 3 days after Dec 1 2025", date(2025, 12, 18)),
        ("1 week and 2 days from today", date(2025, 11, 14)),
        ("a day before Christmas", date(2025, 12, 24)),
        ("the week after next Friday", date(2025, 11, 14)),
        ("the day after tomorrow", date(2025, 11, 7)),
        ("three weeks before 2026-01-01", date(2025, 12, 11)),
    ],
)
def test_offsets_from_anchor(text: str, expected: date) -> None:
    assert p(text) == expected


def test_nested_offsets() -> None:
    assert p("2 days before 5 days after tomorrow") == date(2025, 11, 9)
    assert p("1 week after 1 week after today") == date(2025, 11, 19)


def test_month_and_year_arithmetic_clamps_to_month_end() -> None:
    assert p("1 month after January 31, 2026") == date(2026, 2, 28)
    assert p("1 year after February 29, 2024") == date(2025, 2, 28)
    assert p("1 month before March 31, 2026") == date(2026, 2, 28)
    assert p("12 months after October 31, 2025") == date(2026, 10, 31)


def test_business_days() -> None:
    # Friday Nov 7 + 3 business days skips the weekend.
    assert p("3 business days after Friday") == date(2025, 11, 12)
    assert p("1 weekday after Friday") == date(2025, 11, 10)
    assert p("2 business days before Monday, November 10, 2025") == date(2025, 11, 6)
    assert p("in 5 business days") == date(2025, 11, 12)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("first Monday of December 2025", date(2025, 12, 1)),
        ("third Thursday of November 2025", date(2025, 11, 20)),
        ("last Friday of November 2025", date(2025, 11, 28)),
        ("second Tuesday of next month", date(2025, 12, 9)),
        ("last Friday of this month", date(2025, 11, 28)),
        ("1st Monday in Sept 2026", date(2026, 9, 7)),
    ],
)
def test_nth_weekday_of_month(text: str, expected: date) -> None:
    assert p(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("last day of February 2026", date(2026, 2, 28)),
        ("last day of February 2024", date(2024, 2, 29)),
        ("first day of next month", date(2025, 12, 1)),
        ("end of next month", date(2025, 12, 31)),
        ("beginning of this year", date(2025, 1, 1)),
        ("last day of this year", date(2025, 12, 31)),
        ("first day of December", date(2025, 12, 1)),
    ],
)
def test_first_and_last_day_of_period(text: str, expected: date) -> None:
    assert p(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "banana",
        "next",
        "tomorrow banana",
        "5 days before",
        "banana after tomorrow",
        "February 30, 2025",
        "13/45/2025",
        "2025-02-30",
        "fifth Monday of February 2026",
        "99999999999999 days from now",
        "in 5 fortnights of nothing",
    ],
)
def test_unrecognized_input_raises_value_error(text: str) -> None:
    with pytest.raises(ValueError):
        p(text)


def test_today_defaults_to_current_date() -> None:
    assert parse("today") == date.today()
    assert parse("tomorrow") > date.today()


def test_misc_phrasings() -> None:
    assert p("first of next month") == date(2025, 12, 1)
    assert p("next Friday at noon") == date(2025, 11, 7)
    assert p("in a couple of days") == date(2025, 11, 7)
