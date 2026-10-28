# OASIS 2.0 contract

Status: DRAFT 2.0.0-draft.2. Not a final release. Interoperability between independent implementations is not demonstrated.
This text does not claim certification or production readiness.
OASIS means Open Asset Standard Interchange Schema.
The accompanying [glossary](GLOSSARY.md) defines every term used here. The [data model](../../specification/2.0.0-draft.2/DATA-MODEL.md) draws the shapes; it is informative.

- Revision: 2026-10-28. Section 15 is retitled "Unsupported documents" and holds one rule, `UNS-1`. The appendices are renumbered. Editorial; no field, schema, or identifier changed.
- Revision: 2.0.0-draft.2, 2026-10-21. Applies the field renames and additions approved on the working group call of 2026-10-16. See "Changes in 2.0.0-draft.2" below.
- Revision: 2026-10-14. Grandfathered language tags are matched case insensitively. `EXT-4` admits no policy exception.
- Revision: 2026-10-14. `EXT-4` byte preservation is defined as the exact byte sequence of each namespace value. `ANN-1` language tags are checked against the full RFC 5646 grammar. `MD-2` length bounds are stated.
- Revision: 2026-10-14, after the harness build. `SAFE-1` states the two files validation may open: the document and the schema bundle. No other rule changed.
- Revision: 2026-10-14. Snapshot equality is defined without `members`. Metadata values are limited to scalars or arrays of scalars in the schema. Extensions on options and metadata values are expressed. Syntax checks are added for language tags and media types. Added: namespace token uniqueness, image-sequence range order, absent version references on groups and annotations, the meaning of extension preservation, and `SAFE-1` as a normative rule. Corrections to `PKG-8` and `DT-3`.
- Revision: 2026-10-05. Rule markers are aligned with the schemas. The collection type field is renamed to `collection_kind`. The text states where extensions are allowed. The connection credential reference is optional. Storage locations gain an optional description and dates. Annotations gain an optional title and nested provenance. Asset-side membership against incomplete collections is clarified.
- Revision: 2026-10-05. Section 6 is reworked: origin removed, source timecode anchor added, timeline ownership stated, explicit timecode rate table, bounds and arithmetic rules.
- Executes the steward's six design decisions for 2.0: one core profile, packages with registries, JSON Schema 2020-12 with stable identifiers, exact frame timing, namespaced extensions with an access summary, and no report format

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

## 1. Reading this contract

Normative sections are 3 to 15, and `SAFE-1` in this section. The rest of sections 1, 2, and 16, and the appendices are informative.
`MUST`, `MUST NOT`, and `SHOULD` express requirements.
Every normative rule has an identifier in the form `AREA-n`. A rule marked **S** is expressed by the JSON Schema files. A rule marked **T** cannot be expressed by JSON Schema and is implemented by a conformance checker. A rule marked **S+T** is partly each.

Schema acceptance, semantic conformance, and application behavior are distinct results. Passing one does not prove the others.
`SAFE-1` (T). Validation MUST NOT open any file other than the document under validation and the schema bundle it validates against. It MUST NOT open a file or location named by a value in the document, connect to a network or storage system, resolve a credential, or read media bytes.
Applications remain responsible for authorization and execution.

## 2. Design summary

This is a major version. Section 15 states the rule for documents the standard does not cover.

- One definition per entity. No embedded copy of a definition differs from the standalone one.
- The package is the unit of exchange. Registries hold shared definitions. Records reference them by id.
- Exact time: rational rates, integer frames counted from the first frame, an optional source timecode anchor, derived values that must agree.
- Explicit file groups and tracks describe how the files of an asset relate.
- Versions, relationships, a collection kind, a metadata value representation, a checksum algorithm label, and an access summary are part of the core profile.
- Extensions are namespaced and registered. Unknown keys outside them are rejected.
- No reporting of any kind.

## 3. Documents, records, and the version selector

`DOC-1` (T). A document is UTF-8 JSON under RFC 8259 with unique object member names and valid Unicode scalar values. A byte-order mark, a duplicate member name, `NaN`, `Infinity`, malformed encoding, or an unpaired surrogate escape makes the document invalid.

`DOC-2` (T). Numbers are preserved exactly before any conversion into runtime types. Comparisons use the mathematical value. A checker that cannot evaluate a number exactly MUST report a setup failure, not round and report conformance.

`DOC-3` (T). Validators MUST NOT insert defaults, normalize Unicode, rewrite dates, normalize paths, reorder arrays, or replace tokens. Absence, `null`, and empty are three distinct states and are preserved as written.

