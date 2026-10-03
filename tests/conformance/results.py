"""Build and check result protocol 1.0.0 records for the local harness.

``build_validate_result`` produces one ``validate``-direction result for a
fixture case, a format mode, and a named bundle root. Structural outcomes
come from the Python structural adapter. The semantic part of an
``exchange-1x`` case comes from a profile checker, by default
``profiles.exchange_checker``; ``legacy-1x`` never calls it. Results never
copy validator error messages, because those messages can echo input values.

Command line (prints one result as JSON)::

    python3 -m tests.conformance.results --fixture ID --format-mode MODE --root NAME
"""

import argparse
import functools
import hashlib
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft7Validator

from tests.conformance import loader
from tests.conformance.bundle import MANIFEST_NAME, parse_bundle_manifest
from tests.conformance.corpus import DIAGNOSTIC_SEVERITY, fixture_cases
from tests.conformance.profiles import check_reference_context, exchange_checker
from tests.conformance.strict_json import (
    MAX_ABS_EXPONENT,
    MAX_EXPANSION_UNITS,
    MAX_TOKEN_BYTES,
    parse_input,
    parse_schema_bytes,
)
from tests.conformance.types import (
    Diagnostic,
    FixtureCase,
    InputInvalid,
    NumericResourceRefused,
    ParsedInput,
    ProfileOutcome,
    SetupFailed,
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FIXTURES = HERE / "fixtures"
RESULT_SCHEMA = HERE / "result.schema.json"
ROOTS = {"baseline": HERE / "baseline", "current": REPO / "definitions"}
FORMAT_MODES = ("required", "historical-unchecked")

PROTOCOL_VERSION = "1.0.0"
IMPLEMENTATION_ID = "oasis-python-reference-harness"
IMPLEMENTATION_VERSION = "0.1.0-draft"
AUTHORS = ("OASIS conformance harness contributors",)
DEPENDENCIES = ("jsonschema==4.26.0", "referencing==0.37.0", "rfc3339-validator==0.1.4")

_REVISION = re.compile(r"[0-9a-f]{40}")
_INPUT_INVALID_MESSAGE = "Input bytes cannot be parsed under the strict JSON transport policy."
_UNCHECKED_LIMITATION = (
    "Date-time format assertions were not checked: labelled historical-unchecked baseline comparison."
)


class ResultInvalid(ValueError):
    """A result breaks the result schema or a cross-field rule."""


ProfileChecker = Callable[[FixtureCase, ParsedInput, str], ProfileOutcome]


# Ordering: RFC 6901 escaped strings compared by Unicode scalar value.
# Python str comparison is by code point, which is exactly that order.

def sort_pointers(pointers: Iterable[str]) -> list:
    """Return the unique pointers in contract lexical order."""
    return sorted(set(pointers))


def sort_diagnostics(diagnostics: Iterable[Diagnostic]) -> list:
    """Drop repeated code/path pairs (first wins), then sort by path, then code."""
    unique = {}
    for diagnostic in diagnostics:
        unique.setdefault((diagnostic.path, diagnostic.code), diagnostic)
    return [unique[key] for key in sorted(unique)]


def severity_problems(diagnostics: Iterable[Diagnostic]) -> list:
    """Return one problem per diagnostic whose severity is not its catalog severity."""
    problems = []
    for index, diagnostic in enumerate(diagnostics):
        expected = DIAGNOSTIC_SEVERITY.get(diagnostic.code)
        if expected is None:
            problems.append(f"diagnostics[{index}]: code is not in the catalog")
        elif diagnostic.severity != expected:
            problems.append(f"diagnostics[{index}]: severity does not match the catalog")
    return problems


@functools.lru_cache(maxsize=1)
def _result_validator():
    schema = parse_schema_bytes(RESULT_SCHEMA.read_bytes())
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema)


