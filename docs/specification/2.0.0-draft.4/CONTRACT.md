# OASIS 2.0 contract

Status: DRAFT 2.0.0-draft.4. Not a final release. Interoperability between independent implementations is not demonstrated.
This text does not claim certification or production readiness.
OASIS means Open Asset Standard Interchange Schema.
The accompanying [glossary](GLOSSARY.md) defines every term used here. The [data model](../../specification/2.0.0-draft.4/DATA-MODEL.md) draws the shapes; it is informative.

- Revision: 2.0.0-draft.4, 2026-11-02. Adds the multi-file package for very large exports: a package folder with a manifest file and member files (section 16, `MFP-1` to `MFP-9`). Revises `SAFE-1`, `REC-1`, `REC-2`, `PKG-1`, `PKG-2`, `PKG-3`, `PKG-5`, `PKG-8`, and `FILE-4` for the two package forms. No record field changed. See "Changes in 2.0.0-draft.4" below.
- Revision: 2.0.0-draft.3, 2026-10-31. Applies the design decisions approved from 2026-10-29 to 2026-10-31: the stated purpose, timing in frames or seconds, versions, file copies and storage, collection membership, metadata lists and annotations, number limits, and the version check. See "Changes in 2.0.0-draft.3" below.
- Revision: 2026-10-28. Section 15 is retitled "Unsupported documents" and holds one rule, `UNS-1`. The appendices are renumbered. Editorial; no field, schema, or identifier changed.
- Revision: 2.0.0-draft.2, 2026-10-21. Applies the field renames and additions approved on the working group call of 2026-10-16. See "Changes in 2.0.0-draft.2" below.
- Revision: 2026-10-14. Grandfathered language tags are matched case insensitively. `EXT-4` admits no policy exception.
- Revision: 2026-10-14. `EXT-4` byte preservation is defined as the exact byte sequence of each namespace value. `ANN-1` language tags are checked against the full RFC 5646 grammar. `MD-2` length bounds are stated.
- Revision: 2026-10-14, after the harness build. `SAFE-1` states the two files validation may open: the document and the schema bundle. No other rule changed.
- Revision: 2026-10-14. Snapshot equality is defined without `members`. Metadata values are limited to scalars or arrays of scalars in the schema. Extensions on options and metadata values are expressed. Syntax checks are added for language tags and media types. Added: namespace token uniqueness, image-sequence range order, absent version references on groups and annotations, the meaning of extension preservation, and `SAFE-1` as a normative rule. Corrections to `PKG-8` and `DT-3`.
- Revision: 2026-10-05. Rule markers are aligned with the schemas. The collection type field is renamed to `collection_kind`. The text states where extensions are allowed. The connection credential reference is optional. Storage locations gain an optional description and dates. Annotations gain an optional title and nested provenance. Asset-side membership against incomplete collections is clarified.
- Revision: 2026-10-05. Section 6 is reworked: origin removed, source timecode anchor added, timeline ownership stated, explicit timecode rate table, bounds and arithmetic rules.
- Executes the steward's six design decisions for 2.0: one core profile, packages with record lists, JSON Schema 2020-12 with stable identifiers, exact frame timing, namespaced extensions with an access summary, and no report format

## Changes in 2.0.0-draft.2

Date: 2026-10-21. Source: working group call, 2026-10-16. These changes rename, add, and remove fields. Existing rules keep their identifiers. Two new rules, `FILE-5` and `GRP-6`, cover the new fields.

- The field that names a record's type is now `type`, not `kind`, on every record: package, asset, collection, storage location, metadata definition, and annotation. A collection snapshot inside an asset also uses `type`. An annotation nested inside an asset still carries no record type field. The relationship field `kind` and the collection field `collection_kind` keep their names for now; whether they should change is still open.
- On a metadata definition, the data type of the values (string, integer, enum, and so on) moves from `type` to `value_type`. This is needed because `type` now names the record type.
- A metadata definition no longer has `name`. Its `id` identifies the field, and the optional `label` gives a human name.
- An asset's `groups` array is now `file_groups`.
- A file group's `kind` is now `role`. The allowed values are the same, and it is still required. A file group may also carry an optional `label`.
- A file may carry an optional `role` (`master`, `mezzanine`, `preview`, `thumbnail`, `sidecar`, `other`) and an optional `label`.
- A file group member's `track_kind` is now `track_type`. It is still required.
- A file group member may carry an optional `segment_index`. It gives the order of a file when one recording is split across several files, as some cameras and recording formats do. It is sequence order only and implies no frame arithmetic. New rule `GRP-6` states how segments are numbered.
- New rule `FILE-5` states what each file role means.
- `spec_version` is `2.0.0-draft.2`. Schema identifiers are unchanged.

## Changes in 2.0.0-draft.3

Date: 2026-10-31. Source: the design decisions approved from 2026-10-29 to 2026-10-31. These changes rename, add, and remove fields and rules. Existing rules keep their identifiers. Removed identifiers are not reused.

Purpose and exchange documents:

- Section 2 states the purpose. OASIS is an interchange format for moving metadata between systems and for long-term metadata archiving. It is not an update or synchronization protocol.
- Only a package is an exchange document. Standalone records are removed. The package root carries `type` and `spec_version`. Records inside a package carry neither field (`REC-1`, `REC-2`).
- The root checks run in a fixed order: `DOC-1`, the exchange document test, the version check, then the root `type` test (`REC-2`, `UNS-1`).
- Removed rules: `REC-3` (one `spec_version` per document), `REC-4` (replaced by `UNS-1`), and `EXT-5` (no standalone records).
- `annotation.schema.json` is removed. The ten record-only examples are deleted. `package-full.json` shows every field of every record type. The asset, collection, storage location, and metadata definition schemas stay as parts of the schema bundle.

Packages and references:

- The manifest `completeness` object is removed. `PKG-4` is removed. New `PKG-9`: a package states facts as they stood at `produced_at` and carries no command.
- Every reference resolves inside the package (`PKG-6`). The partial-registry warnings of `PKG-6`, `REL-3`, and `MD-6` are removed. A package never depends on another package.
- The package arrays are called record lists, not registries.
- `REC-5` defines identifiers in Unicode code points, with a fixed whitespace set. `ID-5`: a reference has identifier syntax.
- `PKG-7` reworded. `PKG-8` adds collection member order by `position`.

Numbers, extensions, and versions:

- `DOC-2` rewritten: numbers are exact decimal values, and an integer is any number whose value is whole.
- New `DOC-4`: the number limits of RFC 7493 section 2.2 apply to the whole document.
- `EXT-4` rewritten: extension data is preserved by value, not byte for byte.
- `EXT-1`: file location entries and collection membership entries carry `extensions`. The small value object list drops `connection` and adds `sequence`, `sequence_image`, and `ratio`.
- `UNS-1` rewritten: a checker compares `spec_version` exactly and reports an unsupported version with no other finding. New `UNS-2`: no compatibility between versions is defined.

Time:

- Timing has a frame form and a seconds form (`TIME-11`). New `timing` fields: `duration_seconds`, `timecode_base`, `sample_rate`, `duration_samples`. New annotation fields: `start_sample`, `end_sample`.
- Rewritten: `TIME-3`, `TIME-4`, `TIME-5`, `TIME-7`, `TIME-9`, `TIME-10`, `TIME-11`, `TIME-12`. Amended: `TIME-8`. New: `TIME-13` (sample positions), `TIME-14` (source timecode in the seconds form).
- A point may sit at the end boundary. The `TIME-9` clause for an object with `start_frame`, `end_frame`, and `duration_frames` is removed.
- A variable-frame-rate asset uses the seconds form (`TIME-10`).
- A relationship `range` may be in frames, in seconds, or in both (`REL-1`). New `REL-4`: a subclip length agrees with its range.
- New `GRP-7`: part starts of a split recording. New `GRP-8`: a preview shares its version's timeline. New `ANN-5`: a position of 0 is the start of the timeline.

Versions:

- A version holds its own `timing`, `files`, `file_groups`, `metadata`, `annotations`, and `relationships` (`VER-1`). The `version` field is removed from files, file groups, and annotations.
- New asset fields: `current_version` (`VER-6`) and `unassigned` (`VER-5`). New rules `VER-4` to `VER-7`. `VER-1` and `VER-2` rewritten: `ordinal` gives order and never selects the current version. `VER-3` is removed.
- New relationship field `target_version` (`REL-6`). New `REL-5`: duplicate relationships are rejected.
- `ID-4` rewritten: nested ids are unique across every holder of an asset. `ID-6` (snapshots) is removed.

Files, storage, and tracks:

- File: `storage_location` and `path` move into `locations`, a list of copies. A location entry has `storage_location`, `path`, `availability`, `missing_frames`, and `extensions`. `status` and `version` are removed. New fields: `reel_name`, `duration_seconds`, `bit_rate`, `sequence`. A file may have no known copy.
- `FILE-1` rewritten. `FILE-2` removed. `FILE-3` and `FILE-5` amended. New: `FILE-6` (copies), `FILE-7` (technical fields), `FILE-8` (compact image sequences), `FILE-9` (reel name). An informative note next to `FILE-6` states that two file entries with the same storage location and path describe one stored file.
- Storage location: `connection` is removed, with its `method` and `credential_reference`. `system` is a closed list: `source_local`, `network_share`, `s3`, `gcs`, `azure_blob`, `tape`, `other`. `STO-1` and `STO-2` rewritten. New `STO-3`: storage types and locators.
- File group: `complete` and `version` are removed (`GRP-1`). `GRP-6` rewritten: a gap in segment numbers shows missing parts. `GRP-2` and `GRP-4` amended.
- Member: `sequence_range` is removed. New fields: `stream_index`, `sequence_frame`, `start_frame`, `start_seconds`, `label`, `language`, `channel_layout`, `codec`, `bit_rate`, `duration_seconds`, `width`, `height`, `display_aspect_ratio`, `bit_depth`, `frame_rate`, `capture_frame_rate`, `frame_count`, `scan_type`, `sample_rate`. `channel_count` is allowed on `audio` members only. `GRP-3` rewritten. New: `GRP-9` (presence at a storage location), `GRP-10` (stream selection), `GRP-11` (track descriptions), `GRP-12` (explicit image sequences).

Collections:

- The collection field `collection_kind` is now `collection_type`. The values are `logical`, `storage`, and `other`. `query` is removed. A saved search is not a collection (`COL-2`).
- Membership is recorded on the member: `member_of` on assets and collections, with an optional `position`. The collection `members` and `parent` fields and the asset `collections` field are removed. `COL-1`, `COL-3`, and `COL-4` rewritten. `COL-5` removed. New `COL-7`: member order by `position`.

Metadata, annotations, and access:

- The relationship field `kind` is now `type` (`REL-1`, `REL-2`).
- Metadata definition: new `list_type` (`fixed` or `open`), required for `enum`. `options` may be empty. New `MD-7` (fixed and open lists) and `MD-8` (no repeated items in any `multiple` value). `MD-1`, `MD-4`, `MD-5`, and `MD-6` amended.
- Annotation: new optional `visibility` (`public` or `private`), allowed on every annotation whatever its purpose (`ANN-4`). The standalone annotation record and its `asset` field are removed. `ANN-1` and `ANN-3` amended.
- `access` is optional. The `unknown` status is removed. An absent `access` means unknown (`ACC-1`, `ACC-2`). `ACC-3` is removed.
- Asset `deleted` reports a source fact. It is never an instruction (`AST-3`).

Status:

- `spec_version` is `2.0.0-draft.3`. Schema identifiers are unchanged.
- Section 16 states what OASIS tests and what the developers of each product are responsible for.

## Changes in 2.0.0-draft.4

Date: 2026-11-02. Source: the decisions of 2026-11-02 for very large exports. These changes add a second form of the package. They change no record field. Existing rules keep their identifiers.

- A package has two forms. A single-document package is one JSON document, as before. A multi-file package is a package folder that holds a manifest file, `oasis-package.json`, and member files in one folder for each record type (section 16).
- The manifest gains an optional `members` list (`PKG-2`, `MFP-2`). Each member entry names one member file with its path, record type, record count, size, and SHA-256 digest. `manifest.members` marks the multi-file form. A package root with `manifest.members` has none of the four record arrays (`MFP-1`).
- A member file is JSON Lines: one record on each line, as plain text (`.jsonl`) or gzip (`.jsonl.gz`) (`MFP-4`).
- New rules `MFP-1` to `MFP-9` define the multi-file package. They state the form, the manifest file name, the member entries and member paths, and the member files in the package folder. They also state the line and compression rules, the counts, absent and empty lists, and the scope of each rule across member files. The last two rules state the order in which a producer writes and the equivalence of the two forms.
- `REC-1`, `REC-2`, `PKG-1`, `PKG-2`, `PKG-3`, `PKG-5`, and `PKG-8` are revised for the two forms. The rules for a single document keep their meaning.
- `FILE-4` states that the digest of a member file is not a file checksum.
- `SAFE-1` lets validation read the member files that the manifest file lists, list the package folder, and use its own working files. Validation never follows a symbolic link inside the package folder.
- Section 2 states both forms as current. The new section 16 holds the multi-file package. "Status and claims" is now section 17.
- The word "bundle" keeps one meaning: the schema bundle. The multi-file form is a form of the package, not a bundle.
- `spec_version` is `2.0.0-draft.4`. Schema identifiers are unchanged.

## 1. Reading this contract

Normative sections are 3 to 16, and `SAFE-1` in this section. The rest of sections 1, 2, and 17, and the appendices are informative. A paragraph inside a normative section that starts with "Informative note" is informative.
`MUST`, `MUST NOT`, and `SHOULD` express requirements.
Every normative rule has an identifier in the form `AREA-n`. A rule marked **S** is expressed by the JSON Schema files. A rule marked **T** cannot be expressed by JSON Schema and is implemented by a conformance checker. A rule marked **S+T** is partly each.