`REC-1` (S). Every record object carries `type` and `spec_version`. `type` is one of `package`, `asset`, `collection`, `storage_location`, `metadata_definition`, `annotation`. `spec_version` is the string `2.0.0-draft.2` for this draft.

`REC-2` (S+T). A document root is one of the six record types. A standalone record validates structurally on its own. References inside it resolve only in package context (section 4).

`REC-3` (T). Inside a package every record's `spec_version` MUST equal the package's. A mismatch is rejected.

`REC-4` (T). A consumer MUST read `type` and `spec_version` before selecting a schema. A record whose `spec_version` major is not 2 MUST NOT be validated against a 2.x schema. The consumer reports an unsupported version.

`REC-5` (S). Every record has `id`: a nonempty string with no leading or trailing whitespace, at most 256 characters. Uniqueness is defined in section 5.

`REC-6` (S). Every record may have `source`: an object with `system` (nonempty string, the producing system's name), optional `instance` (string, one deployment of that system), and `id` (nonempty string, the entity's identifier in that system). `source` is provenance. It is never used for reference resolution.

`REC-7` (S). Every record may have `extensions` (section 13). Every object in a record is closed: a key that is not declared by the schema and not inside `extensions` makes the record structurally invalid.

## 4. Packages, manifest, and registries

A package is a single JSON document whose root record has `type: "package"`.

`PKG-1` (S). A package has `manifest` (required), and the arrays `storage_locations`, `metadata_definitions`, `collections`, `assets`, each optional. An absent array and an empty array are both allowed and are distinct (see `PKG-6`).

`PKG-2` (S). `manifest` has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `producer` | object `{name, version}` of nonempty strings | yes | Software that wrote the package. |
| `produced_at` | date-time (section 14) | yes | When the package was written. |
| `counts` | object with integer `storage_locations`, `metadata_definitions`, `collections`, `assets`, each 0 or more | yes | Declared record count per array. |
| `completeness` | object with the same four keys, each `complete` or `partial` | yes | Whether the array is the producer's whole set for that kind. |
| `namespaces` | array of namespace declarations (section 13) | yes, may be empty | Every extension namespace used anywhere in the package. |
| `description` | string | no | Free text for humans. |

`PKG-3` (T). Each `counts` value MUST equal the length of its array. An absent array counts as 0. A mismatch is rejected. The count is a truncation and framing check for the single document; it is not a claim about the source system.

`PKG-4` (T). `completeness: complete` for a kind means every entity of that kind that the producer holds for the exchanged scope is present. `partial` means some are absent. A consumer MUST NOT treat an absent entity in a `partial` array as a deletion or removal.

`PKG-5` (T). The package carries no digest of itself. Transport integrity is outside this contract. Checksums apply to files only (section 8).

`PKG-6` (T). A record in `collections` or `assets` MAY reference a `storage_location`, `metadata_definition`, or `collection` by id. The target MUST be present in the package's registry array when that registry is `complete`. When the registry is `partial`, an unresolved reference is a warning, not a rejection. In a standalone record outside a package, no reference is checked.

`PKG-7` (S). Records inside a package are full records of their type, not abbreviated forms. There is no separate embedded shape.

`PKG-8` (T). Ordering inside each array carries no meaning except where a rule says so (file group members, option lists). Version order is given by `ordinal`, not by array position (`VER-2`).

## 5. Identity and references

`ID-1` (T). Within a package, `id` MUST be unique within its record type: no two assets share an id, no two collections share an id, and so on. Compare strings exactly, with no case folding or trimming. A repeated id is rejected on every occurrence after the first.

`ID-2` (T). Ids of different record types are different namespaces. An asset and a collection may share the same string.

`ID-3` (T). Identity scope is the package. Two packages from the same `source.system` and `source.instance` that carry the same `source.id` SHOULD describe the same entity, but the standard does not require consumers to merge them. A consumer that merges records across packages does so under its own policy.

`ID-4` (S). The following nested objects also carry `id` unique within their record: files within an asset, file groups within an asset, versions within an asset, annotations within an asset, options within a metadata definition. Uniqueness is scoped to the containing record (T).

`ID-5` (T). A reference is a string naming an `id` of the target type. References never carry embedded copies. The reference fields are listed in each section. An unresolved reference follows `PKG-6`.

`ID-6` (T). A snapshot is allowed only where this contract says so (asset `collections`, section 10). A snapshot is a read-only copy of a registry record and uses the same schema as the registry record. A snapshot MUST omit `members` (`COL-5`). When the registry record is also present, every other field of the snapshot MUST equal the registry record's field, compared as parsed JSON values with exact numbers (`DOC-2`), and the snapshot MUST NOT carry a field the registry record lacks. Any other difference is rejected.

