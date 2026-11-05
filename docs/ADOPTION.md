# Adopting OASIS 2.0

Status: DRAFT 2.0.0-draft.4, not a final release.
The rules this guide explains can change before the final release.
Interoperability between independent implementations is not demonstrated.

OASIS means Open Asset Standard Interchange Schema.
This guide explains how to produce, validate, and receive OASIS 2.0 documents, and what each result means for your system.
The [contract](specification/2.0.0-draft.4/CONTRACT.md) is the normative source. If this guide and the contract differ, the contract applies.
The [glossary](specification/2.0.0-draft.4/GLOSSARY.md) defines the terms used here.
The [data model](specification/2.0.0-draft.4/DATA-MODEL.md) draws the shapes.
The [conformance harness README](../tests/conformance/README.md) gives the exact commands, output format, and catalog messages.

This guide makes no claim of certification, production readiness, or endorsement by any organization.

## Contents

1. [What OASIS 2.0 is](#what-oasis-20-is)
2. [Three separate results](#three-separate-results)
3. [Set up offline validation](#set-up-offline-validation)
4. [Validate a document](#validate-a-document)
5. [Outcome order](#outcome-order)
6. [Diagnostic catalog](#diagnostic-catalog)
7. [Packages and references](#packages-and-references)
8. [Multi-file packages](#multi-file-packages)
9. [Collection membership](#collection-membership)
10. [Time](#time)
11. [Numbers and versions](#numbers-and-versions)
12. [Extensions and preservation](#extensions-and-preservation)
13. [Access summary](#access-summary)
14. [Validation grants no access](#validation-grants-no-access)
15. [Numeric resource guards](#numeric-resource-guards)
16. [Member file reader limits](#member-file-reader-limits)
17. [Harness limits](#harness-limits)

## What OASIS 2.0 is

OASIS 2.0 is a neutral JSON format for exchanging media asset records between systems.
It has one core profile.

The package is the only exchange document. It holds a manifest and four record lists.
A package has two forms with the same records and the same rules:

- A single-document package is one JSON document.
- A multi-file package is a package folder with a manifest file and member files. It is for exports that are too large for one document. See [Multi-file packages](#multi-file-packages).

Only the package root carries `type` and `spec_version`. Records inside a package carry neither field (`REC-1`).
The record list that holds a record states its type.
A record on its own is not an exchange document (`REC-2`).

| Record list | Each record describes |
| --- | --- |
| `storage_locations` | One place where copies of files are stored. |
| `metadata_definitions` | One metadata field: its value type, cardinality, list type, and options. |
| `collections` | A named grouping that the source stores. Members name the collection, not the other way round. |
| `assets` | One content item, with its versions, files, file groups, relationships, metadata values, and annotations. |

An annotation is a nested object in an asset, a version, or `unassigned`. It is not a record.

The schemas use JSON Schema 2020-12 and live in [`definitions/`](../definitions/README.md).
Synthetic example packages are in [`definitions/examples/`](../definitions/examples/README.md).

## Three separate results

OASIS keeps three results apart. Passing one does not prove the others.

| Result | Question it answers | Who decides |
| --- | --- | --- |
| Schema acceptance | Does the package match the schema bundle? | A JSON Schema 2020-12 validator with the schema bundle |
| Semantic conformance | Does the package follow the contract rules that a schema cannot express? | A conformance checker, such as the reference harness |
| Application behavior | Did a receiving system import, store, preserve, and protect the data correctly? | The receiving system and its operators |

A structurally valid package can still fail a semantic rule.
A passing result is not permission to import.
The reference harness checks documents only. It gives no evidence about how any application behaves.

## Set up offline validation

Run every command in this guide from the root of a Git checkout of the repository.
The commands were checked with Python 3.12 on Linux.

Only setup uses the network. It installs pinned Python packages.
After setup, validation reads only local files.

### Python environment

```sh
mkdir -p tmp
python3 -m venv tmp/oasis-conformance
tmp/oasis-conformance/bin/python -m pip install -r tests/conformance/requirements-lock.txt
```

If your host has no `python3-venv` package, you can use `uv` instead:

```sh
uv venv --python "$(command -v python3)" tmp/oasis-conformance
uv pip install --python tmp/oasis-conformance/bin/python -r tests/conformance/requirements-lock.txt
```

`tests/conformance/setup-environments.sh` does the same Python setup.

### Fully offline install

Download the pinned packages once while you are online:

```sh
python3 -m pip download -r tests/conformance/requirements-lock.txt -d tmp/wheelhouse
```

Then install on the offline host with no package index:

```sh
tmp/oasis-conformance/bin/python -m pip install --no-index --find-links tmp/wheelhouse -r tests/conformance/requirements-lock.txt
```

### Check the setup

Run the full harness test suite:

```sh
tmp/oasis-conformance/bin/python -W error -m unittest discover -s tests/conformance -t . -p 'test_*.py'
```

Run only the example checks:

```sh
tmp/oasis-conformance/bin/python -m unittest tests.conformance.test_examples
```

## Validate a document

The `validate` command checks one document file through every stage:

```sh
tmp/oasis-conformance/bin/python -m tests.conformance.validate definitions/examples/package-complete.json
```

The command reads `spec_version` and `type` itself. You do not name a schema.

### Validate a multi-file package

Give the command the package folder, or the manifest file in it:

```sh
tmp/oasis-conformance/bin/python -m tests.conformance.validate definitions/examples/multi-file-complete
tmp/oasis-conformance/bin/python -m tests.conformance.validate definitions/examples/multi-file-complete/oasis-package.json
```

The command decides the form from what you give it:

- A folder means the manifest file `oasis-package.json` in that folder. The command refuses a manifest file there that is a symbolic link, a pipe, or another special file. The result is `setup-failed`, with the note `Setup failed: input file cannot be read.`
- A file whose root has `manifest.members` is a manifest file. Its folder is the package folder: the parent of the path as you gave it. A manifest file that you name directly may be a symbolic link, because the path is your own input.
- A package folder that you name may be a symbolic link too, for the same reason.
- Any other file is a single document. The command checks it exactly as before. A folder whose `oasis-package.json` has no `manifest.members` is also checked as a single document.

Inside the package folder, the command never follows a symbolic link (`SAFE-1`).
A member file that is a link, or that sits under a linked folder, gets `MEMBER_NOT_REGULAR`. The command reads nothing behind the link.

Three options apply to a multi-file package only:

| Option | Default | Meaning |
| --- | --- | --- |
| `--work-dir DIR` | a new temporary folder, removed at the end | The folder where the command keeps its SQLite working files. With this option, the files stay there after the run. Do not put this folder inside the package folder. |
| `--max-line-bytes N` | 67,108,864 (64 MiB) | The longest member file line that the command reads, in bytes. |
| `--max-gzip-ratio N` | 1000 | How far a gzip member file may expand, as a multiple of its stored size, plus 1 MiB. |

The two limits are settings of the checker, not rules of the contract. See [Member file reader limits](#member-file-reader-limits).

### Text output

The first line is the status line. Lines after it give the findings.

```text
PASS status=complete type=package structural=valid semantic=run
```

- `PASS`, `FAIL`, or `ERROR` is the overall answer.
- `status` is the execution status: `complete`, `input-invalid`, `unsupported`, or `setup-failed`.
- `structural` is `valid`, `invalid`, or `not-run`.
- `semantic` is `run` or `not-run`.

Each diagnostic line gives the severity, the code, the path, and a fixed message.
A structural failure lists each schema error by its path and failing keyword.
A `note:` line gives a fixed limitation text, for example why setup failed.

In a multi-file package, a line also names the member file and the line in it, when they apply:

```text
FAIL status=complete type=package structural=valid semantic=run
warning MEMBERS_SMALL /manifest/members: A list has several member files that hold few records each.
error ID_DUPLICATE member 1 line 1 /id: A record id is repeated within its record list.
```

- `member 1` is the member entry at `/manifest/members/1`. The member path itself is never printed.
- `line 1` is the line in that member file. The path after it, `/id`, points inside the record on that line.
- A finding about a whole member file has no line and no path, for example `error MEMBER_LINE_INVALID member 0: ...`.
- A finding about a file that the manifest does not list shows `(unlisted file)`. Its path is never printed.

### JSON output

Add `--json` to get one JSON result record instead of text:

```sh
tmp/oasis-conformance/bin/python -m tests.conformance.validate definitions/examples/package-complete.json --json
```

The record names the harness and its pinned packages, the SHA-256 of the input bytes and of the schema bundle manifest, the routed type and version, the three results, the diagnostics, the schema errors, and any limitations.
Its `form` is `single-document` or `multi-file`. For a multi-file package, the input digest is that of the manifest file bytes.
A finding in a multi-file package can also carry these keys:

- `member`: the pointer to the member entry, such as `/manifest/members/3`.
- `line`: the line number in that member file, 1 or more.
- `unlisted_path`: for a file that the manifest does not list, its path relative to the package folder.

`tests/conformance/result.schema.json` describes it.
Use the JSON form when a program reads the result.

### Exit codes

| Exit | Answer | Meaning |
| --- | --- | --- |
| 0 | `PASS` | The checks ran, the structure is valid, and no diagnostic has severity `error`. Warnings are allowed. |
| 1 | `FAIL` | The input is not strict JSON, or the document is not an exchange document or is unsupported. Or a number breaks a number limit, a member file fails a package check, the structure is invalid, or a diagnostic has severity `error`. |
| 2 | `ERROR` | Setup failed. The document was not judged. For example, a member file cannot be read, or a member file passes a reader limit. Wrong option syntax also exits 2. |

Exit 2 is a problem with the environment or a resource guard, not a verdict on the document.
Fix the setup and run the command again.

### Output never repeats input values

Messages are fixed catalog text. A path stops before the first key that an author chose.
So you can share a result without sharing the data in the document.
The result record still carries the input digest and the file name you gave. Treat the record as being as sensitive as the file name.

A finding in a multi-file package names a member file only by its place in `members`, never by its path.
The path of a file that the manifest does not list appears only in the JSON record, in `unlisted_path`. The text output never shows it.
Treat a JSON record as being as sensitive as the names in your package folder.

## Outcome order

A document passes through six stages: parse, route, number limits, structural, semantic, and result.
The first stage that stops decides the outcome.

| Condition | Execution status | Structural | Semantic | Diagnostics |
| --- | --- | --- | --- | --- |
| The input file cannot be read, a locked package is missing, the schema bundle is bad or declares an unsupported version, a numeric guard is exceeded, or nesting is too deep | `setup-failed` | `not-run` | `not-run` | None. A limitation names the reason. |
| The bytes break the strict JSON policy | `input-invalid` | `not-run` | `not-run` | `INPUT_INVALID` at the root |
| The root is not an object, or has no `spec_version` member | `unsupported` | `not-run` | `not-run` | `NOT_EXCHANGE_DOCUMENT` at the root |
| `spec_version` is not exactly `2.0.0-draft.4` | `unsupported` | `not-run` | `not-run` | `VERSION_UNSUPPORTED` only |
| The version is supported, and the root has no `type` or a `type` other than `package` | `unsupported` | `not-run` | `not-run` | `NOT_EXCHANGE_DOCUMENT` at the root, or at `/type` when `type` is present |
| A number breaks a number limit (`DOC-4`) | `input-invalid` | `not-run` | `not-run` | `NUMBER_OUT_OF_RANGE` or `NUMBER_TOO_PRECISE` for each number that fails |
| The document does not match the schema bundle | `complete` | `invalid` | `not-run` | None. Schema errors are listed by path and keyword. |
| The document matches the schema bundle | `complete` | `valid` | `run` | Every semantic diagnostic |

A setup failure outranks an input problem. An input problem outranks a routing problem. A routing problem outranks a number limit problem. A number limit problem outranks a structural problem.
Semantic checks run only on a structurally valid document.

The version check comes before every rule except the strict JSON policy and the test for a root with no `spec_version` (`UNS-1`).
An unsupported document gets `VERSION_UNSUPPORTED` and no other finding.
The harness does not report it as conforming or as invalid.

The strict JSON policy requires UTF-8 under [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259.html).
It refuses a byte-order mark, invalid UTF-8, malformed JSON, duplicate member names, `NaN`, `Infinity`, and unpaired surrogate escapes (`DOC-1`).

`complete` means the checks ran. It does not mean the document passed.
Read the `structural` value and the diagnostics too, or use the exit code.

### Outcome order for a multi-file package

The table above does not change for a single document.
A multi-file package adds stages for the package itself. They come before the stages for the records.
The command reads each member file once. It runs the line stages on every line during that read.

| Stage | Condition | Execution status | Structural | Semantic | Diagnostics |
| --- | --- | --- | --- | --- | --- |
| Setup | A member file or a folder of the package cannot be read. Or a member file passes a reader limit, or the working files cannot be written. | `setup-failed` | `not-run` | `not-run` | None. A limitation names the reason. |
| Manifest file | The manifest file fails a stage of the single-document table | as in that table | as in that table | as in that table | as in that table |
| Manifest file | The folder form finds a link, a pipe, or another special file at `oasis-package.json` | `setup-failed` | `not-run` | `not-run` | None. The note is `Setup failed: input file cannot be read.` |
| Member rules | The `members` list breaks a rule. For example, a path repeats, or a `counts` value differs from the sum of the member counts. | `complete` | `valid` | `run` | `MANIFEST_FILE_NAME`, `MEMBER_PATH_DUPLICATE`, `MEMBER_PATH_CASE_COLLISION`, `MEMBER_TYPE_MISMATCH`, `MEMBER_EMPTY_UNEXPECTED`, `COUNT_MISMATCH` |
| Folder scan | Before the read, a listed member file is missing, is not a regular file, or has the wrong size. Or a record folder holds an unlisted file. | `input-invalid` | `not-run` | `not-run` | `MEMBER_MISSING`, `MEMBER_NOT_REGULAR`, `MEMBER_SIZE_MISMATCH`, `MEMBER_UNLISTED` |
| Member integrity | During the read, a member file fails a check of its own bytes. The checks are: a regular file at open time, size, SHA-256, compression, line rules, and line count. | `input-invalid` | `not-run` | `not-run` | `MEMBER_NOT_REGULAR`, `MEMBER_SIZE_MISMATCH`, `MEMBER_CHECKSUM_MISMATCH`, `MEMBER_COMPRESSION_MISMATCH`, `MEMBER_LINE_INVALID`, `MEMBER_COUNT_MISMATCH` |
| Line parse | A line breaks the strict JSON policy | `input-invalid` | `not-run` | `not-run` | `INPUT_INVALID` at the member and line, for each such line |
| Line number limits | A number on a line breaks a number limit (`DOC-4`) | `input-invalid` | `not-run` | `not-run` | `NUMBER_OUT_OF_RANGE` or `NUMBER_TOO_PRECISE` at the member and line |
| Line structure | A line does not match the record schema of its record type | `complete` | `invalid` | `not-run` | None. Schema errors are listed by member, line, path, and keyword. |
| Semantic | Every line matches its record schema | `complete` | `valid` | `run` | Every semantic diagnostic, and the warnings `FILE_UNLISTED` and `MEMBERS_SMALL` |

The first stage that fails decides the outcome, and the result reports only the findings of that stage.
So a missing or damaged member file never gives a flood of reference findings. The records of a damaged package are not trustworthy.
The member rule and folder scan stages also find warnings: `MEMBERS_SMALL` and `FILE_UNLISTED`. These warnings appear only when the outcome reaches the semantic stage.
A setup failure outranks every finding.

Some details of the member integrity stage:

- After the first member file that fails an integrity check, the command only computes the size and the SHA-256 of each later member file. So the result lists every damaged member file, and no line stage runs on them.
- A damaged gzip stream gives `MEMBER_COMPRESSION_MISMATCH`. This includes a cut-off stream, and zero bytes or any other bytes after the last gzip member (RFC 1952). A `.jsonl.gz` file of 0 bytes also gives this code. The command does not compare the line count of such a file, because it could not read every line.
- A line rule failure gives one `MEMBER_LINE_INVALID` for the member file, with no line number. The line rules forbid a CR, a blank line, a byte-order mark, a space or tab before or after the object, and a last line with no LF.

The command reads storage locations first, then metadata definitions, collections, and assets.
In each record list, it reads the member files in the order of `members`, and each file from its first line.
This order decides which repeat is "after the first", for example for `ID_DUPLICATE` (`MFP-7`). File names and the file system order never decide it.

### Diagnostic paths

Paths are JSON Pointers ([RFC 6901](https://www.rfc-editor.org/rfc/rfc6901.html)). The empty path is the root. Array indexes start at zero.
Diagnostics are sorted by path, then by code.
In a multi-file package, a finding about a member entry has its full pointer in the manifest file, such as `/manifest/members/3/sha256`, and `member` set.
A finding on a line has `member` and `line` set, and its path points inside the record on that line.
Diagnostics in a multi-file package sort by member, then line, then path, then code. A finding with no member comes first.
Compare results by code, path, and severity. Do not compare message text.
A number limit path stops at the first `extensions` member, and before any key that the schema bundle does not define. So the path never repeats a key that an author chose.

## Diagnostic catalog

Severity `error` fails the command. Severity `warning` does not.
Two codes are warnings: `FILE_UNLISTED` and `MEMBERS_SMALL`. Both apply to multi-file packages only. Every other code is an error.
The rule column names the contract rule that each code enforces.
The codes with rules `MFP-1` to `MFP-6` apply to multi-file packages only. They come last.

| Code | Rule | Severity | What it means for you |
| --- | --- | --- | --- |
| `INPUT_INVALID` | `DOC-1` | error | The bytes are not strict JSON. Fix the encoding or the syntax at the producer. |
| `NOT_EXCHANGE_DOCUMENT` | `REC-2` | error | The document is not a package. A root array, a bare record with no `spec_version`, or a document from another format with no `spec_version` gets this code. A document with a `spec_version` that the checker does not support gets `VERSION_UNSUPPORTED` instead, whatever its `type`. It is never validated against a 2.0 schema. |
| `VERSION_UNSUPPORTED` | `UNS-1` | error | The `spec_version` is not exactly a version that the checker supports. Never rewrite a version to make it route. |
| `NUMBER_OUT_OF_RANGE` | `DOC-4` | error | A number has an absolute value greater than 2^53 - 1. Write such a value as a string. |
| `NUMBER_TOO_PRECISE` | `DOC-4` | error | The value of a number is not the shortest decimal form of its nearest binary64 number. The value is tested, not the spelling: `100.0` and `1e2` pass, `0.10000000000000001` fails. Use a shortest-form number writer. |
| `COUNT_MISMATCH` | `PKG-3` | error | A manifest count differs from its array length. In a multi-file package, it differs from the sum of the member counts of its list. The package may be truncated. |
| `REFERENCE_UNRESOLVED` | `PKG-6` | error | A reference names a record that is not in the package. Add the record, or drop the reference. |
| `ID_DUPLICATE` | `ID-1` | error | Two records in one record list share an id. Reported on each repeat after the first. |
| `NESTED_ID_DUPLICATE` | `ID-4` | error | Two versions, files, file groups, or annotations of one asset, or two options of one definition, share an id. File, file group, and annotation ids are unique across the asset level, every version, and `unassigned`. |
| `RATE_NOT_LOWEST_TERMS` | `TIME-2` | error | A rate such as `48000/2002` is not in lowest terms. This also applies to member `frame_rate` and `capture_frame_rate`. |
| `RANGE_NOT_INCREASING` | `TIME-4`, `TIME-13` | error | A range does not end after it starts, in frames, in seconds, or in samples. |
| `TIMELINE_UNDECLARED` | `TIME-5`, `TIME-12` | error | A frame field sits on a timeline that is not in the frame form. |
| `SECONDS_DISAGREE` | `TIME-7` | error | A seconds value names a different frame than its frame field. This covers positions, `duration_seconds`, and part starts. |
| `TIMECODE_DISAGREE` | `TIME-7`, `TIME-8` | error | A timecode label differs from the label derived from its frame field. |
| `SAMPLE_DISAGREE` | `TIME-13` | error | A sample position or `duration_samples` does not restate its seconds value at the timeline `sample_rate`. |
| `SAMPLE_RATE_UNDECLARED` | `TIME-13` | error | A marker has a sample position, but its timeline declares no `sample_rate`. |
| `POSITION_OUT_OF_BOUNDS` | `TIME-9` | error | A frame, seconds, or sample position, or a part start, lies outside the timeline length. |
| `PART_START_OUT_OF_ORDER` | `GRP-7` | error | The part starts of one track pair do not increase with `segment_index`. |
| `SUBCLIP_LENGTH_DISAGREES` | `REL-4` | error | The length of a `subclip_of` child does not agree with the length of its range on the target. |
| `LOCATION_DUPLICATE` | `FILE-6` | error | A file lists one storage location more than once. Describe two places on one storage system as two storage location records. |
| `SEQUENCE_RANGE_EMPTY` | `FILE-8` | error | An image sequence has a `last_frame` less than its `first_frame`. |
| `SEQUENCE_STEP_MISMATCH` | `FILE-8` | error | The last frame number is not reached from the first in whole steps. |
| `SEQUENCE_PATTERN_INVALID` | `FILE-8` | error | A path of a file with `sequence` does not hold the text `{frame}` exactly once. |
| `SEQUENCE_FRAME_OUTSIDE` | `FILE-8` | error | A frame number in `images` or `missing_frames` is not an expected number of the sequence. |
| `SEQUENCE_IMAGE_REPEATED` | `FILE-8` | error | A sequence lists details for one image more than once. |
| `TRACK_DUPLICATE` | `GRP-4` | error | A file group repeats a track type and index pair, and that pair holds no segments or sequence images. |
| `FILE_REFERENCE_UNRESOLVED` | `GRP-4` | error | A file group member names a file that is not in the same holder as the file group. |
| `SEGMENT_INDEX_MISSING` | `GRP-6` | error | A file group member shares a track type and index pair with a segment but has no `segment_index`. |
| `SEGMENT_INDEX_DUPLICATE` | `GRP-6` | error | Two segments of one track type and index pair in a file group share a `segment_index`. |
| `SEGMENT_OUT_OF_ORDER` | `GRP-6` | error | The segments of one track type and index pair are not listed in ascending `segment_index` order. |
| `STREAM_DUPLICATE` | `GRP-10` | error | A file group selects one stream of a file twice. |
| `CHANNEL_LAYOUT_MISMATCH` | `GRP-11` | error | A `channel_layout` does not have `channel_count` entries. |
| `STREAM_FACTS_DISAGREE` | `GRP-11` | error | Two members in one holder describe one stream with different values. |
| `SEQUENCE_FRAME_MISSING` | `GRP-12` | error | A member shares a track pair with sequence images but has no `sequence_frame`. |
| `SEQUENCE_FRAME_DUPLICATE` | `GRP-12` | error | A file group repeats a `sequence_frame` within one track pair. |
| `SEQUENCE_FRAME_OUT_OF_ORDER` | `GRP-12` | error | The sequence images of one track pair are not in ascending `sequence_frame` order. |
| `TRACK_PARTS_MIXED` | `GRP-12` | error | One track pair mixes segments and sequence images. |
| `SEQUENCE_FRAME_ON_COMPACT` | `GRP-12` | error | A member with `sequence_frame` names a file that has `sequence`. |
| `ORDINAL_DUPLICATE` | `VER-2` | error | Two versions of one asset share an ordinal. |
| `VERSION_REFERENCE_UNRESOLVED` | `VER-6`, `REL-6` | error | A `current_version` or `target_version` names no version of its asset. |
| `TARGET_VERSION_REQUIRED` | `REL-6` | error | A relationship has a `range` but no `target_version`, and its target has versions. |
| `DEFINITION_SHARED_AND_VERSIONED` | `VER-7` | error | A metadata definition used at asset level is also used in a version or in `unassigned`. Put each metadata field at one level only. |
| `RELATIONSHIP_SELF` | `REL-3` | error | A relationship targets its own asset. |
| `RELATIONSHIP_DUPLICATE` | `REL-5` | error | One `relationships` list holds two entries that are equal in every field except `description` and `extensions`. |
| `COLLECTION_CYCLE` | `COL-4` | error | A `member_of` entry is part of a cycle among collections. A collection that names itself is a cycle. |
| `MEMBERSHIP_DUPLICATE` | `COL-7` | error | A `member_of` names one collection more than once, and at least one of those entries has no `position`. |
| `POSITION_DUPLICATE` | `COL-7` | error | Two entries that name one collection share a `position`. |
| `VALUE_SHAPE_MISMATCH` | `MD-4` | error | A metadata value does not match the `value_type` and cardinality of its definition. |
| `VALUE_DATE_INVALID` | `MD-4`, `DT-1`, `DT-3` | error | A date or date-time metadata value is not valid. |
| `VALUE_OPTION_UNKNOWN` | `MD-4`, `MD-7` | error | An enum value item on a `fixed` list is not an option id of its definition. |
| `VALUE_REPEATED` | `MD-8` | error | A `multiple` value repeats an item. This applies to every value type. |
| `DEFINITION_REPEATED` | `MD-5` | error | One `metadata` list names the same metadata definition twice. |
| `NAMESPACE_UNDECLARED` | `EXT-2` | error | A package uses an extension namespace that its manifest does not declare. |
| `NAMESPACE_DECLARED_TWICE` | `EXT-2` | error | A manifest declares the same namespace token twice. |
| `MANIFEST_FILE_NAME` | `MFP-1` | error | A file with `manifest.members` is not named `oasis-package.json`. Rename the manifest file. |
| `MEMBER_PATH_DUPLICATE` | `MFP-2` | error | The `members` list names one member path twice. Reported on each repeat after the first. |
| `MEMBER_PATH_CASE_COLLISION` | `MFP-2` | error | Two member paths differ only in letter case. On a file system that ignores letter case, they name one file. |
| `MEMBER_TYPE_MISMATCH` | `MFP-2` | error | The `record_type` of a member entry is not the first segment of its `path`. |
| `MEMBER_MISSING` | `MFP-3` | error | A listed member file is not in the package folder. The package is incomplete, for example after a cut-off upload. |
| `MEMBER_NOT_REGULAR` | `MFP-3` | error | A member path is a symbolic link or passes through a linked folder. Or it names something that is not a regular file, such as a folder or a pipe. The command reads nothing behind it. |
| `MEMBER_SIZE_MISMATCH` | `MFP-3` | error | The size of a member file differs from its `size_bytes`. The file is cut off or changed, or it changed during the check. |
| `MEMBER_CHECKSUM_MISMATCH` | `MFP-3` | error | The SHA-256 of a member file differs from its `sha256`. The file changed after the producer wrote the manifest file. |
| `MEMBER_UNLISTED` | `MFP-3` | error | A record folder holds a file that the manifest does not list. It can be a member file that the manifest lost. Remove stray files, such as macOS `._` and `.DS_Store` files. |
| `FILE_UNLISTED` | `MFP-3` | warning | A file outside the record folders is not listed in the manifest. The check still passes. |
| `MEMBER_COMPRESSION_MISMATCH` | `MFP-4` | error | A member file is not compressed as its name says, or its gzip stream is damaged, cut off, or followed by other bytes. A `.jsonl.gz` file of 0 bytes also gets this code. |
| `MEMBER_LINE_INVALID` | `MFP-4` | error | A member file breaks a line rule. It has a CR, a blank line, a byte-order mark, a space or tab before or after the object, or no LF after the last line. Reported once for the file, with no line number. |
| `MEMBER_COUNT_MISMATCH` | `MFP-5` | error | The `count` of a member entry differs from the number of lines in its file. |
| `MEMBER_EMPTY_UNEXPECTED` | `MFP-6` | error | A member entry has `count` 0, but other member files of its list hold records. A member file with no records is allowed only when its whole list is empty. |
| `MEMBERS_SMALL` | `MFP-3` | warning | A record list has two or more member files that hold fewer than 1,000 records each on average. Write fewer, larger files. The check still passes. |

Some rules have no document check, because a document alone cannot show them.
The [harness README](../tests/conformance/README.md#rules-with-no-document-check) lists them with the reason for each.

## Packages and references

The package is the only exchange document.
A one-asset export is a package that holds the asset and every record that its references need.
The checker resolves every reference, checks membership, checks timing on each holder, and checks extension namespaces against the manifest.

Every reference resolves inside the package (`PKG-6`).
An unresolved reference is an error: `REFERENCE_UNRESOLVED`. There is no partial or warning result.
A package never depends on another package. When two packages need the same storage location or definition, each package holds its own copy.
Values inside `extensions` are not references, and the checker does not resolve them.

The manifest `counts` must equal the number of records in each record list (`PKG-3`). In a single document, that is the array length, and an absent array counts as 0.
In a multi-file package, each `counts` value is the sum of the member counts of its list (`MFP-5`).
The count protects against truncation of the package. It is not a claim about the source system.

A package describes its records as they stood at `produced_at`. It carries no command (`PKG-9`).
A missing record, field, or value is not an instruction to delete, clear, or replace anything.
An asset's `deleted` date states that the source reported a deletion. It is not an instruction to delete, hide, or purge anything (`AST-3`).
Your application decides whether and how to match, merge, replace, or delete its own data.

## Multi-file packages

A multi-file package holds one package in a package folder.
The manifest file holds the package root. Member files hold the records, one record on each line.
The records and the rules are the same as in a single document (contract section 16).

### When to use it

Use a multi-file package when an export is too large for one JSON document.
As a guideline, consider it for more than about 100,000 assets. This guideline is not binding.
Neither form has a size limit. Small exports keep the single document.

### Folder layout

```text
<package folder>/
  oasis-package.json              the manifest file
  storage_locations/
    part-00001.jsonl
  metadata_definitions/
    part-00001.jsonl
  collections/
    part-00001.jsonl
  assets/
    part-00001.jsonl
    part-00002.jsonl
```

- The manifest file is `oasis-package.json`, at the top of the package folder. The name is fixed (`MFP-1`).
- Each record folder holds the member files of one record type: `storage_locations/`, `metadata_definitions/`, `collections/`, or `assets/`. A record folder may hold subfolders, such as `assets/source=a/` (`MFP-2`).
- Member file names are free. Each name ends in `.jsonl` for plain text or `.jsonl.gz` for gzip. The `part-00001` names are an example only.
- A member path uses only ASCII letters, digits, `.`, `_`, `-`, and `=`, with `/` between segments. Each segment starts with a letter, a digit, or `_`. Two member paths differ in more than letter case.
- A record folder may be absent when its list is absent.

### The manifest file

The manifest file is a package root with no record arrays. Its manifest adds the `members` list:

```json
{
  "type": "package",
  "spec_version": "2.0.0-draft.4",
  "id": "pkg-2026-11-02-site-a",
  "source": {"system": "example-system", "id": "site-a"},
  "manifest": {
    "producer": {"name": "example-exporter", "version": "1.4.0"},
    "produced_at": "2026-11-02T18:00:00Z",
    "counts": {"storage_locations": 12, "metadata_definitions": 214, "collections": 11105, "assets": 200000},
    "namespaces": [],
    "members": [
      {"path": "assets/part-00001.jsonl", "record_type": "assets", "count": 100000,
       "size_bytes": 1043288111, "sha256": "<64 lowercase hex digits>"}
    ]
  }
}
```

The example shows one member entry only. A real manifest file lists every member file.

| Field | Meaning |
| --- | --- |
| `path` | The member path, relative to the package folder. Unique in the list. |
| `record_type` | The record type of every record in the file. It equals the first segment of `path`. |
| `count` | The number of records in the file, which is its number of lines. |
| `size_bytes` | The size of the file as stored. For a `.jsonl.gz` file, the compressed size. |
| `sha256` | The SHA-256 of the file as stored, as 64 lowercase hexadecimal digits. |

- `manifest.counts` gives the total of each list across all its member files (`MFP-5`).
- `manifest.namespaces` declares every extension namespace that any member file uses (`EXT-2`).
- The order of `members` has no meaning for the package. The checker uses it only to choose which repeat it reports.
- The manifest file has no digest of its own (`PKG-5`).

### Member files

A member file is JSON Lines. Each line is one complete record, exactly as an item of the matching array in a single document.
A line has no `type` and no `spec_version`. An asset is never split across lines or files.

Line rules (`MFP-4`):

- Every line ends with one LF, the last line too.
- No CR, no blank line, and no byte-order mark.
- No space or tab before or after the JSON object.
- Each line is strict JSON on its own and meets the number limits (`DOC-1` to `DOC-4`).

Compression:

- A `.jsonl` file is plain UTF-8 text.
- A `.jsonl.gz` file is a gzip stream. It may hold several gzip members one after another, as standard tools write them. No byte follows the last gzip member.
- The line rules apply to the decompressed text.
- One package may mix plain and gzip member files.

Size guideline: put up to about 100,000 records, or 1 GiB of uncompressed text, in each member file, whichever comes first. A larger list uses several files.
The guideline is not a limit. The checker warns with `MEMBERS_SMALL` when a list with two or more member files averages fewer than 1,000 records in each.

### Absent and empty lists

A single document keeps an absent list and an empty list apart (`DOC-3`). A multi-file package does the same (`MFP-6`):

- A list is absent when no member entry has its record type.
- A list is empty when it has member entries and their counts total 0.
- A member file with 0 records is allowed only in an empty list. A plain one has 0 bytes. A gzip one is a gzip stream with no content.

### Rules across member files

Every rule applies to the whole package, not to each member file (`MFP-7`).
Identifiers are unique per record type across all member files.
A reference may point at a record in any member file, earlier or later.
Collection positions are unique per collection across every member file.

### Write a multi-file package

You can write a package as you read your source. You do not need to hold the whole export, sort identifiers, or read the source twice (`MFP-8`).

1. Make the package folder and the record folders that you need.
2. Write the records as you read them. Write each record as JSON with no line break inside it, followed by one LF. Put each record in a member file of its record type.
3. Start a new member file when the current one reaches the size guideline.
4. Close each member file. Record its path, record type, line count, size, and SHA-256 as stored.
5. Write the manifest file last, after every member file is complete. List only complete files. Never list a partial or temporary file.
6. Check the package folder with the `validate` command.

A producer that stops before step 5 leaves no valid package. So a crash cannot produce a package that looks complete.

### Deliver a package folder as a `.tgz` file

A `.tgz` file (tar, then gzip) is a delivery wrapper. It is not part of the contract, and the checker does not read it.
Recommended practice:

- Put one top-level folder in the archive: the package folder.
- Use the POSIX pax tar format, so long paths and large files work.
- Keep member files plain (`.jsonl`) inside a `.tgz` file. Gzip member files inside a gzip archive cost time and save almost nothing.

On Linux, GNU tar adds no extra files:

```sh
tar --format=pax -czf export.tgz <package folder>
```

On macOS, leave out the `._` and `.DS_Store` files. The macOS `tar` adds `._` files, which hold file attributes, unless `COPYFILE_DISABLE=1` is set. `--no-mac-metadata` stops the same files, and `--exclude` leaves out the Finder files. Such files inside a record folder fail the check with `MEMBER_UNLISTED`.
Not yet tried on macOS: run these commands once on a Mac before you rely on them.

```sh
COPYFILE_DISABLE=1 tar --format=pax --no-mac-metadata --exclude='.DS_Store' -czf export.tgz <package folder>
tar -tzf export.tgz | grep -E '(^|/)(\._|\.DS_Store$)'
```

The second command must print nothing.

### Unpack a `.tgz` file safely

Unpack with safe settings: no absolute paths, no `..` segments, no links that point outside the folder, and no device files.
For example, use Python `tarfile` with the `data` filter:

```sh
python3 -c 'import sys, tarfile; tarfile.open(sys.argv[1]).extractall(sys.argv[2], filter="data")' export.tgz received
```

Then check the unpacked package folder. The checker also refuses a link at any member path (`MEMBER_NOT_REGULAR`).

### Other ways to deliver

You can also move a package folder as separate files with no wrapper, for example `.jsonl.gz` member files in object storage. This needs no change to the package.
The checker reads local files only. Copy the package folder to local disk before you check it.

## Collection membership

Membership is recorded on the member (`COL-3`).
An asset or a collection lists the collections it belongs to in `member_of`.
A collection record does not list its members.

- Each `member_of` entry names one collection and may carry a `position` and `extensions`.
- An absent or empty `member_of` states no membership. It never states non-membership. The collection may have other members in the source that this package does not hold.
- A collection may belong to several collections. Membership among collections never forms a cycle (`COL-4`).
- `position` orders the members of the collection that the entry names. All entries that name one collection share one position scope. Positions are unique in that scope, compare by value, and need not be consecutive (`COL-7`).
- Never take an order from array order or record order (`PKG-8`). An entry without `position` is a member with no known place in the order.
- `collection_type` is `logical`, `storage`, or `other`. A saved search is not a collection (`COL-2`).

## Time

A `timing` object gives a timeline to an asset with no versions, or to a version (`TIME-11`, `TIME-12`).
It has one of two forms.

- **Frame form.** `time_base` is present. Frames define each position, and seconds and timecode labels restate them. `duration_frames` is optional, and `duration_seconds` restates it.
- **Seconds form.** `time_base` is absent, and `duration_seconds` is required. Elapsed seconds define each position. A `source_timecode` needs `timecode_base` (`TIME-14`). Markers carry no timecode labels.

Rules for both forms:

- **Rate.** A rate is a fraction of two integers, such as `24000/1001`, in lowest terms (`TIME-2`). There is no default rate.
- **Positions.** Frame 0 is the first presented frame. Seconds measure elapsed time from the start of the timeline. A position of 0 is the start, never "no position" (`TIME-3`, `ANN-5`).
- **Endpoints.** A range includes its start and excludes its end, in either unit. A point has no end. A frame field, when present, defines the marker. Otherwise seconds define it (`TIME-4`).
- **Timeline.** Annotation positions and part starts use the timeline of their holder. A relationship `range` uses the timeline of the target version that `target_version` names, or of the target asset when it has no versions (`TIME-12`, `REL-6`). The asset level of an asset with versions, and `unassigned`, have no timeline.
- **Restated values.** Seconds agree with a frame when the nearest frame to `seconds × rate` is that frame. A tie at exactly one half rounds toward zero. The checker uses exact rational arithmetic (`TIME-7`).
- **Labels.** A timecode label is the holder's `source_timecode` anchor plus the frame offset, modulo 24 hours (`TIME-8`). Labels on markers need a frame field and an anchor, and only at the rates in the contract's label table.
- **Drop-frame.** `drop_frame: true` is allowed only at `30000/1001` and `60000/1001` (`TIME-6`). Drop-frame skips labels, never media frames.
- **Samples.** A timeline may declare `sample_rate`. `start_sample`, `end_sample`, and `duration_samples` then restate seconds (`TIME-13`). A sample is not a frame.
- **Bounds.** A position must lie inside the timeline length, when it is known. A position equal to the length is the end boundary: a point may sit there, and a range ends there at the latest. A part start is strictly less than the length (`TIME-9`, `GRP-7`).
- **Variable rate.** A variable-frame-rate asset uses the seconds form, with no `time_base` and no frame fields. A nominal rate may go in extensions (`TIME-10`).

For seconds, the checker finds the nearest frame to the seconds value, with a tie toward zero, and compares that frame with the frame field.
For a label, the checker derives the label from the frame value, then compares the two labels.
It never converts a label back to a frame. So a 24-hour rollover is never ambiguous.
If a restated value disagrees, the frame is the authority and the restated value is the error.
A producer that cannot compute a restated value correctly should omit it.

## Numbers and versions

### Exact numbers

A checker reads each JSON number as the exact decimal value of its text (`DOC-2`).
Numbers compare by value: `1`, `1.0`, `1e0`, and `10e-1` are equal.
An integer field accepts every number whose value is whole: `100`, `100.0`, and `1e2` are the same integer.

### Number limits

Every JSON number in a package must meet the number limits of RFC 7493 section 2.2 (`DOC-4`).
This includes numbers inside `extensions` and metadata values.

1. Range: the absolute value is at most 2^53 - 1, which is `9007199254740991`.
2. Precision: the value equals the shortest decimal form of its nearest binary64 number.

A number that fails either limit makes the package invalid.
The limits test a copy of the number. Every other rule uses the exact value, so decimal seconds stay exact.

### Producer guidance for numbers

- Every decimal with 15 or fewer significant digits passes the precision limit when its absolute value is 0 or lies between `1e-307` and 2^53 - 1. This covers millisecond and microsecond seconds values.
- The default number writers of JavaScript, Python (`repr`, `json`), and Go (`strconv.FormatFloat` with precision -1, `encoding/json`) write the shortest form. Their output passes.
- A writer that prints 17 significant digits can write a value that fails. For example, C `printf("%.17g")` writes `0.1` as `0.10000000000000001`, which fails. Use a shortest-form formatter instead.
- Java before release 19 does not always write the shortest form. Java 19 and later write it for normal numbers, but pick a different decimal for some very small values. Java writes the smallest positive number as `4.9E-324`, which fails. `5e-324` passes.
- A writer that prints the full exact binary expansion of a number can write a value that fails. For example, `0.1` written as `0.1000000000000000055511151231257827021181583404541015625` fails. A writer that picks a different shortest decimal at a tie also fails.
- JSON writers do not apply the range limit. Python writes `2**53` as `9007199254740992`, which fails. Convert such values to strings yourself.
- A value that does not fit, such as a 64-bit identifier, goes in a JSON string where the field accepts a string. For a large metadata value, use a definition with `value_type` `string`.

### The version check

The harness supports exactly one version: `2.0.0-draft.4` (`UNS-2`).
It compares the root `spec_version` with that string exactly, character for character (`UNS-1`).
It does no case folding and no trimming, and it applies no Semantic Versioning rule.
It never applies the rules of one version to a package that declares another, even when the two versions share a major or minor number.
This contract defines no compatibility between versions.

A package that declares `2.0.0-draft.2`, or any other version, is unsupported. The harness reports `VERSION_UNSUPPORTED` and nothing else.
The harness checks the number limits after the version check, because the limits are rules of the version.

## Extensions and preservation

Custom data goes in `extensions`, under a namespace token such as `vendor_a` (`EXT-1`).
Every record carries `extensions`. So do files, file location entries, file groups, members, versions, relationships, annotations, metadata values, options, and membership entries.
Every object outside `extensions` is closed. An unknown key anywhere else makes the package invalid.

- `EXT-2`: every namespace token used in a package must be declared once in `manifest.namespaces`, with its owner. A declared token that is unused is allowed.
- `EXT-3`: the token `oasis` is reserved. Producers never declare or use it.
- `EXT-4`: a receiver that re-emits a record or a nested entity must keep every extension value that it does not interpret, with the same value, under the same token, on the same entity. This covers namespaces it does not recognize, and members it does not interpret inside namespaces it does recognize.

Preservation is by value, not byte for byte.
Two values are the same when they have the same JSON type, numbers are equal by value, strings have the same Unicode code points, and arrays and objects hold the same values.
A receiver may change whitespace, member order, number spelling, and string escape spelling.
It must not change a value or a type, add or drop a member or an array item, change array order, or apply Unicode normalization.
It also keeps the manifest declaration of each namespace that it re-emits.

A receiver that cannot keep these values must state that its output does not conform to `EXT-4`.
A receiver that never re-emits records is not bound by this rule.
The harness checks declarations only. It cannot check what a receiver does later.

## Access summary

`access` is optional on an asset or a collection (`ACC-1`). When present, it has one field, `status`:

| State | Meaning (`ACC-2`) |
| --- | --- |
| `status: none` | The source information shows no access restriction on the entity. |
| `status: restricted` | The source information shows at least one access restriction. |
| `access` absent | The package supplies no access information. The state is unknown. Absence never means `none`. |

A producer writes `access` only when the source supplies the information. It never infers `none` from silence.
Details such as principals, grants, and denials are not part of this draft. A producer may place them in extensions.
Annotation `visibility` is separate: `public`, `private`, or absent for unknown (`ANN-4`).

Treat an entity with no `access` as unknown, not as open.
Your application decides how to protect such an entity. Never grant wider access than the source had because the package gave no access information.

The harness reads the access status as a value only. It does not evaluate access.

## Validation grants no access

`SAFE-1`: validation opens only the document, the schema bundle, and, for a multi-file package, the member files that the manifest file lists inside the package folder.
For a multi-file package, it may also list the package folder to find unlisted files, and it may write its own working files in a work folder.
It never follows a symbolic link inside the package folder. It never opens a file or location named by a value in the package.
It never connects to a network or storage system, resolves a credential, or reads media bytes.
The harness reads the document bytes, or the manifest file and the listed member files, and the local schema bundle files. Nothing else.
It never retrieves a schema. Schema identifiers are names, not locations.

A validation result does not grant filesystem, network, media, or credential access.
Your application stays responsible for authorization and for every action it takes on the data.
A passing result does not mean a document is safe or approved to import.
A storage location record has no connection settings and no credential fields. A producer never writes a secret, a credential, an access token, or a signed or temporary URL in any field of a package (`STO-2`).
Mounting, connection settings, and local path mapping belong to the receiving application.
Validation never computes the checksum of a media file. A declared file checksum is a claim by the producer (`FILE-4`).
The checker does compute the SHA-256 of each member file of a multi-file package, because the manifest file declares it (`MFP-3`).

## Numeric resource guards

OASIS keeps JSON numbers exact (`DOC-2`). The harness never rounds a number to fit a runtime type.
To protect itself, the strict parser applies these limits to every number in the input, before routing:

| Limit | Value |
| --- | --- |
| Numeric token length, including sign and exponent syntax | 1,024 ASCII bytes |
| Absolute decimal exponent | 10,000 |

These are operational guards, not OASIS value ranges. The number limits of `DOC-4` are the value rules.
An input that exceeds a guard is not invalid.
The result is `setup-failed` and exit 2, with a limitation that names the exceeded limit.
A few unusual spellings that pass `DOC-4`, such as `0e99999`, can still exceed a guard.

## Member file reader limits

The checker reads a member file in blocks. Two limits protect it from a member file that is too large to read safely:

| Limit | Option | Default |
| --- | --- | --- |
| The longest line, in bytes, not counting its LF | `--max-line-bytes N` | 67,108,864 (64 MiB) |
| How far a gzip member file may expand: decompressed bytes at most this multiple of the stored bytes read so far, plus 1 MiB | `--max-gzip-ratio N` | 1000 |

These limits are settings of the checker. They are not rules of the contract, and the contract sets no maximum line length.
A member file that passes a limit is not invalid. The result is `setup-failed` and exit 2, with a fixed limitation:

- `Setup failed: a member file line is longer than the line length limit.`
- `Setup failed: a member file expands beyond the decompression ratio limit.`

With these limits, the memory of the reader stays bounded by its read block and the line limit, whatever the size of the file.
Raise a limit only for a package that you trust.

## Harness limits

- The harness validates documents only. It has no producer, consumer, or round-trip adapter.
- It makes no interoperability claim.
- It never computes the checksum of a media file, and it does not evaluate access.
- The fixture corpus is small and synthetic. Scale and operational limits are untested.
- For a multi-file package, the checker keeps its indexes in SQLite working files, so its memory does not grow with the size of the records. `--work-dir DIR` names the work folder. Without it, the checker makes a new temporary folder and removes it at the end. Do not put the work folder inside the package folder: the next check would find its files as unlisted files.
- The checker keeps every finding that it reports in memory. Each finding takes about 324 bytes. So a package with many millions of findings can need several GiB of memory. A valid package has few findings.
- No nesting limit is approved. Very deep input fails setup at the interpreter or decoder limit. Ordinary documents are far below it.

The [harness README](../tests/conformance/README.md#limits) gives the details, including nesting depth and regular expression limits.
