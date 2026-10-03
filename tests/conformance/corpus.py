"""Load and validate the proposed fixture manifest.

This module is named ``corpus`` because ``tests/conformance/fixtures/`` is the
corpus directory and cannot share an import name with a module.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from tests.conformance.strict_json import parse_schema_bytes
from tests.conformance.types import ExpectedDiagnostic, FixtureCase, InputInvalid, SetupFailed

DEFAULT_MANIFEST = Path(__file__).resolve().parent / "fixtures" / "manifest.json"

KNOWN_PROFILES = ("legacy-1x", "exchange-1x")
ENGINES = ("python-jsonschema",)
CONTEXTS = (
    "standalone", "asset-embedded", "asset-batch", "collection-batch", "asset-batch-embedded",
)
INPUT_KINDS = ("json", "raw-json")
EXECUTION_STATUSES = ("complete", "blocked", "unsupported", "input-invalid", "setup-failed")
ROUTINGS = ("not-applied", "selected", "unsupported")
ADAPTER_STATUSES = ("complete", "input-invalid", "setup-failed")
EXCLUSION_STATUSES = ("proposed", "approved")
PRESERVATION_STATUSES = ("preserved", "changed")

# Diagnostic catalog: code to fixed severity. Single source for later tasks.
DIAGNOSTIC_SEVERITY = {
    "INPUT_INVALID": "error",
    "VERSION_UNSUPPORTED": "error",
    "PROFILE_UNSUPPORTED": "error",
    "IDENTITY_UNUSABLE": "error",
    "IDENTITY_DUPLICATE": "error",
    "COLLECTION_CYCLE": "error",
    "SIZE_UNUSABLE": "error",
    "RATE_UNUSABLE": "error",
    "RANGE_REVERSED": "error",
    "CONNECTION_DATA_UNREVIEWED": "error",
    "RIGHTS_UNSUPPORTED": "error",
    "REFERENCE_UNRESOLVED": "warning",
    "MEMBERSHIP_UNINTERPRETED": "warning",
    "VALUE_SEMANTICS_UNSPECIFIED": "warning",
    "TIMING_UNINTERPRETED": "warning",
    "INTEGRITY_UNVERIFIED": "warning",
    "CHECKSUM_UNINTERPRETED": "warning",
    "COMPLETENESS_UNVERIFIED": "warning",
}

# RFC 6901: empty, or "/"-prefixed tokens where "~" is only "~0" or "~1".
_POINTER = re.compile(r"\A(?:/(?:[^~/]|~[01])*)*\Z")


@dataclass(frozen=True)
class PreservationComparison:
    id: str
    source_case_id: str
    output_case_id: str
    expected_status: str
    paths: tuple[str, ...]


def _fail(where, problem):
    raise SetupFailed(f"fixture manifest: {where}: {problem}")


def _mapping(value, where, keys):
    if not isinstance(value, dict):
        _fail(where, "must be an object")
    if set(value) != set(keys):
        _fail(where, "fields must be exactly " + ", ".join(sorted(keys)))
    return value


def _text(value, where):
    if not isinstance(value, str):
        _fail(where, "must be a string")
    return value


def _choice(value, allowed, where):
    if not isinstance(value, str) or value not in allowed:
        _fail(where, "not an allowed value")
    return value


def _pointer(value, where):
    if not isinstance(value, str) or not _POINTER.match(value):
        _fail(where, "not a valid RFC 6901 JSON Pointer")
    return value


def _bool_or_null(value, where):
    if value is not None and not isinstance(value, bool):
        _fail(where, "must be a boolean or null")
    return value


def _profile(value, where):
    if not isinstance(value, str) or value not in KNOWN_PROFILES:
        _fail(where, "unknown profile")
    return value


def _expectations(value, where):
    _mapping(value, where, ENGINES)
    for engine in ENGINES:
        spot = f"{where}.{engine}"
        entry = _mapping(
            value[engine], spot,
            ("required", "historical-unchecked", "adapter_status", "limitation"),
        )
        _bool_or_null(entry["required"], spot + ".required")
        _bool_or_null(entry["historical-unchecked"], spot + ".historical-unchecked")
        _choice(entry["adapter_status"], ADAPTER_STATUSES, spot + ".adapter_status")
        if entry["limitation"] is not None:
            _text(entry["limitation"], spot + ".limitation")
    return value


def _exclusions(value, where):
    if not isinstance(value, list):
        _fail(where, "must be a list")
    for index, item in enumerate(value):
        spot = f"{where}[{index}]"
        _mapping(item, spot, ("validator", "status", "reason"))
        _choice(item["validator"], ENGINES, spot + ".validator")
        _choice(item["status"], EXCLUSION_STATUSES, spot + ".status")
        _text(item["reason"], spot + ".reason")
    return value


def _diagnostics(value, where):
    if not isinstance(value, list):
        _fail(where, "must be a list")
    result = []
    for index, item in enumerate(value):
        spot = f"{where}[{index}]"
        _mapping(item, spot, ("code", "path"))
        _choice(item["code"], DIAGNOSTIC_SEVERITY, spot + ".code")
        _pointer(item["path"], spot + ".path")
        result.append(ExpectedDiagnostic(item["code"], item["path"]))
    return tuple(result)


def _reference_context(value, where):
    _mapping(value, where, ("asset_ids", "collection_ids"))
    for key in ("asset_ids", "collection_ids"):
        ids = value[key]
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            _fail(f"{where}.{key}", "must be a list of strings")
    return value


def _input_path(base, relative, where):
    _text(relative, where)
    parts = Path(relative).parts
    if Path(relative).is_absolute() or ".." in parts or not parts:
        _fail(where, "path must stay beneath the fixture directory")
    target = base / relative
    if not target.is_file():
        _fail(where, "input file is missing")
    return relative


def _case(raw, base, index):
    where = f"cases[{index}]"
    keys = (
        "id", "schema_name", "path", "profile", "context", "expected_valid",
        "validator_expectations", "expected_diagnostics", "expected_execution_status",
        "expected_routing", "input_kind", "reference_context", "provenance", "exclusions",
    )
    _mapping(raw, where, keys)
    expected_valid = _bool_or_null(raw["expected_valid"], where + ".expected_valid")
    if not isinstance(raw["provenance"], dict):
        _fail(where + ".provenance", "must be an object")
    return FixtureCase(
        id=_text(raw["id"], where + ".id"),
        schema_name=_text(raw["schema_name"], where + ".schema_name"),
        path=_input_path(base, raw["path"], where + ".path"),
        expected_valid=expected_valid,
        profile=_profile(raw["profile"], where + ".profile"),
        context=_choice(raw["context"], CONTEXTS, where + ".context"),
        validator_expectations=_expectations(
            raw["validator_expectations"], where + ".validator_expectations"
        ),
        expected_diagnostics=_diagnostics(
            raw["expected_diagnostics"], where + ".expected_diagnostics"
        ),
        expected_execution_status=_choice(
            raw["expected_execution_status"], EXECUTION_STATUSES,
            where + ".expected_execution_status",
        ),
        expected_routing=_choice(raw["expected_routing"], ROUTINGS, where + ".expected_routing"),
        input_kind=_choice(raw["input_kind"], INPUT_KINDS, where + ".input_kind"),
        reference_context=_reference_context(
            raw["reference_context"], where + ".reference_context"
        ),
        provenance=raw["provenance"],
        exclusions=_exclusions(raw["exclusions"], where + ".exclusions"),
    )


def _comparison(raw, index, cases_by_id):
    where = f"preservation_comparisons[{index}]"
    _mapping(raw, where, ("id", "source_case_id", "output_case_id", "expected_status", "paths"))
    for key in ("source_case_id", "output_case_id"):
        case = cases_by_id.get(raw[key]) if isinstance(raw[key], str) else None
        if case is None:
            _fail(f"{where}.{key}", "names no fixture case")
        if case.input_kind != "json":
            _fail(f"{where}.{key}", "names an input that is not parseable JSON")
    paths = raw["paths"]
    if not isinstance(paths, list):
        _fail(where + ".paths", "must be a list")
    for n, path in enumerate(paths):
        _pointer(path, f"{where}.paths[{n}]")
    if paths != sorted(set(paths)):
        _fail(where + ".paths", "must be sorted and unique")
    return PreservationComparison(
        id=_text(raw["id"], where + ".id"),
        source_case_id=raw["source_case_id"],
        output_case_id=raw["output_case_id"],
        expected_status=_choice(
            raw["expected_status"], PRESERVATION_STATUSES, where + ".expected_status"
        ),
        paths=tuple(paths),
    )


def _load(manifest_path):
    path = Path(manifest_path) if manifest_path is not None else DEFAULT_MANIFEST
    try:
        tree = parse_schema_bytes(path.read_bytes())
    except OSError:
        _fail("file", "cannot be read")
    except (InputInvalid, SetupFailed):
        _fail("file", "is not strict JSON")
    if not isinstance(tree, dict):
        _fail("root", "must be an object")
    profiles = tree.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        _fail("profiles", "must be a nonempty list")
    for index, profile in enumerate(profiles):
        _profile(profile, f"profiles[{index}]")
    raw_cases = tree.get("cases")
    if not isinstance(raw_cases, list):
        _fail("cases", "must be a list")
    base = path.parent
    cases = []
    seen = set()
    for index, raw in enumerate(raw_cases):
        case = _case(raw, base, index)
        if case.id in seen:
            _fail(f"cases[{index}].id", "duplicate fixture ID")
        if case.profile not in profiles:
            _fail(f"cases[{index}].profile", "profile is not declared by the manifest")
        seen.add(case.id)
        cases.append(case)
    return tree, cases


def fixture_cases(manifest_path: Path | None = None) -> list[FixtureCase]:
    """Return every validated corpus case in manifest order."""
    return _load(manifest_path)[1]


def preservation_comparisons(manifest_path: Path | None = None) -> list[PreservationComparison]:
    """Return the validated comparator examples, checking both case references."""
    tree, cases = _load(manifest_path)
    raw = tree.get("preservation_comparisons", [])
    if not isinstance(raw, list):
        _fail("preservation_comparisons", "must be a list")
    by_id = {case.id: case for case in cases}
    result = []
    seen = set()
    for index, item in enumerate(raw):
        comparison = _comparison(item, index, by_id)
        if comparison.id in seen:
            _fail(f"preservation_comparisons[{index}].id", "duplicate comparison ID")
        seen.add(comparison.id)
        result.append(comparison)
    return result
