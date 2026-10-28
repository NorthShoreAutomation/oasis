# OASIS conformance harness

## Purpose

This harness checks OASIS 2.0 JSON documents against one schema bundle, the bundle at `definitions/`, under one core profile.
The bundle manifest `definitions/bundle-manifest.json` lists every schema file, its SHA-256 digest, and its identifier.

For one document, the harness checks strict JSON syntax, the record type and version, the structure against the schemas, and the semantic rules that the schemas cannot express.
It reports each finding as a diagnostic with a fixed code.

The harness does not claim more than that.
A passing result is not import authorization, and it is not proof that two implementations exchange data correctly.

## The five stages and the outcome order

Each document goes through five stages, in this order:

1. Parse: the strict JSON parser reads the bytes (`strict_json.py`).
2. Route: the root `type` and `spec_version` select a schema (`document.py`).
3. Structural: the selected schema validates the document (`loader.py`).
4. Semantic: the cross-field and cross-record checks run (`semantic.py`, `timecode.py`).
5. Result: the command builds one result record (`validate.py`).

The first stage that stops decides the outcome.
A setup failure outranks a problem with the input.
An input problem outranks a routing problem, and a routing problem outranks a structural problem.
Semantic checks run only on a structurally valid document.

## Status

- This is a draft harness for contract version `2.0.0-draft.2`. It is not a release.
- Interoperability between independent implementations is not demonstrated.
- The fixture corpus in `fixtures/` is small and synthetic. Scale and operational limits are untested.

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

Full command (all harness tests):

```sh
tmp/oasis-conformance/bin/python -W error -m unittest discover -s tests/conformance -t . -p 'test_*.py'
```

Focused command (semantic checks on records and packages):

```sh
tmp/oasis-conformance/bin/python -m unittest tests.conformance.test_semantic_records tests.conformance.test_semantic_package
```

Focused command (timecode arithmetic and regular expressions):

```sh
tmp/oasis-conformance/bin/python -m unittest tests.conformance.test_timecode tests.conformance.test_ecma_regex
```

## Validate command line

This command checks one JSON document file through all five stages:

```sh
tmp/oasis-conformance/bin/python -m tests.conformance.validate FILE [--json]
```

The text output has one status line, then zero or more detail lines:

- Status line: `PASS`, `FAIL`, or `ERROR`, then `status=`, `type=`, `structural=`, and `semantic=` values.
- Diagnostic line: the severity, the code, the path (`(root)` for the empty path), and the catalog message.
- Schema error lines: `schema errors: N`, then one indented line per error with its path and its failing keyword.
- Note line: `note:` and a fixed limitation text, for example the reason for a setup failure.

Exit codes:

- Exit 0 (`PASS`): status `complete`, structure valid, and no diagnostic with severity `error`. Warnings are allowed.
- Exit 1 (`FAIL`): status `input-invalid` or `unsupported`, invalid structure, or at least one error diagnostic.
- Exit 2 (`ERROR`): status `setup-failed`. This includes an input file that cannot be read, a missing locked Python package, a bad bundle, a numeric resource refusal, and nesting beyond the interpreter limit. Wrong option syntax also exits 2, with usage text on standard error and nothing on standard output.

Output never contains input values.
Diagnostics carry fixed catalog messages, and notes are fixed text.
A schema error shows only its location and its failing keyword.
A location stops before the first author-chosen object key.
Text output escapes control characters.

Example, a standalone collection with one warning:

```text
$ tmp/oasis-conformance/bin/python -m tests.conformance.validate definitions/examples/collection-full.json
PASS status=complete type=collection structural=valid semantic=run
warning DEFINITION_UNAVAILABLE /metadata/0: The metadata definition is not in the document, so the value shape was not checked.
```

Example, a fixture with one semantic error:

```text
$ tmp/oasis-conformance/bin/python -m tests.conformance.validate tests/conformance/fixtures/records/relationship-self.json
FAIL status=complete type=asset structural=valid semantic=run
error RELATIONSHIP_SELF /relationships/0/target: A relationship targets its own asset.
```

