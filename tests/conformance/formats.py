"""Pure date and date-time string checks shared by the loader and the semantic stage.

``check_date_time`` implements the ``DT-1`` grammar and ``check_date`` the
``DT-3`` Gregorian date. Neither does any I/O, and this module imports nothing
from the loader, so the semantic stage can use it without loading a bundle.
"""

import calendar
import re

from tests.conformance.types import SetupFailed

try:
    from rfc3339_validator import validate_rfc3339
except ImportError:  # pragma: no cover - the locked environment provides it
    validate_rfc3339 = None

__all__ = ["check_date", "check_date_time"]

_DATE_TIME = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]"
    r"([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?"
    r"(?:[Zz]|[+-]([0-9]{2}):([0-9]{2}))"
)

_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")


def check_date_time(value: str) -> bool:
    """DT-1: the contract date-time grammar, checked against the calendar."""
    if validate_rfc3339 is None:
        raise SetupFailed("rfc3339-validator is not available")
    match = _DATE_TIME.fullmatch(value)
    if match is None:
        return False
    year, month, day, hour, minute, second = (int(g) for g in match.groups()[:6])
    if year < 1 or not 1 <= month <= 12:
        return False
    if not 1 <= day <= calendar.monthrange(year, month)[1]:
        return False
    if hour > 23 or minute > 59 or second > 59:
        return False
    offset_hour, offset_minute = match.group(7), match.group(8)
    if offset_hour is not None and (int(offset_hour) > 23 or int(offset_minute) > 59):
        return False
    # The grammar has already matched, so the only letters are T/t and Z/z.
    # rfc3339-validator accepts only upper case, so compare in upper case.
    return validate_rfc3339(value.upper()) is True


def check_date(value: str) -> bool:
    """DT-3: YYYY-MM-DD, year at least 1, and a valid Gregorian date."""
    match = _DATE.fullmatch(value)
    if match is None:
        return False
    year, month, day = (int(g) for g in match.groups())
    if year < 1 or not 1 <= month <= 12:
        return False
    return 1 <= day <= calendar.monthrange(year, month)[1]