## 6. Time

This is a frame-based timing model with SMPTE-compatible timecode labels. It does not claim SMPTE conformance. Time applies to assets, annotations, and relationship ranges.

`TIME-1` (S). A time base is an object `{rate, drop_frame}`. `rate` is `{numerator, denominator}`, both integers 1 or more. `drop_frame` is a boolean.

`TIME-2` (T). A rate is written in lowest terms. `24000/1001` is valid; `48000/2002` is rejected.

`TIME-3` (S). Positions and durations are integers, 0 or more, in frames at the owning timeline's time base. The fields are `start_frame`, `end_frame`, and `duration_frames`. Frame 0 is the first presented frame of the asset. Positions never count from a timecode.

`TIME-4` (S+T). Endpoints: `start_frame` is inclusive, `end_frame` is exclusive. A range has `end_frame` greater than `start_frame`. A point has no `end_frame`. `end_frame` equal to or less than `start_frame` is rejected. `end_frame` without `start_frame` is rejected.

`TIME-5` (S+T). There is no default rate. Every frame field belongs to exactly one timeline, and that timeline MUST declare a time base. A frame field whose timeline has no time base is rejected.

`TIME-12` (T). Timeline ownership. An asset's `timing` defines the asset timeline. An annotation's frame fields are on the timeline of the asset it belongs to and use that asset's time base; an annotation declares no time base of its own in this draft. A relationship `range` is on the timeline of the target asset and uses the target's time base; a relationship with a `range` whose target has no `timing` is rejected. A file group member `sequence_range` is not a timeline; it is file-name numbering and is never compared to any time base.

`TIME-6` (S). `drop_frame: true` is allowed only with rate `30000/1001` or `60000/1001`. Any other combination is rejected.

`TIME-7` (S+T). Derived values are optional and restate a frame value for readers: `start_seconds`, `end_seconds` (numbers), `start_timecode`, `end_timecode` (strings). A derived field is allowed only when its frame field is present. Seconds mean elapsed time from frame 0 and MUST be finite and 0 or more. Seconds agree with a frame value when the integer nearest to `seconds × numerator ÷ denominator` equals the frame value, with a tie at exactly one half rounding toward zero; agreement means the seconds name the same frame, not that they equal the exact elapsed time. Checkers use exact rational arithmetic for this test. A timecode label agrees when it equals the label derived from the frame value under `TIME-8`. Any disagreement is rejected.

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

Anchor: a label is derived as the asset's `source_timecode` anchor (`TIME-11`) plus the frame offset, counted in labels under the drop-frame rule when it applies, modulo 24 hours. Labels are allowed only when the asset declares `source_timecode`. A checker derives the label from the frame value and compares; it never converts a label back to a frame, so a 24-hour rollover is never ambiguous.

`TIME-9` (T). Bounds and arithmetic. For an asset with `duration_frames` D: a point satisfies `0 ≤ start_frame < D`; a range satisfies `0 ≤ start_frame < end_frame ≤ D`. Violations are rejected. When an object carries `start_frame`, `end_frame`, and `duration_frames` together, `duration_frames` MUST equal `end_frame − start_frame`. When the asset declares no `duration_frames`, no upper bound is checked.

`TIME-10` (T). Variable frame rate is not supported in this draft. A producer with a variable-rate asset MUST omit `timing` and all frame fields and MAY record the facts in extensions. A timestamp-based timing form is a candidate for a later profile.

`TIME-11` (S). Asset `timing` is an optional object `{time_base, source_timecode, duration_frames}`. `time_base` is required when `timing` is present. `source_timecode` is the optional timecode label of frame 0 in the source material, at the asset's rate, with `;` when `drop_frame` is true and `:` otherwise. One anchor assumes continuous timecode through the asset; material with timecode discontinuities is unsupported in this draft and MUST omit `source_timecode`. `duration_frames` is the optional length of the asset timeline.

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
| `deleted` | date-time | no | Soft deletion in the source system. Presence means the asset is a tombstone. |
| `timing` | object | no | Section 6, `TIME-11`. Required when any annotation or incoming relationship range carries frame fields. |
| `versions` | array | no | Section 9. |
| `files` | array | no | Section 8. |
| `file_groups` | array | no | Section 8. |
| `relationships` | array | no | Section 9. |
| `metadata` | array | no | Section 11. |
| `annotations` | array | no | Section 12. |
| `collections` | array | no | Section 10, asset-side convenience. |
| `access` | object | yes | Section 13, `ACC-1`. |