Schema acceptance, semantic conformance, and application behavior are distinct results. Passing one does not prove the others.
`SAFE-1` (T). Validation MUST NOT open any file other than the document under validation, the schema bundle it validates against, and, for a multi-file package, the member files that its manifest file lists at member paths inside the package folder. For a multi-file package, the document under validation is its manifest file, and validation MAY list the contents of the package folder to find unlisted files (`MFP-3`). It MAY create and use its own temporary working files in a folder that the caller names or in the system temporary folder. It MUST NOT follow a symbolic link inside the package folder, open a member path that leads outside the package folder, open a file or location named by any other value, connect to a network or storage system, resolve a credential, or read media bytes. The path that the caller gives to a document, a manifest file, or a package folder is the caller's choice, and it MAY pass through a symbolic link.
Applications remain responsible for authorization and execution.

## 2. Design summary

This section is informative. This is a major version. Section 15 states the rule for documents the standard does not cover.

OASIS is an interchange format for moving metadata between systems and for long-term metadata archiving. It is not an update or synchronization protocol. Packages are self-contained. A package has two forms, and both use the same record definitions. A single-document package is one JSON document. A multi-file package is a package folder with a manifest file and member files, for exports that are too large for one document (section 16).

- One definition per entity. The package is the only exchange document. The record definitions are its parts.
- Two forms of one package are equivalent when they hold the same records. When each record list keeps its record order, a checker gives both forms the same outcome and the same findings (`MFP-9`).
- A package holds every record that its references need. Its record lists hold storage locations, metadata definitions, collections, and assets. Records reference each other by id.
- A package states facts about its source as they stood when it was produced. It carries no command.
- Exact time: a timeline in frames at a rational rate, or in elapsed seconds. Restated values must agree.
- An asset may have versions. Each version holds its own timeline, files, file groups, metadata, annotations, and relationships.
- A file describes its content once and lists its stored copies. Explicit file groups and tracks describe how the files of an asset relate.
- Relationships, membership recorded on the member, a collection type, typed metadata values with fixed or open lists, a checksum algorithm label, and an optional access summary are part of the core profile.
- Extensions are namespaced and declared. Their values are preserved by value. Unknown keys outside them are rejected.
- Numbers keep their exact decimal value and meet the limits of RFC 7493 section 2.2.
- No reporting of any kind.

## 3. Documents and records

`DOC-1` (T). A document is UTF-8 JSON under RFC 8259 with unique object member names and valid Unicode scalar values. A byte-order mark, a duplicate member name, `NaN`, `Infinity`, malformed encoding, or an unpaired surrogate escape makes the document invalid.

`DOC-2` (T). Exact numbers. A checker reads each JSON number as the exact decimal value of its text. It never replaces the value with a rounded binary value. Numbers compare by value: `1`, `1.0`, `1e0`, and `10e-1` are equal, and number spelling carries no meaning. A field or value of type integer accepts every number whose value is whole, however it is written: `100`, `100.0`, and `1e2` are the same integer. A number with a nonzero fractional part, such as `100.5`, is not an integer. A checker that cannot evaluate a number exactly MUST report a setup failure. It MUST NOT round and then report conformance.

`DOC-3` (T). Validators MUST NOT insert defaults, normalize Unicode, rewrite dates, normalize paths, reorder arrays, or replace tokens. Absence, `null`, and empty are three distinct states and are preserved as written.

`DOC-4` (T). Number limits. OASIS adopts the number rules of I-JSON, RFC 7493 section 2.2, as requirements for the whole document, including `extensions` and metadata values. Every JSON number MUST meet both limits:

1. Range: its absolute value is at most 2^53 - 1, which is `9007199254740991`.
2. Precision: its value equals the shortest decimal form of its nearest binary64 number. Conversion to binary64 uses IEEE 754 round to nearest, ties to even. Among the decimals with the fewest significant digits that round to that binary64 number, the shortest form is the one nearest to it; when two are equally near, it is the one whose last digit is even.

A number that fails either limit makes the document invalid. A value that does not fit, such as a 64-bit identifier or a number with more digits, is written as a JSON string where the field accepts a string. The limits test a copy of the number. Every other rule uses the exact value under `DOC-2`, so decimal seconds stay exact. A checker applies `DOC-4` after the version check (`UNS-1`), because the limits are rules of the version.

Informative note: one range limit is enough. Every binary64 number with an absolute value above 2^53 - 1 is whole. So "fit binary64" plus "whole numbers beyond 2^53 - 1 are strings" leaves no JSON number above 2^53 - 1.

Informative note: RFC 7493 says SHOULD NOT. OASIS makes the limits a MUST.

Informative note: the adoption covers RFC 7493 section 2.2 only. It does not adopt the rest of I-JSON. For example, `DOC-1` does not reject Unicode noncharacters, and `DT-1` accepts lowercase `t` and `z`, which RFC 7493 section 4.3 recommends against. This contract cites section 2.2, not "I-JSON" alone.

Informative note: a cap of 15 significant digits is not used. It would reject `3.141592653589793` and `0.30000000000000004`, which common programming languages write by default.

`REC-1` (S). The document root is a package. It carries `type` with the value `package` and `spec_version` with the value `2.0.0-draft.4` for this draft. Records inside a package carry neither field. The array that holds a record states its type: `storage_locations`, `metadata_definitions`, `collections`, or `assets`. In a multi-file package, the `record_type` of a member entry states the type of every record in that member file (`MFP-2`). A `type` or `spec_version` field on a record inside a package is an unknown key and is rejected (`REC-7`).

`REC-2` (T). Only a package is an exchange document. The record definitions are parts of a package. They are not exchange documents. A package in either form is an exchange document. For a multi-file package, the root checks run on its manifest file (`MFP-1`). A member file, and a line in it, are not exchange documents and get no root check: the member entry states their record type (`MFP-2`, `MFP-4`). A checker runs the root checks in this order:

1. `DOC-1`. Bytes that break it are invalid input.
2. A root that is not an object, or has no `spec_version` member, is not an exchange document.
3. A `spec_version` that is present but is not a version the checker supports, compared exactly, is unsupported (`UNS-1`).
4. A supported version with no root `type` member, or a root `type` other than `package`, is not an exchange document.

A checker reports a document that is not an exchange document at pointer `""`, or at `/type` when `spec_version` is supported and `type` is present, and checks nothing else. A one-asset export is a package that holds the asset and every record that its references need (`PKG-6`).

`REC-5` (S). Every record, and every nested object whose `id` the core schemas declare, has an identifier: a string of 1 to 256 Unicode code points. Its first and last code points are not whitespace. Whitespace in this contract means exactly U+0009 to U+000D, U+0020, U+00A0, U+1680, U+2000 to U+200A, U+2028, U+2029, U+202F, U+205F, U+3000, and U+FEFF, which is the ECMA-262 set. An empty identifier, or one made only of whitespace, is rejected. Whitespace inside an identifier is allowed. Identifiers compare by exact code points, with no case folding, trimming, or Unicode normalization (`ID-1`, `DOC-3`). `source.id` is provenance under `REC-6`. It is not an identifier under this rule. Nothing inside an extension namespace is an identifier under this rule, whatever its member names.

`REC-6` (S). Every record may have `source`: an object with `system` (nonempty string, the producing system's name), optional `instance` (string, one deployment of that system), and `id` (nonempty string, the entity's identifier in that system). `source` is provenance. It is never used for reference resolution.

`REC-7` (S). Every record may have `extensions` (section 13). Every object in a record is closed: a key that is not declared by the schema and not inside `extensions` makes the record structurally invalid.

## 4. Packages, manifest, and record lists

A package holds a manifest and four record lists. Its root has `type` `package`. A package has one of two forms. A single-document package is one JSON document that holds the record lists as arrays. A multi-file package holds the same root, without the arrays, in its manifest file, and holds the records in member files (section 16). A package root without `manifest.members` is a single-document package.

`PKG-1` (S). A package has `type` and `spec_version` (`REC-1`), `id` (required, `REC-5`), and `manifest` (required). It MAY have `source` (`REC-6`) and `extensions` (section 13). A single-document package has the arrays `storage_locations`, `metadata_definitions`, `collections`, `assets`, each optional. An absent array and an empty array are both allowed. They stay distinct states under `DOC-3`. A multi-file package has none of the four arrays (`MFP-1`). Its member files hold its record lists, and `MFP-6` states when a list is absent or empty.

`PKG-2` (S). `manifest` has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `producer` | object `{name, version}` of nonempty strings | yes | Software that wrote the package. |
| `produced_at` | date-time (section 14) | yes | When the package was written. |
| `counts` | object with integer `storage_locations`, `metadata_definitions`, `collections`, `assets`, each 0 or more | yes | Declared record count per record list (`PKG-3`). |
| `namespaces` | array of namespace declarations (section 13) | yes, may be empty | Every extension namespace used anywhere in the package. |
| `members` | array of member entries (`MFP-2`) | only in a multi-file package | The member files of a multi-file package. Its presence marks the multi-file form (`MFP-1`). |
| `description` | string | no | Free text for humans. |

`PKG-3` (T). Each `counts` value MUST equal the number of records in its record list. A mismatch is rejected. In a single-document package, that number is the length of the array, and an absent array counts as 0. In a multi-file package, it is the sum of the `count` values of the member entries of that record type. A list with no member entry counts as 0. Each member `count` equals the number of lines in its member file (`MFP-5`). The count is a truncation and framing check for the package; it is not a claim about the source system.

`PKG-5` (T). A package carries no digest of itself. The manifest file of a multi-file package carries a SHA-256 digest for each member file (`MFP-2`, `MFP-3`). The manifest file itself has no digest. Transport integrity of a single document, of a manifest file, and of any delivery wrapper or storage object is outside this contract. The checksums of section 8 apply to the files that file objects describe.

`PKG-6` (T). Every reference in a package to a package-level record (a storage location, a metadata definition, a collection, or an asset) MUST resolve to a record of its target type in that package. An unresolved reference is rejected. References to nested objects resolve under their own rules: a file group member's `file` under `GRP-4`, `current_version` under `VER-6`, `target_version` under `REL-6`, and an `enum` value item under `MD-4` and `MD-7`: on a `fixed` list it must be an option `id`; on an `open` list an item equal to an option `id` names that option and any other string is text, not a reference. Every reference in the package must resolve under one of these rules. A package never depends on another package. When separate packages need the same supporting record, each package holds its own copy. Values inside `extensions` are not references under this rule, and a checker does not resolve them.

Informative note: the reference fields of this draft are:

| Reference field | Target type | Target scope |
| --- | --- | --- |
| `member_of[].collection` on assets and collections | collection | package |
| collection `storage.storage_location` | storage location | package |
| file `locations[].storage_location` | storage location | package |
| metadata value `definition` | metadata definition | package |
| metadata value of `value_type` `asset_reference` | asset | package |
| metadata value of `value_type` `collection_reference` | collection | package |
| relationship `target` | asset | package |
| file group member `file` | file | the holder of the file group (`GRP-4`) |
| `current_version` | version | the asset (`VER-6`) |
| relationship `target_version` | version | the target asset (`REL-6`) |
| `enum` value item on a `fixed` list | option | the value's definition (`MD-7`) |

`PKG-7` (S). Each item of a package array is a full record of the type that the array names. No record has an abbreviated or embedded form.

`PKG-8` (T). Ordering inside each array carries no meaning except where a rule says so (file group members, option lists). Version order is given by `ordinal`, not by array position (`VER-2`). Collection member order is given by `position` (`COL-7`), never by array order or record order. In a multi-file package, the order of the member entries, of the member files, and of the lines in a file carries no meaning either (`MFP-2`, `MFP-7`).

`PKG-9` (T). A package describes its records as they stood at `produced_at`. It carries no command. A missing record, field, or value is not an instruction to delete, clear, or replace anything. An asset's `deleted` date is a fact about the source, not an instruction. Receiving applications decide whether and how to match, merge, replace, clear, retain, or delete their own data.

## 5. Identity and references

`ID-1` (T). Within a package, `id` MUST be unique within its record type: no two assets share an id, no two collections share an id, and so on. Compare strings exactly, with no case folding or trimming. A repeated id is rejected on every occurrence after the first.

`ID-2` (T). Ids of different record types are different namespaces. An asset and a collection may share the same string.

`ID-3` (T). Identity scope is the package. Two packages from the same `source.system` and `source.instance` that carry the same `source.id` SHOULD describe the same entity, but the standard does not require consumers to merge them. A consumer that merges records across packages does so under its own policy.

`ID-4` (S+T). These nested objects carry an `id` (S): versions, files, file groups, and annotations of an asset, and options of a metadata definition. Version ids are unique within the asset. File ids are unique among all files of the asset, in every holder: the asset level, each version, and `unassigned`. File group ids and annotation ids follow the same rule. Option ids are unique within their definition. A checker reports every repeat after the first, visiting the asset level, then each version in array order, then `unassigned` (T). One scope per asset lets a reader name any nested object by its asset and its own id.

`ID-5` (S+T). A reference is a string that names the `id` of a target of one stated type. It has the identifier syntax of `REC-5`, so an empty or whitespace-only reference is rejected (S). A reference never carries a copy of its target. Every reference resolves under `PKG-6` or under the nested-object rule that `PKG-6` names. A metadata value of `value_type` `asset_reference` or `collection_reference` is a reference, and so is an `enum` value item on a `fixed` list. The schema does not check their syntax, but a value that breaks it can never match an identifier, so `PKG-6` or `MD-4` rejects it (T). On an `open` list, an `enum` value item that matches no option `id` is text, not a reference, and `REC-5` does not apply to it.

## 6. Time

Timing has two forms. The frame form counts integer frames at a rational rate and uses SMPTE-compatible timecode labels. It does not claim SMPTE conformance. The seconds form measures elapsed seconds. Time applies to assets, versions, annotations, file group member part starts, and relationship ranges.

