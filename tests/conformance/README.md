# OASIS conformance harness

## Purpose

This harness checks OASIS 2.0 package documents against one schema bundle, the bundle at `definitions/`, under one core profile.
The only exchange document is a package. A bare record, such as a single asset, is not an exchange document.
The bundle manifest `definitions/bundle-manifest.json` lists every schema file, its SHA-256 digest, and its identifier.

For one document, the harness checks strict JSON syntax, the root `type` and version, the number limits, the structure against the schemas, and the semantic rules that the schemas cannot express.
For a multi-file package, it also checks the member list, the package folder, and each member file, and it runs the same checks on every line (`multifile.py`).
It reports each finding as a diagnostic with a fixed code.

The harness does not claim more than that.
A passing result is not import authorization, and it is not proof that two implementations exchange data correctly.

## The six stages and the outcome order

Each document goes through six stages, in this order:

1. Parse: the strict JSON parser reads the bytes (`DOC-1`, `strict_json.py`).
2. Route: the root checks select the package schema (`REC-2`, `UNS-1`, `document.py`).
3. Number limits: every JSON number meets the limits of RFC 7493 section 2.2 (`DOC-4`, `number_limits.py`).
4. Structural: the package schema validates the document (`loader.py`).
5. Semantic: the cross-field and cross-record checks run (`semantic.py`, `package_check.py`, `timecode.py`).
6. Result: the command builds one result record (`validate.py`).

The route stage runs the root checks in this order:

1. The exchange document test: the root is an object with a `spec_version` member. If not, the result is `NOT_EXCHANGE_DOCUMENT` at the root.
2. The version check: `spec_version` is exactly `2.0.0-draft.4`, compared character for character. If not, the result is `VERSION_UNSUPPORTED` at `/spec_version` and nothing else.
3. The root `type` test: `type` is `package`. If not, the result is `NOT_EXCHANGE_DOCUMENT` at the root, or at `/type` when `type` is present.

The first stage that stops decides the outcome.
A setup failure outranks a problem with the input.
An input problem outranks a routing problem, and a routing problem outranks a number limit problem.
A number limit problem outranks a structural problem.
Semantic checks run only on a structurally valid document.

## Multi-file package stages

`multifile.evaluate_folder` checks a multi-file package in these stages. The first stage that fails decides the outcome, and only its findings are reported:

1. Manifest file: the stages of a single document, on the manifest file. A manifest root without `manifest.members` is a single document.
2. Member rules (`check_member_list`): the member list on its own, with no disk access. Errors give `complete`, structure `valid`, semantic `run`.
3. Folder scan (`scan_folder`): each member path with `os.lstat`, then a walk of the package folder for unlisted files. No file is opened and no link is followed. Errors give `input-invalid`.
4. The read (`MemberReader`): each member file once, by record list in the order storage locations, metadata definitions, collections, assets, and in manifest order inside each list. The reader computes the SHA-256 and checks the line framing as it reads. Each line runs the record stages: parse, number limits, structure against the record schema of its type, and semantic (`package_check.py`).
5. Member integrity, at the end of each member file: size, SHA-256, compression, line rules, and line count. Errors give `input-invalid`. After the first integrity failure, later member files are only hashed.

Of the read stages, the earliest one that fails decides: integrity, then line parse, then line number limits, then line structure, then semantic.
The warnings of the member rules and the scan (`MEMBERS_SMALL`, `FILE_UNLISTED`) appear only when the outcome reaches the semantic stage.
A setup failure outranks every finding.
The adopter guide gives the full outcome table.

## Status

- This is a draft harness for contract version `2.0.0-draft.4`. It supports that version only. It is not a release.
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

This command checks one JSON document file through all six stages, or one multi-file package:

```sh
tmp/oasis-conformance/bin/python -m tests.conformance.validate PATH [--json] [--work-dir DIR] [--max-line-bytes N] [--max-gzip-ratio N]
```

`PATH` is a document file, a multi-file manifest file, or a package folder.

- A folder means `PATH/oasis-package.json`. The command opens that manifest file as it opens a member file: never through a symbolic link, and never a pipe or another special file. Such a manifest file gives `setup-failed` with the note `Setup failed: input file cannot be read.`
- A file whose root has `manifest.members` is a multi-file manifest. Its package folder is the parent of the path as given. A manifest file named directly may be a link, because the path is the caller's own input.
- A package folder named as `PATH` may be a link, for the same reason.
- Any other file is a single document. A folder whose `oasis-package.json` has no `manifest.members` is also checked as a single document.