`AST-2` (S). `title` with only whitespace is rejected.

## 8. Files, storage, file groups, and tracks

Files are the recorded bytes of an asset. A file names its storage location by reference.

`FILE-1` (S). A file object has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Unique within the asset (`ID-4`). |
| `storage_location` | string | yes | Reference to a `storage_location` id (`ID-5`). |
| `path` | nonempty string | yes | Locator within that storage location. Opaque to validation. |
| `size_bytes` | integer 0 or more | no | Declared size. |
| `checksum` | object `{algorithm, value}` | no | `FILE-3`. |
| `media_type` | string | no | IANA media type, when known. The schema checks the `type/subtype` syntax of RFC 6838, not registration. |
| `version` | string | no | Reference to a version id within the asset (section 9). |
| `created` | date-time | no | |
| `modified` | date-time | no | |
| `status` | string | no | Producer's availability token. Free form. |
| `role` | token | no | `master`, `mezzanine`, `preview`, `thumbnail`, `sidecar`, `other`. `FILE-5`. |
| `label` | string | no | Short human name for the file. |
| `extensions` | object | no | Section 13. |

`FILE-2` (T). A file has exactly one storage location. A copy on another storage is another file object. Two files MAY share `checksum` and `size_bytes`; the standard does not deduplicate.

`FILE-3` (S). `checksum.algorithm` is one of `md5`, `sha1`, `sha256`, `sha512`, `blake3`. `checksum.value` is lowercase hexadecimal of the length the algorithm produces: 32, 40, 64, 128, 64 characters respectively.

`FILE-4` (T). Validation never computes a checksum. A declared checksum is a claim by the producer.

`FILE-5` (T). File roles: `master` is an original or best available recording. `mezzanine` is a high-quality intermediate made for further work or delivery. `preview` is a lower-quality copy for viewing. `thumbnail` is a still image representation. `sidecar` is a data file that accompanies media, such as captions or a metadata file. `other` is anything else. A file role describes the file on its own. It does not group files; file group membership does that (`GRP-5`). A file's role and the role of a file group that contains it are not required to match.

`STO-1` (S). A `storage_location` record has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | nonempty string | yes | Human name. |
| `system` | token | yes | Storage kind. Pattern `^[a-z][a-z0-9_]{0,62}$`. Suggested values: `filesystem`, `object_store`, `block_store`, `tape`, `optical`, `cloud_service`, `other`. Any token matching the pattern is accepted. |
| `description` | string | no | Free text. |
| `root` | string | no | Base locator that file `path` values are relative to. Opaque. |
| `created`, `modified` | date-time | no | |
| `connection` | object `{method, credential_reference}` | no | `STO-2`. `method` required, `credential_reference` optional. |
| `status` | string | no | Producer's availability token. |

`STO-2` (S+T). `connection.method` is a token with the same pattern as `system`. `connection.credential_reference` is an opaque string that names a credential held outside the package. The object is closed. A producer MUST NOT place a secret value in any field of a storage location (T, not checkable; stated for producers). Validation never connects.

`GRP-1` (S). A file group object has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Unique within the asset. |
| `role` | token | yes | `primary`, `preview`, `thumbnail`, `companion`, `other`. |
| `label` | string | no | Short human name for the file group. |
| `complete` | boolean | yes | Whether every member the producer knows of is listed. |
| `version` | string | no | Reference to a version id within the asset. |
| `members` | array of member objects | yes, 1 or more | `GRP-3`. |
| `extensions` | object | no | |

`GRP-2` (T). File group roles: `primary` is the content the asset is about, at its best available quality. `preview` is a lower-quality rendition for viewing. `thumbnail` is a still image representation. `companion` is data that accompanies the content, such as captions, sidecar metadata, or a transcript file. `other` is anything else. Role describes purpose, not format.

`GRP-3` (S). A member object has `file` (reference to a file id within the asset, required), `track_type` (`video`, `audio`, `image`, `data`, `other`, required), `track_index` (integer 0 or more, required), `channel_count` (integer 1 or more, optional), `sequence_range` (object `{start, end}` of integers, optional; for image sequences, inclusive start and exclusive end frame numbers in the file names; `start` MUST be less than `end`, so the range is never empty (T)), `segment_index` (integer 0 or more, optional; `GRP-6`), and `extensions`.

`GRP-4` (T). Within one file group, `(track_type, track_index)` pairs MUST be unique, except that the segments of one spanned recording share a pair (`GRP-6`). Member order is the presentation order. A `file` reference MUST resolve within the asset.

