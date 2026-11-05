"""The fixture manifest: one expected outcome per fixture record or package.

``fixtures/manifest.json`` lists every file in ``fixtures/records/`` and every
folder in ``fixtures/packages/`` exactly once. A single-document case has the
path ``records/<id>.json``. A multi-file package case has the path
``packages/<id>/``, and the folder holds the package: its
``oasis-package.json`` and its member files. ``load_manifest`` strict-parses
the manifest and refuses any shape problem with ``SetupFailed``: an unknown or
missing key, a wrong type, an unknown status value, unsorted diagnostics, a
duplicate id, a path of neither form, a case whose file or folder is missing,
or a record file or package folder with no case.

An expected diagnostic is ``[code, path]`` or ``[code, path, member, line]``.
``member`` is the index of the member entry in ``manifest.members`` and
``line`` is the 1-based line in that member file. Either is ``null`` when the
finding has none. Only a package case may give ``member`` and ``line``.
Diagnostics are sorted as the checker sorts them: a finding without a member
first, then by member, line, path, and code.

``expected_schema_error`` is present exactly on a structurally invalid case:
the keyword and the RFC 6901 pointer of one error that the schema stage
reports. A ``false`` subschema has no keyword and is named ``false``.
"""

from dataclasses import dataclass
from pathlib import Path

from tests.conformance.strict_json import parse_schema_bytes
from tests.conformance.types import InputInvalid, SetupFailed

__all__ = ["DEFAULT_MANIFEST", "FixtureCase", "load_manifest"]

DEFAULT_MANIFEST = Path(__file__).resolve().parent / "fixtures" / "manifest.json"

PACKAGE_MANIFEST = "oasis-package.json"

MANIFEST_VERSION = "2.0.0"
CONTRACT = "2.0.0-draft.4"

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
_SCHEMA_ERROR_KEYS = frozenset({"keyword", "path"})
_STATUSES = frozenset({"complete", "input-invalid", "unsupported"})
_STRUCTURALS = frozenset({"valid", "invalid", "not-run"})


@dataclass(frozen=True)
class FixtureCase:
    """One manifest entry: a fixture record and its expected outcome."""

    id: str
    path: str
    expected_status: str
    expected_structural: str
    # Each item is (code, path) or (code, path, member, line), as written in the manifest.
    expected_diagnostics: tuple[tuple, ...]
    rules: tuple[str, ...]
    note: str
    expected_schema_error: tuple[str, str] | None = None

    @property
    def is_package(self) -> bool:
        """True for a multi-file package case (``packages/<id>/``); false for a single record."""
        return self.path.startswith("packages/")

    @property
    def located_diagnostics(self) -> tuple[tuple[str, str, int | None, int | None], ...]:
        """The expected diagnostics, each as (code, path, member, line) with ``None`` for a missing part."""
        return tuple((item + (None, None))[:4] if len(item) == 2 else item for item in self.expected_diagnostics)


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


def _index(value, where, minimum):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail("%s is not null or an integer of %d or more" % (where, minimum))
    return value


def _diagnostic(item, where, package):
    if not isinstance(item, list) or len(item) not in ((2, 4) if package else (2,)):
        _fail("%s holds an entry that is not a [code, path%s] list" % (where, ", member, line" if package else ""))
    if not isinstance(item[0], str) or not item[0] or not isinstance(item[1], str):
        _fail("%s holds an entry whose code or path is not a string" % where)
    if len(item) == 2:
        return item[0], item[1]
    return item[0], item[1], _index(item[2], where + " member", 0), _index(item[3], where + " line", 1)


def _order_key(item):
    """The order of the checker: no member first, then member, line, path, and code."""
    member, line = (item[2], item[3]) if len(item) == 4 else (None, None)
    return (-1 if member is None else member, 0 if line is None else line, item[1], item[0])


def _diagnostics(value, where, package):
    if not isinstance(value, list):
        _fail("%s is not an array" % where)
    items = [_diagnostic(item, where, package) for item in value]
    if items != sorted(items, key=_order_key):
        _fail("%s is not sorted by member, line, path, then code" % where)
    return tuple(items)


def _pointer(value, where):
    if not isinstance(value, str) or not all(
        part.replace("~0", "").replace("~1", "").count("~") == 0 for part in value.split("/")
    ) or (value and not value.startswith("/")):
        _fail("%s is not a JSON Pointer" % where)
    return value


def _schema_error(value, where):
    entry = _object(value, _SCHEMA_ERROR_KEYS, where)
    return _string(entry["keyword"], where + " keyword"), _pointer(entry["path"], where + " path")


def _case(value, index):
    where = "case %d" % index
    if not isinstance(value, dict):
        _fail("%s is not an object" % where)
    schema_error = None
    if "expected_schema_error" in value:
        if value.get("expected_structural") != "invalid":
            _fail("%s has expected_schema_error but is not structurally invalid" % where)
        schema_error = _schema_error(value["expected_schema_error"], where + " expected_schema_error")
        value = {k: v for k, v in value.items() if k != "expected_schema_error"}
    elif value.get("expected_structural") == "invalid":
        _fail("%s is structurally invalid but has no expected_schema_error" % where)
    entry = _object(value, _CASE_KEYS, where)
    case_id = _string(entry["id"], where + " id")
    path = _string(entry["path"], where + " path")
    package = path.startswith("packages/")
    expected_path = "packages/%s/" % case_id if package else "records/%s.json" % case_id
    if path != expected_path or "/" in case_id or case_id.startswith("."):
        _fail("%s path is not records/<id>.json or packages/<id>/" % where)
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
        expected_diagnostics=_diagnostics(entry["expected_diagnostics"], where + " expected_diagnostics", package),
        rules=_strings(entry["rules"], where + " rules"),
        note=_string(entry["note"], where + " note"),
        expected_schema_error=schema_error,
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
        if case.is_package:
            if not (base / case.path / PACKAGE_MANIFEST).is_file():
                _fail("case %s names a package folder with no %s" % (case.id, PACKAGE_MANIFEST))
        elif not (base / case.path).is_file():
            _fail("case %s names a file that does not exist" % case.id)
    records = base / "records"
    files = {entry.name for entry in records.iterdir()} if records.is_dir() else set()
    if files != {case.id + ".json" for case in cases if not case.is_package}:
        _fail("a file in records has no case")
    packages = base / "packages"
    folders = {entry.name for entry in packages.iterdir()} if packages.is_dir() else set()
    if folders != {case.id for case in cases if case.is_package}:
        _fail("an entry in packages has no case")
    return cases
