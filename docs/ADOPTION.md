# Adopting OASIS 1.x

Status: DRAFT `1.2.0-draft.1`. This guide is not a release.
The rules it explains are approved as a draft and can change before the final release.

OASIS means Open Asset Standard Interchange Schema.
This guide explains how to read, validate, and exchange OASIS 1.x records.
The [contract](specification/1.2.0-draft.1/CONTRACT.md) is the normative source. If this guide and the contract differ, the contract applies.
The [glossary](specification/1.2.0-draft.1/GLOSSARY.md) defines the terms used here.

This guide makes no claim of certification, demonstrated interoperability, production readiness, or endorsement by any organization.

## Contents

1. [What OASIS 1.x is](#what-oasis-1x-is)
2. [Four separate results](#four-separate-results)
3. [Set up offline validation](#set-up-offline-validation)
4. [Validate a document](#validate-a-document)
5. [Select a profile](#select-a-profile)
6. [Format modes](#format-modes)
7. [Version routing and accepted labels](#version-routing-and-accepted-labels)
8. [Local schema registration and the bundle manifest](#local-schema-registration-and-the-bundle-manifest)
9. [Read results and diagnostics](#read-results-and-diagnostics)
10. [Embedded and standalone differences](#embedded-and-standalone-differences)
11. [Extensions and preservation](#extensions-and-preservation)
12. [Partial records and uncertain completeness](#partial-records-and-uncertain-completeness)
13. [Validation grants no access](#validation-grants-no-access)
14. [Numeric resource guards](#numeric-resource-guards)
15. [Harness limits](#harness-limits)
16. [Known 1.x limits](#known-1x-limits)
17. [Compatibility notes: legacy wire tokens](#compatibility-notes-legacy-wire-tokens)

## What OASIS 1.x is

OASIS 1.x is a set of JSON Schema (Draft 7) files that describe media asset records.
A record can describe an asset, its files, where those files are stored, its metadata, the collections it belongs to, and timed annotations.
The schemas live in `definitions/`.

The bundle has eight schema files. Seven of them are interchange entry points:

| Entry point | Describes | Required root fields |
| --- | --- | --- |
| `asset.schema.json` | One asset, with embedded files, metadata sets, collections, and annotations | `asset_id`, `title`, `type` |
| `asset_batch_import.schema.json` | A nonempty list of standalone assets | `assets` |
| `collection.schema.json` | One collection | `collection_id`, `label` |
| `collection_batch_import.schema.json` | A nonempty list of standalone collections | `collections` |
| `metadata_set.schema.json` | Metadata field definitions | `fields` |
| `storage_location.schema.json` | One storage location | `storage_id`, `system`, `path` |
| `temporal_annotation.schema.json` | One timed annotation | `source_id` |

The eighth file, `migration-report-output.schema.json`, is an application report.
It is outside the exchange profile.

Synthetic, validated examples for all seven entry points are in [`definitions/examples/`](../definitions/examples/README.md).

## Four separate results

OASIS keeps four results apart. Passing one does not prove the others.

| Result | Question it answers | Who decides |
| --- | --- | --- |
| Schema acceptance | Does the document match the selected JSON Schema? | A structural validator |
| Semantic outcome | Under the selected profile, which meanings are risky, undefined, or blocked? | The `exchange-1x` profile checker |
| Import outcome | Did a receiving application accept and store the data? | The receiving application |
| Preservation | Did the data survive a producer or consumer step without change? | A comparison of the data before and after that step |

A structurally valid document can still be blocked by the profile.
A `complete` profile result is not permission to import.
The reference harness runs validation only. It produces no import or preservation evidence.

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

The `validate` command checks one JSON record file with both structural and semantic checks:

```sh
tmp/oasis-conformance/bin/python -m tests.conformance.validate definitions/examples/collection.json --schema collection.schema.json
```

Options:

- `FILE`: the path to the JSON record file.
- `--schema`: the entry point name, such as `asset.schema.json`. Required.
- `--profile`: `exchange-1x` (default) or `legacy-1x`.
- `--format-mode`: `required` (default) or `historical-unchecked`. `exchange-1x` accepts only `required`.
- `--context`: the reference context as JSON. The default is empty context. It applies to `exchange-1x` only; `legacy-1x` ignores it.
- `--root`: `definitions` (default) for the current schemas, or `baseline` for the frozen 1.1.1 schemas.
- `--json`: print one JSON object instead of text lines.

The command prints one status line, then one line for each diagnostic.
For `definitions/examples/collection.json`, the output is:

```text
PASS status=complete routing=selected structural=valid
warning REFERENCE_UNRESOLVED /assets/0: A collection reference cannot resolve within explicit context.
warning REFERENCE_UNRESOLVED /assets/1: A collection reference cannot resolve within explicit context.
```

The collection names two assets, and the empty context does not know them.
To supply the known asset identifiers, add `--context`:

```sh
tmp/oasis-conformance/bin/python -m tests.conformance.validate definitions/examples/collection.json --schema collection.schema.json \
  --context '{"asset_ids": ["asset-0001", "asset-0002"], "collection_ids": []}'
```

With that context, the same document has no diagnostics.

When the structure is invalid, the command prints the number of schema errors.
It then prints the location and the failing keyword of each error. `(root)` means the whole document.
A location stops before any object key that the record author chose, so key text never appears.
This example uses `--profile legacy-1x` on an asset record with no `asset_id`:

```sh
tmp/oasis-conformance/bin/python -m tests.conformance.validate tests/conformance/fixtures/records/missing-required-asset.json --schema asset.schema.json --profile legacy-1x
```

```text
FAIL status=complete routing=not-applied structural=invalid
schema errors: 1
  (root) keyword required
```

With `--json`, the command prints one JSON object:

```json
{
  "file": "definitions/examples/collection.json",
  "schema": "collection.schema.json",
  "profile": "exchange-1x",
  "format_mode": "required",
  "root": "definitions",
  "routing": "selected",
  "structural": "valid",
  "execution_status": "complete",
  "diagnostics": [
    {"code": "REFERENCE_UNRESOLVED", "path": "/assets/0", "severity": "warning", "message": "A collection reference cannot resolve within explicit context."},
    {"code": "REFERENCE_UNRESOLVED", "path": "/assets/1", "severity": "warning", "message": "A collection reference cannot resolve within explicit context."}
  ],
  "input_sha256": "<SHA-256 of the input file>",
  "artifact_sha256": "<SHA-256 of the bundle manifest>",
  "structural_errors": [],
  "limitations": []
}
```

Exit codes:

| Exit code | First word | Meaning |
| --- | --- | --- |
| 0 | `PASS` | Status `complete`. Warnings are allowed. For `legacy-1x`, the structure is also valid. |
| 1 | `FAIL` | Status `blocked`, `unsupported`, or `input-invalid`, or `legacy-1x` input with invalid structure. |
| 2 | `ERROR` | Setup failed, or a numeric resource guard refused the input. A `note:` line gives the reason. |

Setup failures include a missing Python package, an input file that cannot be read, and a `--context` value that is not JSON.
With `--json`, a setup failure still prints one JSON object with `execution_status: setup-failed`.
Wrong option syntax, such as a missing `--schema` or an unknown `--root` value, is a usage error.
It prints a usage message on standard error, prints nothing on standard output, and exits 2.

`legacy-1x` gives no semantic verdict, so its status is `complete` for valid and invalid structure.
The command treats invalid `legacy-1x` structure as a failed check.
The output never contains input values. Messages are the fixed catalog messages. Text output escapes control characters.
Very deep nesting can fail setup. See [Harness limits](#harness-limits).

### Result records for corpus fixtures

The harness can print a full result record for a fixture in `tests/conformance/fixtures/manifest.json`:

```sh
tmp/oasis-conformance/bin/python -m tests.conformance.results --fixture exchange-duplicate-asset --format-mode required --root current
```

- `--fixture`: a case ID from the fixture manifest.
- `--format-mode`: `required` or `historical-unchecked`.
- `--root`: `current` for `definitions/`, or `baseline` for the frozen 1.1.1 schemas in `tests/conformance/baseline/`.

The record follows `tests/conformance/result.schema.json` (result protocol `1.0.0`).
It records the Git commit of the checkout, so this command needs a Git checkout.
It also records the SHA-256 digests of the input file and of the bundle manifest.
The record sets `independence_claim` to `false`.
For validation, `preservation.status` is always `not-tested` and `output` is always `null`.

## Select a profile

The caller must select three things before validation: the entry point, the bundled schema revision, and the profile.
No value inside a record selects them.

| Profile | What runs | What it claims |
| --- | --- | --- |
| `legacy-1x` | Structural validation only | Schema acceptance only. Routing is `not-applied`, status is `complete`, and there are no diagnostics, for valid and invalid input. |
| `exchange-1x` | Version routing, structural validation, then bounded semantic checks | A semantic inspection with stated limits. Warnings stay visible. Errors block the profile. |

`exchange-1x` covers the seven interchange entry points.
On the migration report it returns `PROFILE_UNSUPPORTED` at the root, with routing and status `unsupported`.
An unknown profile name is a setup failure, not a document diagnostic.

Selecting `exchange-1x` does not change what the schemas accept.
It adds a separate semantic result next to the structural result.

## Format modes

| Mode | Date-time checks | Use |
| --- | --- | --- |
| `required` | On | The normal mode. `exchange-1x` requires it. |
| `historical-unchecked` | Off | Only for a labelled comparison with historical baseline behavior under `legacy-1x`. |

In `required` mode, the date-time grammar is a selected subset of [RFC 3339 section 5.6](https://www.rfc-editor.org/rfc/rfc3339.html#section-5.6):

- four-digit years from 0001 to 9999, and valid Gregorian dates;
- hours 00 to 23, minutes and seconds 00 to 59;
- a `T` or `t` separator;
- an optional decimal fraction with at least one digit;
- `Z`, `z`, or a signed `HH:MM` offset, with offset hours 00 to 23 and offset minutes 00 to 59.

A space separator, an offset without its colon, and leap-second labels are refused.
An offset of `-00:00` is accepted and kept as written.
Format checks apply only where a schema declares `format: date-time`.
Custom timestamp-like strings and metadata values are not checked.

Schema `pattern` checks apply in both modes. For the bundled patterns, `\d` matches ASCII digits only, and `$` matches only at the absolute end of the string.

## Version routing and accepted labels

Under `exchange-1x`, these `schema_version` labels route to the caller-selected bundle:

- `1.0.0`
- `1.1.0`
- `1.1.1`
- `1.2.0-draft.1`

Any other value produces `VERSION_UNSUPPORTED` at that selector path. This includes non-string values.
A routing failure suppresses all semantic checks. The structural result is still reported.
A supported label mixed with an unsupported label in one batch also blocks routing.
Accepted labels can coexist in one batch.

Only declared selectors are inspected:

- the root `schema_version` of an asset, collection, metadata set, storage location, asset batch, or collection batch;
- `schema_version` on each standalone asset or collection inside a batch array.

These are not selectors:

- `schema_version` inside an embedded object;
- a `schema_version` key inside a custom object or an annotation;
- an asset's `version` field, which is free legacy data.

A standalone temporal annotation has no declared selector. Its revision comes only from the caller's selection.

An absent selector uses the caller's selection. Do not write a selector into a record that has none.
New producers that follow these DRAFT rules should emit `1.2.0-draft.1` only where the shape declares `schema_version`.
A label alone does not prove the producer's release, export history, or business meaning.

`legacy-1x` does not inspect labels. It can accept a record labelled for a later major version.
Sending such a record to an unmodified 1.x consumer is not safe version routing.

## Local schema registration and the bundle manifest

Validation never retrieves a schema from the network.
Each bundle root has a `bundle-manifest.json`:

- `definitions/bundle-manifest.json` for the current bundle (`bundle_revision` `1.2.0-draft.1`);
- `tests/conformance/baseline/bundle-manifest.json` for the frozen 1.1.1 bundle.

The manifest has `manifest_version` (`1.0.0`), `bundle_revision`, and a `schemas` array.
Each schema entry has these fields:

| Field | Meaning |
| --- | --- |
| `name` | The schema file name. The caller selects an entry point by this name. |
| `path` | The file path, relative to the bundle root. It must stay inside the bundle. |
| `sha256` | The SHA-256 digest of the exact schema file bytes. |
| `id` | The schema's existing absolute root `$id`, or `null`. |
| `base_uri` | The absolute identifier used to register and compile the schema. |
| `aliases` | Other absolute identifiers registered for the same schema. |

When a schema has no `$id`, its `base_uri` is `https://schemas.oasis.invalid/bundles/<bundle_revision>/<name>`.
When a schema has an absolute `$id`, `base_uri` equals that `$id`, and the bundle form above is an alias.
The `.invalid` domain is reserved. It never resolves on a network.

At setup, the loader:

- checks the manifest shape and every schema digest;
- refuses absolute paths, parent traversal, and identifier collisions;
- registers each schema under its `base_uri` and aliases;
- resolves relative references, such as `./asset.schema.json`, against the `base_uri`;
- compiles each entry point by its `base_uri`;
- refuses any reference to a resource the manifest does not list, with no retrieval attempt;
- audits every reachable schema: only the four bundled regular expressions, no `multipleOf`, and only the `date-time` format.

Any failure is a setup failure. The document is not evaluated.

If you change a schema, you must refresh its digest in the manifest. Otherwise setup fails.
The manifest is distribution metadata. It is not an OASIS record and not a completeness claim.

## Read results and diagnostics

### Outcome order

The checks run in this order. The first condition that applies sets the outcome.

| Condition | Routing | Structural | Execution status | Diagnostics |
| --- | --- | --- | --- | --- |
| Setup failure: missing resource, unknown profile, unknown entry point name, bad reference context, or `exchange-1x` with `historical-unchecked` format mode | `not-applied` | `not-run` | `setup-failed` | None. The reason is a limitation. |
| Input breaks the strict JSON policy | `not-applied` | `not-run` | `input-invalid` | `INPUT_INVALID` at the root |
| Input exceeds a numeric resource guard | `not-applied` | `not-run` | `setup-failed` | None. The limit is a limitation. |
| `legacy-1x` | `not-applied` | `valid` or `invalid` | `complete` | None |
| `exchange-1x` on the migration report | `unsupported` | `valid` or `invalid` | `unsupported` | `PROFILE_UNSUPPORTED` at the root |
| `exchange-1x` with an unsupported label | `unsupported` | `valid` or `invalid` | `unsupported` | `VERSION_UNSUPPORTED` at each bad selector |
| `exchange-1x`, structurally invalid | `selected` | `invalid` | `blocked` | None |
| `exchange-1x`, valid, any error | `selected` | `valid` | `blocked` | All semantic diagnostics |
| `exchange-1x`, valid, warnings or nothing | `selected` | `valid` | `complete` | All semantic diagnostics |

The strict JSON policy requires UTF-8 under [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259.html).
It refuses a byte-order mark, invalid UTF-8, malformed JSON, duplicate member names, `NaN`, `Infinity`, and unpaired surrogate escapes.

`complete` means the inspection ran. It does not mean import success, preservation, or no warnings.

### Diagnostic paths

Each diagnostic has a code, a path, a severity, and a message.
Paths are JSON Pointers ([RFC 6901](https://www.rfc-editor.org/rfc/rfc6901.html)). The empty string is the root.
Array indexes start at zero.
Diagnostics are sorted by path and then by code, as plain strings. So `/assets/10/asset_id` comes before `/assets/2/asset_id`.
Equal code and path pairs are reported once.
Compare results by code, path, and severity. Do not compare message text.
Messages never repeat input values.

Structural errors are reported only as `structural: invalid`. They never become semantic codes.

### Diagnostic catalog

Errors block the `exchange-1x` profile. Warnings do not.

| Code | Severity | When it appears | What to do |
| --- | --- | --- | --- |
| `INPUT_INVALID` | error | The input bytes break the strict JSON policy. | Fix the encoding or JSON syntax. |
| `VERSION_UNSUPPORTED` | error | A declared `schema_version` is not an accepted label. | Producers should emit an accepted label. Consumers must not rewrite a label to make it route. |
| `PROFILE_UNSUPPORTED` | error | `exchange-1x` was selected for the migration report. | Use `legacy-1x` for that report. |
| `IDENTITY_UNUSABLE` | error | An explicit `asset_id`, `collection_id`, `storage_id`, `set_id`, annotation `source_id`, or metadata field `name` is empty or only whitespace. | Supply a usable identifier. |
| `IDENTITY_DUPLICATE` | error | A top-level batch repeats an `asset_id` or `collection_id`. Reported on each repeat after the first. | Resolve the repeat at the source. The profile does not merge or deduplicate. Comparison is exact: no trimming or case folding. |
| `COLLECTION_CYCLE` | error | A collection parent link is a self-loop, or forms a cycle inside a collection batch. | Break the cycle. |
| `SIZE_UNUSABLE` | error | A file `size` is negative. | Correct or omit the size. An absent size stays absent. |
| `RATE_UNUSABLE` | error | An annotation `frame_rate` is zero. | Supply a positive rate or omit it. |
| `RANGE_REVERSED` | error | A complete frame pair or seconds pair ends before it starts. | Correct the range. |
| `CONNECTION_DATA_UNREVIEWED` | error | A storage location has nonempty `connection_details`. | No connection policy is approved yet, so the record is blocked. Producers should not put connection data in exchanged records. An empty object is permitted. |
| `RIGHTS_UNSUPPORTED` | error | Asset `rights_information`, collection `permissions`, or storage `security` is nonempty. | Handle rights outside this profile. Never drop restrictions or broaden access to proceed. |
| `REFERENCE_UNRESOLVED` | warning | A collection `parent` or string member is not known in the document or reference context. | Supply the identifier in the reference context, or accept the open reference. |
| `MEMBERSHIP_UNINTERPRETED` | warning | An embedded collection `assets` item is not a string. | The item is kept, but it has no portable meaning. |
| `VALUE_SEMANTICS_UNSPECIFIED` | warning | A metadata field has a `value`. | The value is kept. Its representation is not yet defined by the profile. |
| `TIMING_UNINTERPRETED` | warning | Annotation timing mixes frames and seconds, uses a timecode, lacks a complete range, or uses frames with no positive rate. At most one per annotation. | Prefer one unit with a complete pair. Supply a positive rate with frames. |
| `INTEGRITY_UNVERIFIED` | warning | A file has no checksum, or an empty one. | Supply a checksum if you have one. |
| `CHECKSUM_UNINTERPRETED` | warning | A file has a nonempty checksum. | The string has no defined algorithm or covered bytes. Agree on them outside the record. |
| `COMPLETENESS_UNVERIFIED` | warning | Always, at the root of every batch. | Reconcile the batch against its source by other means. |

The contract gives the exact rule for each code. See its rule locations and diagnostic catalog.

### Reference context

The reference context tells the profile which identifiers exist outside the document.
It has exactly two keys, `asset_ids` and `collection_ids`. Each is a list of nonblank strings.
Any other shape is a setup failure.

The profile also learns identifiers from the document itself:

- A standalone collection knows its own usable `collection_id`.
- A collection batch knows each usable top-level `collection_id` that occurs exactly once.
- An asset knows its own usable `asset_id`. It also knows each usable embedded `collection_id` that occurs exactly once in its `collections` list.
- An asset batch knows each usable top-level `asset_id` that occurs exactly once. Each asset in the batch knows only the collections embedded in that asset.

An identifier is usable when it is not empty and not only whitespace.
Repeated or unusable identifiers in a list are excluded. The context cannot restore them.
The profile never fetches a missing target.

## Embedded and standalone differences

The same concept can have a different shape when it is embedded in another record.
The selected entry point decides which shape applies.

| Concept | Standalone shape | Embedded shape |
| --- | --- | --- |
| Asset root | Open: extra properties are permitted. | Not applicable |
| File | Not a standalone entry point | Closed. Requires `type`, `role`, `uri`, and an embedded `storage_location`. |
| Storage location | Root is open. | Closed inside a file or a collection's `parent_storage`. |
| Metadata set | Root is open. `set_id` is optional. A field `value` is accepted as open extra data. | Closed. `set_id` is required. A field `value` is declared and unconstrained. |
| Collection | Root is open. `assets` permits only strings. | Closed. `assets` accepts any JSON items. |
| Temporal annotation | Root is open. Requires a start position. Unless `is_point_marker` is `true`, also requires an end position. Timecodes must match the legacy pattern. | Closed. No timing requirement and no timecode pattern. |

A storage identifier alone does not replace the required embedded file storage location.
Field objects inside metadata sets stay open in both shapes.
Schema defaults are annotations only. A validator must not insert them into a record.

## Extensions and preservation

The asset, collection, metadata set, storage location, and batch roots each have an `extensions` object for custom data.
Open roots also accept other unknown properties.
Closed embedded objects, such as files and embedded storage locations, accept no extra properties. Do not add extensions there.

Schema descriptions recommend `x_` or `custom_` prefixes for extension keys. This is guidance, not a rule that rejects other keys.

The profile does not look inside opaque data:
`extensions`, `technical_metadata`, annotation `metadata`, connection data, security, permissions, unknown properties, and non-string membership items.
A key with a familiar name inside that data gets no identity, timing, rights, or version meaning.

A consumer that claims preservation must keep:

- every schema-accepted property, including unknown properties in open objects;
- the difference between an absent property, `null`, and an empty value;
- array order, strings, booleans, and exact numbers;
- an existing `schema_version` or its absence.

Object key order and whitespace do not matter.
Equal numbers compare equal when parsed without precision loss. For example, `25`, `25.0`, and `2.5e1` are equal.
Unicode normalization, date rewriting, path normalization, default insertion, and token replacement are changes, not preservation.

`tests/conformance/preservation.py` compares two decoded JSON trees under these rules.
It is a comparator only. It is not evidence that any producer or consumer preserves data.

## Partial records and uncertain completeness

OASIS 1.x records can be partial. The profile does not treat a gap as a deletion.

- An omitted, empty, or partial membership list does not remove members.
- Neither the asset side nor the collection side of a membership is the complete authoritative list.
- An absent or `null` parent means no parent link. It is not a removal instruction.
- Missing parents are not created.
- One recorded storage location does not mean it is the only copy.
- An absent file size is not zero.

Every batch gets `COMPLETENESS_UNVERIFIED`.
The array length, custom counts, and custom checksums do not prove that the batch holds the full source export.
To claim completeness, you need a defined scope and reconciliation evidence from outside the record.
Streaming and newline-delimited framing are outside this DRAFT.

## Validation grants no access

Validation reads the document bytes and the local bundle files. Nothing else.
It never opens a locator, resolves credentials, hashes media, or connects to a storage provider.
It never retrieves a schema.

A validation result does not grant filesystem, network, media, or credential access.
Your application stays responsible for authorization and for any action it takes on the data.
A `complete` result does not mean a record is safe or approved to import.
The profile does not identify secrets by guessing field names, and no result certifies that custom data is free of secrets.
Result files are as sensitive as their input.

## Numeric resource guards

OASIS keeps JSON numbers exact. The harness never rounds a number to fit a runtime type.
To protect itself, the strict parser applies these limits to every number in the input:

| Limit | Value |
| --- | --- |
| Numeric token length, including sign and exponent syntax | 1,024 ASCII bytes |
| Absolute decimal exponent | 10,000 |
| Expansion budget per document: coefficient digits plus absolute exponent, summed over all numbers | 100,000 digit units |

These are operational guards, not OASIS value ranges.
An input that exceeds a guard is not invalid.
The result is `setup-failed` with `structural: not-run` and no diagnostics. The limitation names the exceeded limit.
Malformed input is reported as `input-invalid` first, even when it also has an oversized number. The one exception is very deep nesting, described below.

## Harness limits

The Python harness is the only structural engine. These limits are recorded and accepted:

- **Nesting depth.** No nesting limit is approved. The harness stops at its interpreter or decoder limit.
  - Well-formed input nested more than about 1,000 levels fails setup.
  - Malformed input nested about 10,000 levels or more reports `setup-failed`, not `input-invalid`.
  - Files with derivatives nested about 165 levels or more fail setup.
  - Ordinary records are far below all of these depths.
- **Draft 7 metaschema reference.** A schema that references the Draft 7 metaschema fails setup, because the metaschema is not a bundle resource.
- **Unreferenced `$defs`.** Draft 7 does not define `$defs`. The harness audits a `$defs` member only when a reference reaches it.

[`tests/conformance/README.md`](../tests/conformance/README.md#nesting-depth) gives the details.

## Known 1.x limits

- The DRAFT adds no wire properties, required fields, or enum values to the 1.1.1 baseline.
- File grouping by equal `role` values cannot describe every independent rendition or track.
- A checksum string has no defined algorithm, expected value, or covered bytes.
- Metadata field definitions, such as `type`, `pattern`, `minimum`, and `enum_values`, are data. They are not executed as schema rules over the field's value.
- Metadata value representation is not defined.
- Timecode, frame, and seconds conversion is not defined. This includes drop-frame numbering, clock origin, and whether an end point is inclusive.
- A positive decimal frame rate, such as `23.976`, is kept as written. It is not converted to an exact rational rate.
- Rights, permissions, and connection data cannot be exchanged under `exchange-1x`.
- Identifiers have no global namespace. Identifiers from separate exchanges may collide.
- Batch completeness cannot be proven inside the record.
- The harness covers validation only. It has no producer, consumer, or round-trip adapter.
- The conformance corpus is small and synthetic. Scale and operational limits are untested.

## Compatibility notes: legacy wire tokens

This section lists literal values from the published 1.x schemas.
Keep these tokens exactly as written. Do not assume they have the same meaning in other systems.

### Annotation type

The legacy `annotation_type` field accepts these tokens: `Generic`, `Comments`, `QualityControlMarker`, and `Transcription`.

- Keep each token literally.
- The schema declares `Generic` as a default. A default is an annotation only. An absent `annotation_type` stays absent. Do not write `Generic` into the record.
- A mapping to another system must state its uncertainty. These tokens have no universal destination meaning.

### File role

The legacy file `role` field is a free string. The schema description lists conventional values: `essence` (primary media), `proxy` (a lower-resolution derivative), `thumbnail`, and `sidecar` (a companion file that is not media).

- Published 1.1 treats files in one asset with equal `role` values as one logical media group.
- No version label alone proves that an older producer intended this grouping.
- Keep file order and role strings. Do not split or create groups during inspection.

### Point marker default

The schema declares `is_point_marker` with a default of `false`. As with all defaults, do not insert it into a record.
