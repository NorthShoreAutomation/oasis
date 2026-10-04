"""Validate one JSON record file with structural and semantic checks.

Run from the repository root::

    python3 -m tests.conformance.validate FILE --schema NAME
        [--profile legacy-1x|exchange-1x] [--format-mode required|historical-unchecked]
        [--context JSON] [--root definitions|baseline] [--json]

Defaults: profile ``exchange-1x``, format mode ``required``, root
``definitions``, and empty reference context. The outcome follows the
CONTRACT.md outcome table through the same code as
``results.build_validate_result``, so setup failure outranks input failure.

Exit codes:

- 0 (PASS): status ``complete``. Warnings are allowed. For ``legacy-1x``,
  the structure must also be valid.
- 1 (FAIL): status ``blocked``, ``unsupported``, or ``input-invalid``; or
  ``legacy-1x`` with status ``complete`` but invalid structure. The profile
  gives no semantic verdict for legacy input, so a structural rejection is
  the failing check.
- 2 (ERROR): setup failure, a numeric resource refusal, an input file that
  cannot be read, a missing locked package, or an undecodable ``--context``
  for ``exchange-1x`` (``legacy-1x`` ignores context). Wrong option syntax
  is an argparse usage error, also exit 2, with no ERROR line.

Output never contains input values. Diagnostics carry fixed catalog
messages. Schema errors are reported only by JSON Pointer location and
failing keyword, because validator messages can echo input values.
"""

import argparse
import hashlib
import json
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
from tests.conformance.types import SetupFailed  # noqa: E402

_import_failure = None
try:
    from tests.conformance import results
    from tests.conformance.bundle import MANIFEST_NAME, parse_bundle_manifest
    from tests.conformance.profiles import validate_profile
except ModuleNotFoundError as error:
    if (error.name or "").partition(".")[0] not in LOCKED_IMPORT_NAMES:
        raise
    results, _import_failure = None, _MISSING_PACKAGE
except SetupFailed as error:
    # Import-time environment checks, such as the integer digit limit.
    results, _import_failure = None, f"Setup failed: {error}."

# Command root names and the results.ROOTS names they select.
ROOT_NAMES = {"definitions": "current", "baseline": "baseline"}
FORMAT_MODES = ("required", "historical-unchecked")
EMPTY_CONTEXT = {"asset_ids": [], "collection_ids": []}
_UNREADABLE_INPUT = "Setup failed: input file cannot be read."
_UNDECODABLE_CONTEXT = "Setup failed: reference context cannot be decoded as JSON."


def _pointer(parts) -> str:
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def safe_pointer(error) -> str:
    """Return the error's instance pointer, cut before the first author-chosen key.

    The schema path is walked beside the instance path. A key is kept only
    when the schema names it under ``properties``; array indexes from
    ``items`` and ``additionalItems`` are kept. A key reached through
    ``patternProperties`` or ``additionalProperties``, or any step that
    cannot be matched, ends the pointer, so input key text never appears.
    """
    schema_path = list(error.absolute_schema_path)
    instance_path = list(error.absolute_path)
    kept = []
    i = 0
    while i < len(schema_path) and len(kept) < len(instance_path):
        token = schema_path[i]
        last = i == len(schema_path) - 1
        step = instance_path[len(kept)]
        if token == "properties" and not last:
            if step != schema_path[i + 1]:
                break
            kept.append(step)
            i += 2
        elif token in ("items", "additionalItems") and not last:
            if not isinstance(step, int) or isinstance(step, bool):
                break
            kept.append(step)
            # The tuple form of items names the index in the schema path.
            i += 2 if token == "items" and isinstance(schema_path[i + 1], int) else 1
        elif token in ("patternProperties", "additionalProperties"):
            break
        elif token == "dependencies":
            i += 2
        else:
            i += 1
    return _pointer(kept)


def _printable(text: str) -> str:
    """Escape control and other non-printable characters for one-line output."""
    return "".join(c if c.isprintable() else f"\\u{ord(c):04x}" for c in text)


