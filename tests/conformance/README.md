# OASIS conformance harness

## Purpose

This harness checks OASIS JSON documents against the OASIS schemas.
It compares two schema roots:

- `tests/conformance/baseline/`: the frozen v1.1.1 schemas (bundle revision `v1.1.1-1e2849b287bb`).
- `definitions/`: the current schemas (bundle revision `1.2.0-draft.1`).

Each root has a `bundle-manifest.json` that lists every schema file, its SHA-256 digest, and its base URI.
The fixture corpus in `fixtures/manifest.json` is the expectation authority.

Each fixture case selects a profile:

- `legacy-1x`: structural checks only. No semantic check runs.
- `exchange-1x`: structural checks, then version routing and the semantic checks in `profiles.py`.
  The checks follow the DRAFT 1.2.0-draft.1 contract and report the diagnostic codes in its catalog.

## Status

- This is a DRAFT 1.2.0-draft.1 harness. It is not a release.
- Structural checks run for every case. Semantic checks run only for `exchange-1x` cases.
- A corpus sweep checks every `exchange-1x` case at both roots against its declared routing, execution status, and diagnostics.
  It also checks that every `legacy-1x` result is unchanged: routing `not-applied`, status `complete`, and no diagnostics.
- `preservation.py` compares two decoded JSON trees under the contract's preservation rules.
  It is a comparator only. Its tests use the synthetic `preservation_comparisons` examples in the manifest.

### Limits

- A semantic result is not import authorization. A `complete` result does not mean a document is safe or approved to import.
- The harness runs the `validate` direction only. It has no producer, consumer, or round-trip adapter.
  It provides no producer or consumer evidence, and no preservation evidence for any implementation.
- It makes no interoperability claim.
- The corpus is small and synthetic. Scale and operational limits are untested.

## Offline guarantee

Tests never use the network.
Schema loading reads only the files that the selected bundle manifest lists.
A reference to any other resource fails setup. Nothing is retrieved.
Only the setup step below uses the network, to install pinned packages.

## Setup

Run all commands from the repository root.

### Scripted setup

```sh
tests/conformance/setup-environments.sh
```

The script builds the Python environment in `tmp/oasis-conformance`.
It installs the exact versions in `requirements-lock.txt`.
It is safe to run again.
If `python3 -m venv` fails because the host has no `python3-venv` package, the script uses an installed `uv` instead.

### Manual setup

```sh
mkdir -p tmp
python3 -m venv tmp/oasis-conformance
. tmp/oasis-conformance/bin/activate
python3 -m pip install -r tests/conformance/requirements.txt
```

On a host without `python3-venv`, replace the `venv` and `pip` lines with:

```sh
uv venv --python "$(command -v python3)" tmp/oasis-conformance
uv pip install --python tmp/oasis-conformance/bin/python -r tests/conformance/requirements.txt
```

### Offline install (optional)

A fully offline install needs cached public wheels.
While online, download them once:

```sh
python3 -m pip download -r tests/conformance/requirements-lock.txt -d tmp/wheelhouse
```

Then install with no index:

```sh
python3 -m pip install --no-index --find-links tmp/wheelhouse -r tests/conformance/requirements.txt
```

## Run the tests

Use the environment's Python. Activate the environment, or call `tmp/oasis-conformance/bin/python` directly.

Focused command (baseline and result protocol):

```sh
tmp/oasis-conformance/bin/python -m unittest tests.conformance.test_baseline tests.conformance.test_result_protocol
```

Focused command (semantic profile, corpus sweep, and preservation comparator):

```sh
tmp/oasis-conformance/bin/python -m unittest tests.conformance.test_profiles tests.conformance.test_preservation
```

Full command (all harness tests):

```sh
tmp/oasis-conformance/bin/python -W error -m unittest discover -s tests/conformance -t . -p 'test_*.py'
```

## Numeric resource limits

The strict parser applies these limits to every JSON number:

| Limit | Value |
| --- | --- |
| Numeric token length, including sign and exponent syntax | 1,024 ASCII bytes |
| Absolute decimal exponent | 10,000 |
| Expansion budget per document (coefficient digits plus absolute exponent, summed over all tokens) | 100,000 digit units |

These limits are operational setup guards. They protect the harness from very large numbers.
They are not OASIS value ranges, and they do not make a document invalid.
When a document exceeds a limit, the run fails setup. It never reports the document as invalid input.

## Nesting depth

- No nesting threshold is approved yet. The harness enforces no declared nesting limit.
  It stops at interpreter or decoder limits instead.
  The depths below are approximate. They depend on the Python interpreter recursion limit (default 1,000) and on the decoder limits.
  Ordinary corpus inputs are far below all of them.
- Well-formed input nested more than about 1,000 levels.
  The harness fails setup: its post-parse scan reaches the interpreter recursion limit.
- Malformed input nested about 10,000 levels or more.
  Python's JSON decoder gives up at about that depth before it finds the syntax error, so the harness reports `setup-failed`.
  For this case, the harness does not meet the contract rule that malformed input is reported first.
  Below about 10,000 levels, the harness reports malformed input as `input-invalid`.
- Well-formed input with derivative files nested about 165 levels or more (`files[].derivatives`).
  The harness fails setup: structural validation reaches the interpreter recursion limit, and the limitation names that limit.
  No nesting threshold is approved, so this result is not a conformance claim about such input.

## Validate command line

This command checks one JSON record file with structural and semantic checks:

```sh
tmp/oasis-conformance/bin/python -m tests.conformance.validate FILE --schema NAME [--profile legacy-1x|exchange-1x] [--format-mode required|historical-unchecked] [--context JSON] [--root definitions|baseline] [--json]
```

- Defaults: profile `exchange-1x`, format mode `required`, root `definitions`, and empty reference context.
- Output: one status line (`PASS`, `FAIL`, or `ERROR`, then status, routing, and structural values), then one line per diagnostic. `--json` prints one JSON object instead.
- Exit 0: status `complete`, warnings allowed. For `legacy-1x`, the structure must also be valid.
- Exit 1: status `blocked`, `unsupported`, or `input-invalid`, or `legacy-1x` with invalid structure. Legacy status is `complete` for any structure, so the command treats a structural rejection as the failing check.
- Exit 2 (`ERROR` line, or a setup-failed JSON object): setup failure, a numeric resource refusal, an input file that cannot be read, a missing locked Python package, or a `--context` value that is not JSON.
- Exit 2 (usage message on standard error only): wrong option syntax, such as a missing `--schema` or an unknown `--root` value.
- `--context` applies to `exchange-1x` only; `legacy-1x` does not decode it.
- Output never contains input values. Schema errors show only their location and failing keyword. A location stops before any author-chosen object key (`patternProperties` or `additionalProperties`). Text output escapes control characters.

It uses the same outcome code as the result command below. `test_validate.py` checks it.

## Result command line

This command prints one validate-direction result as JSON, checked against `result.schema.json`:

```sh
tmp/oasis-conformance/bin/python -m tests.conformance.results --fixture ID --format-mode MODE --root NAME
```

- `--fixture`: a case ID from `fixtures/manifest.json`.
- `--format-mode`: `required` checks date-time formats. `historical-unchecked` does not, to compare with the historical baseline.
- `--root`: `baseline` or `current`.

The result records the current Git commit as its source revision.
