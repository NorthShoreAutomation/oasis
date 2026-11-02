# Adopting OASIS 2.0

Status: DRAFT 2.0.0-draft.3, not a final release.
The rules this guide explains can change before the final release.
Interoperability between independent implementations is not demonstrated.

OASIS means Open Asset Standard Interchange Schema.
This guide explains how to produce, validate, and receive OASIS 2.0 documents, and what each result means for your system.
The [contract](specification/2.0.0-draft.3/CONTRACT.md) is the normative source. If this guide and the contract differ, the contract applies.
The [glossary](specification/2.0.0-draft.3/GLOSSARY.md) defines the terms used here.
The [data model](specification/2.0.0-draft.3/DATA-MODEL.md) draws the shapes.
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
8. [Collection membership](#collection-membership)
9. [Time](#time)
10. [Numbers and versions](#numbers-and-versions)
11. [Extensions and preservation](#extensions-and-preservation)
12. [Access summary](#access-summary)
13. [Validation grants no access](#validation-grants-no-access)
14. [Numeric resource guards](#numeric-resource-guards)
15. [Harness limits](#harness-limits)

## What OASIS 2.0 is

OASIS 2.0 is a neutral JSON format for exchanging media asset records between systems.
It has one core profile.

The package is the only exchange document: one JSON document with a manifest and four record lists.
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

### JSON output

Add `--json` to get one JSON result record instead of text:

```sh
tmp/oasis-conformance/bin/python -m tests.conformance.validate definitions/examples/package-complete.json --json
```

The record names the harness and its pinned packages, the SHA-256 of the input bytes and of the schema bundle manifest, the routed type and version, the three results, the diagnostics, the schema errors, and any limitations.
`tests/conformance/result.schema.json` describes it.
Use the JSON form when a program reads the result.

### Exit codes

| Exit | Answer | Meaning |
| --- | --- | --- |
| 0 | `PASS` | The checks ran, the structure is valid, and no diagnostic has severity `error`. Warnings are allowed. |
| 1 | `FAIL` | The input is not strict JSON, the document is not an exchange document or is unsupported, a number breaks a number limit, the structure is invalid, or a diagnostic has severity `error`. |
| 2 | `ERROR` | Setup failed. The document was not judged. Wrong option syntax also exits 2. |

Exit 2 is a problem with the environment or a resource guard, not a verdict on the document.
Fix the setup and run the command again.

### Output never repeats input values

Messages are fixed catalog text. A path stops before the first key that an author chose.
So you can share a result without sharing the data in the document.
The result record still carries the input digest and the file name you gave. Treat the record as being as sensitive as the file name.

## Outcome order

A document passes through six stages: parse, route, number limits, structural, semantic, and result.
The first stage that stops decides the outcome.

| Condition | Execution status | Structural | Semantic | Diagnostics |
| --- | --- | --- | --- | --- |
| The input file cannot be read, a locked package is missing, the schema bundle is bad or declares an unsupported version, a numeric guard is exceeded, or nesting is too deep | `setup-failed` | `not-run` | `not-run` | None. A limitation names the reason. |
| The bytes break the strict JSON policy | `input-invalid` | `not-run` | `not-run` | `INPUT_INVALID` at the root |
| The root is not an object, or has no `spec_version` member | `unsupported` | `not-run` | `not-run` | `NOT_EXCHANGE_DOCUMENT` at the root |
| `spec_version` is not exactly `2.0.0-draft.3` | `unsupported` | `not-run` | `not-run` | `VERSION_UNSUPPORTED` only |
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

### Diagnostic paths

Paths are JSON Pointers ([RFC 6901](https://www.rfc-editor.org/rfc/rfc6901.html)). The empty path is the root. Array indexes start at zero.
Diagnostics are sorted by path, then by code.
Compare results by code, path, and severity. Do not compare message text.
A number limit path stops at the first `extensions` member, and before any key that the schema bundle does not define. So the path never repeats a key that an author chose.

## Diagnostic catalog

Severity `error` fails the command. Severity `warning` does not.
This draft defines no warning code. The result format keeps the `warning` severity for later drafts.
The rule column names the contract rule that each code enforces.

| Code | Rule | Severity | What it means for you |
| --- | --- | --- | --- |
| `INPUT_INVALID` | `DOC-1` | error | The bytes are not strict JSON. Fix the encoding or the syntax at the producer. |
| `NOT_EXCHANGE_DOCUMENT` | `REC-2` | error | The document is not a package. A root array, a bare record with no `spec_version`, or a document from another format with no `spec_version` gets this code. A document with a `spec_version` that the checker does not support gets `VERSION_UNSUPPORTED` instead, whatever its `type`. It is never validated against a 2.0 schema. |
| `VERSION_UNSUPPORTED` | `UNS-1` | error | The `spec_version` is not exactly a version that the checker supports. Never rewrite a version to make it route. |
| `NUMBER_OUT_OF_RANGE` | `DOC-4` | error | A number has an absolute value greater than 2^53 - 1. Write such a value as a string. |
| `NUMBER_TOO_PRECISE` | `DOC-4` | error | The value of a number is not the shortest decimal form of its nearest binary64 number. The value is tested, not the spelling: `100.0` and `1e2` pass, `0.10000000000000001` fails. Use a shortest-form number writer. |
| `COUNT_MISMATCH` | `PKG-3` | error | A manifest count differs from its array length. The package may be truncated. |
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

The manifest `counts` must equal the array lengths (`PKG-3`). An absent array counts as 0.
The count protects against truncation of the one document. It is not a claim about the source system.

A package describes its records as they stood at `produced_at`. It carries no command (`PKG-9`).
A missing record, field, or value is not an instruction to delete, clear, or replace anything.
An asset's `deleted` date states that the source reported a deletion. It is not an instruction to delete, hide, or purge anything (`AST-3`).
Your application decides whether and how to match, merge, replace, or delete its own data.

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

The harness supports exactly one version: `2.0.0-draft.3` (`UNS-2`).
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

`SAFE-1`: validation never opens any file other than the document and the schema bundle, never opens a file or location named by a value in the document, and never connects to a network or storage system, resolves a credential, or reads media bytes.
The harness reads the document bytes and the local schema bundle files. Nothing else.
It never retrieves a schema. Schema identifiers are names, not locations.

A validation result does not grant filesystem, network, media, or credential access.
Your application stays responsible for authorization and for every action it takes on the data.
A passing result does not mean a document is safe or approved to import.
A storage location record has no connection settings and no credential fields. A producer never writes a secret, a credential, an access token, or a signed or temporary URL in any field of a package (`STO-2`).
Mounting, connection settings, and local path mapping belong to the receiving application.
Validation never computes a file checksum. A declared checksum is a claim by the producer (`FILE-4`).

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

## Harness limits

- The harness validates documents only. It has no producer, consumer, or round-trip adapter.
- It makes no interoperability claim.
- It never computes a checksum and does not evaluate access.
- The fixture corpus is small and synthetic. Scale and operational limits are untested.
- No nesting limit is approved. Very deep input fails setup at the interpreter or decoder limit. Ordinary documents are far below it.

The [harness README](../tests/conformance/README.md#limits) gives the details, including nesting depth and regular expression limits.