| Concept | Frame form | Seconds form |
| --- | --- | --- |
| How a timeline shows its form | `time_base` present | `time_base` absent, `duration_seconds` present |
| Length | `duration_frames` (optional); `duration_seconds` restates it | `duration_seconds` (required) |
| Marker positions | frames, seconds, or both | seconds only |
| Timecode labels on markers | allowed with frames | not allowed |
| Source timecode | `source_timecode` at the asset rate | `source_timecode` with its own `timecode_base` |
| Typical sources | video at a known constant rate | audio, variable-rate video, screen recordings, review tools that store milliseconds |

A holder with no `timing` may still carry seconds-only markers. No upper bound is checked for them.

`TIME-1` (S). A time base is an object `{rate, drop_frame}`. `rate` is `{numerator, denominator}`, both integers 1 or more. `drop_frame` is a boolean.

`TIME-2` (T). A rate is written in lowest terms. `24000/1001` is valid; `48000/2002` is rejected.

`TIME-3` (S+T). A position is given in frames, in seconds, or in both. Frame fields (`start_frame`, `end_frame`, `duration_frames`) are integers 0 or more at the timeline's time base. Frame 0 is the first presented frame. Seconds fields (`start_seconds`, `end_seconds`, `duration_seconds`) are numbers 0 or more that measure elapsed time from the start of the timeline. A checker reads seconds exactly as written, as decimals, with no binary rounding. Seconds values also meet the number limits of `DOC-4`. A value with 15 or fewer significant digits meets them when it is 0 or lies between `1e-307` and 2^53 - 1. Positions never count from a timecode.

`TIME-4` (S+T). Endpoints and the defining unit.

- When a marker has a frame field, its frames define it. `end_frame` without `start_frame` is rejected. Seconds and labels are allowed only for frame fields that are present.
- When a marker has no frame field, its seconds define it. `end_seconds` without `start_seconds` is rejected.
- In the defining unit, a range has an end greater than its start. A point has no end. An end equal to or less than the start is rejected.
- A range includes its start and excludes its end, in either unit.

`TIME-5` (S+T). There is no default rate. A frame field is allowed only on a timeline in the frame form. A frame field on a seconds-form timeline, or on a holder with no `timing`, is rejected. Seconds fields need no time base.

`TIME-6` (S). `drop_frame: true` is allowed only with rate `30000/1001` or `60000/1001`. Any other combination is rejected.

`TIME-7` (S+T). Restated values. When an endpoint or a length is given both in frames and in seconds, the frame value is exact and the seconds restate it. The seconds agree when the integer nearest to `seconds × numerator ÷ denominator` equals the frame value, with a tie at exactly one half rounding toward zero. This applies to `start_seconds`, `end_seconds`, and `duration_seconds`. Agreement means the seconds name the same frame, not that they equal the exact elapsed time. Checkers use exact rational arithmetic. A timecode label agrees when it equals the label derived from the frame value under `TIME-8`. Any disagreement is rejected. The restated length of a `timing` object is checked on every holder's `timing`, each version included.

Informative note: there is no fixed decimal count for seconds. Milliseconds always name the right frame at any rate below 1000 frames per second, because the rounding error is less than half a frame.

`TIME-8` (S+T). Timecode labels.

Syntax: `HH:MM:SS:FF` for non-drop and `HH:MM:SS;FF` for drop-frame, ASCII digits only, two digits per field. Hours are 00 to 23, minutes and seconds 00 to 59, frames 00 to one less than the count in the table. Subframes, field marks, and other SMPTE character forms are deliberately not supported.

Labels are allowed only at these rates. At any other rate, frames and seconds are allowed and labels MUST be absent.

| Rate | Frame field range | Drop-frame allowed |
| --- | --- | --- |
| `24/1`, `24000/1001` | 00 to 23 | no |
| `25/1` | 00 to 24 | no |
| `30/1` | 00 to 29 | no |
| `30000/1001` | 00 to 29 | yes |
| `48/1` | 00 to 47 | no |
| `50/1` | 00 to 49 | no |
| `60/1` | 00 to 59 | no |
| `60000/1001` | 00 to 59 | yes |

The 48, 50, and 60 counts use a full two-digit frame field. This is a label convention that converts to SMPTE ST 12-1 frame-pair addressing; it is not that addressing.

Drop-frame rule: at `30000/1001` frame labels 00 and 01, and at `60000/1001` labels 00 to 03, are skipped at the start of every minute except minutes 00, 10, 20, 30, 40, and 50. A label that names a skipped frame is rejected. Drop-frame skips labels, never media frames.

Anchor: a label derives from the `source_timecode` of the holder's timing (`TIME-11`) plus the frame offset, counted in labels under the drop-frame rule when it applies, modulo 24 hours. This anchor sentence also covers a seconds-form `source_timecode` at its `timecode_base` (`TIME-14`). Labels on markers are allowed only when the holder's timing declares `source_timecode`. Labels on markers also require a frame field, so they appear only on frame-form timelines. A checker derives the label from the frame value and compares; it never converts a label back to a frame, so a 24-hour rollover is never ambiguous.

`TIME-9` (T). Bounds.

- Frame positions, against `duration_frames` D: a point satisfies `0 ≤ start_frame ≤ D`. A range satisfies `0 ≤ start_frame < end_frame ≤ D`.
- Seconds positions, when the marker has no frame field, against the length in seconds S: a point satisfies `0 ≤ start_seconds ≤ S`. A range satisfies `0 ≤ start_seconds < end_seconds ≤ S`. In the seconds form, S is `duration_seconds`. In the frame form, S is `duration_frames × denominator ÷ numerator`, calculated exactly. The comparison is exact. `TIME-7` rounding applies only to a frame and seconds pair, never to a bound.
- A position equal to the length is the end boundary. It marks the point immediately after the last frame or sample, not another playable frame. A point may sit there. A range ends there at the latest.
- The length is the length of the holder's timeline for annotation positions and part starts, and of the target timeline under `TIME-12` for relationship ranges. Part starts must be strictly less than the length (`GRP-7`).
- Without a length, no upper bound is checked.
- Violations are rejected.

`TIME-10` (T). A variable-frame-rate asset uses the seconds form. It has no `time_base` and no frame fields. A nominal or average rate MAY go in extensions. A producer MUST NOT describe a variable-rate asset in the frame form, because its frame numbers do not map to elapsed time (not checkable; stated for producers).

`TIME-11` (S). `timing` is optional. It sits on the asset record of an asset with no versions, or on a version. An asset with versions has no asset-level `timing` (`VER-4`). `timing` has one of two forms.

- Frame form: `time_base` is present. `duration_frames` is the optional length in frames. `duration_seconds` is optional, is allowed only with `duration_frames`, and restates it under `TIME-7`. `source_timecode` is the optional label of frame 0 at the asset rate (`TIME-8`).
- Seconds form: `time_base` is absent. `duration_seconds` is the required length in elapsed seconds. `duration_frames` is absent. `source_timecode` is optional and requires `timecode_base`, and `timecode_base` is allowed only with `source_timecode` (`TIME-14`).

The length covers the whole timeline. In the frame form, `duration_frames` is the frame count of the picture as the source reports it. One anchor assumes continuous timecode through the timeline. Material with timecode discontinuities omits `source_timecode`. Either form MAY also carry `sample_rate` and `duration_samples` (`TIME-13`).

`TIME-12` (T). Timeline ownership. A `timing` object defines one timeline: that of the asset when it has no versions, or that of the version that holds it. Annotation positions and member part starts are on the timeline of their holder. The asset level of an asset with versions and `unassigned` have no timeline, so they hold no annotation position and no part start (`VER-4`, `VER-5`). A relationship `range` is on the timeline of the target version that `target_version` names, or of the target asset when it has no versions (`REL-6`). A range with frame fields needs that timeline in the frame form; otherwise it is rejected. A range in seconds only needs no timing; when that timeline has a length, `TIME-9` applies. `sequence` and `sequence_frame` number file names. They are not a timeline.

`TIME-13` (S+T). A timeline MAY declare `sample_rate`, an integer 1 or more, in samples per second. A marker MAY restate a seconds field as a sample position: `start_sample` restates `start_seconds` and `end_sample` restates `end_seconds`. Each requires its seconds field (S) and a timeline `sample_rate` (T). `duration_samples` restates `duration_seconds` and requires it and `sample_rate` (S). A seconds value agrees with a sample position when the integer nearest to `seconds × sample_rate` equals it, with a tie at exactly one half rounding toward zero. When a range carries both sample fields, `start_sample` MUST be less than `end_sample`. A sample position MUST NOT exceed `duration_samples` when both are present, and a range's `start_sample` MUST be less than it. A sample is not a frame: a sample position never names a frame, and `sample_rate` is never a time base. `sample_rate` and `duration_samples` are fields of the holder's `timing`. They are checked on every holder's `timing`, each version included. Sample positions on an annotation restate seconds on the holder's timeline.

`TIME-14` (S+T). In the seconds form, `source_timecode` is the label of the timecode frame that contains the start of the holder's timeline, counted at `timecode_base`. `timecode_base` follows `TIME-1` and `TIME-6`, and its rate MUST be in the `TIME-8` table. Markers on a seconds-form timeline carry no timecode labels. The anchor creates no frame positions on the timeline. `timecode_base` and a seconds-form `source_timecode` are fields of the holder's `timing`.

## 7. Assets

`AST-1` (S). An asset has, in addition to the record fields of section 3:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `title` | nonempty string | yes | Human name. Not an identifier. |
| `category` | string | no | Producer's classification token. Neutral, free form. |
| `description` | string | no | Free text. |
| `status` | string | no | Producer's lifecycle token. Free form. |
| `created` | date-time | no | Creation in the source system. |
| `modified` | date-time | no | Last modification in the source system. |
| `deleted` | date-time | no | When the source deleted the asset. `AST-3`. |
| `timing` | object | no | Section 6, `TIME-11`. Only when the asset has no versions (`VER-4`). |
| `versions` | array | no | Section 9, `VER-1`. |
| `current_version` | reference | no | `VER-6`. |
| `unassigned` | object | no | `VER-5`. |
| `files` | array | no | Section 8. With versions, files about the whole asset (`VER-4`). |
| `file_groups` | array | no | Section 8. With versions, file groups about the whole asset, with no part start (`VER-4`). |
| `relationships` | array | no | Section 9. With versions, no `subclip_of`. |
| `metadata` | array | no | Section 11. With versions, values about the whole asset (`VER-7`). |
| `annotations` | array | no | Section 12. With versions, only annotations without a position field. |
| `member_of` | array of membership entries | no | `COL-3`. |
| `access` | object | no | Section 13, `ACC-1`. |

`AST-2` (S). `title` with only whitespace is rejected.

`AST-3` (T). `deleted` states that the source reported the asset deleted at that date-time, whether or not the source can still restore it. Absence makes no deletion statement. A producer writes `deleted` only when the source states a deletion. It never infers one from a missing record or an unavailable file. A deleted asset is a full record, and every other rule applies to it. `deleted` is a fact about the source. It is not an instruction to delete, hide, or purge a record or media in a receiving system (`PKG-9`). `status` stays a free producer token with no deletion meaning in the core.

## 8. Files, storage, file groups, and tracks

Files are the recorded content of an asset. A file object describes its content once and lists its stored copies in `locations`. Each copy names a storage location by reference and a path inside it. File groups state which files belong together. Their members select the tracks and streams of those files and describe them.

`FILE-1` (S). A file object has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | id | yes | Unique within the asset (`ID-4`). |
| `locations` | array of location entries | no | The stored copies that the source reports (`FILE-6`). Absent or empty: no known copy. |
| `size_bytes` | integer 0 or more (`DOC-4` sets the upper limit) | no | Size of the content in bytes. It holds for every copy. |
| `checksum` | object `{algorithm, value}` | no | `FILE-3`. It holds for every copy. |
| `media_type` | string | no | IANA media type, when known. The schema checks the `type/subtype` syntax of RFC 6838, not registration. |
| `created`, `modified` | date-time | no | Dates of the content as the source states them. Dates of one copy go in extensions on its location entry. |
| `role` | token | no | `master`, `mezzanine`, `preview`, `thumbnail`, `sidecar`, `other`. `FILE-5`. |
| `label` | string | no | Short human name. |
| `reel_name` | nonempty string | no | `FILE-9`. |
| `duration_seconds`, `bit_rate` | seconds; integer 0 or more, bits per second | no | `FILE-7`. |
| `sequence` | object | no | `FILE-8`. |
| `extensions` | object | no | Section 13. |

`FILE-3` (S). `checksum.algorithm` is one of `md5`, `sha1`, `sha256`, `sha512`, `blake3`. `checksum.value` is lowercase hexadecimal of the length the algorithm produces: 32, 40, 64, 128, 64 characters respectively. One checksum describes the bytes of every copy. A file with `sequence` has no checksum (`FILE-8`).

`FILE-4` (T). Validation never computes the checksum of a file that a file object describes. A declared checksum is a claim by the producer. The SHA-256 digest of a member file of a multi-file package is not a file checksum under this rule: validation computes it (`MFP-3`).

`FILE-5` (T). File roles: `master` is an original recording, or a finished master rendition, at any quality. `mezzanine` is a high-quality intermediate made for further work or delivery. `preview` is a lower-quality copy for viewing. `thumbnail` is a still image representation. `sidecar` is a data file that accompanies media, such as captions or a metadata file. `other` is anything else. A role never ranks files. Several files of one holder MAY have the role `master`. A copy of a file is a location of that file, not another file (`FILE-6`). A file role describes the file on its own. It does not group files; file group membership does that (`GRP-5`). A file's role and the role of a file group that contains it are not required to match.

`FILE-6` (S+T). Copies.