Inside the package folder, the command never follows a link. A member file that is a link, or that sits under a linked folder, gives `MEMBER_NOT_REGULAR`, and nothing behind it is read.
`multifile.evaluate_folder` checks a multi-file package. Its stage order is in its docstring and in "Multi-file package stages" above.
The three options apply to a multi-file package only:

- `--work-dir DIR`: the folder for the SQLite working files of the check. They stay there after the run. Without this option, the command uses a new temporary folder and removes it at the end. Do not put this folder inside the package folder: the next check would find its files as unlisted files.
- `--max-line-bytes N`: the longest member file line that the reader accepts, in bytes, not counting the LF. The default is 67,108,864 (64 MiB).
- `--max-gzip-ratio N`: how far a gzip member file may expand, as a multiple of its stored bytes read so far, plus 1 MiB. The default is 1000.

A longer line or a larger expansion stops the check as a setup failure with a fixed limitation, not as a finding. These limits are checker settings, not contract rules.

The text output has one status line, then zero or more detail lines:

- Status line: `PASS`, `FAIL`, or `ERROR`, then `status=`, `type=`, `structural=`, and `semantic=` values.
- Diagnostic line: the severity, the code, the path (`(root)` for the empty path), and the catalog message.
- Schema error lines: `schema errors: N`, then one indented line per error with its path and its failing keyword.
- Note line: `note:` and a fixed limitation text, for example the reason for a setup failure.

Exit codes:

- Exit 0 (`PASS`): status `complete`, structure valid, and no diagnostic with severity `error`. Warnings are allowed.
- Exit 1 (`FAIL`): status `input-invalid` (strict JSON or a number limit) or `unsupported`, invalid structure, or at least one error diagnostic.
- Exit 2 (`ERROR`): status `setup-failed`. This includes an input file that cannot be read, a missing locked Python package, a bad bundle, a numeric resource refusal, and nesting beyond the interpreter limit. Wrong option syntax also exits 2, with usage text on standard error and nothing on standard output.

Output never contains input values.
Diagnostics carry fixed catalog messages, and notes are fixed text.
A schema error shows only its location and its failing keyword.
A location stops before the first author-chosen object key.
Text output escapes control characters.

Example, a package with no finding:

```text
$ tmp/oasis-conformance/bin/python -m tests.conformance.validate definitions/examples/package-complete.json
PASS status=complete type=package structural=valid semantic=run
```

Example, a fixture with one semantic error:

```text
$ tmp/oasis-conformance/bin/python -m tests.conformance.validate tests/conformance/fixtures/records/relationship-self.json
FAIL status=complete type=package structural=valid semantic=run
error RELATIONSHIP_SELF /assets/0/relationships/0/target: A relationship targets its own asset.
```

Example, a fixture with one structural error:

```text
$ tmp/oasis-conformance/bin/python -m tests.conformance.validate tests/conformance/fixtures/records/structural-asset-unknown-key.json
FAIL status=complete type=package structural=invalid semantic=not-run
schema errors: 1
  /assets/0 keyword unevaluatedProperties
```

Example, a fixture that breaks a number limit:

```text
$ tmp/oasis-conformance/bin/python -m tests.conformance.validate tests/conformance/fixtures/records/number-precision-17-digits.json
FAIL status=input-invalid type=package structural=not-run semantic=not-run
error NUMBER_TOO_PRECISE /assets/0/annotations/0/start_seconds: A number has more precision than a binary64 number holds.
```

`test_validate.py` checks the command.

## Result record

With `--json`, the command prints one JSON object instead of the text lines. `result.schema.json` describes it. The fields are:

- `harness`: the harness `id`, its `version`, and its direct `dependencies` pins.
- `file`: the file argument as given.
- `form`: `single-document` or `multi-file`.
- `input_sha256`: the SHA-256 of the input bytes, or `null` when the file cannot be read.
- `bundle_manifest_sha256`: the SHA-256 of the bundle manifest bytes, or `null` when setup stops first.
- `type` and `spec_version`: the routed values (`package` and `2.0.0-draft.4`), or `null` when routing did not select the package schema. A number limit failure keeps both values.
- `execution_status`: `complete`, `input-invalid`, `unsupported`, or `setup-failed`.
- `structural`: `valid`, `invalid`, or `not-run`.
- `semantic`: `run` or `not-run`.
- `diagnostics`: objects with `code`, `rule`, `severity`, `path`, and `message`, sorted by path, then code. A finding in a multi-file package can also have `member`, `line`, and `unlisted_path`. See "Finding locations" below.
- `structural_errors`: objects with `path` and `keyword`, sorted. A `false` subschema has no keyword of its own, so its keyword is reported as `false`. An error in a multi-file package can also have `member` and `line`.
- `limitations`: fixed text notes. A setup failure has at least one.

