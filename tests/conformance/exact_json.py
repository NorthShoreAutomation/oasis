"""Exact-number JSON text for the working store of the semantic stage.

The semantic stage keeps some record parts on disk as JSON text. Numbers
must come back with the same value (``DOC-2``), so no binary number is ever
made. ``dumps`` writes an ``int`` as written and a ``Decimal`` by ``str``.
A ``Decimal`` whose text has no fraction and no exponent gets ``E0``, so it
reads back as a ``Decimal`` and not as an ``int``. Key order is kept, and
the text has no spaces. ``loads`` reads integers as ``int`` and all other
numbers as ``Decimal``.

The input is a parsed JSON tree from ``strict_json``: ``dict`` with ``str``
keys, ``list``, ``str``, ``int``, finite ``Decimal``, ``bool``, and
``None``. Any other value, a ``float`` included, raises ``TypeError``.
"""

import json
from decimal import Decimal

__all__ = ["dumps", "loads"]


def _number_text(value: Decimal) -> str:
    if not value.is_finite():
        raise TypeError("not a finite number")
    text = str(value)
    if "." not in text and "E" not in text:
        text += "E0"
    return text


def _write(value, parts):
    if value is None:
        parts.append("null")
    elif value is True:
        parts.append("true")
    elif value is False:
        parts.append("false")
    elif isinstance(value, int):
        parts.append(int.__repr__(value))
    elif isinstance(value, Decimal):
        parts.append(_number_text(value))
    elif isinstance(value, str):
        parts.append(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, list):
        parts.append("[")
        for index, item in enumerate(value):
            if index:
                parts.append(",")
            _write(item, parts)
        parts.append("]")
    elif isinstance(value, dict):
        parts.append("{")
        for index, (key, item) in enumerate(value.items()):
            if not isinstance(key, str):
                raise TypeError("an object key is not a string")
            if index:
                parts.append(",")
            parts.append(json.dumps(key, ensure_ascii=False))
            parts.append(":")
            _write(item, parts)
        parts.append("}")
    else:
        raise TypeError("not a JSON value of the exact-number tree")


def dumps(value) -> str:
    """Return the compact JSON text of ``value`` with exact numbers."""
    parts = []
    _write(value, parts)
    return "".join(parts)


def _refuse_constant(name):
    raise ValueError("a non-finite number constant is not exact JSON")


def loads(text: str):
    """Return the tree of ``text``: integers as ``int``, other numbers as ``Decimal``."""
    return json.loads(text, parse_float=Decimal, parse_constant=_refuse_constant)
