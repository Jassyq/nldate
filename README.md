# nldate

Parse natural-language dates into `datetime.date` objects.

```python
from datetime import date
from nldate import parse

parse("5 days before December 1st, 2025")  # date(2025, 11, 26)
parse("1 year and 2 months after yesterday")  # relative to today
parse("next Tuesday", today=date(2025, 11, 5))  # date(2025, 11, 11)
parse("last Friday of November 2025")  # date(2025, 11, 28)
```

Unrecognised input (including the empty string) raises `ValueError`.

Supported: absolute dates (`Dec 1st, 2025`, `2025-12-01`, `12/1/25`), `today`/`tomorrow`/`yesterday`,
weekdays (`next Tuesday`, `Friday next week`), offsets (`in 3 days`, `two weeks ago`,
`2 weeks, 3 days after tomorrow`, business days), nth weekday of a month,
first/last day of a month or year, and a few holidays. Offsets can be nested.

## Development

```
uv run pytest
uv run mypy src/
uv run ruff check
uv run ruff format --check
```