### Finding locations

These keys are absent when unset. A single-document result has none of them.

- `member`: the pointer `/manifest/members/<n>` to the member entry in the manifest file. A finding never names a member file by its path.
- `line`: the line number in that member file, 1 or more. The `path` of the finding is then a pointer inside the record on that line.
- `unlisted_path`: for a file that the manifest does not list, its path relative to the package folder. It appears only in the JSON record. The text output shows `(unlisted file)` instead.

The text output shows a located finding as `error ID_DUPLICATE member 17 line 4 /id: message`.
A finding about a whole member file has no line and the empty path, and shows as `error MEMBER_LINE_INVALID member 3: message`.
A finding about a member entry has its full pointer into the manifest file, for example `error MEMBER_MISSING member 1 /manifest/members/1/path: message`.
Findings in a multi-file package sort by member, then line, then path, then code.

Some codes cover several cases:

- `MEMBER_COMPRESSION_MISMATCH` covers a file whose compression does not match its name, and a damaged or cut-off gzip stream. It also covers any byte after the last gzip member, zero padding too (RFC 1952), and a `.jsonl.gz` file of 0 bytes. The line count of such a file is not compared.
- `MEMBER_LINE_INVALID` covers a CR, a blank line, a byte-order mark, a space or tab before or after the object, and a missing final LF. It is reported once for each member file, with no line number.
- `MEMBER_SIZE_MISMATCH` comes from the folder scan, or from the read when a file changed after the scan. In the second case, it replaces the checksum finding.

## Diagnostic catalog

Severity `error` fails the command. Severity `warning` does not.
Two codes are warnings: `FILE_UNLISTED` and `MEMBERS_SMALL`. Both apply to multi-file packages only. Every other code is an error.
Paths are RFC 6901 JSON Pointers to the value that caused the finding; the empty path is the root.
The codes, rules, and severities are the same as the catalog in `docs/ADOPTION.md`, in the same order. `test_semantic_records.py` checks that they agree.
The multi-file codes use the rules `MFP-1` to `MFP-6`. They come last.

