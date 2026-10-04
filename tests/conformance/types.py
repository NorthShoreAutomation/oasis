"""Shared types for the offline conformance harness."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


class SetupFailed(Exception):
    """The harness environment or a schema bundle is unusable."""


class InputInvalid(Exception):
    """An input document violates the strict parse policy."""


class NumericResourceRefused(SetupFailed):
    """A numeric resource guard was exceeded."""


@dataclass(frozen=True)
class ExpectedDiagnostic:
    """A diagnostic that a fixture case declares it expects."""

    code: str
    path: str


@dataclass(frozen=True)
class Diagnostic:
    """A diagnostic that an adapter reports."""

    code: str
    path: str
    severity: str
    message: str


@dataclass(frozen=True)
class ProfileOutcome:
    """What a profile checker reports for one structurally evaluated input."""

    routing: str
    execution_status: str
    diagnostics: tuple = ()


@dataclass(frozen=True)
class FixtureCase:
    """One corpus case as declared by the fixture manifest."""

    id: str
    schema_name: str
    path: str
    expected_valid: bool | None
    profile: str
    context: str
    validator_expectations: Mapping[str, Any]
    # Keyword-only so it can default to empty while later fields stay required.
    expected_diagnostics: tuple[ExpectedDiagnostic, ...] = field(default=(), kw_only=True)
    expected_execution_status: str
    expected_routing: str
    input_kind: str
    reference_context: Any
    provenance: Any
    exclusions: Any


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