- `locations` lists the stored copies of the file that the source reports, one entry per copy. It is optional and may be empty (S). An absent and an empty `locations` both mean that no copy is known. The file record still states its content: an archive may keep the record of a file whose copies are lost, because its size, checksum, and technical facts still matter.
- A producer lists only the copies that the source reports. It omits a copy that the source reports missing, such as a file that the source marks missing, and MAY keep that source record in extensions on the file. It never invents a copy (not checkable).
- An entry has `storage_location`, a reference to a storage location record (`PKG-6`), and `path`, a nonempty string, the locator of the copy inside that storage location (`STO-3`). It MAY have `availability`, `missing_frames` (`FILE-8`), and `extensions`.
- Several entries are the source's claim that the copies hold identical bytes. `size_bytes`, `checksum`, `media_type`, and the technical fields describe every copy. The claim needs no checksum.
- A producer writes several entries in one file only when the source holds them as copies of one file, for example copies that the source made, archived, transferred, or restored. It MUST NOT combine files because their names, sizes, or dates match. When the source states different sizes or checksums for two copies, they are two files (not checkable).
- A copy is not a rendition and not a version. Another copy never adds a file group or a version (`GRP-2`).
- In one file, each storage location appears in at most one location entry (T; reported at the `storage_location` of each repeat after the first). Two copies on one storage system are described with two storage location records, for example one record for each top folder. A copy is named by its file `id` and its `storage_location`, so a copy needs no id of its own.
- `availability` states how the source reports the copy when the package is produced. `online`: readable now, with no retrieval step. `nearline`: stored, and the storage system makes it readable on request through a retrieval step, such as an archive restore or a tape library load. `offline`: stored on media that a person must load or bring back, such as a tape on a shelf. Absent: unknown. A producer writes it only from source data or a documented dialect policy (not checkable). `availability` is not a deletion statement (`AST-3`) and not a completeness statement.
- Validation never opens a location and never tests availability (`SAFE-1`).

Informative note: two file entries that name the same storage location and the same path describe one stored file. A reader that totals storage, or removes stored files, counts that file once and keeps it while any entry still names it.

`FILE-7` (S+T). Technical fields. The file fields are `duration_seconds` and `bit_rate`. The member fields are in `GRP-11`. For all of them:

- They are optional, and they describe the content of every copy (`FILE-6`).
- A producer writes a technical field only when the source reports the value, or when the producer reads it from the media. It never writes a value guessed from a name, an extension, a role, or another field. It splits a combined description string into fields only when the source documents that string exactly. Other technical facts MAY go in extensions (not checkable).
- A missing technical field never makes a package invalid. Validation checks the declared structure and the internal consistency of the values: types, lowest terms (`TIME-2`), the channel count against the layout, and agreement between members that describe one stream (`GRP-11`). It never checks a value against the media and never reads media (`SAFE-1`).
- Every value meets `DOC-4`. A file larger than 2^53 - 1 bytes has no `size_bytes`; the producer MAY keep the size as a string in extensions.
- No technical field is compared with a timeline. `TIME-11` makes `duration_frames` the picture frame count that the source reports for the whole timeline. A producer MAY take it from the `frame_count` of the primary video member only when that member covers the whole picture timeline. A member that is one part of a split recording (it carries `segment_index`) covers only its part, so its `frame_count` is never the timeline length. The producer then uses a whole-picture frame count that the source supplies, or calculates the nearest frame count from a known whole-picture duration in seconds and the rate (`TIME-7`), and omits `duration_frames` only when neither is available. No rule compares the two.

`FILE-8` (S+T). Compact image sequences.

- `sequence` is an object with `first_frame` and `last_frame` (integers), `step` (integer 1 or more), `padding` (integer 1 or more), and optional `images`. An item of `images` has `frame` (required, integer), `size_bytes` (integer 0 or more), and `checksum`, and gives at least one of the last two.
- A file with `sequence` stands for a numbered series of image files. The expected numbers are `first_frame`, `first_frame + step`, and so on, to `last_frame`. Both ends are included. Numbers may be zero or negative. One image is allowed. Exactly: when `last_frame` is not less than `first_frame`, an integer n is an expected number when `first_frame <= n <= last_frame` and `(n - first_frame) % step == 0`. This test also applies when the step check below fails. When `last_frame` is less than `first_frame`, no number is expected.
- `last_frame` MUST NOT be less than `first_frame` (T; reported at `sequence/last_frame`). `last_frame - first_frame` MUST be a multiple of `step` (T; reported at `sequence/step`).
- Frame numbers name images. They are not timeline positions (`TIME-12`). A sequence that starts at image 1001 can start playback at time zero.
- Each `path` of the file holds the text `{frame}` exactly once (T; reported at that path). All other text is literal. The name of image n is the path with `{frame}` replaced by n in decimal. A negative number starts with a minus sign. The digits of the absolute value follow, with leading zeros to at least `padding` digits. The sign does not count toward `padding`. A number never loses digits. With `padding` 4: 7 gives `0007`, -5 gives `-0005`, and 12345 gives `12345`.
- In a file without `sequence`, `{frame}` is plain text. A name that holds the text `{frame}` uses the explicit form (`GRP-12`).
- `step` is the regular spacing of the numbers, such as 2 when every second frame was rendered. A number that the step skips is not missing.
- A file with `sequence` has no `size_bytes` and no `checksum` (S). Its `media_type` and the technical fields of its member describe each image. `sequence.images` MAY give the `size_bytes` or `checksum` of single images. Each entry describes one image only. No value covers the whole sequence. Each `frame` there is an expected number (T) and appears once (T).
- `missing_frames` on a location entry lists the expected numbers whose images that copy lacks, as the source checked it. `[]` states that the source checked the copy and found none missing. Absent states that the copy was not checked. Each number is an expected number (T) and appears once (S). One copy's list says nothing about another copy. `missing_frames` appears only on copies of a file with `sequence` (S). A producer writes it only when the source reports a check of that copy (not checkable).
- A pattern describes expected names. It does not claim that anyone opened the storage location. Validation never lists a location (`SAFE-1`).

`FILE-9` (S). Camera reel name.

- `reel_name` names the camera roll, card, magazine, or source tape on which the content of the file was first recorded, as the source states it. It is a nonempty string (S). Its text is kept as the source states it.
- It is a fact of the recording, not of storage. It is not a storage location, a copy, or a path (`FILE-6`, `STO-3`). The barcode of an archive tape is never a `reel_name`. A producer never makes a storage location from a reel name (not checkable).
- A producer writes it only when the source states it for that file, or when the producer reads it from the file's own metadata. It never derives a reel name from a file or folder name, or from another file (not checkable).
- It is not an identifier. `REC-5` does not apply, and many files can have one reel name.
- It sits on the file, because a reel is a fact of the recording medium of the whole file. One asset can mix reels, such as a picture card and a sound roll, so the asset has no reel name. The segments of one split recording each carry the reel name that the source states for them.
- A file has at most one reel name. When the source links a file to several reels, such as a conformed master, the producer writes no `reel_name` and MAY keep the list in extensions (not checkable).

