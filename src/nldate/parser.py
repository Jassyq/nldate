"""Natural-language date parsing.

The grammar is deliberately generous.  Input is lower-cased and normalised
(punctuation and filler words such as "the" and "on" are dropped), then run
through a short chain of recognisers:

1. offsets anchored to another expression ("5 days before <expr>")
2. offsets from today ("in 3 days", "2 weeks ago")
3. simple anchors ("today", "tomorrow", ...)
4. periods and weekdays ("next week", "last Tuesday", "Friday next week")
5. "first Monday of <month>" and "last day of <month>"
6. absolute dates ("December 1st, 2025", "2025-12-01", "12/1/25", ...)

Conventions for ambiguous phrases:

* a bare weekday ("Friday") is the next such day, today included;
* "next <weekday>" is the first such day strictly after today and
  "last <weekday>" the most recent one strictly before today;
* "this <weekday>" is that day within the current Monday-to-Sunday week;
* "next week"/"next month"/"next year" move forward by exactly one unit;
* months and years are added calendar-wise and clamp to the end of the month
  (Jan 31 + 1 month = Feb 28), then weeks and days are added;
* numeric dates are month-first (12/1/2025 is December 1st) unless that is
  impossible (25/12/2025).
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterable
from datetime import date, timedelta

MONTHS: dict[str, int] = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}  # fmt: skip

WEEKDAYS: dict[str, int] = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tues": 1, "tue": 1,
    "wednesday": 2, "weds": 2, "wed": 2,
    "thursday": 3, "thurs": 3, "thur": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}  # fmt: skip

HOLIDAYS: dict[str, tuple[int, int]] = {
    "new years day": (1, 1),
    "new year": (1, 1),
    "valentines day": (2, 14),
    "valentines": (2, 14),
    "st patricks day": (3, 17),
    "independence day": (7, 4),
    "halloween": (10, 31),
    "christmas eve": (12, 24),
    "christmas day": (12, 25),
    "christmas": (12, 25),
    "new years eve": (12, 31),
}

_UNITS_TO_ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_ORDINALS_TO_NINETEEN = [
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
    "eleventh",
    "twelfth",
    "thirteenth",
    "fourteenth",
    "fifteenth",
    "sixteenth",
    "seventeenth",
    "eighteenth",
    "nineteenth",
]

NUMBER_WORDS: dict[str, int] = {w: i for i, w in enumerate(_UNITS_TO_ONES)}
NUMBER_WORDS.update({w: 20 + 10 * i for i, w in enumerate(_TENS)})
NUMBER_WORDS.update({"a": 1, "an": 1, "a couple of": 2, "a dozen": 12})

ORDINAL_WORDS: dict[str, int] = {w: i + 1 for i, w in enumerate(_ORDINALS_TO_NINETEEN)}
ORDINAL_WORDS.update({"twentieth": 20, "thirtieth": 30})


def _alt(words: Iterable[str]) -> str:
    """Regex alternation, longest first so that "sept" wins over "sep"."""
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


# --- regex building blocks -------------------------------------------------

_MONTH = rf"(?:{_alt(MONTHS)})"
_WEEKDAY = rf"(?:{_alt(WEEKDAYS)})"
_ORD_UNIT = "first|second|third|fourth|fifth|sixth|seventh|eighth|ninth"
_ORD_WORD = rf"(?:(?:twenty|thirty)[ -](?:{_ORD_UNIT})|{_alt(ORDINAL_WORDS)}|twentieth|thirtieth)"
_ORD_DIGITS = r"\d{1,2}(?:st|nd|rd|th)"
_DAY = rf"(?:\d{{1,2}}(?:st|nd|rd|th)?|{_ORD_WORD})"
_YEAR = r"\d{4}"
_NUM_WORD = (
    rf"(?:(?:{'|'.join(_TENS)})(?:[ -](?:{'|'.join(_UNITS_TO_ONES[1:10])}))?"
    rf"|{'|'.join(reversed(_UNITS_TO_ONES))}|a couple of|a dozen|an|a)"
)
_NUM = rf"(?:\d+|{_NUM_WORD})"
_UNIT = r"(?:business days?|working days?|weekdays?|days?|weeks?|fortnights?|months?|years?)"
_ITEM = rf"{_NUM}\s+{_UNIT}"
_OFFSET = rf"{_ITEM}(?:(?:\s+(?:and|plus))?\s+{_ITEM})*"
_FORWARD = r"after|from|past|following|since|later than"
_BACKWARD = r"before|prior to|earlier than|ahead of|preceding|until|till"
_CONNECTOR = rf"(?:{_FORWARD}|{_BACKWARD})"
_HOLIDAY = rf"(?:{_alt(HOLIDAYS)})"
_NTH = rf"(?:{_ORD_WORD}|{_ORD_DIGITS}|last)"

_RE_OFFSET_CONNECTOR = re.compile(rf"^({_OFFSET})\s+({_CONNECTOR})\s+(.+)$")
_RE_UNIT_CONNECTOR = re.compile(rf"^({_UNIT})\s+({_CONNECTOR})\s+(.+)$")
_RE_IN_OFFSET = re.compile(rf"^in\s+({_OFFSET})$")
_RE_OFFSET_AGO = re.compile(rf"^({_OFFSET})\s+(?:ago|earlier|back)$")
_RE_OFFSET_HENCE = re.compile(rf"^({_OFFSET})\s+(?:hence|later)$")
_RE_ITEM = re.compile(rf"({_NUM})\s+({_UNIT})")

_RE_PERIOD = re.compile(
    r"^(next|last|previous|this|coming)\s+(week|month|year|fortnight)$"
)
_RE_WEEKDAY = re.compile(
    rf"^(?:(next|last|previous|this|coming|upcoming)\s+)?({_WEEKDAY})$"
)
_RE_WEEKDAY_WEEK = re.compile(
    rf"^(?:({_WEEKDAY})\s+(next|last|previous|this)\s+week"
    rf"|(next|last|previous|this)\s+week\s+({_WEEKDAY}))$"
)
_RE_NTH_WEEKDAY = re.compile(rf"^({_NTH})\s+({_WEEKDAY})\s+(?:of|in)\s+(.+)$")
_RE_FIRST_LAST_DAY = re.compile(r"^(first|last)\s+day\s+of\s+(.+)$")
_RE_START_END = re.compile(r"^(beginning|start|end)\s+of\s+(.+)$")
_RE_FIRST_OF_REL = re.compile(
    r"^(first|last)\s+of\s+((?:next|last|previous|this)\s+(?:month|year|week))$"
)
_RE_PERIOD_SPEC_MONTH = re.compile(rf"^({_MONTH})(?:\s+({_YEAR}))?$")
_RE_PERIOD_SPEC_REL = re.compile(
    r"^(?:(next|last|previous|this)\s+)?(month|year|week)$"
)

_RE_ISO = re.compile(
    r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})"
    r"(?:[t ]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?z?)?$"
)
_RE_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_RE_NUMERIC = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})$")
_RE_NUMERIC_SHORT = re.compile(r"^(\d{1,2})/(\d{1,2})$")
_RE_MONTH_DAY = re.compile(rf"^({_MONTH})\s+({_DAY})(?:\s+(?:of\s+)?({_YEAR}))?$")
_RE_DAY_MONTH = re.compile(
    rf"^({_DAY})(?:\s+of)?\s+({_MONTH})(?:\s+(?:of\s+)?({_YEAR}))?$"
)
_RE_HOLIDAY = re.compile(rf"^({_HOLIDAY})(?:\s+({_YEAR}))?$")
_RE_WEEKDAY_PREFIX = re.compile(rf"^{_WEEKDAY}\s+(.+)$")

_RE_TRAILING_TIME = re.compile(
    r"\s+at\s+(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)$"
)
_RE_TRAILING_DAYPART = re.compile(r"\s+(?:morning|afternoon|evening|night)$")


# --- helpers ---------------------------------------------------------------


def _normalize(s: str) -> str:
    t = s.lower().replace("’", "'").replace("'", "")
    t = t.replace("&", " and ").replace(",", " ")
    t = re.sub(r"(?<=[a-z])\.", "", t)  # "dec." -> "dec"
    t = " ".join(w for w in t.split() if w not in {"the", "on"})
    t = _RE_TRAILING_TIME.sub("", t)
    t = _RE_TRAILING_DAYPART.sub("", t)
    return "today" if t == "tonight" else t


def _number(token: str) -> int:
    if token.isdigit():
        return int(token)
    token = token.replace("-", " ")
    if token in NUMBER_WORDS:
        return NUMBER_WORDS[token]
    tens, _, ones = token.partition(" ")
    return NUMBER_WORDS[tens] + NUMBER_WORDS[ones]


def _day_number(token: str) -> int:
    if token[0].isdigit():
        return int(re.sub(r"\D", "", token))
    token = token.replace("-", " ")
    if token in ORDINAL_WORDS:
        return ORDINAL_WORDS[token]
    tens, _, ones = token.partition(" ")
    return NUMBER_WORDS[tens] + ORDINAL_WORDS[ones]


def _two_digit_year(y: int) -> int:
    return y + (2000 if y < 69 else 1900) if y < 100 else y


def _add_months(d: date, n: int) -> date:
    total = d.year * 12 + (d.month - 1) + n
    year, month0 = divmod(total, 12)
    if not 1 <= year <= 9999:
        raise ValueError("date out of range")
    last = calendar.monthrange(year, month0 + 1)[1]
    return date(year, month0 + 1, min(d.day, last))


def _add_business_days(d: date, n: int) -> date:
    step = 1 if n >= 0 else -1
    weeks, rest = divmod(abs(n), 5)
    d += timedelta(weeks=step * weeks)
    while rest:
        d += timedelta(days=step)
        if d.weekday() < 5:
            rest -= 1
    return d


def _apply_offset(offset: str, base: date, sign: int) -> date:
    months = days = business_days = 0
    for num, unit in _RE_ITEM.findall(offset):
        n = _number(num) * sign
        if unit.startswith("year"):
            months += 12 * n
        elif unit.startswith("month"):
            months += n
        elif unit.startswith("week") and not unit.startswith("weekday"):
            days += 7 * n
        elif unit.startswith("fortnight"):
            days += 14 * n
        elif unit.startswith("day"):
            days += n
        else:  # business days, working days, weekdays
            business_days += n
    result = _add_months(base, months) + timedelta(days=days)
    return _add_business_days(result, business_days)


def _resolve_weekday(today: date, target: int, qualifier: str | None) -> date:
    if qualifier == "this":
        monday = today - timedelta(days=today.weekday())
        return monday + timedelta(days=target)
    if qualifier == "next":
        return today + timedelta(days=(target - today.weekday()) % 7 or 7)
    if qualifier in {"last", "previous"}:
        return today - timedelta(days=(today.weekday() - target) % 7 or 7)
    return today + timedelta(days=(target - today.weekday()) % 7)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _period_bounds(spec: str, today: date) -> tuple[date, date] | None:
    """Return the first and last day of a period like "next month"."""
    if m := _RE_PERIOD_SPEC_MONTH.match(spec):
        return _month_bounds(int(m[2]) if m[2] else today.year, MONTHS[m[1]])
    if m := _RE_PERIOD_SPEC_REL.match(spec):
        shift = {"next": 1, "last": -1, "previous": -1}.get(m[1] or "", 0)
        if m[2] == "month":
            first = _add_months(today.replace(day=1), shift)
            return _month_bounds(first.year, first.month)
        if m[2] == "year":
            return date(today.year + shift, 1, 1), date(today.year + shift, 12, 31)
        monday = today - timedelta(days=today.weekday()) + timedelta(weeks=shift)
        return monday, monday + timedelta(days=6)
    if re.fullmatch(_YEAR, spec):
        return date(int(spec), 1, 1), date(int(spec), 12, 31)
    return None


def _nth_weekday(nth: str, weekday: int, first: date, last: date) -> date:
    if nth == "last":
        result = last - timedelta(days=(last.weekday() - weekday) % 7)
    else:
        n = _day_number(nth)
        result = first + timedelta(days=(weekday - first.weekday()) % 7, weeks=n - 1)
    if not first <= result <= last:
        raise ValueError(f"no such weekday in {first:%B %Y}")
    return result


# --- recognisers -----------------------------------------------------------


def _parse_absolute(text: str, today: date) -> date | None:
    if m := _RE_ISO.match(text):
        return date(int(m[1]), int(m[2]), int(m[3]))
    if m := _RE_COMPACT.match(text):
        return date(int(m[1]), int(m[2]), int(m[3]))
    if m := _RE_NUMERIC.match(text):
        first, second, year = int(m[1]), int(m[2]), _two_digit_year(int(m[3]))
        if first > 12 >= second:  # clearly day-first, e.g. 25/12/2025
            first, second = second, first
        return date(year, first, second)
    if m := _RE_NUMERIC_SHORT.match(text):
        return date(today.year, int(m[1]), int(m[2]))
    if m := _RE_MONTH_DAY.match(text):
        return date(int(m[3]) if m[3] else today.year, MONTHS[m[1]], _day_number(m[2]))
    if m := _RE_DAY_MONTH.match(text):
        return date(int(m[3]) if m[3] else today.year, MONTHS[m[2]], _day_number(m[1]))
    if m := _RE_HOLIDAY.match(text):
        month, day = HOLIDAYS[m[1]]
        return date(int(m[2]) if m[2] else today.year, month, day)
    if m := _RE_WEEKDAY_PREFIX.match(text):  # "Monday, December 1st, 2025"
        return _parse_absolute(m[1], today)
    return None


def _parse_relative(text: str, today: date) -> date | None:
    if text in {"today", "now"}:
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    if text == "yesterday":
        return today - timedelta(days=1)

    if m := _RE_PERIOD.match(text):
        shift = {"next": 1, "last": -1, "previous": -1}.get(m[1], 0)
        if m[2] == "month":
            return _add_months(today, shift)
        if m[2] == "year":
            return _add_months(today, 12 * shift)
        return today + timedelta(weeks=shift * (2 if m[2] == "fortnight" else 1))

    if m := _RE_WEEKDAY.match(text):
        qualifier = None if m[1] in {None, "coming", "upcoming"} else m[1]
        return _resolve_weekday(today, WEEKDAYS[m[2]], qualifier)

    if m := _RE_WEEKDAY_WEEK.match(text):
        name, qualifier = (m[1], m[2]) if m[1] else (m[4], m[3])
        shift = {"next": 1, "last": -1, "previous": -1}.get(qualifier, 0)
        monday = today - timedelta(days=today.weekday()) + timedelta(weeks=shift)
        return monday + timedelta(days=WEEKDAYS[name])

    if m := _RE_NTH_WEEKDAY.match(text):
        bounds = _period_bounds(m[3], today)
        if bounds is not None:
            return _nth_weekday(m[1], WEEKDAYS[m[2]], *bounds)

    if m := (
        _RE_FIRST_LAST_DAY.match(text)
        or _RE_START_END.match(text)
        or _RE_FIRST_OF_REL.match(text)
    ):
        bounds = _period_bounds(m[2], today)
        if bounds is not None:
            return bounds[0] if m[1] in {"first", "beginning", "start"} else bounds[1]
    return None


def _parse(text: str, today: date) -> date:
    if m := _RE_OFFSET_CONNECTOR.match(text):
        sign = -1 if re.fullmatch(_BACKWARD, m[2]) else 1
        return _apply_offset(m[1], _parse(m[3], today), sign)
    if m := _RE_UNIT_CONNECTOR.match(text):  # "day after tomorrow"
        return _parse(f"1 {m[1]} {m[2]} {m[3]}", today)
    if m := _RE_IN_OFFSET.match(text) or _RE_OFFSET_HENCE.match(text):
        return _apply_offset(m[1], today, 1)
    if m := _RE_OFFSET_AGO.match(text):
        return _apply_offset(m[1], today, -1)

    result = _parse_relative(text, today)
    if result is None:
        result = _parse_absolute(text, today)
    if result is None:
        raise ValueError(f"could not understand date: {text!r}")
    return result


def parse(s: str, today: date | None = None) -> date:
    """Turn a natural-language date such as "next Tuesday" into a ``date``.

    ``today`` is the reference point for relative expressions and defaults to
    the current date.  Raises ``ValueError`` if ``s`` is not recognised or
    names a date that does not exist.
    """
    if today is None:
        today = date.today()
    text = _normalize(s)
    if not text:
        raise ValueError("empty date string")
    try:
        return _parse(text, today)
    except OverflowError as e:
        raise ValueError(f"date out of range: {s!r}") from e