`GRP-5` (T). A file MAY belong to several file groups or to none. File group membership, not file order or any token on the file, defines which files belong together. There is no implicit grouping.

`GRP-6` (T). Spanned recordings. When one recording is split across several files, each file is a member with the same `(track_type, track_index)` pair and its own `segment_index`. Within one file group, every member that shares a pair with another member MUST carry `segment_index`, and the `segment_index` values within that pair MUST be unique. Segments MUST appear in `members` in ascending `segment_index` order, so member order and segment order agree (`GRP-4`). Numbering belongs to the original recording and starts at 0. In a complete file group, the values within a pair MUST have no gaps. In an incomplete file group (`complete: false`), missing segments leave gaps and the remaining segments keep their original numbers. A single member MAY carry `segment_index` when it is the only exported segment of a larger recording; its file group SHOULD then declare `complete: false`. `segment_index` is sequence order only: it says nothing about frame counts, durations, or where one segment ends on the asset timeline. A member with no `segment_index` is a whole recording.

## 9. Versions and relationships

`VER-1` (S). `versions` is an array of version objects, each with `id` (unique within the asset), `ordinal` (integer 0 or more), optional `label` (string), optional `created` and `modified` (date-time), and `extensions`.

`VER-2` (T). `ordinal` values MUST be unique within the asset. The version with the greatest ordinal is the current version. Array order carries no meaning; ordinal does.

`VER-3` (T). A file, file group, or annotation `version` reference MUST resolve to a version id within the same asset. A file or file group with no `version` belongs to every version. An annotation with no `version` is about the asset as a whole and applies to every version. When the asset has no `versions` array, `version` MUST be absent on every file, file group, and annotation.

`REL-1` (S). `relationships` is an array of objects with `kind` (`derived_from`, `subclip_of`, `variant_of`), `target` (reference to an asset id), optional `range` (`{start_frame, end_frame}` on the target asset's timeline in the target's time base, `TIME-12`), optional `description`, and `extensions`.

`REL-2` (S+T). `derived_from`: this asset was produced from the target. `subclip_of`: this asset is a time range of the target; `range` is required. `variant_of`: this asset is an alternative presentation of the target with the same content. These three are the complete list for this draft. Edit sequences, timelines, and transitions are out of scope.

`REL-3` (T). `target` resolves under `PKG-6`. A relationship to a target not in the package is a warning when `assets` is `partial`, and is rejected when `assets` is `complete`. A self-reference is rejected. Cycles are not checked in this draft.

## 10. Collections

`COL-1` (S). A `collection` record has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `title` | nonempty string | yes | Human name. |
| `collection_kind` | token | yes | `logical`, `storage`, `query`, `other`. `COL-2`. The field is not named `type` because `type` is the record type (`REC-1`). |
| `description` | string | no | |
| `parent` | string | no | Reference to a collection id. Absent means top level. |
| `storage` | object `{storage_location, path}` | no | Required when `collection_kind` is `storage`; otherwise absent. `storage_location` references a storage location id; `path` is opaque. |
| `members` | object `{complete, assets}` | no | `COL-3`. |
| `created`, `modified` | date-time | no | |
| `metadata` | array | no | Section 11. |
| `access` | object | yes | Section 13. |

`COL-2` (S). `logical` is a grouping made by people or rules in the source system with no storage meaning. `storage` mirrors a location in a storage system and declares it in `storage`. `query` is the result of a saved search at production time. `other` is anything else. A `storage` collection with no `storage` object, or a non-storage collection with one, is rejected.

`COL-3` (S+T). `members.assets` is an array of asset id references. `members.complete` is a boolean. The collection record is the authority for membership. When `complete` is `true`, an asset not listed is not a member. When `false`, absence means unknown, never removal. An absent `members` object means membership was not exported and is unknown.

`COL-4` (T). `parent` MUST resolve under `PKG-6`. A collection MUST NOT be its own ancestor. A cycle among collections in the package is rejected. A self-parent is rejected.

`COL-5` (T). An asset's `collections` array (section 7) is a convenience for standalone reading. Each entry is either a collection id reference (string) or a snapshot object that is a full collection record, with `type`, `spec_version`, and `id`, and without `members` (`ID-6`). When the package's `collections` registry is present, every asset-side entry MUST agree with the registry: when the referenced collection has `members.complete: true`, the asset MUST appear in its `members.assets`, and disagreement is rejected. When the referenced collection has `members.complete: false` or no `members` object, the asset-side entry is allowed and is informative; it is evidence of membership but does not make the collection's list complete. The asset-side list never contradicts a complete collection list.

