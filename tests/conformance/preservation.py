"""Compare two decoded JSON trees under the CONTRACT.md preservation rules.

This module is a comparator only. It makes no producer, consumer, or
round-trip claim, and running it is not preservation evidence for any
implementation. It compares trees that ``strict_json.parse_input`` produced
(``ParsedInput.value``), so numbers are exact ``int`` or ``Decimal`` values.

Rules:

- Object key order is ignored. Array order is significant.
- Mathematically equal numbers are equal (``25``, ``25.0``, ``2.5e1``).
  Comparison is exact; numbers are never converted to float.
- A boolean is never equal to a number. Null is distinct from absence.
- Strings are compared exactly, with no normalization of any kind.
- A missing or added member is reported at the member path.
- An array length difference is reported at the array path, and every
  shared-prefix index is still compared. Tail indexes are not reported.
- A scalar or type difference is reported at the differing value path.
- Paths are RFC 6901 JSON Pointers, sorted and deduplicated in the same
  lexical order as diagnostics.
"""

from decimal import Decimal

from tests.conformance.results import sort_pointers


def _token(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _kind(value) -> str:
    # bool is a subclass of int, so it is checked first.
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, Decimal)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    raise TypeError("compare_trees accepts only parse_input trees")


def compare_trees(source, output) -> tuple[str, list[str]]:
    """Return ("preserved", []) when the trees are equal, else ("changed", paths)."""
    changed = []
    # An explicit stack keeps deep trees off the interpreter recursion limit.
    stack = [("", source, output)]
    while stack:
        path, left, right = stack.pop()
        kind = _kind(left)
        if kind != _kind(right):
            changed.append(path)
        elif kind == "object":
            for key in left.keys() | right.keys():
                member = f"{path}/{_token(key)}"
                if key in left and key in right:
                    stack.append((member, left[key], right[key]))
                else:
                    changed.append(member)
        elif kind == "array":
            if len(left) != len(right):
                changed.append(path)
            for index, (a, b) in enumerate(zip(left, right)):
                stack.append((f"{path}/{index}", a, b))
        elif left != right:
            # int and Decimal compare exactly with each other.
            changed.append(path)
    if not changed:
        return "preserved", []
    return "changed", sort_pointers(changed)
