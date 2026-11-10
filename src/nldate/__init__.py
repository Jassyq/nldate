"""nldate: parse natural-language dates like "5 days before December 1st, 2025"."""

import sys

from nldate.parser import parse

__all__ = ["main", "parse"]


def main() -> None:
    """Command line entry point: ``nldate "next Tuesday"``."""
    if len(sys.argv) < 2:
        sys.exit('usage: nldate "<date expression>"')
    try:
        print(parse(" ".join(sys.argv[1:])).isoformat())
    except ValueError as e:
        sys.exit(f"error: {e}")
