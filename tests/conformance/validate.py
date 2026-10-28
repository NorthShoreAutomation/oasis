"""Validate one OASIS 2.0 document file and report one result record.

Run from the repository root::

    python3 -m tests.conformance.validate FILE [--json]

Stages, in order. The first stage that stops decides the outcome, so setup
outranks input, input outranks routing, and routing outranks structure:

1. Read the input file. An unreadable file is ``setup-failed``.
2. Load the schema bundle from ``definitions`` and record the SHA-256 of its
   manifest. A missing locked package or a bad bundle is ``setup-failed``.
3. Strict-parse the input. A strict JSON policy violation is
   ``input-invalid`` with one ``INPUT_INVALID`` diagnostic. A numeric
   resource refusal or nesting beyond the interpreter limit is
   ``setup-failed`` with a limitation that names the limit.
4. Route on ``type`` and ``spec_version``. An unsupported document is
   ``unsupported`` with the routing diagnostics; no schema is run.
5. Structural validation against the selected entry point. Errors give
   ``structural: invalid`` and the semantic stage is not run.
6. Semantic checks. Diagnostics are sorted by path, then code.

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
    from tests.conformance.bundle import read_manifest_bytes
    from tests.conformance.document import route
    from tests.conformance.loader import load_bundle
    from tests.conformance.semantic import CATALOG, check, diagnostic
    from tests.conformance.strict_json import parse_input
except ModuleNotFoundError as error:
    if (error.name or "").partition(".")[0] not in LOCKED_IMPORT_NAMES:
        raise
    _import_failure = _MISSING_PACKAGE
except SetupFailed as error:
    # Import-time environment checks, such as the integer digit limit.
    _import_failure = f"Setup failed: {error}."

HARNESS_ID = "oasis-python-reference-harness"
HARNESS_VERSION = "2.0.0-draft.2"
# The direct pins of requirements.txt.
DEPENDENCIES = ("jsonschema==4.26.0", "referencing==0.37.0", "rfc3339-validator==0.1.4")

ROOT = Path(__file__).resolve().parents[2] / "definitions"

_UNREADABLE_INPUT = "Setup failed: input file cannot be read."
_SEMANTIC_NESTING = "Setup failed: semantic check nesting exceeds the Python interpreter recursion limit."

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


def _structural_errors(errors) -> list:
    pairs = {(safe_pointer(error), error.validator) for error in errors}
    return [{"path": path, "keyword": keyword} for path, keyword in sorted(pairs)]


def _diagnostics(diagnostics) -> list:
    ordered = sorted(diagnostics, key=lambda d: (d.path, d.code))
    return [
        {"code": d.code, "rule": d.rule, "severity": d.severity, "path": d.path, "message": d.message}
        for d in ordered
    ]


def _blank_record(data) -> dict:
    return {
        "harness": {"id": HARNESS_ID, "version": HARNESS_VERSION, "dependencies": list(DEPENDENCIES)},
        "file": None,
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


def evaluate(data: bytes, root: Path) -> dict:
    """Run the stages on input bytes against the bundle at root; return the result record.

    ``file`` is None here; ``main`` fills it with the command argument.
    """
    record = _blank_record(data)
    if _import_failure is not None:
        return _setup_failed(record, _import_failure)
    try:
        manifest_bytes = read_manifest_bytes(root)
        record["bundle_manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        bundle = load_bundle(root, manifest_bytes)
    except SetupFailed as error:
        return _setup_failed(record, f"Setup failed: {error}.")

    try:
        parsed = parse_input(data)
    except InputInvalid:
        record["execution_status"] = "input-invalid"
        record["diagnostics"] = _diagnostics([diagnostic("INPUT_INVALID", "")])
        return record
    except SetupFailed as error:
        # NumericResourceRefused and the nesting limit: fixed text naming the limit.
        return _setup_failed(record, f"Setup failed: {error}.")

    routing = route(parsed.value)
    record["type"] = routing.kind
    record["spec_version"] = routing.spec_version
    if routing.status != "selected":
        record["execution_status"] = "unsupported"
        record["diagnostics"] = _diagnostics(routing.diagnostics)
        return record

    try:
        errors = bundle.entry_point(routing.kind).validate(parsed)
    except SetupFailed as error:
        return _setup_failed(record, f"Setup failed: {error}.")
    if errors:
        record["execution_status"] = "complete"
        record["structural"] = "invalid"
        record["structural_errors"] = _structural_errors(errors)
        return record

    try:
        diagnostics = check(parsed.value, routing)
    except RecursionError:
        return _setup_failed(record, _SEMANTIC_NESTING)
    record["execution_status"] = "complete"
    record["structural"] = "valid"
    record["semantic"] = "run"
    record["diagnostics"] = _diagnostics(diagnostics)
    return record


def exit_code(record: dict) -> int:
    """Return 2 for setup failure, 0 for a clean complete result, else 1."""
    if record["execution_status"] == "setup-failed":
        return 2
    clean = record["execution_status"] == "complete" and record["structural"] == "valid"
    if clean and not any(d["severity"] == "error" for d in record["diagnostics"]):
        return 0
    return 1


def _shown(path: str) -> str:
    return path or "(root)"


def _human(record: dict, code: int) -> str:
    verdict = ("PASS", "FAIL", "ERROR")[code]
    lines = [
        f"{verdict} status={record['execution_status']} type={record['type'] or 'none'} "
        f"structural={record['structural']} semantic={record['semantic']}"
    ]
    for d in record["diagnostics"]:
        lines.append(f"{d['severity']} {d['code']} {_shown(d['path'])}: {d['message']}")
    if record["structural_errors"]:
        lines.append(f"schema errors: {len(record['structural_errors'])}")
        for error in record["structural_errors"]:
            lines.append(f"  {_shown(error['path'])} keyword {error['keyword']}")
    for limitation in record["limitations"]:
        lines.append(f"note: {limitation}")
    return "\n".join(_printable(line) for line in lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m tests.conformance.validate",
        description="Validate one OASIS 2.0 document file. Exit 0 pass, 1 fail, 2 setup failure or usage error.",
    )
    parser.add_argument("file", help="path to the JSON document file")
    parser.add_argument("--json", action="store_true", help="print the result record as one JSON object")
    args = parser.parse_args(argv)
    try:
        data = Path(args.file).read_bytes()
    except OSError:
        data = None
    if data is None:
        record = _setup_failed(_blank_record(None), _UNREADABLE_INPUT)
    else:
        record = evaluate(data, ROOT)
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