def _cross_field_problems(result) -> list:
    """Rules that Draft 7 cannot express simply. Assumes the schema passed."""
    diagnostics = [Diagnostic(**item) for item in result["diagnostics"]]
    problems = severity_problems(diagnostics)
    if diagnostics != sort_diagnostics(diagnostics):
        problems.append("diagnostics are not sorted and unique by path and code")
    preservation = result["preservation"]
    if preservation["status"] != "changed" and preservation["paths"]:
        problems.append("preservation paths must be empty unless status is changed")
    if preservation["paths"] != sort_pointers(preservation["paths"]):
        problems.append("preservation paths are not sorted and unique")
    if result["direction"] == "validate":
        if preservation["status"] != "not-tested":
            problems.append("validate direction requires preservation not-tested")
        if result["output"] is not None:
            problems.append("validate direction requires null output")
    elif preservation["status"] == "not-tested":
        # Without comparable output the status is unsupported, never not-tested.
        problems.append(f"{result['direction']} direction preservation must not be not-tested")
    failed = result["execution_status"] in ("setup-failed", "input-invalid")
    if failed != (result["structural"] == "not-run"):
        problems.append("structural not-run is used only, and always, for setup or input failure")
    if result["execution_status"] == "setup-failed" and diagnostics:
        problems.append("setup failure carries no diagnostics")
    if result["execution_status"] == "input-invalid" and [(d.code, d.path) for d in diagnostics] != [("INPUT_INVALID", "")]:
        problems.append("input-invalid carries exactly INPUT_INVALID at the root")
    known_profile = result["profile"] in ("legacy-1x", "exchange-1x")
    if not known_profile and result["execution_status"] != "setup-failed":
        # Setup failure outranks every later outcome, including input failure.
        problems.append("unknown profile requires setup-failed")
    if failed:
        if result["routing"] != "not-applied":
            problems.append("setup or input failure requires not-applied routing")
    elif known_profile:
        problems.extend(_outcome_table_problems(result, diagnostics))
    return problems


# Routing-stage codes; every other catalog code is a semantic diagnostic.
_ROUTING_CODES = frozenset({"INPUT_INVALID", "PROFILE_UNSUPPORTED", "VERSION_UNSUPPORTED"})


def _outcome_table_problems(result, diagnostics) -> list:
    """CONTRACT.md outcome table rows after setup and input failure. Assumes structural is valid or invalid."""
    routing, status, structural = result["routing"], result["execution_status"], result["structural"]
    codes = [(d.code, d.path) for d in diagnostics]
    if result["profile"] == "legacy-1x":
        problems = []
        if routing != "not-applied":
            problems.append("legacy-1x requires not-applied routing")
        if status != "complete":
            problems.append("legacy-1x requires complete status")
        if diagnostics:
            problems.append("legacy-1x carries no semantic diagnostics")
        return problems
    if routing == "unsupported":
        problems = []
        if status != "unsupported":
            problems.append("unsupported routing requires unsupported status")
        excluded = codes == [("PROFILE_UNSUPPORTED", "")]
        versions = bool(codes) and all(code == "VERSION_UNSUPPORTED" for code, _ in codes)
        if not (excluded or versions):
            problems.append(
                "unsupported routing requires PROFILE_UNSUPPORTED at the root or only VERSION_UNSUPPORTED"
            )
        return problems
    if routing != "selected":
        return ["exchange-1x outcome requires selected or unsupported routing"]
    if status not in ("blocked", "complete"):
        return ["selected routing requires blocked or complete status"]
    problems = []
    if any(d.code in _ROUTING_CODES for d in diagnostics):
        problems.append("selected routing carries only semantic diagnostics")
    if structural == "invalid":
        if status != "blocked":
            problems.append("selected structural invalid requires blocked status")
        if diagnostics:
            problems.append("selected structural invalid carries no semantic diagnostics")
        return problems
    has_error = any(d.severity == "error" for d in diagnostics)
    if has_error and status != "blocked":
        problems.append("selected structural valid with an error-severity diagnostic requires blocked status")
    if not has_error and status != "complete":
        problems.append("selected structural valid without error-severity diagnostics requires complete status")
    return problems


