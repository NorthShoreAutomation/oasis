"""The fixture manifest: one expected outcome per fixture record.

``fixtures/manifest.json`` lists every file in ``fixtures/records/`` exactly
once. ``load_manifest`` strict-parses the manifest and refuses any shape
problem with ``SetupFailed``: an unknown or missing key, a wrong type, an
unknown status value, unsorted diagnostics, a duplicate id, a path that is
not ``records/<id>.json``, a case whose file is missing, or a record file with
no case.
"""

from dataclasses import dataclass
from pathlib import Path

from tests.conformance.strict_json import parse_schema_bytes
from tests.conformance.types import InputInvalid, SetupFailed

__all__ = ["DEFAULT_MANIFEST", "FixtureCase", "load_manifest"]

DEFAULT_MANIFEST = Path(__file__).resolve().parent / "fixtures" / "manifest.json"

MANIFEST_VERSION = "2.0.0"
CONTRACT = "2.0.0-draft.2"

_TOP_KEYS = frozenset({"manifest_version", "contract", "provenance", "cases"})
_PROVENANCE_KEYS = frozenset({"kind", "source", "reuse_terms"})
_CASE_KEYS = frozenset(
    {
        "id",
        "path",
        "expected_status",
        "expected_structural",
        "expected_diagnostics",
        "rules",
        "note",
    }
)
_STATUSES = frozenset({"complete", "input-invalid", "unsupported"})
_STRUCTURALS = frozenset({"valid", "invalid", "not-run"})


@dataclass(frozen=True)
class FixtureCase:
    """One manifest entry: a fixture record and its expected outcome."""

    id: str
    path: str
    expected_status: str
    expected_structural: str
    expected_diagnostics: tuple[tuple[str, str], ...]
    rules: tuple[str, ...]
    note: str


def _fail(message):
    raise SetupFailed("fixture manifest: " + message)


def _object(value, keys, where):
    if not isinstance(value, dict):
        _fail("%s is not an object" % where)
    if set(value) != keys:
        _fail("%s does not have exactly the keys %s" % (where, ", ".join(sorted(keys))))
    return value


def _string(value, where):
    if not isinstance(value, str) or not value:
        _fail("%s is not a non-empty string" % where)
    return value


def _strings(value, where):
    if not isinstance(value, list):
        _fail("%s is not an array" % where)
    return tuple(_string(item, where) for item in value)


def _diagnostics(value, where):
    if not isinstance(value, list):
        _fail("%s is not an array" % where)
    pairs = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2 or not all(isinstance(s, str) for s in item):
            _fail("%s holds an entry that is not a [code, path] pair" % where)
        _string(item[0], where)
        pairs.append((item[0], item[1]))
    if pairs != sorted(pairs, key=lambda pair: (pair[1], pair[0])):
        _fail("%s is not sorted by path then code" % where)
    return tuple(pairs)


def _case(value, index):
    where = "case %d" % index
    entry = _object(value, _CASE_KEYS, where)
    case_id = _string(entry["id"], where + " id")
    path = _string(entry["path"], where + " path")
    if path != "records/%s.json" % case_id or "/" in case_id or case_id.startswith("."):
        _fail("%s path is not records/<id>.json" % where)
    status = entry["expected_status"]
    if status not in _STATUSES:
        _fail("%s expected_status is not a known status" % where)
    structural = entry["expected_structural"]
    if structural not in _STRUCTURALS:
        _fail("%s expected_structural is not a known value" % where)
    if (structural == "not-run") != (status != "complete"):
        _fail("%s expected_structural is not-run exactly when the status is not complete" % where)
    return FixtureCase(
        id=case_id,
        path=path,
        expected_status=status,
        expected_structural=structural,
        expected_diagnostics=_diagnostics(entry["expected_diagnostics"], where + " expected_diagnostics"),
        rules=_strings(entry["rules"], where + " rules"),
        note=_string(entry["note"], where + " note"),
    )


def load_manifest(path: Path = DEFAULT_MANIFEST) -> tuple[FixtureCase, ...]:
    """Read and check the fixture manifest at path. Raises SetupFailed on any shape problem."""
    path = Path(path)
    try:
        document = parse_schema_bytes(path.read_bytes())
    except OSError:
        _fail("cannot be read")
    except InputInvalid:
        _fail("is not strict JSON")
    top = _object(document, _TOP_KEYS, "root")
    if top["manifest_version"] != MANIFEST_VERSION:
        _fail("manifest_version is not %s" % MANIFEST_VERSION)
    if top["contract"] != CONTRACT:
        _fail("contract is not %s" % CONTRACT)
    provenance = _object(top["provenance"], _PROVENANCE_KEYS, "provenance")
    for key in sorted(_PROVENANCE_KEYS):
        _string(provenance[key], "provenance " + key)
    if not isinstance(top["cases"], list):
        _fail("cases is not an array")
    cases = tuple(_case(value, index) for index, value in enumerate(top["cases"]))
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        _fail("a case id is repeated")
    base = path.parent
    for case in cases:
        if not (base / case.path).is_file():
            _fail("case %s names a file that does not exist" % case.id)
    records = base / "records"
    files = {entry.name for entry in records.iterdir()} if records.is_dir() else set()
    if files != {case.id + ".json" for case in cases}:
        _fail("a file in records has no case")
    return cases
