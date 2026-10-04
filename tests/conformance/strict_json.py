"""Strict JSON input parser with exact numbers and numeric resource guards.

Parse order for every document:

1. Reject a UTF-8 byte-order mark, then decode strict UTF-8.
2. Parse with ``json.loads``. Hooks reject duplicate member names and the
   constants NaN, Infinity, and -Infinity. Number hooks return a private
   tagged lexeme, so no number is converted during parsing.
3. Reject unpaired surrogates in object member names and string values.
4. Apply the numeric resource guards to every lexeme in the document.
5. Convert integer lexemes to ``int`` and all other number lexemes to
   ``Decimal``. The ``Decimal`` constructor is exact and never rounds.

Steps 1 to 3 raise ``InputInvalid``. Step 4 raises ``NumericResourceRefused``,
which is a setup failure. Malformed input always reports ``InputInvalid``
first, even when it also contains an oversized number.

Nesting deeper than the Python interpreter recursion limit allows, in
``json.loads`` or in the later tree walks, raises ``SetupFailed`` with a fixed
message.

Numeric resource guards (operational setup guards, not OASIS ranges):

- Token length: the lexeme exactly as written, including sign, decimal
  point, and exponent syntax, must be at most 1,024 ASCII bytes.
- Exponent: the exponent digit text, ignoring its sign and leading zeros,
  must have at most 5 digits. This is checked before any integer is built
  from it. The exponent value must then be at most 10,000 in absolute value.
- Expansion budget: each number token charges its coefficient digits plus the
  absolute exponent value (0 when there is no exponent). Coefficient digits
  are every digit character written before the exponent marker, in both the
  integer part and the fraction part. The sign and decimal point are not
  counted. Leading and trailing zeros are counted. The charges are summed over
  every number token in the document. The sum must be at most 100,000.

Error messages name the exceeded limit and never echo input values.
"""

import hashlib
import json
import sys
from decimal import Decimal

from tests.conformance.types import (
    _PARSED_INPUT_TOKEN,
    InputInvalid,
    NumericResourceRefused,
    ParsedInput,
    SetupFailed,
)

MAX_TOKEN_BYTES = 1024
MAX_ABS_EXPONENT = 10000
MAX_EXPONENT_DIGITS = len(str(MAX_ABS_EXPONENT))
MAX_EXPANSION_UNITS = 100000

NESTING_LIMIT_MESSAGE = "input nesting exceeds the Python interpreter recursion limit"

_BOM = b"\xef\xbb\xbf"


def check_int_digit_limit():
    """Fail setup when Python cannot convert a maximum-length integer token."""
    limit = sys.get_int_max_str_digits()
    if limit != 0 and limit < MAX_TOKEN_BYTES:
        raise SetupFailed(
            "sys.get_int_max_str_digits() must be 0 or at least %d" % MAX_TOKEN_BYTES
        )


check_int_digit_limit()


class _NumberLexeme:
    """A JSON number kept as its original text until the guards pass."""

    __slots__ = ("text", "is_integer")

    def __init__(self, text, is_integer):
        self.text = text
        self.is_integer = is_integer


def _integer_lexeme(text):
    return _number_lexeme(text, True)


def _float_lexeme(text):
    return _number_lexeme(text, False)


def _number_lexeme(text, is_integer):
    # The C scanner accepts only ASCII digits. The pure-Python fallback
    # scanner matches Unicode digits, so enforce RFC 8259 digits here too.
    if not text.isascii():
        raise InputInvalid("number contains non-ASCII digits")
    return _NumberLexeme(text, is_integer)


def _reject_constant(_name):
    raise InputInvalid("nonfinite number constant is not permitted")


def _reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputInvalid("duplicate object member name")
        result[key] = value
    return result


def _has_surrogate(text):
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def _scan(node, lexemes):
    """Reject unpaired surrogates and collect number lexemes in document order."""
    if isinstance(node, str):
        if _has_surrogate(node):
            raise InputInvalid("string value contains an unpaired surrogate")
    elif isinstance(node, dict):
        for key, value in node.items():
            if _has_surrogate(key):
                raise InputInvalid("object member name contains an unpaired surrogate")
            _scan(value, lexemes)
    elif isinstance(node, list):
        for item in node:
            _scan(item, lexemes)
    elif isinstance(node, _NumberLexeme):
        lexemes.append(node)


def _charge(text):
    """Guard one lexeme and return its expansion charge in digit units."""
    if len(text) > MAX_TOKEN_BYTES:
        raise NumericResourceRefused(
            "numeric token length exceeds %d bytes" % MAX_TOKEN_BYTES
        )
    marker = max(text.find("e"), text.find("E"))
    if marker < 0:
        coefficient, exponent = text, 0
    else:
        coefficient = text[:marker]
        digits = text[marker + 1 :].lstrip("+-").lstrip("0")
        if len(digits) > MAX_EXPONENT_DIGITS:
            raise NumericResourceRefused(
                "absolute decimal exponent exceeds %d" % MAX_ABS_EXPONENT
            )
        exponent = int(digits) if digits else 0
        if exponent > MAX_ABS_EXPONENT:
            raise NumericResourceRefused(
                "absolute decimal exponent exceeds %d" % MAX_ABS_EXPONENT
            )
    return sum(ch.isdigit() for ch in coefficient) + exponent


def _guard(lexemes):
    total = 0
    for lexeme in lexemes:
        total += _charge(lexeme.text)
        if total > MAX_EXPANSION_UNITS:
            raise NumericResourceRefused(
                "numeric expansion budget exceeds %d digit units per document"
                % MAX_EXPANSION_UNITS
            )


def _convert(node):
    if isinstance(node, _NumberLexeme):
        return int(node.text) if node.is_integer else Decimal(node.text)
    if isinstance(node, dict):
        return {key: _convert(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_convert(item) for item in node]
    return node


def _parse(data):
    try:
        return _parse_tree(data)
    except RecursionError:
        raise SetupFailed(NESTING_LIMIT_MESSAGE) from None


def _parse_tree(data):
    if not isinstance(data, bytes):
        raise TypeError("strict parser input must be bytes")
    if data.startswith(_BOM):
        raise InputInvalid("byte-order mark is not permitted")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise InputInvalid("input is not valid UTF-8") from None
    try:
        tree = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
            parse_int=_integer_lexeme,
            parse_float=_float_lexeme,
        )
    except json.JSONDecodeError as error:
        raise InputInvalid(
            "malformed JSON at line %d column %d" % (error.lineno, error.colno)
        ) from None
    lexemes = []
    _scan(tree, lexemes)
    _guard(lexemes)
    return _convert(tree)


def parse_input(data: bytes) -> ParsedInput:
    """Strict-parse input bytes into a ``ParsedInput``."""
    value = _parse(data)
    return ParsedInput(value, hashlib.sha256(data).hexdigest(), _token=_PARSED_INPUT_TOKEN)


def parse_schema_bytes(data: bytes):
    """Strict-parse schema bytes into a plain exact-number tree."""
    return _parse(data)
