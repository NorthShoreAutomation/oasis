"""Shared types for the offline conformance harness."""

from dataclasses import dataclass, field
from typing import Any


class SetupFailed(Exception):
    """The harness environment or a schema bundle is unusable."""


class InputInvalid(Exception):
    """An input document violates the strict parse policy."""


class NumericResourceRefused(SetupFailed):
    """A numeric resource guard was exceeded."""


# Held only by tests.conformance.strict_json.parse_input. Any other caller
# that constructs ParsedInput gets a TypeError.
_PARSED_INPUT_TOKEN = object()


@dataclass(frozen=True)
class ParsedInput:
    """A strict-parsed input: the exact-number tree and the input SHA-256.

    ``value`` holds ``int`` for integer lexemes and ``Decimal`` for all other
    numbers. ``sha256`` is the lowercase hex digest of the original bytes.
    Only ``parse_input`` may construct this type.
    """

    value: Any
    sha256: str
    _token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self._token is not _PARSED_INPUT_TOKEN:
            raise TypeError("ParsedInput is constructed only by parse_input")


@dataclass(frozen=True)
class Diagnostic:
    """One finding: a catalog code, its rule, severity, JSON Pointer, and text."""

    code: str
    rule: str
    severity: str
    path: str
    message: str


@dataclass(frozen=True)
class Routing:
    """The routing decision: ``selected`` or ``unsupported``.

    ``kind`` (the root record ``type``) and ``spec_version`` hold the supported values, or None when the
    declared value is absent or not supported.
    """

    status: str
    kind: str | None
    spec_version: str | None
    diagnostics: tuple[Diagnostic, ...]