## 11. Metadata definitions and values

Definitions live in the package registry. Values live on assets and collections.

`MD-1` (S). A `metadata_definition` record has:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `label` | string | no | Human label. |
| `description` | string | no | |
| `value_type` | token | yes | `string`, `integer`, `number`, `boolean`, `date`, `datetime`, `enum`, `asset_reference`, `collection_reference`. |
| `cardinality` | token | yes | `single` or `multiple`. |
| `options` | array of `{id, label}`, 1 or more | required when `value_type` is `enum`; otherwise absent | Option `id` is unique within the definition (`ID-4`). `label` is optional. |
| `constraints` | object | no | `MD-3`. |
| `required` | boolean | no | A hint from the source system. Validators do not enforce it on values. |

The definition's `id` (`REC-5`) identifies the field. A producer that needs to keep the source system's machine name uses it as the `id` when it is a valid id (`REC-5`), or records it in an extension namespace on the definition.

`MD-2` (S+T). `constraints` is a closed object with optional `minimum`, `maximum` (numbers, for `integer` and `number`), `min_length`, `max_length` (integers 0 or more, for `string`), and `pattern` (string, ECMA-262 regular expression source, for `string`). The schema checks `pattern` with the `regex` format where the validator supports it; a conformance checker MUST reject a `pattern` that is not a valid ECMA-262 expression (T). Constraints are data about the source field. They are not JSON Schema keywords and validators MUST NOT execute them over values (T).

`MD-3` (S). A metadata value object, in an asset or collection `metadata` array, has `definition` (reference to a metadata definition id, required) and `value` (required).

`MD-4` (S+T). The value representation per `value_type`:

| `value_type` | `single` value | `multiple` value |
| --- | --- | --- |
| `string` | JSON string | array of strings |
| `integer` | JSON integer | array of integers |
| `number` | JSON number | array of numbers |
| `boolean` | JSON boolean | array of booleans |
| `date` | string `YYYY-MM-DD`, valid Gregorian date | array of such strings |
| `datetime` | date-time string (section 14) | array of such strings |
| `enum` | string equal to an option `id` | array of option ids, no repeats |
| `asset_reference` | asset id reference | array of asset id references |
| `collection_reference` | collection id reference | array of collection id references |

The schema accepts only a JSON string, integer, number, or boolean, or an array of those (S). Objects, nested arrays, and `null` anywhere in a value are rejected by the schema. A value whose JSON type does not match the definition's `value_type` and `cardinality` is rejected (T). A `date` or `datetime` value with bad syntax or an invalid calendar date is rejected (T). An `enum` value that is not an option id is rejected. A `multiple` value MAY be an empty array. `null` is not a value; a producer omits the value object instead. A metadata value object MAY carry `extensions` (`EXT-1`).

`MD-5` (T). `definition` resolves under `PKG-6`. Each definition id appears at most once in one record's `metadata` array. A repeat is rejected.

`MD-6` (T). Reference-typed values resolve under `PKG-6` with the same partial-registry rule.

## 12. Annotations

An annotation is a statement about an asset, optionally about a time range of it.

`ANN-1` (S). An annotation is a nested object inside `asset.annotations`, or a standalone `annotation` record. The nested form carries no `type` or `spec_version` and MAY carry `source`; the standalone form carries all record fields of section 3. Both have:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Unique within the asset, or a record id when standalone. |
| `asset` | string | required when standalone; absent when embedded | Reference to the asset. |
| `purpose` | token | yes | `ANN-2`. |
| `title` | string | no | Short name of the annotation. |
| `text` | string | no | The annotation's content. |
| `category` | string | no | Source system label, free form. |
| `author` | string | no | Neutral name or identifier of who made it. Not a principal. |
| `language` | string | no | BCP 47 language tag for `text`. The schema checks well-formedness under the RFC 5646 section 2.1 grammar, including grandfathered forms, with the case-insensitive matching that RFC 5646 requires. Registry membership of subtags is not checked and is not required. |
| `created`, `modified` | date-time | no | |
| `start_frame`, `end_frame` | integer | no | `TIME-3`, `TIME-4`, on the asset's timeline (`TIME-12`). Absent both means the annotation is about the whole asset. |
| `start_seconds`, `end_seconds`, `start_timecode`, `end_timecode` | derived | no | `TIME-7`. |
| `version` | string | no | Reference to a version id within the asset. |
| `metadata` | array | no | Section 11. |
| `extensions` | object | no | |