| Code | Rule | Severity | Message |
| --- | --- | --- | --- |
| `INPUT_INVALID` | `DOC-1` | error | Input bytes cannot be parsed under the strict JSON policy. |
| `NOT_EXCHANGE_DOCUMENT` | `REC-2` | error | The document root is not a package exchange document. |
| `VERSION_UNSUPPORTED` | `UNS-1` | error | The declared spec_version is not supported by this checker. |
| `NUMBER_OUT_OF_RANGE` | `DOC-4` | error | A number has an absolute value greater than 2^53 - 1. |
| `NUMBER_TOO_PRECISE` | `DOC-4` | error | A number has more precision than a binary64 number holds. |
| `COUNT_MISMATCH` | `PKG-3` | error | A declared count does not equal the length of its array. |
| `REFERENCE_UNRESOLVED` | `PKG-6` | error | A reference does not resolve in the package. |
| `ID_DUPLICATE` | `ID-1` | error | A record id is repeated within its record list. |
| `NESTED_ID_DUPLICATE` | `ID-4` | error | A nested id is repeated within its asset or definition. |
| `RATE_NOT_LOWEST_TERMS` | `TIME-2` | error | A rate is not written in lowest terms. |
| `RANGE_NOT_INCREASING` | `TIME-4`, `TIME-13` | error | A range does not end after it starts. |
| `TIMELINE_UNDECLARED` | `TIME-5`, `TIME-12` | error | A frame field is on a timeline that is not in the frame form. |
| `SECONDS_DISAGREE` | `TIME-7` | error | A seconds value names a different frame than its frame field. |
| `TIMECODE_DISAGREE` | `TIME-7`, `TIME-8` | error | A timecode label differs from the label derived from its frame field. |
| `SAMPLE_DISAGREE` | `TIME-13` | error | A sample value does not restate its seconds value at the sample rate. |
| `SAMPLE_RATE_UNDECLARED` | `TIME-13` | error | A sample field is on a timeline that declares no sample_rate. |
| `POSITION_OUT_OF_BOUNDS` | `TIME-9` | error | A position lies outside the timeline length. |
| `PART_START_OUT_OF_ORDER` | `GRP-7` | error | Part starts of one track pair do not increase with segment_index. |
| `SUBCLIP_LENGTH_DISAGREES` | `REL-4` | error | A subclip length does not agree with the length of its range on the target. |
| `LOCATION_DUPLICATE` | `FILE-6` | error | A file lists one storage location more than once. |
| `SEQUENCE_RANGE_EMPTY` | `FILE-8` | error | An image sequence ends before it starts. |
| `SEQUENCE_STEP_MISMATCH` | `FILE-8` | error | The last frame number is not reached from the first in whole steps. |
| `SEQUENCE_PATTERN_INVALID` | `FILE-8` | error | A sequence path does not hold the {frame} placeholder exactly once. |
| `SEQUENCE_FRAME_OUTSIDE` | `FILE-8` | error | A listed frame number is not an expected number of the sequence. |
| `SEQUENCE_IMAGE_REPEATED` | `FILE-8` | error | A sequence lists details for one image more than once. |
| `TRACK_DUPLICATE` | `GRP-4` | error | A file group repeats a track type and index pair. |
| `FILE_REFERENCE_UNRESOLVED` | `GRP-4` | error | A file group member names a file that is not in the same holder. |
| `SEGMENT_INDEX_MISSING` | `GRP-6` | error | A file group member shares a track type and index pair with a segment but has no segment_index. |
| `SEGMENT_INDEX_DUPLICATE` | `GRP-6` | error | A file group repeats a segment_index within one track type and index pair. |
| `SEGMENT_OUT_OF_ORDER` | `GRP-6` | error | File group segments are not in ascending segment_index order. |
| `STREAM_DUPLICATE` | `GRP-10` | error | A file group selects one stream of a file twice. |
| `CHANNEL_LAYOUT_MISMATCH` | `GRP-11` | error | A channel layout does not have channel_count entries. |
| `STREAM_FACTS_DISAGREE` | `GRP-11` | error | Two members describe one stream with different values. |
| `SEQUENCE_FRAME_MISSING` | `GRP-12` | error | A member shares a pair with sequence images but has no sequence_frame. |
| `SEQUENCE_FRAME_DUPLICATE` | `GRP-12` | error | A file group repeats a sequence_frame within one pair. |
| `SEQUENCE_FRAME_OUT_OF_ORDER` | `GRP-12` | error | Sequence images are not in ascending sequence_frame order. |
| `TRACK_PARTS_MIXED` | `GRP-12` | error | One track pair mixes segments and sequence images. |
| `SEQUENCE_FRAME_ON_COMPACT` | `GRP-12` | error | An explicit sequence image names a compact sequence file. |
| `ORDINAL_DUPLICATE` | `VER-2` | error | Two versions share an ordinal. |
| `VERSION_REFERENCE_UNRESOLVED` | `VER-6`, `REL-6` | error | A version reference names no version of its asset. |
| `TARGET_VERSION_REQUIRED` | `REL-6` | error | A relationship range has no target_version, and its target has versions. |
| `DEFINITION_SHARED_AND_VERSIONED` | `VER-7` | error | A metadata definition used at asset level is also used in a version or in unassigned. |
| `RELATIONSHIP_SELF` | `REL-3` | error | A relationship targets its own asset. |
| `RELATIONSHIP_DUPLICATE` | `REL-5` | error | A relationships list repeats an entry in every field except description and extensions. |
| `COLLECTION_CYCLE` | `COL-4` | error | A member_of entry is on a cycle among collections. |
| `MEMBERSHIP_DUPLICATE` | `COL-7` | error | A member_of list names one collection more than once without a position on each entry. |
| `POSITION_DUPLICATE` | `COL-7` | error | Two entries that name one collection share a position. |
| `VALUE_SHAPE_MISMATCH` | `MD-4` | error | A metadata value does not match the value_type and cardinality of its definition. |
| `VALUE_DATE_INVALID` | `MD-4`, `DT-1`, `DT-3` | error | A date or date-time metadata value is not valid. |
| `VALUE_OPTION_UNKNOWN` | `MD-4`, `MD-7` | error | An enum value on a fixed list is not an option id of its definition. |
| `VALUE_REPEATED` | `MD-8` | error | A multiple value repeats an item. |
| `DEFINITION_REPEATED` | `MD-5` | error | A metadata list names the same definition twice. |
| `NAMESPACE_UNDECLARED` | `EXT-2` | error | An extension namespace is used but not declared in the manifest. |
| `NAMESPACE_DECLARED_TWICE` | `EXT-2` | error | A namespace token is declared more than once. |
| `MANIFEST_FILE_NAME` | `MFP-1` | error | A multi-file manifest file is not named oasis-package.json. |
| `MEMBER_PATH_DUPLICATE` | `MFP-2` | error | A member list repeats a member path. |
| `MEMBER_PATH_CASE_COLLISION` | `MFP-2` | error | Two member paths differ only in letter case. |
| `MEMBER_TYPE_MISMATCH` | `MFP-2` | error | A member record_type differs from the first segment of its path. |
| `MEMBER_MISSING` | `MFP-3` | error | A listed member file does not exist. |
| `MEMBER_NOT_REGULAR` | `MFP-3` | error | A listed member path is a link, or it is not a regular file in regular folders. |
| `MEMBER_SIZE_MISMATCH` | `MFP-3` | error | A member file size differs from its size_bytes. |
| `MEMBER_CHECKSUM_MISMATCH` | `MFP-3` | error | A member file SHA-256 differs from its sha256. |
| `MEMBER_UNLISTED` | `MFP-3` | error | A file in a record folder is not listed in the manifest. |
| `FILE_UNLISTED` | `MFP-3` | warning | A file outside the record folders is not listed in the manifest. |
| `MEMBER_COMPRESSION_MISMATCH` | `MFP-4` | error | A member file is not compressed as its name says. |
| `MEMBER_LINE_INVALID` | `MFP-4` | error | A line of a member file breaks the line rules. |
| `MEMBER_COUNT_MISMATCH` | `MFP-5` | error | A member count differs from the number of lines in its file. |
| `MEMBER_EMPTY_UNEXPECTED` | `MFP-6` | error | A member file has no records, but its list has records in other member files. |
| `MEMBERS_SMALL` | `MFP-3` | warning | A list has several member files that hold few records each. |