def _structural_errors(errors) -> list:
    pairs = {(safe_pointer(error), error.validator) for error in errors}
    return [{"path": path, "keyword": keyword} for path, keyword in sorted(pairs)]


def _exit_code(profile: str, status: str, structural: str) -> int:
    if status == "setup-failed":
        return 2
    if status == "complete" and not (profile == "legacy-1x" and structural == "invalid"):
        return 0
    return 1


def _shown(path: str) -> str:
    return path or "(root)"


def _blank_record(args, data) -> dict:
    return {
        "file": args.file,
        "schema": args.schema,
        "profile": args.profile,
        "format_mode": args.format_mode,
        "root": args.root,
        "routing": "not-applied",
        "structural": "not-run",
        "execution_status": "setup-failed",
        "diagnostics": [],
        "input_sha256": None if data is None else hashlib.sha256(data).hexdigest(),
        "artifact_sha256": None,
        "structural_errors": [],
        "limitations": [],
    }


def _evaluate(args, data: bytes) -> dict:
    root_path = results.ROOTS[ROOT_NAMES[args.root]]
    record = _blank_record(args, data)
    try:
        manifest_bytes = (root_path / MANIFEST_NAME).read_bytes()
    except OSError:
        record["limitations"] = ["Setup failed: bundle manifest cannot be read."]
        return record
    record["artifact_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    try:
        parse_bundle_manifest(manifest_bytes, root_path)
    except SetupFailed as error:
        record["limitations"] = [f"Setup failed: {error}."]
        return record
    # legacy-1x ignores context, so it is decoded only for other profiles.
    context = EMPTY_CONTEXT
    if args.context is not None and args.profile != "legacy-1x":
        try:
            context = json.loads(args.context)
        except (ValueError, RecursionError):
            record["limitations"] = [_UNDECODABLE_CONTEXT]
            return record
    outcome = results.evaluate_input(
        data,
        schema_name=args.schema,
        profile=args.profile,
        reference_context=context,
        format_mode=args.format_mode,
        root_path=root_path,
        manifest_bytes=manifest_bytes,
        check_profile=lambda document, structural: validate_profile(
            args.schema, document, args.profile, structural=structural, reference_context=context
        ),
    )
    record.update(
        routing=outcome.routing,
        structural=outcome.structural,
        execution_status=outcome.execution_status,
        diagnostics=[
            {"code": d.code, "path": d.path, "severity": d.severity, "message": d.message}
            for d in outcome.diagnostics
        ],
        structural_errors=_structural_errors(outcome.structural_errors),
        limitations=list(outcome.limitations),
    )
    return record


def _human(record: dict, code: int) -> str:
    verdict = ("PASS", "FAIL", "ERROR")[code]
    lines = [
        f"{verdict} status={record['execution_status']} routing={record['routing']} "
        f"structural={record['structural']}"
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
        description="Validate one JSON record file. Exit 0 pass, 1 fail, 2 setup failure or usage error.",
    )
    parser.add_argument("file", help="path to the JSON record file")
    parser.add_argument("--schema", required=True, help="entry point name, such as asset.schema.json")
    parser.add_argument("--profile", default="exchange-1x", metavar="{legacy-1x,exchange-1x}")
    parser.add_argument("--format-mode", default="required", choices=FORMAT_MODES)
    parser.add_argument("--context", help='reference context JSON: {"asset_ids": [...], "collection_ids": [...]}')
    parser.add_argument("--root", default="definitions", choices=sorted(ROOT_NAMES))
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    args = parser.parse_args(argv)
    try:
        data = Path(args.file).read_bytes()
    except OSError:
        data = None
    if data is None or results is None:
        record = _blank_record(args, data)
        record["limitations"] = [_UNREADABLE_INPUT if data is None else _import_failure]
    else:
        record = _evaluate(args, data)
    code = _exit_code(args.profile, record["execution_status"], record["structural"])
    if args.json:
        sys.stdout.write(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(_human(record, code))
    return code


if __name__ == "__main__":
    sys.exit(main())