`ANN-2` (S+T). `purpose` is one of `note`, `review`, `quality`, `transcript`, `chapter`, `keyword`, `other`. `note` is a free comment. `review` is an approval, rejection, or change request. `quality` is a technical quality observation. `transcript` is spoken or written content at that time. `chapter` is a structural marker. `keyword` is a tag. `other` is anything else; a producer SHOULD record the source meaning in `category` or extensions. Producers MUST NOT map a source type to a purpose it does not have; use `other`.

`ANN-3` (S+T). An annotation with any frame field on an asset that has no `timing` is rejected. Timing follows section 6 in full.

## 13. Extensions and access

`EXT-1` (S). `extensions` is allowed on every record and on these nested entity objects: file, file group, member, version, relationship, annotation, metadata value, and option. Small value objects such as manifest, checksum, rate, time base, range, connection, and access carry no extensions. `extensions` is an object whose keys are namespace tokens matching `^[a-z][a-z0-9_]{0,62}$` and whose values are objects. The inner objects are open: any JSON is allowed inside a namespace.

`EXT-2` (S+T). Every namespace token used anywhere in a package MUST be declared in `manifest.namespaces`. A declaration has `token` (required), `owner` (nonempty string, required: the organisation or product that defines the namespace), `schema` (absolute URI string, optional, informative), and `description` (optional). A used token with no declaration is rejected. A declared token that is unused is allowed. Each token MUST appear in at most one declaration; a repeated token is rejected (T).

`EXT-3` (S). The token `oasis` is reserved for this standard and MUST NOT be declared or used by producers in this draft. No other token is reserved.

`EXT-4` (T). Consumers MUST preserve every namespace they do not understand byte for byte when they re-emit the record. The preserved unit is the UTF-8 byte sequence of that namespace's value object in the input document, from its opening brace to its closing brace inclusive, with the whitespace, member order, number spelling, and escape spelling inside it unchanged. The consumer re-emits that byte sequence under the same token in `extensions`. The surrounding document MAY be re-encoded. A re-emitted record in which any unknown namespace is altered or omitted does not conform to this rule; no documented policy makes it conform. A consumer that cannot retain the bytes MUST state that its output does not conform to `EXT-4`. A consumer that does not re-emit records is not bound by this rule.

`EXT-5` (T). Standalone records outside a package MAY use undeclared namespaces, since there is no manifest. The declaration check applies in package context only.

`ACC-1` (S). `access` is a closed object `{status}` where `status` is `none`, `restricted`, or `unknown`. It is required on every asset and collection.

`ACC-2` (T). `none` means the producer knows of no access restriction on the entity. `restricted` means the producer knows of at least one. `unknown` means the producer did not or could not determine it. Details, principals, grants, and denials are not part of this draft and MAY be placed in extensions.

`ACC-3` (T). A consumer that cannot represent `restricted` or `unknown` for an entity MUST block or quarantine it. No consumer may grant wider access to an entity than its source had because the restriction could not be represented.

## 14. Date and time strings

`DT-1` (S+T). A date-time string follows RFC 3339 section 5.6 with these limits: four-digit year 0001 to 9999, a valid Gregorian date, hours 00 to 23, minutes and seconds 00 to 59, `T` or `t` separator, optional fraction with at least one digit, and `Z`, `z`, or a signed `HH:MM` offset. A space separator, an offset without a colon, and leap second 60 are rejected. `-00:00` is preserved literally.

`DT-2` (T). Format checking is required. A validator that cannot check this grammar MUST report a setup failure.

`DT-3` (T). A date string is `YYYY-MM-DD` with a valid Gregorian date. No core field is a date; the form is used by metadata values whose `value_type` is `date` and is checked under `MD-4` (T). The schema bundle carries a `date` definition for checkers to reuse.

## 15. Unsupported documents

`UNS-1` (T). A 2.0 consumer MUST NOT accept a document with no `type` or with a `spec_version` outside major 2. It reports the document as unsupported and never validates it against a 2.0 schema.

## 16. Status and claims

This is a draft. The schemas, examples, and this contract can change before a final release. Interoperability between independent implementations is not demonstrated. No adopter, vendor, or standards body is represented as endorsing it. The scope is small synthetic packages. Scale and operational limits are untested. Promotion to a final release requires two independently authored producer and consumer implementations that exchange the core profile with no unexplained loss, and a separate approval.

The standard carries no report format. How a tool reports its own conversion results is the tool's concern.

## Appendix A: decision to rule map

D1 to D6 name the steward's six design decisions for 2.0: D1 one core profile; D2 packages with registries; D3 JSON Schema 2020-12 with stable identifiers; D4 exact frame timing and explicit media structure; D5 namespaced extensions with an access summary; D6 no reporting.