Example, a fixture with one structural error:

```text
$ tmp/oasis-conformance/bin/python -m tests.conformance.validate tests/conformance/fixtures/records/structural-asset-unknown-key.json
FAIL status=complete type=asset structural=invalid semantic=not-run
schema errors: 1
  (root) keyword unevaluatedProperties
```

`test_validate.py` checks the command.

## Result record

With `--json`, the command prints one JSON object instead of the text lines. `result.schema.json` describes it. The fields are:

- `harness`: the harness `id`, its `version`, and its direct `dependencies` pins.
- `file`: the file argument as given.
- `input_sha256`: the SHA-256 of the input bytes, or `null` when the file cannot be read.
- `bundle_manifest_sha256`: the SHA-256 of the bundle manifest bytes, or `null` when setup stops first.
- `type` and `spec_version`: the routed values, or `null`.
- `execution_status`: `complete`, `input-invalid`, `unsupported`, or `setup-failed`.
- `structural`: `valid`, `invalid`, or `not-run`.
- `semantic`: `run` or `not-run`.
- `diagnostics`: objects with `code`, `rule`, `severity`, `path`, and `message`, sorted by path, then code.
- `structural_errors`: objects with `path` and `keyword`, sorted.
- `limitations`: fixed text notes. A setup failure has at least one.

## Diagnostic catalog

Severity `error` fails the command. Severity `warning` does not. Paths are RFC 6901 JSON Pointers to the value that caused the finding; the empty path is the root.

| Code | Rule | Severity | Message |
| --- | --- | --- | --- |
| `INPUT_INVALID` | `DOC-1` | error | Input bytes cannot be parsed under the strict JSON policy. |
| `TYPE_UNSUPPORTED` | `UNS-1` | error | The document root has no supported record type. |
| `VERSION_UNSUPPORTED` | `REC-4`, `UNS-1` | error | The declared spec_version is not supported by this checker. |
| `COUNT_MISMATCH` | `PKG-3` | error | A declared count does not equal the length of its array. |
| `REFERENCE_UNRESOLVED` | `PKG-6` | error | A reference does not resolve in a complete registry. |
| `REFERENCE_UNRESOLVED_PARTIAL` | `PKG-6` | warning | A reference does not resolve in a partial registry. |
| `ID_DUPLICATE` | `ID-1` | error | A record id is repeated within its record type. |
| `NESTED_ID_DUPLICATE` | `ID-4` | error | A nested id is repeated within its record. |
| `SNAPSHOT_MISMATCH` | `ID-6` | error | A collection snapshot differs from the registry record. |
| `RATE_NOT_LOWEST_TERMS` | `TIME-2` | error | A rate is not written in lowest terms. |
| `RANGE_NOT_INCREASING` | `TIME-4` | error | A range does not end after it starts. |
| `TIMELINE_UNDECLARED` | `TIME-5`, `TIME-12` | error | A frame field belongs to a timeline with no time base. |
| `TIMELINE_UNAVAILABLE` | `TIME-12`, `ANN-3` | warning | The owning asset is not in the document, so timing agreement was not checked. |
| `SECONDS_DISAGREE` | `TIME-7` | error | A derived seconds value names a different frame. |
| `TIMECODE_DISAGREE` | `TIME-7`, `TIME-8` | error | A timecode label differs from the label derived from the frame value. |
| `FRAME_OUT_OF_BOUNDS` | `TIME-9` | error | A frame position lies outside the asset duration. |
| `SEQUENCE_RANGE_EMPTY` | `GRP-3` | error | An image sequence range does not end after it starts. |
| `TRACK_DUPLICATE` | `GRP-4` | error | A file group repeats a track type and index pair. |
| `FILE_REFERENCE_UNRESOLVED` | `GRP-4` | error | A file group member names a file that is not in the asset. |
| `SEGMENT_INDEX_MISSING` | `GRP-6` | error | A file group member shares a track type and index pair with a segment but has no segment_index. |
| `SEGMENT_INDEX_DUPLICATE` | `GRP-6` | error | A file group repeats a segment_index within one track type and index pair. |
| `SEGMENT_OUT_OF_ORDER` | `GRP-6` | error | File group segments are not in ascending segment_index order. |
| `SEGMENT_GAP` | `GRP-6` | error | A complete file group has a gap in the segment_index values of one track type and index pair. |
| `ORDINAL_DUPLICATE` | `VER-2` | error | Two versions share an ordinal. |
| `VERSION_REFERENCE_UNRESOLVED` | `VER-3` | error | A version reference names no version in the asset. |
| `VERSION_WITHOUT_VERSIONS` | `VER-3` | error | A version reference appears on an asset with no versions. |
| `RELATIONSHIP_SELF` | `REL-3` | error | A relationship targets its own asset. |
| `COLLECTION_CYCLE` | `COL-4` | error | A collection is its own ancestor. |
| `MEMBERSHIP_DISAGREES` | `COL-5` | error | An asset claims membership that a complete collection list denies. |
| `VALUE_SHAPE_MISMATCH` | `MD-4` | error | A metadata value does not match the value_type and cardinality of its definition. |
| `VALUE_DATE_INVALID` | `MD-4`, `DT-1`, `DT-3` | error | A date or date-time metadata value is not valid. |
| `VALUE_OPTION_UNKNOWN` | `MD-4` | error | An enum value is not an option id of its definition. |
| `VALUE_OPTION_REPEATED` | `MD-4` | error | A multiple enum value repeats an option id. |
| `DEFINITION_UNAVAILABLE` | `MD-4` | warning | The metadata definition is not in the document, so the value shape was not checked. |
| `DEFINITION_REPEATED` | `MD-5` | error | A metadata array names the same definition twice. |
| `NAMESPACE_UNDECLARED` | `EXT-2` | error | An extension namespace is used but not declared in the manifest. |
| `NAMESPACE_DECLARED_TWICE` | `EXT-2` | error | A namespace token is declared more than once. |