A semantic code can appear more than once in one result, at different paths.
`VALUE_OPTION_UNKNOWN` and `VALUE_REPEATED` can both apply to one value item.

## Rules with no document check

Contract Appendix B lists the rules that a conformance checker implements.
Some of them need no diagnostic code of their own:

| Rule | How the harness covers it |
| --- | --- |
| `DOC-2` | The strict parser reads every number as an exact decimal. Every check uses that value. |
| `DOC-3` | No stage changes the parsed tree. `test_corpus.py` and `test_semantic_package.py` check this. |
| `PKG-8` | Array order carries no meaning, so there is nothing to report. The checks that do use order (`GRP-6`, `GRP-7`, `GRP-12`) report their own codes. |
| `ID-2` | Ids are compared within one record list only, so an asset and a collection can share an id. |
| `ID-5`, `MD-6` | Every reference resolves under `PKG-6` and reports `REFERENCE_UNRESOLVED`. Nested references report their own codes. |
| `TIME-3`, `REL-1` | Their T parts are the order, bounds, and agreement checks of `TIME-4`, `TIME-7`, `TIME-9`, and `TIME-13`. |
| `FILE-5`, `GRP-2`, `REL-2`, `ANN-2` | They define what each value means. The allowed values are structural. Meaning cannot be checked. |
| `GRP-5` | There is no implicit grouping. Absence of a rule cannot be checked. |
| `VER-5` | Its T part is that a file group in `unassigned` uses files in `unassigned` only. A member file that is not there reports `FILE_REFERENCE_UNRESOLVED` (`GRP-4`). |
| `COL-3` | Membership is on the member. A `member_of` reference reports `REFERENCE_UNRESOLVED`. |
| `MD-2` | Constraints are never executed. The bundle loader checks a `pattern` as ECMA-262 syntax with the `regex` format. |
| `ANN-3` | The schema rejects an annotation frame field on a holder with no frame-form timing. Relationship ranges report `TIMELINE_UNDECLARED`. |
| `DT-2` | Format checking is on. A bundle that uses a format the harness cannot check fails setup. |
| `MFP-7` | It states the scope of other rules across member files. Those rules report their own codes, such as `ID_DUPLICATE` and `REFERENCE_UNRESOLVED`, at the member and line. |