def result_problems(result) -> list:
    """Return schema and cross-field problems. Locations only, never values."""
    errors = sorted(_result_validator().iter_errors(result), key=lambda e: list(e.absolute_path))
    if errors:
        return [f"{error.json_path}: fails result schema keyword {error.validator}" for error in errors]
    return _cross_field_problems(result)


def check_result(result) -> None:
    """Raise ResultInvalid when the result breaks the protocol."""
    problems = result_problems(result)
    if problems:
        raise ResultInvalid("; ".join(problems))


def dump_result(result) -> bytes:
    """Serialize a result as UTF-8 JSON bytes with a final newline."""
    return (json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _numeric_limitation(error: NumericResourceRefused) -> str:
    return (
        "Numeric resource guards refused the input before structural evaluation. "
        f"Configured limits: numeric token length at most {MAX_TOKEN_BYTES:,} ASCII bytes; "
        f"absolute decimal exponent at most {MAX_ABS_EXPONENT:,}; "
        f"expansion budget at most {MAX_EXPANSION_UNITS:,} digit units per document. "
        f"Exceeded limit: {error}."
    )


def _read(path: Path, what: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        raise SetupFailed(f"{what} cannot be read") from None


@dataclass(frozen=True)
class Evaluation:
    """The validate-direction outcome for one input, before it becomes a result.

    ``structural_errors`` holds the Draft 7 errors when structural validation
    ran; callers must not copy their messages, which can echo input values.
    """

    routing: str
    structural: str
    execution_status: str
    diagnostics: list
    limitations: tuple
    structural_errors: tuple = ()


def evaluate_input(
    data: bytes,
    *,
    schema_name: str,
    profile: str,
    reference_context,
    format_mode: str,
    root_path: Path,
    manifest_bytes: bytes,
    check_profile: Callable[[ParsedInput, str], ProfileOutcome],
) -> Evaluation:
    """Run setup, strict parsing, structural validation, and the profile check in contract order.

    Setup (unknown profile, ``exchange-1x`` with an unchecked format mode,
    malformed reference context, bundle load, and entry point selection)
    runs before parsing, so setup failure outranks input failure.
    ``check_profile`` is called only for ``exchange-1x``.
    """
    limitations = []
    routing, structural, status, diagnostics, errors = "not-applied", "not-run", "setup-failed", [], []
    parsing = False
    try:
        if profile not in ("legacy-1x", "exchange-1x"):
            raise SetupFailed("profile is not known")
        if profile == "exchange-1x" and format_mode != "required":
            raise SetupFailed("exchange-1x requires format_mode required")
        if profile == "exchange-1x":
            # Setup outranks input failure, so validate the context before parsing.
            check_reference_context(reference_context)
        bundle = loader.load_bundle(root_path, manifest_bytes)
        entry_point = bundle.entry_point(schema_name, check_formats=format_mode == "required")
        parsing = True
        document = parse_input(data)
        parsing = False
        errors = entry_point.validate(document)
        structural = "invalid" if errors else "valid"
        if profile == "legacy-1x":
            status = "complete"
        else:
            outcome = check_profile(document, structural)
            routing, status = outcome.routing, outcome.execution_status
            diagnostics = sort_diagnostics(outcome.diagnostics)
    # Every failure outranks any outcome already computed, so each handler
    # resets all outcome fields.
    except InputInvalid:
        routing, structural, status, errors = "not-applied", "not-run", "input-invalid", []
        diagnostics = [Diagnostic("INPUT_INVALID", "", DIAGNOSTIC_SEVERITY["INPUT_INVALID"], _INPUT_INVALID_MESSAGE)]
    except SetupFailed as error:
        routing, structural, status, diagnostics, errors = "not-applied", "not-run", "setup-failed", [], []
        if parsing and isinstance(error, NumericResourceRefused):
            # Only a refusal of the input bytes is described as one.
            limitations.append(_numeric_limitation(error))
        else:
            limitations.append(f"Setup failed: {error}.")
    if format_mode == "historical-unchecked" and structural != "not-run":
        limitations.append(_UNCHECKED_LIMITATION)
    return Evaluation(routing, structural, status, diagnostics, tuple(limitations), tuple(errors))


def build_validate_result(
    case: FixtureCase,
    *,
    format_mode: str,
    root: str,
    source_revision: str,
    checker: ProfileChecker = exchange_checker,
) -> dict:
    """Build one validate-direction result.

    ``root`` names a bundle in ``ROOTS``. ``source_revision`` is the 40-hex
    commit that the caller resolved. Setup, input, and numeric failures become
    results. When the bundle manifest or input bytes cannot be read, or the
    manifest is invalid, no result can name its artifacts truthfully, so
    ``SetupFailed`` is raised instead. The result is checked before it is
    returned; ``ResultInvalid`` is raised when it breaks the protocol.
    """
    if format_mode not in FORMAT_MODES:
        raise ValueError("format_mode must be required or historical-unchecked")
    if root not in ROOTS:
        raise ValueError("root must name a repository bundle root")
    if not isinstance(source_revision, str) or not _REVISION.fullmatch(source_revision):
        raise ValueError("source_revision must be a 40-character lowercase hexadecimal commit")
    root_path = ROOTS[root]
    # One manifest snapshot names the artifacts and selects the compiled schemas.
    manifest_bytes = _read(root_path / MANIFEST_NAME, "bundle manifest")
    manifest = parse_bundle_manifest(manifest_bytes, root_path)
    data = _read(FIXTURES / case.path, "fixture input")

    outcome = evaluate_input(
        data,
        schema_name=case.schema_name,
        profile=case.profile,
        reference_context=case.reference_context,
        format_mode=format_mode,
        root_path=root_path,
        manifest_bytes=manifest_bytes,
        check_profile=lambda document, structural: checker(case, document, structural),
    )
    routing, structural, status = outcome.routing, outcome.structural, outcome.execution_status
    diagnostics, limitations = outcome.diagnostics, list(outcome.limitations)

    command = shlex.join([
        "python3", "-m", "tests.conformance.results",
        "--fixture", case.id, "--format-mode", format_mode, "--root", root,
    ])
    result = {
        "protocol_version": PROTOCOL_VERSION,
        "implementation": {
            "id": IMPLEMENTATION_ID,
            "version": IMPLEMENTATION_VERSION,
            "source_revision": source_revision,
            "authors": list(AUTHORS),
            "dependencies": list(DEPENDENCIES),
            "independence_claim": False,
        },
        "fixture_id": case.id,
        "schema_name": case.schema_name,
        "schema_revision": manifest.bundle_revision,
        "profile": case.profile,
        "context": case.context,
        "direction": "validate",
        "format_mode": format_mode,
        "routing": routing,
        "structural": structural,
        "diagnostics": [
            {"code": d.code, "path": d.path, "severity": d.severity, "message": d.message}
            for d in diagnostics
        ],
        "execution_status": status,
        "preservation": {"status": "not-tested", "paths": []},
        "output": None,
        "reproduction": {
            "command": command,
            "input_sha256": hashlib.sha256(data).hexdigest(),
            "artifact_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "limitations": limitations,
        },
    }
    check_result(result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Print one validate-direction conformance result.")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--format-mode", required=True, choices=FORMAT_MODES)
    parser.add_argument("--root", required=True, choices=sorted(ROOTS))
    args = parser.parse_args(argv)
    cases = {case.id: case for case in fixture_cases()}
    if args.fixture not in cases:
        parser.error("unknown fixture ID")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()
    result = build_validate_result(
        cases[args.fixture], format_mode=args.format_mode, root=args.root, source_revision=revision
    )
    sys.stdout.buffer.write(dump_result(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