## Rules with no document check

These rules have no check in the harness. Each reason is below.

| Rule | Reason |
| --- | --- |
| `PKG-4` | It defines what `partial` means. A document cannot show what the producer holds. |
| `PKG-8` | Array order carries no meaning, so there is nothing to check. |
| `TIME-9`, equality clause | No schema object carries `start_frame`, `end_frame`, and `duration_frames` together, so the clause has nothing to apply to in this draft. The bounds part of `TIME-9` is checked. |
| `TIME-10` | A variable-rate asset omits `timing`. A document cannot show that its source rate was variable. |
| `FILE-2` | The schema gives a file exactly one `storage_location` string. No further check applies. |
| `FILE-5` | It defines what each file role means. The allowed values are structural. Meaning cannot be checked. |
| `GRP-2` | It defines what each file group role means. Meaning cannot be checked. |
| `GRP-5` | There is no implicit grouping. Absence of a rule cannot be checked. |
| `REL-2` | The meaning of each relationship kind is informative. A `subclip_of` relationship without `range` is a structural error. |
| `ANN-2` | Choosing the right `purpose` is a producer obligation. The allowed values are structural. |
| `ACC-2` | It defines what each access status means. Meaning cannot be checked. |
| `REC-3` | Every record schema fixes `spec_version` to `2.0.0-draft.2` with `const`, so a mismatch inside a package is a structural error in this draft. No separate check is needed. |

These rules state producer or consumer obligations. A document alone cannot show them:

- `SAFE-1`: validation never opens any file other than the document and the schema bundle, never opens a file or location named by a value in the document, and never connects to a network or storage system, resolves a credential, or reads media bytes. The harness follows this rule.
- `REC-4`: a consumer reads `type` and `spec_version` before it selects a schema. The harness does this in its route stage.
- `PKG-5`: a package carries no digest of itself. Transport integrity is outside the contract.
- `ID-3`: identity scope is the package. Merging records across packages is consumer policy.
- `FILE-4`: validation never computes a checksum. A declared checksum is a producer claim.
- `STO-2`, producer part: a producer never places a secret value in a storage location. Validation never connects.
- `EXT-4`: a consumer that re-emits a record preserves every unknown namespace byte for byte.
- `ACC-3`: a consumer that cannot represent `restricted` or `unknown` blocks or quarantines the entity.
- `UNS-1`, consumer part: a consumer does not accept a document with no `type` or with a `spec_version` outside major 2. The harness reports such a document as unsupported.

## Standalone records

A standalone record is a single record file, not a package. It cannot see other records. Two checks give a warning instead of an error:

- `TIMELINE_UNAVAILABLE`: a standalone annotation with a `start_frame` or `end_frame`, or a relationship `range` whose target asset is not in the document. The owning asset's time base is not available, so timing agreement is not checked.
- `DEFINITION_UNAVAILABLE`: a metadata value whose definition is not in the document. The value shape is not checked.

Outside a package, the harness does not resolve references and does not check extension namespaces.
Checks that need only the record itself, such as a collection that names itself as its parent, still run.

The examples in `definitions/examples/` show this. `test_examples.py` asserts the exact diagnostics of each example. The three package examples give none.

## Format checking

The structural stage checks four formats: `date-time`, `date`, `regex`, and `uri`.
Each check is syntax only. A `uri` value is never fetched or resolved.
A schema that uses any other format fails setup.

## Regular expressions

A `pattern` in a schema, and a metadata `constraints.pattern` value, use ECMA-262 syntax.
The harness parses the strict ECMA-262 grammar without Annex B and without the `u` flag (`ecma_regex.py`).
It translates each schema pattern to Python with ECMA meaning: `\d` and `\w` match ASCII only, `$` is the absolute end of the string, and `.` stops at line terminators.
Metadata constraint patterns are checked for syntax only. They are never run against values.

Two limits are known:

- Syntax is judged per UTF-16 code unit, as ECMA-262 does without the `u` flag. So a range or class over characters above U+FFFF is parsed as surrogate units. The translator refuses any pattern that holds a surrogate unit or a character above U+FFFF (`Untranslatable`); no pattern in the bundle is affected.
- A pattern nested beyond the checker's resource limit, which the Python interpreter recursion limit sets, is a setup failure, not an invalid pattern. The note says that pattern nesting exceeds the checker's resource limit.

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

- No nesting threshold is approved. The harness enforces no declared nesting limit.
  It stops at interpreter or decoder limits instead.
  The depths below are approximate. They depend on the Python interpreter recursion limit (default 1,000) and on the decoder limits.
  Ordinary inputs are far below all of them.
- Well-formed input nested more than about 1,000 levels.
  The harness fails setup with a fixed note: the input nesting exceeds the Python interpreter recursion limit.
- Malformed input nested about 10,000 levels or more.
  Python's JSON decoder gives up at about that depth before it finds the syntax error, so the harness reports `setup-failed`.
  For this case, the harness does not meet the rule that malformed input is reported first.
  Below about 10,000 levels, the harness reports malformed input as `input-invalid`.
- If structural validation or a semantic check reaches the interpreter recursion limit, the harness also fails setup with a fixed note that names the limit.
  No nesting threshold is approved, so this result is not a conformance claim about such input.

## Offline guarantee

Tests and the validate command never use the network.
Schema loading reads only the files that the bundle manifest lists, and it verifies each file digest.
A reference to any other resource fails setup. Nothing is retrieved.
The check of each bundle schema against the JSON Schema 2020-12 metaschema is also offline: the metaschemas come from the installed package, and retrieval is refused.
Only the setup step above uses the network, to install pinned packages.

## Limits

- The harness runs the validate direction only. It has no producer, consumer, or round-trip adapter.
- It makes no interoperability claim.
- It never computes a checksum. A declared checksum is not verified.
- It does not evaluate access. An access status is read as a value only.
- A `complete` result does not mean a document is safe or approved to import.