`STO-1` (S). A storage location record has: `id` (`REC-5`), `name` (nonempty string, required), `system` (required, `STO-3`), `root` (string, `STO-3`), `description` (string), `status` (the producer's token for the storage itself, free form), `created` and `modified` (date-time), `source`, and `extensions`.

`STO-2` (T, not checkable). A storage location record describes where copies are stored. It has no connection settings and no credential fields. A producer MUST NOT write a secret, a credential, an access token, or a signed or temporary URL in any field of a package, including `root`, `path`, `description`, and extensions. Authentication, mounting, connection settings, retrieval, and local path mapping belong to the receiving application. Missing connection details never block an exchange. Validation never connects (`SAFE-1`).

`STO-3` (S+T). Storage types and locators.

| `system` | One storage location record is | `root` | `path` | Informative full form |
| --- | --- | --- | --- | --- |
| `source_local` | A place that only the source system can resolve: a drive letter, a mount point, or a source alias. No server or protocol is known. | Optional. The start of the source path, as the source writes it, such as `Z:\`, `/Volumes/volume_a/`, `/mnt/share_a/`, or `[alias_a]`. | The rest of the source path. Without `root`, the whole source path. | `root` followed by `path`, with nothing between them, is the source path exactly. |
| `network_share` | A file share that a server name identifies, through SMB or NFS. | Required. The share as the source writes it, such as `\\server_a\share_a\` or `server_a:/export/share_a/`. | The rest of the path. | `root` followed by `path`. |
| `s3` | One bucket of Amazon S3 or of a service with the S3 interface. Storage classes are in the bucket. | Required. The bucket name only, with no `/`. | The full object key, exactly. No leading `/` is added. | `s3://<root>/<path>` |
| `gcs` | One Google Cloud Storage bucket. | Required. The bucket name only, with no `/`. | The full object name. | `gs://<root>/<path>` |
| `azure_blob` | One Azure Blob Storage container. | Required. `<account>/<container>`. | The full blob name. | `https://<account>.blob.core.windows.net/<container>/<path>` |
| `tape` | One tape cartridge. | Required. The barcode. | The locator on the tape as the source records it, such as an LTFS path or an archive object name. | No standard form. |
| `other` | Any other storage. | Optional, opaque. | Opaque. | None in this draft. |

- `system` is one of the values in the table (S). The table states what one record is, what `root` and `path` hold, and how they join. `root` is required and nonempty for `network_share`, `s3`, `gcs`, `azure_blob`, and `tape` (S). For `s3` and `gcs`, `root` holds no `/`. For `azure_blob`, it is two parts with one `/` (S).
- One record describes one place. Two places on one storage system are two records (`FILE-6`).
- `root` and `path` are the source's text. A producer splits the source path where `root` ends. It does not change separators, letter case, Unicode form, or percent-encoding (not checkable). A dialect policy MAY decode a documented storage form of its source, such as a `<bucket>:<prefix>` form of an S3 root, with or without a trailing `/`. Validators never normalize a path (`DOC-3`).
- A path is not a URI. The full forms in the table are informative.
- A collection `storage.path` (`COL-1`) names a folder or a key prefix in the same way as a file `path`. An empty `storage.path` names the root itself.
- For `other`, this draft defines no meaning for `root` and `path`. A producer MAY state the source's own storage type in extensions.
- No `root` or `path` holds a credential or a signed URL (`STO-2`).

`GRP-1` (S). A file group object has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Unique within the asset (`ID-4`). |
| `role` | token | yes | `primary`, `preview`, `thumbnail`, `companion`, `other`. |
| `label` | string | no | Short human name for the file group. |
| `members` | array of member objects | yes, 1 or more | `GRP-3`. |
| `extensions` | object | no | |

`GRP-2` (T). File group roles: `primary` is a rendition of the content itself, at any quality, such as a camera original, a UHD master, or an HD master. `preview` is a lower-quality rendition for viewing; it shares the timeline of its version (`GRP-8`). `thumbnail` is a still image representation. `companion` is data that accompanies the content, such as captions, sidecar metadata, or a transcript file. `other` is anything else. Role describes purpose, not format. A holder MAY hold any number of file groups with one role, such as a UHD primary group and an HD primary group. Quality does not decide the role. No group is preferred, and OASIS chooses none for a reader. A different encoding, size, or quality is a rendition of the same version, not a new version. Identical copies of one file at several storage locations are one file (`FILE-6`), not renditions.

`GRP-3` (S). A member object has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `file` | reference | yes | A file in the same holder as the file group (`GRP-4`). |
| `track_type` | token | yes | `video`, `audio`, `image`, `data`, `other`. |
| `track_index` | integer 0 or more | yes | Numbers the group's tracks of one type (`GRP-10`). |
| `stream_index` | integer 0 or more | no | The stream inside the file (`GRP-10`). |
| `segment_index` | integer 0 or more | no | The part of a split recording (`GRP-6`). |
| `start_frame`, `start_seconds` | integer; number | no | The part start (`GRP-7`). Allowed only with `segment_index`. |
| `sequence_frame` | integer | no | The image number in an explicit sequence (`GRP-12`). Allowed only on `image` members, never with `segment_index`. |
| `label`, `language`, and the technical fields | | no | `GRP-11`, on the track types it allows. |
| `channel_count`, `channel_layout` | | no | `GRP-11`. Allowed only on `audio` members. |
| `extensions` | object | no | Section 13. |

`GRP-4` (T). Within one file group, `(track_type, track_index)` pairs MUST be unique, except that a pair repeats for the segments of one recording (`GRP-6`) or the images of one explicit sequence (`GRP-12`). Member order is the presentation order. A `file` reference MUST resolve to a file in the same holder as the file group. A group cannot name a file of another version, or a version file from the asset level. A file group in `unassigned` uses files in `unassigned` only.

`GRP-5` (T). A file MAY belong to several file groups or to none. File group membership, not file order or any token on the file, defines which files belong together. There is no implicit grouping.

`GRP-6` (T). Spanned recordings. When one recording is split across several files, each file is a member with the same `(track_type, track_index)` pair and its own `segment_index`. Within one file group, every member that shares a pair with another member carries `segment_index` or `sequence_frame` (`GRP-12`). `segment_index` values within a pair are unique and appear in ascending order in `members`. Numbering belongs to the original recording and starts at 0. Exported parts keep their original numbers, so a gap shows that the parts with the skipped numbers are not in the group. No gap does not show that the group holds every part: a last part can be absent with no gap. A single member MAY carry `segment_index` when it is one part of a larger recording. `segment_index` gives order only; `GRP-7` part starts are the only placement data. A member with no `segment_index` is a whole recording.

`GRP-7` (S+T). Part starts. A member with `segment_index` MAY give the position where its part starts on the holder's timeline, as `start_frame`, `start_seconds`, or both. A member without `segment_index` is a whole recording and has no start field (S). Members of file groups in `unassigned`, and at the asset level of an asset with versions, carry no start (S, `VER-4`, `VER-5`). The fields follow `TIME-3`, `TIME-5`, and `TIME-7`: a frame start needs frame-form timing on the holder (T), and seconds restate a frame start when both are present. Within one `(track_type, track_index)` pair, the starts that are present MUST increase strictly with `segment_index`. A member's start time is `start_frame × denominator ÷ numerator` when `start_frame` is present, else `start_seconds`, compared exactly. The check runs in `segment_index` order, and only for a pair that passes `GRP-6` and `GRP-12`. A start MUST be less than the timeline length when the length is known, compared exactly as in `TIME-9`. A start is never inferred from order alone. A producer MAY calculate starts from supplied part lengths. A start says nothing about where its part ends. Separate recordings in an ordered collection are not segments of one recording.

`GRP-8` (T). A file group with role `preview` represents the same content and the same timeline as the primary content of its version. A different encoding, size, or quality does not create a different timeline. Positions on the version timeline apply to the preview unchanged. A rendition that holds only part of the content, a trimmed preview, is not a `preview` group. A producer describes the excerpt as a separate asset with `subclip_of` (`REL-2`), or keeps the rendition with role `other` and records its mapping in an extension. A consumer never assumes that a position on the master is the same position in a trimmed rendition. OASIS does not say how a consumer shows markers on a preview (not checkable). This rule applies to a `preview` group in a version, and at the asset level of an asset with no versions. It does not apply to a group at the asset level of an asset with versions, which has no timeline. A `preview` group in `unassigned` belongs to a version that the source does not name, so a reader cannot apply any version's positions to it.

`GRP-9` (T, not checkable). Presence at a storage location. For one member file and one storage location, the file is in one of three states:

- Full: the file lists a copy there, and that copy lists no missing image. A copy that was not checked (`missing_frames` absent) counts as full, as the source claims it.
- Partly populated: the copy there is a copy of a sequence file (`FILE-8`) that lists some, but not all, of the expected numbers as missing.
- None: the file lists no copy there, or the copy there lists every expected number as missing and so holds no image of the sequence.

A file group is present at a storage location when every member file is full there. It is partly present there when it is not present, and at least one member file is full or partly populated there. Otherwise the group is not at that storage location. A group with a member whose file has no known copy (`FILE-6`) is present at no storage location. It can still be partly present where other member files are full or partly populated. No record states group copies. A group spread over several tapes is partly present on each tape. A reader combines tape locations to judge archive coverage. A reader MUST NOT treat a group as present at a storage location where a member file is partly populated or has no copy. Presence says nothing about `availability`, and nothing about whether the group holds every part of a recording.

`GRP-10` (S+T). Stream selection.

- `stream_index` selects one stream inside the member's file. It is the position of the stream in the container's own list of streams, counting from 0 and counting streams of every type, including data and timecode streams. A file with one stream, such as a WAV file or an OP-Atom MXF file, has stream 0.
- Media inspection tools report this position as the stream index or the stream order. A track ID in an ISO base media file (ISO/IEC 14496-12), such as an MP4 file, or in a file with the same track structure, is an identifier, not a position. Track IDs need not be consecutive, and a writer can assign them freely. A producer never uses a track ID as `stream_index`.
- `track_index` numbers the group's tracks of one type. `stream_index` locates the stream in the file. Neither is derived from the other.
- Absent means that the source does not state the stream. A producer writes `stream_index` only from the source's stream order. It never infers it from `track_index`, from member order, or from a file name (not checkable).
- In one file group, two members that name the same file MUST NOT name the same `stream_index` (T; reported at the later member's `stream_index`).

`GRP-11` (S+T). Track descriptions. A member MAY describe the stream that it selects with these fields. Each field is allowed only on the track types shown (S).

| Field | Track types | Type and unit | Meaning |
| --- | --- | --- | --- |
| `label` | all | string | Readable name of the track, such as "French dialogue". |
| `language` | all | language tag | Spoken or written language of the track. |
| `codec` | all | nonempty string | Name of the coding format as the source reports it. One name, never a combined description. |
| `bit_rate` | all | integer 0 or more, bits per second | Average bit rate of the stream. |
| `duration_seconds` | all | seconds | Duration of the stream. |
| `width`, `height` | `video`, `image` | integer 1 or more, pixels | Size of the decoded picture, before any aspect ratio correction. |
| `display_aspect_ratio` | `video`, `image` | ratio `{numerator, denominator}` of two positive integers | Shape of the displayed picture, width to height. |
| `bit_depth` | `video`, `image`, `audio` | integer 1 or more, bits | Bits per sample: per color component for a picture, per sample for audio. |
| `frame_rate` | `video` | rate, lowest terms | Constant playback frame rate. Absent for a variable-rate stream (`TIME-10`). |
| `capture_frame_rate` | `video` | rate, lowest terms | The constant rate at which the camera captured the frames of the stream. |
| `frame_count` | `video` | integer 0 or more | Number of frames in the stream. |
| `scan_type` | `video` | `progressive`, `interlaced` | Picture scanning. |
| `sample_rate` | `audio` | integer 1 or more, samples per second | Audio sample rate. Same name and unit as the timing `sample_rate` (`TIME-13`). |
| `channel_count` | `audio` | integer 1 or more | Number of channels in the stream. |
| `channel_layout` | `audio` | array of channel names, 1 or more | The position of each channel, in channel order. |

Track description:

- These fields describe the track that the member selects. Absent means unknown. A producer never infers a language, a layout, or a stream from a track number, member order, or a file name (not checkable).
- When both `channel_count` and `channel_layout` are present, `channel_layout` has `channel_count` entries (T; reported at `channel_layout`).
- One stereo stream is one member with two channels. Two mono streams are two members with one channel each.
- One stream, one description. In one holder, members that name the same file and the same `stream_index` describe one stream, even in different file groups. They MUST have the same `track_type`. They MUST also have the same value for each `GRP-11` field that both carry, except `label` (T). The checker reports it at the field of the later member, and visits groups and members in array order. `label` may differ between groups. The check runs per holder, because a group names files of its own holder only (`GRP-4`).

Language: `language` is a BCP 47 tag, well-formed under RFC 5646 section 2.1. Subtag registration is not checked (S). The tag `und` (undetermined), in any letter case, is rejected (S): BCP 47 compares tags without case, and absence already states that the language is unknown. A producer writes no `language` when the source gives `und`. A longer tag that starts with `und`, such as `und-Latn`, states a fact and is allowed. This rule applies to member `language` only; annotation `language` follows `ANN-1`. `zxx` states that the track has no language content, such as music or effects. `mul` states several languages. A producer SHOULD write the registered form, such as `fr` for ISO 639-2 `fre` or `fra` (not checkable).

Channel layout: `channel_layout` lists the position of each channel of the stream, in channel order, from this list (S). When the source does not give the position of every channel in this list, the producer writes no `channel_layout` and MAY keep the source labels in extensions (not checkable). It never infers a layout from the channel count.

| Name | Position | Common short label |
| --- | --- | --- |
| `mono` | One channel meant for no particular speaker | M |
| `left`, `right` | Front left, front right | L, R |
| `center` | Front center | C |
| `lfe` | Low-frequency effects | LFE |
| `left_surround`, `right_surround` | Surrounds of a 5.1 layout | Ls, Rs |
| `left_side_surround`, `right_side_surround` | Side surrounds of a 7.1 layout | Lss, Rss |
| `left_rear_surround`, `right_rear_surround` | Rear surrounds of a 7.1 layout | Lrs, Rrs |
| `left_center`, `right_center` | Between front left or right and center | Lc, Rc |
| `center_surround` | Rear center | Cs |
| `left_total`, `right_total` | A matrix-encoded stereo pair | Lt, Rt |
| `left_top_front`, `right_top_front` | Upper front left and right | Ltf, Rtf |
| `left_top_rear`, `right_top_rear` | Upper rear left and right | Ltr, Rtr |

Technical fields: `FILE-7` applies to every technical field. `frame_rate` and `capture_frame_rate` are in lowest terms (`TIME-2`; reported at that field). A variable-rate stream has no `frame_rate`; its nominal rate MAY go in extensions (`TIME-10`). `display_aspect_ratio` has no lowest-terms rule. `bit_rate` and `duration_seconds` on a member describe that stream; on the file they describe the whole file.

Capture frame rate:

- `frame_rate` stays the playback rate. `capture_frame_rate` MAY be equal to it, above it, or below it, and no rule compares the two. It never sets a time base, a timeline, a timecode, a duration, or a position. Only `frame_rate` and `timing` do that.
- A producer writes it only when the source reports the capture rate, or when the producer reads it from the media. It never derives it from the playback rate, a name, a project setting, or a slow motion label. Absent means unknown, not "the same as the playback rate" (not checkable).
- A capture rate that varies during the recording, such as a speed ramp, gives no `capture_frame_rate`. Its values MAY go in extensions, as for `TIME-10`.
- A decimal source value, such as a decimal capture rate or a rate in thousandths of a frame per second, maps to an exact rate only by a documented dialect policy, as for `frame_rate`. Without a policy, the value goes in extensions. The policy also settles two source fields that disagree for one recording, such as a decimal value and a rational value.

`GRP-12` (S+T). Explicit image sequences. Each image is its own file, with its own locations, size, and checksum. Each image is a member with `track_type` `image`, one shared `track_index`, and `sequence_frame`, the number of the image. `sequence_frame` is allowed only on `image` members and never with `segment_index` (S). When one member of an `(image, track_index)` pair in a group carries `sequence_frame`, three rules apply to the pair. Every member carries it (T). The values are unique (T). The members appear in ascending order (T). A pair holds either segments or sequence images, never both (T). A member with `sequence_frame` names one image, so its file has no `sequence` (T; reported at the member's `sequence_frame`). Gaps in the numbers are allowed. The explicit form states which images the group lists, not why others are absent.

## 9. Versions and relationships

`VER-1` (S). `versions` is an optional array of version objects. An absent and an empty `versions` mean the same: the asset has one implied original version (`VER-4`). `DOC-3` still keeps the written form. A version object has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | id | yes | Unique within the asset (`ID-4`). |
| `ordinal` | integer 0 or more | yes | Order in the source (`VER-2`). |
| `label` | string | no | The source's name for the version. |
| `created`, `modified` | date-time | no | |
| `timing` | object | no | The version timeline (`TIME-11`, `TIME-12`). |
| `files`, `file_groups` | arrays | no | Section 8. |
| `metadata` | array | no | Section 11. |
| `annotations` | array | no | Section 12. |
| `relationships` | array | no | Section 9. |
| `extensions` | object | no | Section 13. |

A version carries no `member_of`, `access`, or `deleted`. Those are facts about the asset record.

`VER-2` (T). Version order. `ordinal` gives the order of the versions in the source, lowest first, such as the order in which the source made them. Ordinals MUST be unique within the asset. They need not start at 0 or be consecutive. Array order carries no meaning (`PKG-8`). `ordinal` never selects the current version (`VER-6`). Each source version appears once. When the source lists one version more than once, the producer writes one version object and MAY keep the other listings in extensions on it. A repeated version id is rejected under `ID-4`.

`VER-4` (S). Placement.

- An asset with no versions has one implied original version. Everything at its asset level belongs to that version. The implied version has no id, so no reference can name it. `current_version` and `unassigned` are absent (S).
- An asset with versions places each item with its owner. A version holds what belongs to it: `timing`, `files`, `file_groups`, `metadata`, `annotations`, and `relationships`. The asset level holds what is about the asset as a whole: the record fields, `member_of`, `access`, `files`, `file_groups`, `metadata`, `annotations` without a position field, and `relationships` other than `subclip_of`. `unassigned` holds what belongs to a version that the source does not name (`VER-5`).
- With versions, the asset level has no timeline. It holds no `timing`, no annotation with a position field, no file group member with a part start, and no `subclip_of` relationship (S). `GRP-8` does not apply to its file groups. A position, a part start, and a `subclip_of` need one timeline, and only a version has one when versions exist.
- The holder of an item states its version. No item carries a version field.
- A producer places each item where the source puts it. It MUST NOT assign an item to a version that the source does not name. It MUST NOT copy an item into a version where the source does not hold it. With versions, it writes a file or file group at asset level only when the source holds it for the whole asset. A file of a version that the source does not name goes in `unassigned`. The source may have copied items, such as markers copied to a new version. The producer then writes each copy in its version. It does not check that a copied position still fits the content (not checkable).
- OASIS defines no inheritance between the asset level and a version. One metadata field sits at one level only (`VER-7`). A reader MUST NOT read `unassigned` information as belonging to the current version or to every version (not checkable).

`VER-5` (S+T). Unassigned information.

- `unassigned` is an optional object on an asset with versions, whatever the number of versions (S). It holds information that the source holds for one of the asset's versions without naming which. It is not a version. It has no id and no `extensions`, and no reference names it.
- It MAY hold `files`, `file_groups`, `metadata`, `annotations`, and `relationships`. It holds no `timing` (S).
- It has no timeline. Its annotations carry no position field, its file group members carry no part start (`GRP-7`), and its relationships are not `subclip_of` (S).
- A file group in `unassigned` uses files in `unassigned` only (`GRP-4`).
- A reader MUST NOT read `unassigned` information as belonging to the current version, to every version, or to any one version, even when the asset has only one version (not checkable).
- A producer writes an item in `unassigned` only when the source does not name its version. When such an item has a time position, the producer omits the position fields, MAY keep the source values in extensions, and writes the item in `unassigned`. A `subclip_of` of unknown version MAY be kept in extensions only (not checkable).
- An empty `unassigned` object states nothing.

`VER-6` (S+T). Current version. `current_version` is an optional reference on an asset with versions (S). It names the version that the source treats as current. It MUST resolve to a version id in the same asset (T). That version need not have the greatest `ordinal` or the latest date. A producer writes `current_version` only when the source, or a documented dialect policy for it, states which version is current. When it is absent, the current version is unknown. A reader MUST NOT select a current version from `ordinal`, array order, or dates (not checkable).

`VER-7` (T). One level per metadata field. On an asset with versions, a metadata definition used in the asset-level `metadata` MUST NOT also be used in the `metadata` of any version or of `unassigned`. A checker reports each version or `unassigned` entry whose `definition` the asset level also uses, at that entry's `definition`. Definition ids compare exactly, whether or not they resolve. One definition MAY be used in several versions, and in versions and `unassigned` together: each such value belongs to one version. Metadata on annotations is not part of this rule. An asset with no versions has only one metadata holder, so the rule has nothing to compare.

`REL-1` (S+T). `relationships` is an array of objects with `type` (`derived_from`, `subclip_of`, `variant_of`), `target` (reference to an asset id), optional `target_version` (reference to a version id of the target asset, `REL-6`), optional `range`, optional `description`, and optional `extensions`. A `relationships` list sits at the asset level, in a version, or in `unassigned` (`VER-4`, `VER-5`). `range` is a time range on the target timeline (`TIME-12`), with `start_frame` and `end_frame`, or `start_seconds` and `end_seconds`. With the frame pair, either seconds field MAY also be present (`TIME-4`). It always has an end. Frames, when present, define it, and seconds restate them. Without frames, seconds define it. `TIME-4`, `TIME-7`, and `TIME-9` apply.

`REL-2` (S+T). `derived_from`: this asset was produced from the target. `subclip_of`: this asset is a time range of the target, an excerpt at unchanged speed (`REL-4`); `range` is required. `variant_of`: this asset is an alternative presentation of the target with the same content. These three types are the complete list for this draft. Edit sequences, timelines, and transitions are out of scope.

`REL-3` (T). `target` resolves under `PKG-6`. A target that is not in the package is rejected. A self-reference is rejected. Cycles are not checked in this draft.

Informative note: a relationship whose `target` is its own asset is rejected from any holder. A link between two versions of one asset, such as "version 2 was made from version 1", is not a relationship in this draft. A producer MAY keep it in extensions.

`REL-4` (T). A `subclip_of` child is an excerpt at unchanged speed. Its length agrees with its range:

- Range length: `(end_frame - start_frame) × denominator ÷ numerator` at the target rate when the range has frames, else `end_seconds - start_seconds`.
- Child length: `duration_frames × denominator ÷ numerator` at the child rate in the frame form, or `duration_seconds` in the seconds form.
- Allowance: one frame duration of the slowest frame-form timeline among the target and the child. The allowance is 0 when neither is in the frame form.
- The lengths agree when they differ by less than the allowance, or are equal when the allowance is 0. Otherwise the package is rejected.
- The child length MUST be greater than 0.

The child length is the length of the holder's timeline: the version that holds the `subclip_of`, or the child asset when it has no versions. The range length uses the timeline of the target version that `target_version` names, or of the target asset when it has no versions (`REL-6`). When the holder states no length, this check does not apply. `VER-4` and `VER-5` keep a `subclip_of` in a version whenever the child has versions, so the holder always has at most one timeline.

All arithmetic is exact. The effects:

- Both in frames at one rate: the frame counts are equal.
- Frames against seconds: the lengths differ by less than one frame. A range whose two ends were rounded to frames separately can be up to one frame off its length in seconds, so half a frame is not enough. At `30000/1001`, 10 to 20 seconds rounds to frames 300 and 599, which is 299 frames or 9.9766... seconds. A 10-second child differs by 0.7 of a frame and agrees.
- Two different rates: less than one frame of the slower rate.
- Length agreement cannot prove unchanged speed. It catches the usual case, where a speed change makes the lengths differ by a frame or more. A very short range can hide a speed change: at `25/1`, a one-frame range (0.04 seconds) and a 0.001-second child agree.
- With frames at one rate, the counts must still be equal. At `30000/1001`, range frames 300 to 599 (299 frames) and a 300-frame child are rejected.
- Seconds against seconds with no rate: the lengths are equal.
- When the child states no length, this check does not apply. The child length is then the range length, because a subclip plays at unchanged speed; a reader may calculate it.

`REL-5` (T). Within one `relationships` list, two entries that are equal in every field except `description` and `extensions` are a duplicate and are rejected. Fields compare by value (`DOC-2`). An absent field equals only an absent field. A checker reports each duplicate after the first. Each `relationships` list is checked on its own: the asset level, each version, and `unassigned`. `target_version` is a field of the entry, so two entries that differ only in `target_version` are not duplicates. An entry at asset level and an equal entry in a version are not duplicates; they state different facts.

`REL-6` (T). Target version.

- `target_version` names one version of the target asset. It MUST resolve to a version id in the target's `versions`. A target with no versions has only its implied original version, which has no id, so any `target_version` on it is rejected.
- When a relationship has a `range` and its target has versions, `target_version` is required (reported at the relationship). The range lies on that version's timeline (`TIME-12`).
- Without a `range`, `target_version` is optional. When it is absent, the relationship is about the target asset as a whole.
- A `subclip_of` always has a `range`, so it names the source version whenever its target has versions.
- The `TIME-4` order check on a `range` always runs. The checks of this rule run only when `target` resolves under `PKG-6`. The checks against the target timeline (the `TIME-5` and `TIME-12` timeline check, the `TIME-9` bounds, the `TIME-7` agreement, and `REL-4`) run only when `target` resolves and either `target_version` resolves, or `target_version` is absent and the target has no versions. In every other case the target timeline is unknown, so the target-timeline checks do not run.

## 10. Collections

`COL-1` (S). A `collection` record has, in addition to the record fields of section 3:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `title` | nonempty string | yes | Human name. |
| `collection_type` | token | yes | `logical`, `storage`, `other`. `COL-2`. |
| `description` | string | no | |
| `storage` | object `{storage_location, path}` | no | `COL-2`. `storage_location` resolves under `PKG-6`. `path` follows `STO-3`. |
| `member_of` | array of membership entries | no | `COL-3`. The collections that this collection belongs to. |
| `created`, `modified` | date-time | no | |
| `metadata` | array | no | Section 11. |
| `access` | object | no | Section 13, `ACC-1`. |

`COL-2` (S+T). `logical` is a grouping whose membership the source system stores, with no storage meaning. `storage` mirrors a location in a storage system and declares it in `storage`. `other` is any other stored grouping. A `storage` collection with no `storage` object, or another collection with one, is rejected (S). A saved search, or a collection whose membership the source computes from a search, is not a collection in OASIS. A producer MUST NOT export one as a collection of any type (T, not checkable).

`COL-3` (S+T). Membership is recorded on the member. An asset or a collection lists the collections it belongs to in `member_of`. Each entry names one collection by reference in `collection` and MAY carry `position` (`COL-7`) and `extensions`. A collection record does not list its members. The members of a collection are the assets and collections in the package that name it in `member_of`. An absent `member_of` and an empty `member_of` both state no membership. Neither one states non-membership: a collection in a package may have other members in the source that this package does not hold. `member_of` is a field of the asset or collection record itself, never of a version. Every entry resolves under `PKG-6`. So a package that names a collection also holds that collection, and every collection that its `member_of` names, up to the top.

`COL-4` (T). A collection MAY belong to several collections. Membership among collections MUST NOT form a cycle: following `member_of` entries from a collection never leads back to it. A collection that names itself is a cycle. A checker reports every `member_of` entry that is part of a cycle. Assets cannot form a cycle, because no entry names an asset. A record MAY belong both to a collection and to a collection inside it.

Informative note: an entry is part of a cycle when its owner and its target lie in one strongly connected component, or when it names its owner. A checker finds these entries in one pass over the collections, for example with Tarjan's method. It needs no recursion.

`COL-7` (S+T). `position` is an integer: negative, zero, or positive (S). It orders the members of the collection that the entry names. Lower positions come first. All entries that name one collection, from assets and collections together, share one position scope. Positions compare by value (`DOC-2`), so `2` and `2.0` are the same position. Within one scope, positions MUST be unique. A checker reports every entry that shares a position with another. Positions need not start at 0 or 1 and need not be consecutive. A producer writes the source positions and does not renumber them for a partial export. A record MAY name one collection in more than one entry only when each of those entries carries a position. When one `member_of` names a collection more than once and any of those entries has no position, every entry for that collection after the first is a duplicate, and a checker reports each one. An entry without `position` has no place in an order. A reader MUST NOT take an order from array order or record order. Within one collection, some entries MAY carry a position and others not: entries with a position are in order, and entries without one are members with no known place.

## 11. Metadata definitions and values

Definitions live in the package's `metadata_definitions` record list. Values live on assets, versions, `unassigned`, collections, and annotations.

`MD-1` (S). A `metadata_definition` record has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `label` | string | no | Human label. |
| `description` | string | no | |
| `value_type` | token | yes | `string`, `integer`, `number`, `boolean`, `date`, `datetime`, `enum`, `asset_reference`, `collection_reference`. |
| `cardinality` | token | yes | `single` or `multiple`. |
| `list_type` | token `fixed` or `open` | required when `value_type` is `enum`; otherwise absent | `MD-7`. |
| `options` | array of `{id, label}`, 0 or more | required when `value_type` is `enum`; otherwise absent | Option `id` is unique within the definition (`ID-4`). `label` is optional. |
| `constraints` | object | no | `MD-2`. |
| `required` | boolean | no | A hint from the source system. Validators do not enforce it on values. |

The definition's `id` (`REC-5`) identifies the field. A producer that needs to keep the source system's machine name uses it as the `id` when it is a valid id (`REC-5`), or records it in an extension namespace on the definition.

`MD-2` (S+T). `constraints` is a closed object with optional `minimum`, `maximum` (numbers, for `integer` and `number`), `min_length`, `max_length` (integers 0 or more, for `string`), and `pattern` (string, ECMA-262 regular expression source, for `string`). The schema checks `pattern` with the `regex` format where the validator supports it; a conformance checker MUST reject a `pattern` that is not a valid ECMA-262 expression (T). Constraints are data about the source field. They are not JSON Schema keywords and validators MUST NOT execute them over values (T).

`MD-3` (S). A metadata value object, in any `metadata` array, has `definition` (reference to a metadata definition id, required) and `value` (required).

`MD-4` (S+T). The value representation per `value_type`:

| `value_type` | `single` value | `multiple` value |
| --- | --- | --- |
| `string` | JSON string | array of strings |
| `integer` | JSON integer | array of integers |
| `number` | JSON number | array of numbers |
| `boolean` | JSON boolean | array of booleans |
| `date` | string `YYYY-MM-DD`, valid Gregorian date | array of such strings |
| `datetime` | date-time string (section 14) | array of such strings |
| `enum` | a string (`MD-7`) | an array of strings |
| `asset_reference` | asset id reference | array of asset id references |
| `collection_reference` | collection id reference | array of collection id references |

The schema accepts only a JSON string, integer, number, or boolean, or an array of those (S). Objects, nested arrays, and `null` anywhere in a value are rejected by the schema. A value whose JSON type does not match the definition's `value_type` and `cardinality` is rejected (T). A `date` or `datetime` value with bad syntax or an invalid calendar date is rejected (T). On a `fixed` list, a value item that is not an option `id` is rejected. A `multiple` value MAY be an empty array. Repeats are rejected for every value type under `MD-8`. A whole number beyond plus or minus (2^53 - 1) cannot be an `integer` or `number` value (`DOC-4`). A producer declares such a field with `value_type` `string` and writes the digits as a string. `null` is not a value; a producer omits the value object instead. A metadata value object MAY carry `extensions` (`EXT-1`).

`MD-5` (T). `definition` resolves under `PKG-6`. Each definition id appears at most once in one `metadata` list. A repeat is rejected. Each list is checked on its own: the asset level, each version, `unassigned`, a collection, and an annotation. `VER-7` adds one check across the lists of one asset.

`MD-6` (T). Reference-typed values resolve under `PKG-6`.

`MD-7` (S+T). Fixed and open lists.

- A `fixed` list accepts only option ids. A value item that is not an option `id` is rejected (T).
- An `open` list accepts any string. A value item equal to an option `id` is that option. Any other value item is text the source stored outside the defined options.
- A value item is compared with option ids by exact code points. It is never matched to a `label`.
- `options` MAY be empty. An empty `fixed` list accepts no value item. An empty `open` list accepts any value item.
- With `multiple` cardinality, an empty array is valid for every list (`MD-4`).
- A producer exports values as the source stores them. It MUST NOT add an option to the definition, or require a definition update, to make a value fit. When the source has saved typed values into its own option list, they are options in the export like any other.
- The order of `options` stays presentation order (`PKG-8`). Shared lists and lists with levels are not part of this draft.

`MD-8` (T). In a `multiple` value of any `value_type`, each item appears at most once. A repeat is rejected, and a checker reports each repeat after the first. Numbers compare by value (`DOC-2`), so `1` and `1.0` are a repeat. Strings, including dates, date-times, references, and `enum` items, compare by exact code points, whether or not they resolve, so an item can get both a resolution finding and a repeat finding. `true` and `false` compare as themselves. A producer whose source holds a repeated value writes it once and MAY keep the raw list in an extension.

## 12. Annotations

An annotation is a statement about an asset or one of its versions, optionally about a time range of it.

`ANN-1` (S). An annotation is a nested object in an `annotations` list: at the asset level, in a version, or in `unassigned` (`VER-4`, `VER-5`). It carries no `type` or `spec_version` and MAY carry `source`. An annotation has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Unique within the asset (`ID-4`). |
| `purpose` | token | yes | `ANN-2`. |
| `title` | string | no | Short name of the annotation. |
| `text` | string | no | The annotation's content. |
| `category` | string | no | Source system label, free form. |
| `author` | string | no | Neutral name or identifier of who made it. Not a principal. |
| `language` | string | no | BCP 47 language tag for `text`. The schema checks well-formedness under the RFC 5646 section 2.1 grammar, including grandfathered forms, with the case-insensitive matching that RFC 5646 requires. Registry membership of subtags is not checked and is not required. |
| `created`, `modified` | date-time | no | |
| `start_frame`, `end_frame` | integer | no | Frame positions on the holder's timeline (`TIME-3`, `TIME-4`, `TIME-12`). |
| `start_seconds`, `end_seconds` | number | no | Seconds positions, or restated values of the frame fields (`TIME-3`, `TIME-4`, `TIME-7`). |
| `start_timecode`, `end_timecode` | string | no | Timecode labels of the frame fields (`TIME-7`, `TIME-8`). |
| `start_sample`, `end_sample` | integer 0 or more | no | Sample positions that restate the seconds fields (`TIME-13`). |
| `visibility` | token `public` or `private` | no | `ANN-4`. |
| `metadata` | array | no | Section 11. |
| `extensions` | object | no | Section 13. |

An annotation with no position field is about the whole of its holder.

`ANN-2` (S+T). `purpose` is one of `note`, `review`, `quality`, `transcript`, `chapter`, `keyword`, `other`. `note` is a free comment. `review` is an approval, rejection, or change request. `quality` is a technical quality observation. `transcript` is spoken or written content at that time. `chapter` is a structural marker. `keyword` is a tag. `other` is anything else; a producer SHOULD record the source meaning in `category` or extensions. Producers MUST NOT map a source type to a purpose it does not have; use `other`.

`ANN-3` (S+T). An annotation with a frame field needs frame-form timing on its holder. The schema checks this at asset level and in each version (S). Timing follows section 6 in full.

`ANN-4` (S+T). `visibility` states who can see the annotation in the source. `public` means the source applies no annotation-specific visibility restriction. It does not remove any access control on the asset. `private` means the source restricts who can see the annotation. It does not necessarily mean that only the author can see it. Absence means unknown, never `public`. A producer writes `visibility` only when the source states it. Audience details, such as groups, share links, and named reviewers, go in extensions. Thread structure, parent links, and resolution state stay in extensions. Restoring a discussion is not a core guarantee. OASIS prescribes no enforcement (section 13). The S part is the value list.

`ANN-5` (T). A position of 0 is the start of the timeline, never "no position". A producer writes a time position only when the source states one. When a source stores a value that stands for "no position", the producer omits the position fields and MAY keep the stored value in extensions.

## 13. Extensions and access

`EXT-1` (S). `extensions` is allowed on every record and on these nested objects: file, file location entry, file group, member, version, relationship, annotation, metadata value, option, and collection membership entry. Small value objects such as manifest, checksum, rate, time base, timing, range, sequence, sequence image, ratio, collection storage, and access carry no extensions. `unassigned` carries none either (`VER-5`). `extensions` is an object whose keys are namespace tokens matching `^[a-z][a-z0-9_]{0,62}$` and whose values are objects. The inner objects are open: any JSON is allowed inside a namespace, within `DOC-1` and `DOC-4`.

`EXT-2` (S+T). Every namespace token used anywhere in a package MUST be declared in `manifest.namespaces`. A declaration has `token` (required), `owner` (nonempty string, required: the organisation or product that defines the namespace), `schema` (absolute URI string, optional, informative), and `description` (optional). A used token with no declaration is rejected. A declared token that is unused is allowed. Each token MUST appear in at most one declaration; a repeated token is rejected (T).

`EXT-3` (S). The token `oasis` is reserved for this standard and MUST NOT be declared or used by producers in this draft. No other token is reserved.

`EXT-4` (T). Data-value preservation. This rule binds a consumer that re-emits a record or a nested entity that it read from a package. The consumer MUST re-emit every extension value that it does not interpret, with the same value, under the same token in the `extensions` of the same entity. This covers every namespace that the consumer does not recognize. It also covers every member, at any depth, that the consumer does not interpret inside a namespace that it recognizes. Two JSON values are the same value when they have the same JSON type and:

- numbers are equal by value (`DOC-2`), so `1`, `1.0`, and `1e0` are the same value;
- strings have the same sequence of Unicode code points, with no Unicode normalization;
- `true`, `false`, and `null` each match only themselves;
- arrays have the same length and the same values in the same order;
- objects have the same member names and the same value for each member.

The consumer MAY change whitespace, object member order, number spelling, and string escape spelling. It MUST NOT change a value or a JSON type, add or drop a member or an array item, or change array order. An empty object, an empty array, and `null` stay as they are. For each namespace that it re-emits, the consumer keeps the manifest declaration (`EXT-2`) with the same `token`, `owner`, `schema`, and `description` values. A consumer that cannot keep these values MUST state that its output does not conform to `EXT-4`. A consumer that does not re-emit records is not bound by this rule. Members that the consumer interprets, that is, reads with the meaning that the extension owner defines, are the responsibility of the consumer and the extension owner. This rule does not limit how the consumer changes them.

Informative note: OASIS defines no identity or version field for an extension. An owner that needs a version puts it inside its namespace, for example `{"vendor_a": {"format_version": "3"}}`. A token is declared per package. The `owner` in each package's declaration names who defines the token in that package.

Example input. The consumer does not recognize `vendor_a`. It recognizes `vendor_b` but does not interpret `review_state`.

```json
"extensions": {
  "vendor_a": {"rank": 1.0, "tags": ["b", "a"], "note": "café", "empty": {}},
  "vendor_b": {"asset": {"id": "x-0001"}, "review_state": "approved"}
}
```

Valid re-emission. Whitespace, member order, number spelling, and escape spelling changed. All values are the same.

```json
"extensions":{"vendor_b":{"review_state":"approved","asset":{"id":"x-0001"}},"vendor_a":{"empty":{},"note":"caf\u00e9","tags":["b","a"],"rank":1}}
```

Invalid re-emission. `rank` changed from a number to a string. `review_state` was dropped from a recognized namespace.

```json
"extensions": {
  "vendor_a": {"rank": "1", "tags": ["b", "a"], "note": "café", "empty": {}},
  "vendor_b": {"asset": {"id": "x-0001"}}
}
```

Other changes and their result:

| Change in a value the consumer does not interpret | Result |
| --- | --- |
| `["b", "a"]` to `["a", "b"]` | Fails: array order changed. |
| `{}` dropped, or written as `null` | Fails: member dropped, or type changed. |
| `0.1` written as `0.1000000000000000055511151231257827` | Fails: value changed. |
| `1` written as `true` | Fails: type changed. |
| `"e\u0301"` (two code points) written as `"\u00e9"` (one code point) | Fails: Unicode normalization changed the code points. |
| `1e2` written as `100` | Allowed: same value. |

`ACC-1` (S). `access` is an optional closed object on an asset or a collection, with `status` (required): `none` or `restricted`.

`ACC-2` (T). `none` means the source information shows no access restriction on the entity. `restricted` means it shows at least one. An absent `access` means the package supplies no access information: the state is unknown. Absence never means `none`. A producer writes `access` only when the source supplies the information. It never infers `none` from silence. Details, principals, grants, and denials are not part of this draft and MAY be placed in extensions.

Informative note: OASIS carries the source's access information. It prescribes no enforcement. Receiving applications decide how to apply it.

## 14. Date and time strings

`DT-1` (S+T). A date-time string follows RFC 3339 section 5.6 with these limits: four-digit year 0001 to 9999, a valid Gregorian date, hours 00 to 23, minutes and seconds 00 to 59, `T` or `t` separator, optional fraction with at least one digit, and `Z`, `z`, or a signed `HH:MM` offset. A space separator, an offset without a colon, and leap second 60 are rejected. `-00:00` is preserved literally.

`DT-2` (T). Format checking is required. A validator that cannot check this grammar MUST report a setup failure.

`DT-3` (T). A date string is `YYYY-MM-DD` with a valid Gregorian date. No core field is a date; the form is used by metadata values whose `value_type` is `date` and is checked under `MD-4` (T). The schema bundle carries a `date` definition for checkers to reuse.

## 15. Unsupported documents

`UNS-1` (T). Version check. A checker reads the root `spec_version` of a document after `DOC-1`, and after the `REC-2` test for a root that is not an object or has no `spec_version` member, and before every other rule. It compares the string exactly, character for character, with the versions it supports. It does no case folding and no trimming, and it applies no Semantic Versioning precedence or build-metadata rule. When it supports that exact version, it checks the package with the rules of that version only: the contract rules and the schema bundle of that version. It never applies the rules of one version to a package that declares another, even when the two versions share a major or minor number. When it does not support that exact version, it reports the document as unsupported and reports no other finding. It does not report an unsupported document as conforming or as invalid. A document whose root is not an object, or has no `spec_version` member, is not an exchange document (`REC-2`). A `spec_version` member that is present but is not a supported version, including a value that is not a string, is unsupported. `DOC-1` comes first because a checker cannot read the version reliably from bytes that break it. For example, two root `spec_version` members can give two answers.

`UNS-2` (T). A checker states the exact `spec_version` values that it supports. This contract defines no compatibility between versions. A later version may define compatibility rules. Until one does, each version is checked only with its own rules.

Informative note: what an application does with an unsupported package is outside this contract.

## 16. Multi-file package

A multi-file package holds one package in a folder, the package folder. It is for exports that are too large for one JSON document. The manifest file holds the package root. Member files hold the records, one record on each line. The record definitions and every other rule of this contract are the same in both forms.

Informative note: a package folder looks like this. The member file names are examples only.

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
    part-00002.jsonl.gz
    source=a/part-00001.jsonl
```

Informative note: as a guideline, a producer can choose the multi-file form for an export of more than about 100,000 assets. This guideline is not a limit. Either form can hold a package of any size.

`MFP-1` (S+T). Form and manifest file.

- A package root with `manifest.members` is a multi-file package. A package root without it is a single-document package (S).
- The root of a multi-file package is a package as `PKG-1` and `PKG-2` define it. It has none of the four record arrays (S).
- The manifest file holds the root. Its name is `oasis-package.json`, and it is at the top of the package folder. The package folder is the folder that holds the manifest file (T; a document with `manifest.members` under any other file name is reported at the root).
- The manifest file meets `DOC-1` to `DOC-4`, `REC-2`, and `UNS-1`, as a single document does. `type`, `spec_version`, `id`, `source`, `extensions`, and the manifest fields keep their meaning.

`MFP-2` (S+T). Member entries and member paths. Each item of `manifest.members` is a member entry. It names one member file. A member entry has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `path` | string | yes | The member path, under the rules below. |
| `record_type` | `storage_locations`, `metadata_definitions`, `collections`, or `assets` | yes | The record type of every record in the file. It equals the first segment of `path`. |
| `count` | integer 0 or more | yes | The number of records in the file (`MFP-5`). |
| `size_bytes` | integer 0 or more | yes | The size of the file as stored. For a `.jsonl.gz` file, this is the compressed size. |
| `sha256` | string of 64 lowercase hexadecimal digits | yes | The SHA-256 digest of the file as stored (`MFP-3`). |

Member path rules:

- A member path is relative to the package folder. It uses `/` as the separator (S).
- Its first segment is a record folder: `storage_locations`, `metadata_definitions`, `collections`, or `assets`. At least one more segment follows. So a record folder MAY hold subfolders, such as `assets/source=a/part-00001.jsonl` (S).
- Each later segment uses only ASCII letters, digits, `.`, `_`, `-`, and `=`. It starts with a letter, a digit, or `_`. So no segment is empty, `.`, `..`, or a hidden name, and a path has no leading `/` and no `\` (S).
- The last segment ends in `.jsonl` for a plain file or in `.jsonl.gz` for a gzip file (S). The rest of the file name is free.
- `record_type` MUST equal the first segment of `path` (T; reported at `record_type`).
- Each member path MUST be unique in `members`. Two member paths MUST also differ in more than letter case, so the package works on a file system that ignores letter case (T). A checker reports at `path` each entry whose path repeats an earlier path exactly. It reports at `path` each other entry whose path equals an earlier path when letter case is ignored.
- The order of `members` carries no meaning (`PKG-8`). `MFP-7` states the one use of this order by a checker.

`MFP-3` (T). Member files in the package folder.

- Each member path names a regular file. Each folder on the way to it is a real folder. A missing member file is rejected (reported at `path`).
- A symbolic link at a member path, or at a folder on the way to it, is rejected (reported at `path`). Validation reads nothing behind such a link (`SAFE-1`).
- A member path that names a folder, a device, a pipe, or any other entry that is not a regular file is rejected (reported at `path`). So is a folder on the way that is not a real folder.
- The size of each member file, as stored, MUST equal its `size_bytes` (reported at `size_bytes`).
- The SHA-256 digest of each member file, as stored, MUST equal its `sha256` (reported at `sha256`).
- An entry inside a record folder, at any depth, that `members` does not list and that is not a folder is rejected. It can be a member file that the manifest lost. Any other entry in the package folder that `members` does not list, other than the manifest file and folders, gets a warning. It is not rejected.
- Size guideline: a member file holds up to about 100,000 records or 1 GiB of uncompressed text, whichever comes first. A larger list uses several member files. This guideline is not a limit. When a record list has two or more member files that hold fewer than 1,000 records each on average, a checker gives a warning at `/manifest/members`. Many very small files make a package slow to move and to read.

Informative note: the macOS `tar` command adds `._` files, and the Finder adds `.DS_Store` files. Such a file inside a record folder makes the package invalid. The adopter guide gives a `tar` command that leaves them out.

Informative note: a checker can compute each digest while it reads the records of the file, so it reads each member file only once.

`MFP-4` (S+T). Member file format.

- A member file is JSON Lines: UTF-8 text with one record on each line. Each line holds one complete record of the record type of its member entry, exactly as an item of the matching array in a single document. A line carries no `type` and no `spec_version` (`REC-1`). A record is never split across lines or member files.
- Line rules (T). Every line ends with one LF (U+000A), the last line too. A member file holds no CR (U+000D), no blank line, and no byte-order mark. A line has no space (U+0020) or tab (U+0009) before or after its JSON object. A member file that breaks a line rule is rejected, once for the file (reported at the member entry).
- Each line meets `DOC-1` to `DOC-4` as a JSON text on its own (T). Each line meets the record schema of its record type (S). A checker reports a finding inside a line by the member entry, the line number, and a JSON Pointer inside the record on that line.
- Compression (T). A `.jsonl` file is plain text. A `.jsonl.gz` file is one gzip stream under RFC 1952. It MAY hold several gzip members one after another, as standard tools write them. No byte follows the last gzip member, not even a zero byte. A file of 0 bytes is not a gzip stream. The line rules apply to the decompressed bytes. The compression of a file MUST match its name. A mismatch, or a damaged or cut-off gzip stream, is rejected (reported at `path`).
- A package MAY mix plain and gzip member files, also in one record list.
- A checker MAY stop reading a member file whose decompressed size passes a set multiple of its stored size, or whose single line passes a set length. That stop is a setup failure of the checker, not a finding about the package. This contract sets no maximum line length.

Informative note: a file that a transfer cut off usually ends without its final LF. So it fails the line rules even before its digest is compared.

`MFP-5` (T). Counts.

- Each member `count` MUST equal the number of lines in its member file (reported at `count`).
- Each `manifest.counts` value MUST equal the sum of the `count` values of the member entries of its record type (`PKG-3`). A list with no member entry counts as 0. A mismatch is reported at that `counts` value.

`MFP-6` (T). Absent and empty lists.

- `DOC-3` keeps an absent list and an empty list distinct. In a multi-file package, a record list is absent when no member entry has its record type. It is empty when it has member entries and their counts total 0.
- A member entry with `count` 0 is allowed only in an empty list. A member entry with `count` 0, in a list that has records in other member files, is rejected (reported at `count`).
- Under the line rules of `MFP-4`, a plain member file with 0 records has 0 bytes. A gzip member file with 0 records is a gzip stream with no content.
- A record folder MAY be absent when its list is absent. A folder that holds no file states nothing.

`MFP-7` (T). Scope across member files. Every rule of this contract applies to the whole package. A rule that compares records inside one document compares records across all member files. A member file does not need to be complete by itself. A record MAY reference a record in any member file, earlier or later. These rules need the most care:

| Rule | Scope in a multi-file package |
| --- | --- |
| `ID-1` | An identifier is unique per record type across all member files of that type. |
| `PKG-3` | The counts of `MFP-5`. |
| `PKG-6`, `ID-5`, `MD-4`, `MD-7` | Every reference resolves in the package, in any member file. |
| `REL-3`, `REL-4`, `REL-6` | The relationship target, target version, and target timeline checks run across all asset member files. |
| `COL-4` | No cycle among collections, across all collection member files. |
| `COL-7` | Positions are unique per collection across every asset and collection that names it, in any member file. |
| `EXT-2` | The manifest file declares every namespace token that any member file uses. |

- Rules on nested objects, such as `ID-4`, `GRP-4`, and `VER-6`, stay inside one record, so inside one line.
- Record order for reports. Some rules report each repeat after the first. For them, the first comes from the order of the member entries in `members`, then from the line order in each member file. It never comes from file names or from the order of a file system. This order chooses which repeat a checker reports. It gives the package no other meaning (`PKG-8`).

Informative note: a checker can keep its indexes for these checks on local disk. Its memory then grows with the number of identifiers and references, not with the size of the records.

`MFP-8` (T, not checkable). Producer order.

- A producer writes each member file completely before it lists the file. It writes the manifest file last, after every member file is complete. It never lists a partial or temporary file.
- A producer that stops before it writes the manifest file leaves no valid package.
- A producer MAY write records in any order, and in any member file of the right record type. This contract requires no record order, no sorted identifiers, and no second pass over the source.

`MFP-9` (T, not checkable). Equivalence of the two forms. A single-document package and a multi-file package are equivalent when all of these are true:

- They have the same root `type`, `spec_version`, `id`, `source`, and `extensions`, and the same `manifest` fields other than `members`. `counts` is equal too.
- Each record list is absent in both, or present in both.
- Each record list holds the same records in both, in any order. Records compare as JSON values under `DOC-2` and `DOC-3`, and a repeated record counts each time.

A tool that converts a package from one form to the other MUST give an equivalent package. Let a multi-file package meet `MFP-1` to `MFP-6`. Let each record list also hold its records in the same order in both forms: array order in the single document, and manifest order, then line order, in the multi-file package (`MFP-7`). A converter keeps that order. Then a checker gives both forms the same outcome. It also gives both the same findings, at the same records and the same pointers inside them, apart from the warnings of `MFP-3`. In another order, a rule that reports each repeat after the first, such as `ID-1`, can report a different repeat. A record that cannot be parsed cannot be converted, so parse findings are outside this comparison.

Informative note: a single-document pointer `/assets/<n><rest>` names a place in asset `<n>`. In the equivalent multi-file package, the same place is on the member file line that holds that asset, at the pointer `<rest>`. The same holds for every record list. A conversion to a single document is practical only for small packages.

## 17. Status and claims

This is a draft. The schemas, examples, and this contract can change before a final release. Interoperability between independent implementations is not demonstrated. No adopter, vendor, or standards body is represented as endorsing it. The scope is small synthetic packages. Scale and operational limits are untested.

OASIS defines the format and checks whether packages follow its rules. The conformance checker and the examples test packages against these rules. OASIS does not test or guarantee how a product reads, stores, shows, or writes package data. The developers of each product are responsible for their implementation. Promotion to a final release requires a separate approval.

The standard carries no report format. How a tool reports its own conversion results is the tool's concern.

## Appendix A: decision to rule map

D1 to D6 name the steward's six design decisions for 2.0: D1 one core profile; D2 packages with record lists; D3 JSON Schema 2020-12 with stable identifiers; D4 exact frame timing and explicit media structure; D5 namespaced extensions with an access summary; D6 no reporting.

| Decision | Rules |
| --- | --- |
| D1 core profile and exclusions | sections 2, 17; `REL-2`, `ACC-2`, `TIME-10`, `ANN-4` |
| D2 packages and record lists | `PKG-1` to `PKG-3`, `PKG-5` to `PKG-9`, `ID-5`, `COL-3`, `COL-7`, `MD-1`, `MD-3`, `MD-8`, `AST-3`, `MFP-1` to `MFP-9` |
| D3 2020-12, identifiers, record type and version | `REC-1`, `REC-2`, `REC-7`, `DOC-4`, `UNS-1`, `UNS-2`, the schema `$id` rule in the schema files |
| D4 time and media structure | `TIME-1` to `TIME-14`, `FILE-1`, `FILE-3` to `FILE-9`, `STO-3`, `GRP-1` to `GRP-12`, `VER-1`, `VER-2`, `VER-4` to `VER-7`, `REL-1` to `REL-6`, `ANN-1` to `ANN-3`, `ANN-5`, `MD-7` |
| D5 extensions and access | `EXT-1` to `EXT-4`, `STO-2`, `ACC-1`, `ACC-2` |
| D6 no report | section 2, section 17 |

## Appendix B: rules a schema cannot express

A conformance checker implements these checks on a document: `DOC-1` to `DOC-4`, `REC-2`, `PKG-3`, `PKG-6`, `PKG-8`, `ID-1`, `ID-2`, the T parts of `ID-4` and `ID-5`, `TIME-2` (on time bases, timecode bases, and member `frame_rate` and `capture_frame_rate`), the T parts of `TIME-3`, `TIME-4`, `TIME-5`, `TIME-7`, and `TIME-8`, `TIME-9`, `TIME-12`, the T part of `TIME-13`, `FILE-5`, the T parts of `FILE-6` (one entry per storage location) and `FILE-8` (range, step, pattern, and image numbers), `GRP-2`, `GRP-4`, `GRP-5`, `GRP-6`, the T parts of `GRP-7`, `GRP-10`, `GRP-11`, and `GRP-12`, `VER-2`, the T parts of `VER-5` and `VER-6`, `VER-7`, the T parts of `REL-1` and `REL-2`, `REL-3`, `REL-4`, `REL-5`, `REL-6`, the T part of `COL-3`, `COL-4`, the T part of `COL-7`, the T part of `MD-2` (constraints are never executed; `pattern` is a valid ECMA-262 expression), the T part of `MD-4` (shape against the definition, `date` and `datetime` syntax under `DT-3` and `DT-1`), `MD-5`, `MD-6`, the T part of `MD-7` (a value item on a `fixed` list is an option `id`), `MD-8`, the T part of `ANN-2`, the T part of `ANN-3`, the T part of `EXT-2` (declared and used tokens agree; each token declared at most once), the T part of `DT-1`, `DT-2`, `DT-3`, and, on a multi-file package, the T parts of `MFP-1`, `MFP-2`, and `MFP-4`, and `MFP-3`, `MFP-5`, `MFP-6`, and `MFP-7`.

These rules state producer, consumer, or checker obligations. They are documented and are not checkable on a document alone: `SAFE-1`, `PKG-5`, `PKG-9`, `ID-3`, `AST-3`, `TIME-10`, the frame-count obligation of `TIME-11`, the T part of `TIME-14`, `FILE-4`, the producer parts of `FILE-6`, `FILE-7`, `FILE-8`, and `FILE-9`, `STO-2`, the producer part of `STO-3`, `GRP-8`, `GRP-9`, the producer parts of `GRP-10` and `GRP-11`, the producer and reader parts of `VER-4`, `VER-5`, and `VER-6`, the saved-search clause of `COL-2`, the producer part of `MD-7`, the T part of `ANN-4`, `ANN-5`, `EXT-4`, `ACC-2`, `UNS-1`, `UNS-2`, `MFP-8`, `MFP-9`.

The schema files express these parts of rules that the body marks T or S+T. A conformance checker does not need to repeat them.

- `TIME-4`: `end_frame` without `start_frame` is rejected. On a marker with no frame field, `end_seconds` without `start_seconds` is rejected. On a marker with frame fields, `end_seconds` without `end_frame` is rejected. Order and bounds stay with a conformance checker.
- `TIME-5` and `ANN-3`: an annotation with a frame field on a holder with no frame-form timing is rejected, at the asset level and in each version. Relationship ranges stay with a conformance checker.
- `TIME-6`: fully expressed. `drop_frame: true` is accepted only with the exact rate objects `30000/1001` and `60000/1001`.
- `TIME-7`: in the frame form, `duration_seconds` without `duration_frames` is rejected. Seconds below 0 are rejected. Agreement stays with a conformance checker.
- `TIME-8`: for `source_timecode` and annotation labels, the schema checks the separator against `drop_frame`, the frame field range per rate, skipped drop-frame labels, labels without a `source_timecode` anchor, and `source_timecode` at a rate outside the table. It checks a seconds-form `source_timecode` in the same way against its `timecode_base`. Derivation agreement stays with a conformance checker.
- `TIME-11`: the two forms are fully expressed. The frame form has `time_base`. The seconds form has `duration_seconds` and no `duration_frames`. `timecode_base` appears only in the seconds form and only with `source_timecode`.
- `TIME-13`: `start_sample` without `start_seconds`, `end_sample` without `end_seconds`, and `duration_samples` without `duration_seconds` or `sample_rate` are rejected. A marker sample field on a holder with no `sample_rate` stays with a conformance checker.
- `TIME-14`: in the seconds form, `source_timecode` without `timecode_base` is rejected, and the `timecode_base` rate must be in the `TIME-8` table.
- `AST-2`: fully expressed. A title with no non-whitespace character is rejected.
- `VER-4` and `VER-5`: an asset with no versions has no `current_version` and no `unassigned`. With versions, the asset level and `unassigned` hold no `timing`, no annotation with a position field, no member with a part start, and no `subclip_of` relationship.
- `GRP-7`: a start field on a member without `segment_index` is rejected.
- `GRP-11`: each field is accepted only on its track types. Member `language` is checked for RFC 5646 well-formedness, and `und` in any letter case is rejected.
- `REL-1`: the fields of `range` and their pairing are expressed. Order, bounds, and agreement stay with a conformance checker.
- `REL-2`: `subclip_of` without `range` is rejected. The meaning of each type is informative.
- `COL-2`: a `storage` collection without `storage`, or another collection with `storage`, is rejected. The meaning of each type is informative. The saved-search clause is not checkable.
- `MD-4`: a `null` value, an object value, a nested array, and `null` inside an array are rejected. Shape against the definition stays with a conformance checker.
- `MD-7`: `list_type` is required when `value_type` is `enum`, and absent otherwise.
- `MD-2`: `pattern` is checked with the `regex` format where supported. Authoritative ECMA-262 validity stays with a conformance checker.
- `ANN-1` and `FILE-1`: `language` is checked for RFC 5646 well-formedness and `media_type` for RFC 6838 `type/subtype` syntax. Neither registry is consulted.
- `EXT-3`: fully expressed. The token `oasis` is rejected as an extension key and as a declared token.
- `MFP-1`: a package root with `manifest.members` and any of the four record arrays is rejected. The manifest file name stays with a conformance checker.
- `MFP-2`: each member entry has its five fields, and `path` follows the separator, segment, character, and name rules. Unique paths, letter case, and the match of `record_type` with `path` stay with a conformance checker.
- `MFP-4`: each line is checked against the record schema of its record type. The line rules, compression, and `DOC-1` to `DOC-4` on each line stay with a conformance checker.

Schema patterns use ECMA-262 semantics. Some regular expression engines let `$` match before a final newline. The conformance harness configures its checker so that this never happens.
