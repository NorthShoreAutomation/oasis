"""Validate one OASIS 2.0 document file or multi-file package and report one result record.

Run from the repository root::

    python3 -m tests.conformance.validate PATH [--json] [--work-dir DIR] [--max-line-bytes N] [--max-gzip-ratio N]

``PATH`` is a document file, a multi-file manifest file, or a package
folder. A folder means ``PATH/oasis-package.json``, which is opened as a
member file is: a link, a pipe, or another special file there is refused
with ``Setup failed: input file cannot be read.`` A file whose root has
``manifest.members`` is a multi-file manifest: the parent of the path as
given is the package folder, and ``multifile.evaluate_folder`` checks the
package, with its own stage order. A manifest file or a package folder that
the caller names may be a link, because that path is the caller's own
input. Inside the package folder no link is followed: a member file that is
a link, or under a linked folder, is ``MEMBER_NOT_REGULAR``. Any other file
is a single document. The three options apply to a multi-file package only.
``--work-dir`` names the folder for the working files, which stay there;
without it a new temporary folder is used and removed at the end. Do not
put it inside the package folder: the next check would find its files as
unlisted files. ``--max-line-bytes`` and
``--max-gzip-ratio`` set the member reader limits (``multifile.ReadLimits``);
passing one is a setup failure, not a finding.

Stages of a single document, in order. The first stage that stops decides the outcome, so setup
outranks input, input outranks routing, routing outranks the number limits,
and the number limits outrank structure:

1. Read the input file. An unreadable file is ``setup-failed``.
2. Load the schema bundle from ``definitions`` and record the SHA-256 of its
   manifest. A missing locked package, a bad bundle, or a bundle whose
   ``spec_version`` is not in the supported table is ``setup-failed``.
3. Parse: strict-parse the input (``DOC-1``). A strict JSON policy violation
   is ``input-invalid`` with one ``INPUT_INVALID`` diagnostic. A numeric
   resource refusal or nesting beyond the interpreter limit is
   ``setup-failed`` with a limitation that names the limit.
4. Route: the root checks of ``REC-2`` and ``UNS-1``, in order (the exchange
   document test, the exact version check, the root ``type`` test). A
   failure is ``unsupported`` with one diagnostic; no other stage runs.
5. Number limits (``DOC-4``). Findings give ``input-invalid`` with the
   record ``type`` and ``spec_version`` set; no schema is run.
6. Structural validation against the selected entry point. Errors give
   ``structural: invalid`` and the semantic stage is not run.
7. Semantic checks. Diagnostics are sorted by path, then code.
8. Result: one result record.

Exit codes:

- 0 (PASS): status ``complete``, structure valid, and no error diagnostic.
  Warnings are allowed.
- 1 (FAIL): status ``input-invalid`` or ``unsupported``, invalid structure,
  or an error diagnostic.
- 2 (ERROR): status ``setup-failed``. Wrong option syntax is an argparse
  usage error, also exit 2, with usage text on stderr and nothing on stdout.

Output never contains input values. Diagnostics carry fixed catalog
messages, limitations are fixed text, and schema errors are reported only
by a JSON Pointer cut before the first author-chosen key and the failing
keyword, because validator messages can echo input values.

The result record has a ``form`` key: ``single-document`` or ``multi-file``.
In a multi-file package a diagnostic or a structural error can carry
``member`` and ``line``. ``member`` is the pointer ``/manifest/members/<n>``
to the member entry, never the member path text, and ``line`` is the 1-based
line in that member file. A diagnostic for a file that the manifest does not
list carries ``unlisted_path``, its path relative to the package folder. That
path is in the JSON record only; the text output shows ``(unlisted file)``.
A key is absent when it is unset. A single-document result has none of them.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

# Import names of every distribution in requirements-lock.txt. Only their
# absence is a setup failure; any other import error surfaces as a traceback.
LOCKED_IMPORT_NAMES = frozenset({
    "attrs", "jsonschema", "jsonschema_specifications", "referencing",
    "rfc3339_validator", "rpds", "six", "typing_extensions",
})
_MISSING_PACKAGE = "Setup failed: a required Python package cannot be imported. Install tests/conformance/requirements-lock.txt."

# The harness types module uses only the standard library.
from tests.conformance.types import InputInvalid, SetupFailed  # noqa: E402

_import_failure = None
try:
    from tests.conformance import multifile
    from tests.conformance.bundle import read_manifest_bytes
    from tests.conformance.document import SUPPORTED_VERSIONS, route
    from tests.conformance.loader import load_bundle
    from tests.conformance.number_limits import check_number_limits
    from tests.conformance.semantic import CATALOG, check, diagnostic
    from tests.conformance.strict_json import parse_input
except ModuleNotFoundError as error:
    if (error.name or "").partition(".")[0] not in LOCKED_IMPORT_NAMES:
        raise
    _import_failure = _MISSING_PACKAGE
except SetupFailed as error:
    # Import-time environment checks, such as the integer digit limit.
    _import_failure = f"Setup failed: {error}."

FORM_SINGLE = "single-document"
FORM_MULTI = "multi-file"

HARNESS_ID = "oasis-python-reference-harness"
HARNESS_VERSION = "2.0.0-draft.4"
# The direct pins of requirements.txt.
DEPENDENCIES = ("jsonschema==4.26.0", "referencing==0.37.0", "rfc3339-validator==0.1.4")

ROOT = Path(__file__).resolve().parents[2] / "definitions"

_UNREADABLE_INPUT = "Setup failed: input file cannot be read."
_BUNDLE_VERSION = "Setup failed: the schema bundle version is not supported by this checker."
_SEMANTIC_NESTING = "Setup failed: semantic check nesting exceeds the Python interpreter recursion limit."
_MANIFEST_WITHOUT_FOLDER = (
    "Setup failed: a multi-file manifest is checked with its package folder, not as one document."
)

# Schema path steps that do not consume an instance step. Each maps to the
# number of schema path tokens the step takes (the keyword and, for some,
# the subschema name or index that follows it).
_TRANSPARENT = {
    "$defs": 2, "allOf": 2, "anyOf": 2, "oneOf": 2, "dependentSchemas": 2,
    "if": 1, "then": 1, "else": 1, "not": 1, "$ref": 1, "dependentRequired": 1,
}
# A key reached through one of these steps is author-chosen and ends the pointer.
_OPEN_KEYS = frozenset({"unevaluatedProperties", "additionalProperties", "propertyNames", "patternProperties"})


def _pointer(parts) -> str:
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def safe_pointer(error) -> str:
    """Return the error's instance pointer, cut before the first author-chosen key.

    The schema path is walked beside the instance path. A key is kept only
    when the schema names it under ``properties``; an array index is kept
    when reached through ``items`` or named under ``prefixItems``. Steps
    such as ``$ref``, ``allOf``, ``anyOf``, ``oneOf``, ``if``, ``then``,
    ``else``, ``not``, ``$defs``, ``dependentRequired``, and
    ``dependentSchemas`` do not consume an instance step and are skipped. A
    key reached through ``unevaluatedProperties``, ``additionalProperties``,
    ``propertyNames``, or ``patternProperties``, or any step that cannot be
    matched, ends the pointer, so input key text never appears.
    """
    schema_path = list(error.absolute_schema_path)
    instance_path = list(error.absolute_path)
    kept = []
    i = 0
    while i < len(schema_path) and len(kept) < len(instance_path):
        token = schema_path[i]
        last = i == len(schema_path) - 1
        step = instance_path[len(kept)]
        is_index = isinstance(step, int) and not isinstance(step, bool)
        if token == "properties" and not last:
            if step != schema_path[i + 1]:
                break
            kept.append(step)
            i += 2
        elif token == "prefixItems" and not last:
            if not is_index or step != schema_path[i + 1]:
                break
            kept.append(step)
            i += 2
        elif token == "items" and not last:
            if not is_index:
                break
            kept.append(step)
            i += 1
        elif isinstance(token, str) and token in _TRANSPARENT:
            i += _TRANSPARENT[token]
        else:
            # An open-key step or any unmatched step ends the pointer.
            break
    return _pointer(kept)


def _printable(text: str) -> str:
    """Escape control and other non-printable characters for one-line output."""
    return "".join(c if c.isprintable() else f"\\u{ord(c):04x}" for c in text)


def schema_keyword(error) -> str:
    """The failing schema keyword; a ``false`` subschema has none and is reported as ``false``."""
    return error.validator if isinstance(error.validator, str) else "false"


_MEMBERS_PREFIX = "/manifest/members/"


def _member_pointer(index: int) -> str:
    return f"{_MEMBERS_PREFIX}{index}"


def _location_key(member, line) -> tuple:
    """Sort key for a location. A finding without a member comes first, then by member and line."""
    return (-1 if member is None else member, 0 if line is None else line)


def _add_location(entry: dict, member, line) -> dict:
    """Add ``member`` and ``line`` to a result entry; an unset one stays absent."""
    if member is not None:
        entry["member"] = _member_pointer(member)
    if line is not None:
        entry["line"] = line
    return entry


def _structural_records(items) -> list:
    """Return result entries for ``(path, keyword, member, line)`` items.

    Equal items are reported once. The order is member, line, path, then
    keyword; a single-document item has no member or line, so it sorts by
    path, then keyword, as before.
    """
    unique = set(items)
    ordered = sorted(unique, key=lambda i: (*_location_key(i[2], i[3]), i[0], i[1]))
    return [_add_location({"path": path, "keyword": keyword}, member, line) for path, keyword, member, line in ordered]


def _structural_errors(errors, locations=None) -> list:
    """Return result entries for schema errors, reduced to a safe pointer and a keyword.

    ``locations`` is optional. When it is given it holds one ``(member, line)``
    pair for each error, in the same order, for errors found on a line of a
    member file.
    """
    errors = list(errors)
    if locations is None:
        locations = [(None, None)] * len(errors)
    return _structural_records(
        (safe_pointer(error), schema_keyword(error), member, line)
        for error, (member, line) in zip(errors, locations, strict=True)
    )


# The most entries that one result lists, counted for the findings and for the schema
# errors on their own. One fault that many records repeat, such as an unresolved
# reference that every asset names, would otherwise grow the result with the record
# count: a document of 32000 assets would list 32000 findings.
# ``multifile.FINDINGS_PER_MEMBER`` bounds one stage of one member file; this bounds
# the result itself, so a single document and a package of many member files are both
# bounded. The cap is far above the count that a reader works through by hand.
MAX_RESULT_ENTRIES = 10000

_RESULT_CAPPED = (
    "Findings were capped: the result lists at most 10000 findings and at most 10000 schema errors, "
    "and the rest are not listed."
)


def add_limitation(record: dict, limitation: str) -> None:
    """Append ``limitation`` to ``record`` once, keeping the ones already there."""
    if limitation not in record["limitations"]:
        record["limitations"].append(limitation)


def cap_entries(record: dict, entries: list) -> list:
    """Return ``entries`` cut to ``MAX_RESULT_ENTRIES``, declaring the cut on ``record``.

    The caller sorts before it caps, so the entries that remain are the first ones
    in result order and the cap is the same on every run. When the cap drops an
    entry, the result declares ``_RESULT_CAPPED``, so a reader never takes a capped
    list for a complete one.
    """
    if len(entries) <= MAX_RESULT_ENTRIES:
        return entries
    add_limitation(record, _RESULT_CAPPED)
    return entries[:MAX_RESULT_ENTRIES]


def assign_diagnostics(record: dict, diagnostics) -> None:
    """Set the result findings from ``diagnostics``, capped at ``MAX_RESULT_ENTRIES``."""
    record["diagnostics"] = cap_entries(record, _diagnostics(diagnostics))


def _diagnostics(diagnostics) -> list:
    """Return result entries, sorted by member, line, path, code, then unlisted path.

    A single-document finding has no member, line, or unlisted path, so its
    order is path, then code.
    """
    ordered = sorted(
        diagnostics,
        key=lambda d: (*_location_key(d.member, d.line), d.path, d.code, d.unlisted_path or ""),
    )
    records = []
    for d in ordered:
        entry = {"code": d.code, "rule": d.rule, "severity": d.severity, "path": d.path, "message": d.message}
        _add_location(entry, d.member, d.line)
        if d.unlisted_path is not None:
            entry["unlisted_path"] = d.unlisted_path
        records.append(entry)
    return records


def _blank_record(data) -> dict:
    return {
        "harness": {"id": HARNESS_ID, "version": HARNESS_VERSION, "dependencies": list(DEPENDENCIES)},
        "file": None,
        "form": FORM_SINGLE,
        "input_sha256": None if data is None else hashlib.sha256(data).hexdigest(),
        "bundle_manifest_sha256": None,
        "type": None,
        "spec_version": None,
        "execution_status": "setup-failed",
        "structural": "not-run",
        "semantic": "not-run",
        "diagnostics": [],
        "structural_errors": [],
        "limitations": [],
    }


def _setup_failed(record: dict, limitation: str) -> dict:
    record["limitations"] = [limitation]
    return record


def _document_stages(record: dict, data: bytes, root: Path):
    """Run the stages 2 to 6 that a single document and a multi-file manifest file share.

    These are setup, parse, route, number limits, and structure, on the
    input bytes ``data`` against the bundle at ``root``. When a stage stops,
    ``record`` holds its outcome and the result is ``None``. Otherwise the
    result is ``(bundle, parsed, routing)``, and ``record`` has the bundle
    digest, ``type``, and ``spec_version``.
    """
    if _import_failure is not None:
        _setup_failed(record, _import_failure)
        return None
    try:
        manifest_bytes = read_manifest_bytes(root)
        record["bundle_manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        bundle = load_bundle(root, manifest_bytes)
    except SetupFailed as error:
        _setup_failed(record, f"Setup failed: {error}.")
        return None
    if bundle.manifest.spec_version not in SUPPORTED_VERSIONS:
        _setup_failed(record, _BUNDLE_VERSION)
        return None

    try:
        parsed = parse_input(data)
    except InputInvalid:
        record["execution_status"] = "input-invalid"
        assign_diagnostics(record, [diagnostic("INPUT_INVALID", "")])
        return None
    except SetupFailed as error:
        # NumericResourceRefused and the nesting limit: fixed text naming the limit.
        _setup_failed(record, f"Setup failed: {error}.")
        return None

    routing = route(parsed.value)
    record["type"] = routing.kind
    record["spec_version"] = routing.spec_version
    if routing.status != "selected":
        record["execution_status"] = "unsupported"
        assign_diagnostics(record, routing.diagnostics)
        return None

    limits = check_number_limits(parsed.value, bundle.property_names)
    if limits:
        record["execution_status"] = "input-invalid"
        assign_diagnostics(record, limits)
        return None

    try:
        errors = bundle.entry_point(routing.kind).validate(parsed)
    except SetupFailed as error:
        _setup_failed(record, f"Setup failed: {error}.")
        return None
    if errors:
        record["execution_status"] = "complete"
        record["structural"] = "invalid"
        record["structural_errors"] = cap_entries(record, _structural_errors(errors))
        return None
    return bundle, parsed, routing


def evaluate(data: bytes, root: Path) -> dict:
    """Run the stages on input bytes against the bundle at root; return the result record.

    ``file`` is None here; ``main`` fills it with the command argument.
    """
    record = _blank_record(data)
    stages = _document_stages(record, data, root)
    if stages is None:
        return record
    _bundle, parsed, routing = stages
    if multifile.has_members(parsed.value):
        # The member files are not in ``data``, so no verdict is possible here.
        return _setup_failed(record, _MANIFEST_WITHOUT_FOLDER)

    try:
        diagnostics = check(parsed.value, routing)
    except RecursionError:
        return _setup_failed(record, _SEMANTIC_NESTING)
    record["execution_status"] = "complete"
    record["structural"] = "valid"
    record["semantic"] = "run"
    assign_diagnostics(record, diagnostics)
    return record


def exit_code(record: dict) -> int:
    """Return 2 for setup failure, 0 for a clean complete result, else 1."""
    if record["execution_status"] == "setup-failed":
        return 2
    clean = record["execution_status"] == "complete" and record["structural"] == "valid"
    if clean and not any(d["severity"] == "error" for d in record["diagnostics"]):
        return 0
    return 1


def _location(entry: dict) -> str:
    """The text location of a finding, for example ``member 17 line 4 /id``.

    The member shows as its manifest position, never as its path. An
    unlisted file has no manifest position and shows as ``(unlisted file)``;
    its path is never printed. A member finding with no line and the empty
    path is about the whole member file, so it shows no path. Any other
    empty path shows as ``(root)``.
    """
    parts = []
    if "member" in entry:
        parts.append(f"member {entry['member'].removeprefix(_MEMBERS_PREFIX)}")
    if "line" in entry:
        parts.append(f"line {entry['line']}")
    if "unlisted_path" in entry:
        parts.append("(unlisted file)")
    elif entry["path"]:
        parts.append(entry["path"])
    elif "member" not in entry or "line" in entry:
        parts.append("(root)")
    return " ".join(parts)


def _human(record: dict, code: int) -> str:
    verdict = ("PASS", "FAIL", "ERROR")[code]
    lines = [
        f"{verdict} status={record['execution_status']} type={record['type'] or 'none'} "
        f"structural={record['structural']} semantic={record['semantic']}"
    ]
    for d in record["diagnostics"]:
        lines.append(f"{d['severity']} {d['code']} {_location(d)}: {d['message']}")
    if record["structural_errors"]:
        lines.append(f"schema errors: {len(record['structural_errors'])}")
        for error in record["structural_errors"]:
            lines.append(f"  {_location(error)} keyword {error['keyword']}")
    for limitation in record["limitations"]:
        lines.append(f"note: {limitation}")
    return "\n".join(_printable(line) for line in lines) + "\n"


def _is_multi_file(data: bytes) -> bool:
    """True when ``data`` parses and its root has ``manifest.members``.

    A ``members`` key is written either as plain text or with at least one
    ``\\u`` escape. A document with neither is a single document, and it is
    not parsed here.
    """
    if b"members" not in data and b"\\u" not in data:
        return False
    try:
        value = parse_input(data).value
    except (InputInvalid, SetupFailed):
        return False
    return multifile.has_members(value)


def _positive_int(text: str) -> int:
    """An option value that is a whole number of 1 or more. The error text does not repeat the value."""
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError("must be a whole number of 1 or more")
    return value


def _read_limits(args) -> "multifile.ReadLimits":
    given = {"max_line_bytes": args.max_line_bytes, "max_gzip_ratio": args.max_gzip_ratio}
    return multifile.ReadLimits(**{name: value for name, value in given.items() if value is not None})


def _check_path(args) -> dict:
    """Return the result record for the command argument: a folder, a manifest file, or a document file."""
    path = Path(args.file)
    # os.path.isdir is False on any OSError, so a path that cannot be read stays a read failure below.
    if os.path.isdir(path):
        if _import_failure is not None:
            record = _blank_record(None)
            record["form"] = FORM_MULTI
            return _setup_failed(record, _import_failure)
        manifest = path / multifile.MANIFEST_NAME
        return multifile.evaluate_folder(manifest, ROOT, args.work_dir, _read_limits(args), from_folder=True)
    try:
        data = path.read_bytes()
    except OSError:
        return _setup_failed(_blank_record(None), _UNREADABLE_INPUT)
    if _import_failure is None and _is_multi_file(data):
        return multifile.evaluate_folder(path, ROOT, args.work_dir, _read_limits(args), from_folder=False)
    return evaluate(data, ROOT)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m tests.conformance.validate",
        description=(
            "Validate one OASIS 2.0 document file or multi-file package. "
            "Exit 0 pass, 1 fail, 2 setup failure or usage error."
        ),
    )
    parser.add_argument(
        "file", metavar="PATH", help="a JSON document file, a multi-file manifest file, or a package folder"
    )
    parser.add_argument("--json", action="store_true", help="print the result record as one JSON object")
    parser.add_argument(
        "--work-dir",
        type=Path,
        metavar="DIR",
        help="folder for the working files of a multi-file check; they stay there "
        "(default: a new temporary folder, removed at the end)",
    )
    parser.add_argument(
        "--max-line-bytes",
        type=_positive_int,
        metavar="N",
        help="longest member file line, in bytes; a longer line stops the check as a setup failure (default: 64 MiB)",
    )
    parser.add_argument(
        "--max-gzip-ratio",
        type=_positive_int,
        metavar="N",
        help="most a gzip member file may expand, as a multiple of its stored bytes, plus 1 MiB (default: 1000)",
    )
    args = parser.parse_args(argv)
    record = _check_path(args)
    # A non-UTF-8 byte in a path decodes to a lone surrogate; record valid text.
    record["file"] = os.fsencode(args.file).decode("utf-8", "backslashreplace")
    code = exit_code(record)
    if args.json:
        sys.stdout.write(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(_human(record, code))
    return code


if __name__ == "__main__":
    sys.exit(main())
