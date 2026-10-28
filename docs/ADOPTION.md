# Adopting OASIS 2.0

Status: DRAFT 2.0.0-draft.2, not a final release.
The rules this guide explains can change before the final release.
Interoperability between independent implementations is not demonstrated.

OASIS means Open Asset Standard Interchange Schema.
This guide explains how to produce, validate, and receive OASIS 2.0 documents, and what each result means for your system.
The [contract](specification/2.0.0-draft.2/CONTRACT.md) is the normative source. If this guide and the contract differ, the contract applies.
The [glossary](specification/2.0.0-draft.2/GLOSSARY.md) defines the terms used here.
The [conformance harness README](../tests/conformance/README.md) gives the exact commands, output format, and catalog messages.

This guide makes no claim of certification, production readiness, or endorsement by any organization.

## Contents

1. [What OASIS 2.0 is](#what-oasis-20-is)
2. [Three separate results](#three-separate-results)
3. [Set up offline validation](#set-up-offline-validation)
4. [Validate a document](#validate-a-document)
5. [Outcome order](#outcome-order)
6. [Diagnostic catalog](#diagnostic-catalog)
7. [Packages and standalone records](#packages-and-standalone-records)
8. [Registries and completeness](#registries-and-completeness)
9. [Time](#time)
10. [Extensions and preservation](#extensions-and-preservation)
11. [Access summary](#access-summary)
12. [Validation grants no access](#validation-grants-no-access)
13. [Numeric resource guards](#numeric-resource-guards)
14. [Harness limits](#harness-limits)

## What OASIS 2.0 is

OASIS 2.0 is a neutral JSON format for exchanging media asset records between systems.
It has one core profile.

The unit of exchange is the package: one JSON document with a manifest, registries, and assets.
A record can also stand alone as its own document.
Every record carries `type`, `spec_version`, and `id`.

| Type | Describes |
| --- | --- |
| `package` | One exchange: a manifest, the registries, and the assets. |
| `asset` | One content item, with its files, file groups, versions, relationships, metadata values, and annotations. |
| `collection` | A named grouping of assets, with its membership. |
| `storage_location` | A place where files live. |
| `metadata_definition` | One metadata field: its value type, cardinality, and options. |
| `annotation` | A statement about an asset, optionally about a frame range of it. |

The schemas use JSON Schema 2020-12 and live in [`definitions/`](../definitions/README.md).
Synthetic examples for every record type are in [`definitions/examples/`](../definitions/examples/README.md).

## Three separate results

OASIS keeps three results apart. Passing one does not prove the others.

| Result | Question it answers | Who decides |
| --- | --- | --- |
| Schema acceptance | Does the document match the schema for its record type? | A JSON Schema 2020-12 validator with the bundle |
| Semantic conformance | Does the document follow the contract rules that a schema cannot express? | A conformance checker, such as the reference harness |
| Application behavior | Did a receiving system import, store, preserve, and protect the data correctly? | The receiving system and its operators |

A structurally valid document can still fail a semantic rule.
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

The command reads `type` and `spec_version` itself. You do not name a schema.

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

The record names the harness and its pinned packages, the SHA-256 of the input bytes and of the bundle manifest, the routed record type and version, the three results, the diagnostics, the schema errors, and any limitations.
`tests/conformance/result.schema.json` describes it.
Use the JSON form when a program reads the result.

### Exit codes

| Exit | Answer | Meaning |
| --- | --- | --- |
| 0 | `PASS` | The checks ran, the structure is valid, and no diagnostic has severity `error`. Warnings are allowed. |
| 1 | `FAIL` | The input is not strict JSON, the document is unsupported, the structure is invalid, or a diagnostic has severity `error`. |
| 2 | `ERROR` | Setup failed. The document was not judged. Wrong option syntax also exits 2. |

Exit 2 is a problem with the environment or a resource guard, not a verdict on the document.
Fix the setup and run the command again.

### Output never repeats input values

Messages are fixed catalog text. A path stops before the first key that an author chose.
So you can share a result without sharing the data in the document.
The result record still carries the input digest and the file name you gave. Treat the record as being as sensitive as the file name.

## Outcome order

A document passes through five stages: parse, route, structural, semantic, and result.
The first stage that stops decides the outcome.

| Condition | Execution status | Structural | Semantic | Diagnostics |
| --- | --- | --- | --- | --- |
| The input file cannot be read, a locked package is missing, the bundle is bad, a numeric guard is exceeded, or nesting is too deep | `setup-failed` | `not-run` | `not-run` | None. A limitation names the reason. |
| The bytes break the strict JSON policy | `input-invalid` | `not-run` | `not-run` | `INPUT_INVALID` at the root |
| The root has no supported `type`, or `spec_version` is not `2.0.0-draft.2` | `unsupported` | `not-run` | `not-run` | `TYPE_UNSUPPORTED`, `VERSION_UNSUPPORTED`, or both |
| The document does not match its schema | `complete` | `invalid` | `not-run` | None. Schema errors are listed by path and keyword. |
| The document matches its schema | `complete` | `valid` | `run` | Every semantic diagnostic |

A setup failure outranks an input problem. An input problem outranks a routing problem. A routing problem outranks a structural problem.
Semantic checks run only on a structurally valid document.

The strict JSON policy requires UTF-8 under [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259.html).
It refuses a byte-order mark, invalid UTF-8, malformed JSON, duplicate member names, `NaN`, `Infinity`, and unpaired surrogate escapes (`DOC-1`).

`complete` means the checks ran. It does not mean the document passed.
Read the `structural` value and the diagnostics too, or use the exit code.

### Diagnostic paths

Paths are JSON Pointers ([RFC 6901](https://www.rfc-editor.org/rfc/rfc6901.html)). The empty path is the root. Array indexes start at zero.
Diagnostics are sorted by path, then by code.
Compare results by code, path, and severity. Do not compare message text.

## Diagnostic catalog

Severity `error` fails the command. Severity `warning` does not.
The rule column names the contract rule that each code enforces.

| Code | Rule | Severity | What it means for you |
| --- | --- | --- | --- |
| `INPUT_INVALID` | `DOC-1` | error | The bytes are not strict JSON. Fix the encoding or the syntax at the producer. |
| `TYPE_UNSUPPORTED` | `UNS-1` | error | The root has no supported record type. Routing reads both `type` and `spec_version`, so a document from another format can get this code, `VERSION_UNSUPPORTED`, or both. It is never validated against a 2.0 schema. |
| `VERSION_UNSUPPORTED` | `REC-4`, `UNS-1` | error | The `spec_version` is not supported. Never rewrite a version to make it route. |
| `COUNT_MISMATCH` | `PKG-3` | error | A manifest count differs from its array length. The package may be truncated. |
| `REFERENCE_UNRESOLVED` | `PKG-6` | error | A reference names a record that is missing from a `complete` registry. |
| `REFERENCE_UNRESOLVED_PARTIAL` | `PKG-6` | warning | A reference names a record that is not in a `partial` registry. The target may exist elsewhere. |
| `ID_DUPLICATE` | `ID-1` | error | Two records of the same type share an id. Reported on each repeat after the first. |
| `NESTED_ID_DUPLICATE` | `ID-4` | error | Two files, file groups, versions, annotations, or options share an id within one record. |
| `SNAPSHOT_MISMATCH` | `ID-6` | error | A collection snapshot on an asset differs from the registry record. |
| `RATE_NOT_LOWEST_TERMS` | `TIME-2` | error | A rate such as `48000/2002` is not in lowest terms. |
| `RANGE_NOT_INCREASING` | `TIME-4` | error | A range does not end after it starts. |
| `TIMELINE_UNDECLARED` | `TIME-5`, `TIME-12` | error | A frame field belongs to a timeline with no time base. |
| `TIMELINE_UNAVAILABLE` | `TIME-12`, `ANN-3` | warning | The owning asset is not in the document, so timing agreement was not checked. |
| `SECONDS_DISAGREE` | `TIME-7` | error | A seconds value names a different frame than its frame field. |
| `TIMECODE_DISAGREE` | `TIME-7`, `TIME-8` | error | A timecode label differs from the label derived from its frame field. |
| `FRAME_OUT_OF_BOUNDS` | `TIME-9` | error | A frame position lies outside the asset duration. |
| `SEQUENCE_RANGE_EMPTY` | `GRP-3` | error | An image sequence range does not end after it starts. |
| `TRACK_DUPLICATE` | `GRP-4` | error | A file group repeats a track type and index pair, and no member of that pair carries `segment_index`. |
| `FILE_REFERENCE_UNRESOLVED` | `GRP-4` | error | A file group member names a file that the asset does not have. |
| `SEGMENT_INDEX_MISSING` | `GRP-6` | error | A file group member shares a track type and index pair with a segment but has no `segment_index`. |
| `SEGMENT_INDEX_DUPLICATE` | `GRP-6` | error | Two segments of one track type and index pair in a file group share a `segment_index`. |
| `SEGMENT_OUT_OF_ORDER` | `GRP-6` | error | The segments of one track type and index pair are not listed in ascending `segment_index` order. |
| `SEGMENT_GAP` | `GRP-6` | error | A complete file group skips a `segment_index` value in one track type and index pair. Mark the file group incomplete when segments are missing. |
| `ORDINAL_DUPLICATE` | `VER-2` | error | Two versions share an ordinal, so the current version is unclear. |
| `VERSION_REFERENCE_UNRESOLVED` | `VER-3` | error | A file, file group, or annotation names a version that the asset does not have. |
| `VERSION_WITHOUT_VERSIONS` | `VER-3` | error | A version reference appears on an asset with no versions. |
| `RELATIONSHIP_SELF` | `REL-3` | error | A relationship targets its own asset. |
| `COLLECTION_CYCLE` | `COL-4` | error | A collection is its own parent or its own ancestor. |
| `MEMBERSHIP_DISAGREES` | `COL-5` | error | An asset claims a collection whose complete member list does not include it. |
| `VALUE_SHAPE_MISMATCH` | `MD-4` | error | A metadata value does not match the `value_type` and cardinality of its definition. |
| `VALUE_DATE_INVALID` | `MD-4`, `DT-1`, `DT-3` | error | A date or date-time metadata value is not valid. |
| `VALUE_OPTION_UNKNOWN` | `MD-4` | error | An enum value is not an option id of its definition. |
| `VALUE_OPTION_REPEATED` | `MD-4` | error | A multiple enum value repeats an option id. |
| `DEFINITION_UNAVAILABLE` | `MD-4` | warning | The metadata definition is not in the document, so the value shape was not checked. |
| `DEFINITION_REPEATED` | `MD-5` | error | One record names the same metadata definition twice. |
| `NAMESPACE_UNDECLARED` | `EXT-2` | error | A package uses an extension namespace that its manifest does not declare. |
| `NAMESPACE_DECLARED_TWICE` | `EXT-2` | error | A manifest declares the same namespace token twice. |

Some rules have no document check, because a document alone cannot show them.
The [harness README](../tests/conformance/README.md#rules-with-no-document-check) lists them with the reason for each.

## Packages and standalone records

A package is the normal way to exchange data.
Inside a package, the checker resolves every reference, compares snapshots, checks membership, checks timing against the owning asset, and checks extension namespaces against the manifest.

A standalone record is a single record file. It cannot see other records.
The checker still runs every check that needs only the record itself.
For example, a collection that names itself as its parent, a relationship to its own asset, a reversed range, and a version reference that the asset cannot resolve are all reported.

Outside a package, the checker does not:

- resolve references to other records (`PKG-6`);
- check extension namespaces, because there is no manifest (`EXT-5`).

Two checks give a warning instead of a result:

- `TIMELINE_UNAVAILABLE`: a standalone annotation with frame fields, or a relationship `range`. The owning asset's time base is not in the document, so timing agreement is not checked.
- `DEFINITION_UNAVAILABLE`: a metadata value whose definition is not in the document. The value shape is not checked.

These warnings do not mean the record is wrong. They mean the check needs package context.
If you need those checks, send the records in a package.
[`definitions/examples/README.md`](../definitions/examples/README.md#declared-warnings) lists the warnings of each example.

## Registries and completeness

A package holds three registries: `storage_locations`, `metadata_definitions`, and `collections`.
Assets refer to registry records by id.
There is one exception: an entry in an asset's `collections` array can be a read-only snapshot of a collection record (`ID-6`, `COL-5`).
A snapshot omits `members`. When the registry record is present, every other field of the snapshot must equal the registry record.

The manifest states, for each of the four arrays, whether it is `complete` or `partial` (`PKG-4`):

- `complete` means the array holds every entity of that kind that the producer has for the exchanged scope.
- `partial` means some are absent.

A receiver must never treat an entity that is absent from a `partial` array as deleted or removed.
Plan your import so that a partial package adds and updates, but never removes.

References resolve under `PKG-6`:

- In a `complete` registry, an unresolved reference is an error: `REFERENCE_UNRESOLVED`.
- In a `partial` registry, it is a warning: `REFERENCE_UNRESOLVED_PARTIAL`. The target may exist in the receiver's own data.

The manifest `counts` must equal the array lengths (`PKG-3`). An absent array counts as 0.
The count protects against truncation of the one document. It is not a claim about the source system.

Collection membership belongs to the collection record (`COL-3`).
When `members.complete` is `true`, an asset that is not listed is not a member.
When it is `false`, or `members` is absent, membership is unknown, never removed.

## Time

OASIS 2.0 counts time in frames. Frames are exact. Everything else restates them.

- **Rate.** A rate is a fraction of two integers, such as `24000/1001`, in lowest terms (`TIME-2`). There is no default rate.
- **Frames.** Positions are whole frames. Frame 0 is the first presented frame of the asset. `start_frame` is inclusive and `end_frame` is exclusive (`TIME-3`, `TIME-4`).
- **Timeline.** An asset's `timing` defines its timeline. An annotation uses its asset's timeline. A relationship `range` uses the target asset's timeline (`TIME-12`).
- **Derived values.** `start_seconds`, `end_seconds`, `start_timecode`, and `end_timecode` are optional (`TIME-7`). Each must name the same frame as its frame field.
- **Seconds.** Seconds agree with a frame when the nearest frame to `seconds × rate` is that frame. A tie at exactly one half rounds toward zero. The checker uses exact rational arithmetic.
- **Labels.** A timecode label is the asset's `source_timecode` anchor plus the frame offset, modulo 24 hours (`TIME-8`). Labels are allowed only when the asset has an anchor, and only at the rates in the contract's label table.
- **Drop-frame.** `drop_frame: true` is allowed only at `30000/1001` and `60000/1001` (`TIME-6`). Drop-frame skips labels, never media frames.
- **Bounds.** A position must lie inside the asset's `duration_frames`, when it is declared (`TIME-9`).
- **Variable rate.** Variable frame rate is not supported in this draft. A producer omits `timing` and all frame fields for such an asset (`TIME-10`).

For seconds, the checker finds the nearest frame to the seconds value, with a tie toward zero, and compares that frame with the frame field.
For a label, the checker derives the label from the frame value, then compares the two labels.
It never converts a label back to a frame. So a 24-hour rollover is never ambiguous.
If a derived value disagrees, the frame is the authority and the derived value is the error.
A producer that cannot compute a derived value correctly should omit it.

## Extensions and preservation

Custom data goes in `extensions`, under a namespace token such as `vendor_a` (`EXT-1`).
Every object outside `extensions` is closed. An unknown key anywhere else makes the record invalid.

- `EXT-2`: every namespace token used in a package must be declared once in `manifest.namespaces`, with its owner. A declared token that is unused is allowed.
- `EXT-3`: the token `oasis` is reserved. Producers never declare or use it.
- `EXT-4`: a receiver that re-emits a record must keep every namespace it does not understand byte for byte. The preserved unit is the exact UTF-8 bytes of that namespace's value object, from its opening brace to its closing brace. Whitespace, member order, number spelling, and escape spelling inside it stay unchanged.
- `EXT-5`: a standalone record may use undeclared namespaces, because it has no manifest.

`EXT-4` has no policy exception. A receiver that cannot keep the bytes must state that its output does not conform to `EXT-4`.
A receiver that never re-emits records is not bound by this rule.
The harness checks declarations only. It cannot check what a receiver does later.

## Access summary

Every asset and collection carries `access.status` (`ACC-1`):

| Status | Meaning (`ACC-2`) |
| --- | --- |
| `none` | The producer knows of no access restriction. |
| `restricted` | The producer knows of at least one restriction. |
| `unknown` | The producer did not or could not determine it. |

Details such as principals, grants, and denials are not part of this draft. A producer may place them in extensions.

`ACC-3` is the block-or-quarantine rule.
A receiver that cannot represent `restricted` or `unknown` for an entity must block it or hold it in quarantine.
It must never grant wider access than the source had because it could not represent a restriction.
For an importer, this means a `restricted` or `unknown` entity never lands in an open area by default.

The harness reads the access status as a value only. It does not evaluate access.

## Validation grants no access

`SAFE-1`: validation never opens any file other than the document and the schema bundle, never opens a file or location named by a value in the document, and never connects to a network or storage system, resolves a credential, or reads media bytes.
The harness reads the document bytes and the local bundle files. Nothing else.
It never retrieves a schema. Schema identifiers are names, not locations.

A validation result does not grant filesystem, network, media, or credential access.
Your application stays responsible for authorization and for every action it takes on the data.
A passing result does not mean a document is safe or approved to import.
A storage location may carry a `credential_reference`, which names a credential held elsewhere. A producer never places a secret value in a storage location (`STO-2`).
Validation never computes a file checksum. A declared checksum is a claim by the producer (`FILE-4`).

## Numeric resource guards

OASIS keeps JSON numbers exact (`DOC-2`). The harness never rounds a number to fit a runtime type.
To protect itself, the strict parser applies these limits to every number in the input:

| Limit | Value |
| --- | --- |
| Numeric token length, including sign and exponent syntax | 1,024 ASCII bytes |
| Absolute decimal exponent | 10,000 |
| Expansion budget per document: coefficient digits plus absolute exponent, summed over all numbers | 100,000 digit units |

These are operational guards, not OASIS value ranges.
An input that exceeds a guard is not invalid.
The result is `setup-failed` and exit 2, with a limitation that names the exceeded limit.

## Harness limits

- The harness validates documents only. It has no producer, consumer, or round-trip adapter.
- It makes no interoperability claim.
- It never computes a checksum and does not evaluate access.
- The fixture corpus is small and synthetic. Scale and operational limits are untested.
- No nesting limit is approved. Very deep input fails setup at the interpreter or decoder limit. Ordinary documents are far below it.

The [harness README](../tests/conformance/README.md#limits) gives the details, including nesting depth and regular expression limits.
