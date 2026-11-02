"""Number limits of the whole document (DOC-4, RFC 7493 section 2.2).

This is the only harness module that may use a binary64 number, and only for
the precision test below. Every other check reads the exact-number tree.

Each JSON number, at any depth and inside ``extensions`` too, is tested by
its exact value:

- Range: the absolute value is greater than 2^53 - 1. ``NUMBER_OUT_OF_RANGE``.
- Precision: the value is not the exact value of the nearest binary64 number,
  that is ``Decimal(repr(float(v))) != v``. Underflow to 0 fails this test.
  ``NUMBER_TOO_PRECISE``. Only a number in range gets this test.

Pointers never carry an author-chosen key. A path ends at the first
``extensions`` member, and before any key that is not a property name of the
schema bundle. One diagnostic is reported per (path, code).
"""

from decimal import Decimal

from tests.conformance.semantic import diagnostic, pointer

__all__ = ["LIMIT", "check_number_limits", "number_finding"]

LIMIT = 2**53 - 1


def number_finding(value):
    """Return the DOC-4 code that ``value`` breaks, or ``None``.

    ``value`` is an ``int`` or a ``Decimal`` from ``strict_json``. A boolean
    is not a number.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return "NUMBER_OUT_OF_RANGE" if abs(value) > LIMIT else None
    if isinstance(value, Decimal):
        if value.copy_abs() > LIMIT:
            return "NUMBER_OUT_OF_RANGE"
        if Decimal(repr(float(value))) != value:
            return "NUMBER_TOO_PRECISE"
    return None


def check_number_limits(value, property_names) -> list:
    """Return the DOC-4 diagnostics of the tree ``value``, sorted by (path, code).

    ``property_names`` is the set of property names of the schema bundle
    (``Bundle.property_names``). The walk uses an explicit stack, so depth is
    bounded only by the parse.
    """
    found = set()
    # (node, path to report at, True when the path is already cut)
    stack = [(value, "", False)]
    while stack:
        node, path, cut = stack.pop()
        if isinstance(node, dict):
            for key, item in node.items():
                if cut:
                    stack.append((item, path, True))
                elif key not in property_names:
                    stack.append((item, path, True))
                elif key == "extensions":
                    stack.append((item, pointer(path, key), True))
                else:
                    stack.append((item, pointer(path, key), False))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                stack.append((item, path if cut else pointer(path, index), cut))
        else:
            code = number_finding(node)
            if code is not None:
                found.add((path, code))
    return [diagnostic(code, path) for path, code in sorted(found)]