Contract Appendix B also lists rules that state producer, consumer, or checker obligations.
A document alone cannot show them, so the harness does not check them:
`SAFE-1`, `PKG-5`, `PKG-9`, `ID-3`, `AST-3`, `TIME-10`, the frame-count obligation of `TIME-11`, the T part of `TIME-14`, `FILE-4`, the producer parts of `FILE-6`, `FILE-7`, `FILE-8`, and `FILE-9`, `STO-2`, the producer part of `STO-3`, `GRP-8`, `GRP-9`, the producer parts of `GRP-10` and `GRP-11`, the producer and reader parts of `VER-4`, `VER-5`, and `VER-6`, the saved-search clause of `COL-2`, the producer part of `MD-7`, the T part of `ANN-4`, `ANN-5`, `EXT-4`, `ACC-2`, `UNS-1`, `UNS-2`, `MFP-8`, `MFP-9`.

The harness follows `SAFE-1`: validation never opens a file or location named by a value in the document, and never connects to a network or storage system.
For a multi-file package, it opens only the manifest file and the member files that it lists. It also lists the package folder and writes its own working files in the work folder. It never follows a link inside the package folder.
`MFP-9` is the equivalence of the two forms. `test_examples.py` checks it for the multi-file example.
For `UNS-1` and `UNS-2`, the harness supports exactly one version and reports any other as unsupported.

## Packages only

The harness routes only a package. A root that is not an object, or has no `spec_version`, gets `NOT_EXCHANGE_DOCUMENT`. When the version is supported, a root with another `type`, or with no `type`, also gets it. A document with an unsupported `spec_version` gets only `VERSION_UNSUPPORTED`, whatever its `type` (the root check order above).
So every check can see every record of the package, and no check gives a warning for a missing record.
Most fixtures in `fixtures/records/` are packages. The `input-` fixtures are not strict JSON. The `routing-` fixtures test the root checks, and most of them hold a document that does not route.
The folders in `fixtures/packages/` are multi-file packages. Each one has a manifest file and its member files, and `test_corpus.py` checks it with the folder form of the check. `fixtures/README.md` describes them.

The examples in `definitions/examples/` are packages: three single documents and the multi-file package folder `multi-file-complete/`. `test_examples.py` checks that each one passes with no diagnostic. It also checks that `multi-file-complete/` and `package-complete.json` are equivalent (`MFP-9`).

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

## Number limits

The number limit stage applies `DOC-4` to every JSON number in the package, including numbers in `extensions` and metadata values:

1. Range: the absolute value is at most 2^53 - 1. Otherwise the finding is `NUMBER_OUT_OF_RANGE`.
2. Precision: the value equals the shortest decimal form of its nearest binary64 number. Otherwise the finding is `NUMBER_TOO_PRECISE`.

A number that breaks a limit makes the package `input-invalid`. The structural and semantic stages do not run.
The stage reports every number that fails, sorted by path.
A path stops at the first `extensions` member, and before any key that the schema bundle does not define.
The limits test a copy of the number. Every other check uses the exact decimal value.

## Numeric resource limits

The strict parser applies these limits to every JSON number:

| Limit | Value |
| --- | --- |
| Numeric token length, including sign and exponent syntax | 1,024 ASCII bytes |
| Absolute decimal exponent | 10,000 |

The limits apply to each number on its own. There is no budget summed over the document.
These limits are operational setup guards. They protect the harness from very large numbers.
They are not the `DOC-4` number limits, and they do not make a document invalid.
When a document exceeds a guard, the run fails setup. It never reports the document as invalid input.

## Member file reader limits

`MemberReader` reads a member file in blocks of 1 MiB. Two limits stop a member file that is too large to read safely:

| Limit | Option | Default | Limitation text |
| --- | --- | --- | --- |
| Line length, in bytes, not counting the LF | `--max-line-bytes` | 67,108,864 | `Setup failed: a member file line is longer than the line length limit.` |
| Gzip expansion: decompressed bytes at most this multiple of the stored bytes read so far, plus 1 MiB | `--max-gzip-ratio` | 1000 | `Setup failed: a member file expands beyond the decompression ratio limit.` |

A limit failure is a setup failure (exit 2), not a finding. The reader never decompresses more than one byte past the ratio allowance.
The memory of the reader stays bounded by the read block and the line limit, whatever the size of the file.

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
- It never computes the checksum of a media file. A declared file checksum is not verified. It does compute the SHA-256 of each member file of a multi-file package and compares it with the manifest file.
- For a multi-file package, it keeps its indexes and the findings of each stage in SQLite files in the work folder (`store.sqlite` and `findings.sqlite`). SQLite temporary files also go there.
- It keeps every reported finding in memory to build the result record. Each finding takes about 324 bytes, so a package with many millions of findings can need several GiB of memory.
- It does not evaluate access. An access status is read as a value only.
- A `complete` result does not mean a document is safe or approved to import.