| Decision | Rules |
| --- | --- |
| D1 core profile and exclusions | sections 2, 16; `REL-2`, `ACC-2`, `TIME-10` |
| D2 packages and registries | `PKG-1` to `PKG-8`, `ID-5`, `ID-6`, `COL-3`, `COL-5`, `MD-1`, `MD-3` |
| D3 2020-12, identifiers, record type and version | `REC-1` to `REC-4`, `REC-7`, `UNS-1`, the schema `$id` rule in the schema files |
| D4 time and media structure | `TIME-1` to `TIME-12`, `FILE-1` to `FILE-5`, `GRP-1` to `GRP-6`, `VER-1` to `VER-3`, `REL-1` to `REL-3`, `ANN-1` to `ANN-3` |
| D5 extensions and access | `EXT-1` to `EXT-5`, `STO-2`, `ACC-1` to `ACC-3` |
| D6 no report | section 2, section 16 |

## Appendix B: rules a schema cannot express

A conformance checker implements these checks on a document: `DOC-1` to `DOC-3`, `REC-2`, `REC-3`, `PKG-3`, `PKG-4`, `PKG-6`, `PKG-8`, `ID-1`, `ID-2`, the T part of `ID-4`, `ID-5`, `ID-6`, `TIME-2`, the T parts of `TIME-4`, `TIME-5`, `TIME-7`, and `TIME-8`, `TIME-9`, `TIME-10`, `TIME-12`, `FILE-2`, `FILE-5`, `GRP-2`, `GRP-4`, `GRP-5`, `GRP-6`, `VER-2`, `VER-3`, the T part of `REL-2`, `REL-3`, the T part of `COL-3`, `COL-4`, `COL-5`, the T part of `MD-2` (constraints are never executed; `pattern` is a valid ECMA-262 expression), the T part of `MD-4` (shape against the definition, `date` and `datetime` syntax under `DT-3` and `DT-1`), `MD-5`, `MD-6`, the T part of `ANN-2`, the T part of `ANN-3`, the T part of `EXT-2` (declared and used tokens agree; each token declared at most once), `EXT-5`, `ACC-2`, the T part of `DT-1`, `DT-2`, `DT-3`. Also the T parts of `GRP-3` (`sequence_range.start < end`) and `VER-3` (resolution and the no-versions case).

These rules state producer or consumer obligations. They are documented and are not checkable on a document alone: `SAFE-1`, `REC-4`, `PKG-5`, `ID-3`, `FILE-4`, the T part of `STO-2`, `EXT-4`, `ACC-3`, `UNS-1`.

The schema files express these parts of rules that the body marks T or S+T. A conformance checker does not need to repeat them.

- `TIME-4`: `end_frame` without `start_frame` is rejected. Order and bounds stay with a conformance checker.
- `TIME-5` and `ANN-3`: an embedded annotation with a frame field on an asset with no `timing` is rejected. Standalone annotations and relationship ranges stay with a conformance checker.
- `TIME-6`: fully expressed. `drop_frame: true` is accepted only with the exact rate objects `30000/1001` and `60000/1001`.
- `TIME-7`: a derived field without its frame field is rejected. Seconds below 0 are rejected. Agreement stays with a conformance checker.
- `TIME-8`: for `source_timecode` and embedded annotation labels, the schema checks the separator against `drop_frame`, the frame field range per rate, skipped drop-frame labels, labels without a `source_timecode` anchor, and `source_timecode` at a rate outside the table. Standalone annotation labels get syntax only. Derivation agreement stays with a conformance checker.
- `AST-2`: fully expressed. A title with no non-whitespace character is rejected.
- `REL-2`: `subclip_of` without `range` is rejected. The meaning of each kind is informative.
- `COL-2`: fully expressed. A `storage` collection without `storage`, or another collection with `storage`, is rejected. The meaning of each kind is informative.
- `MD-4`: a `null` value, an object value, a nested array, and `null` inside an array are rejected. Shape against the definition stays with a conformance checker.
- `MD-2`: `pattern` is checked with the `regex` format where supported. Authoritative ECMA-262 validity stays with a conformance checker.
- `ANN-1` and `FILE-1`: `language` is checked for RFC 5646 well-formedness and `media_type` for RFC 6838 `type/subtype` syntax. Neither registry is consulted.
- `EXT-3`: fully expressed. The token `oasis` is rejected as an extension key and as a declared token.

Schema patterns use ECMA-262 semantics. Some regular expression engines let `$` match before a final newline. The conformance harness configures its checker so that this never happens.
