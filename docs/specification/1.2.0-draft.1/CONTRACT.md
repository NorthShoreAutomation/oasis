# OASIS 1.x contract

Status: DRAFT 1.2.0-draft.1. Approved for publication as a draft. Not a final release. Interoperability between independent implementations is not yet demonstrated.
This text does not claim certification or production readiness.
OASIS means Open Asset Standard Interchange Schema.
The accompanying [glossary](GLOSSARY.md) defines neutral concepts.

## Reading this contract

The normative sections define the selected profile's behavior.
Examples, mapping guides, and comparisons with other standards are informative.
Sections from Published structural baseline through Proposed result protocol are the normative core and explicit profile rules.
Reading this contract and Evidence and claims are informative.
`legacy-1x` claims structural validation only. A semantic inspection claim requires `exchange-1x` and its stated limitations.
Normative `MUST`, `MUST NOT`, and `SHOULD` express requirements for the selected profile.
An optional profile must be selected explicitly. It cannot silently tighten the legacy wire contract.

Schema acceptance, semantic outcome, import outcome, and preservation are distinct results.
Passing one does not prove the others.
Validation MUST NOT grant filesystem, network, media, or credential access.
Applications remain responsible for authorization and execution controls.

## Published structural baseline

The reference baseline is the eight Draft 7 schemas from public commit `1e2849b287bba42fbe6c1767a49f6016ddaff58a`.
The DRAFT proposes no added wire properties, required-field changes, enum changes, or replacement of embedded copies.
The selected entry point and its embedded definitions determine structural acceptance.

| Entry point | Required root fields | Context limits |
| --- | --- | --- |
| `asset.schema.json` | `asset_id`, `title`, `type` | Root open; file and embedded entity roots are closed; metadata field objects remain open. |
| `collection.schema.json` | `collection_id`, `label` | Root open; `assets` contains strings; embedded metadata and storage are closed. |
| `metadata_set.schema.json` | `fields` | Root and field objects open; `set_id` is optional. |
| `storage_location.schema.json` | `storage_id`, `system`, `path` | Root and connection/security objects open. |
| `temporal_annotation.schema.json` | `source_id` | Root open; standalone timing conditions apply. |
| `asset_batch_import.schema.json` | `assets` | Nonempty array of standalone assets; relative schema dependency. |
| `collection_batch_import.schema.json` | `collections` | Nonempty array of standalone collections; relative schema dependency. |
| `migration-report-output.schema.json` | `report_id`, `report_version`, `generated_at`, `database_info`, `asset_summary` | Closed root; retained application report, outside the exchange profile. |

An asset file requires `type`, `role`, `uri`, and embedded `storage_location`.
A storage identifier alone does not replace that location.
Standalone metadata may omit `set_id`; embedded metadata requires it.
Embedded metadata explicitly permits unconstrained `value`. Standalone fields accept it as open extra data.
Embedded collection membership accepts arbitrary JSON items; standalone membership permits only strings.
Embedded annotations lack the standalone timing requirements and timecode pattern.
Defaults are schema annotations. Validators MUST NOT insert them into records.

Published 1.1 file grouping remains unchanged: equal file `role` values within one asset form one logical media group.
That legacy interpretation cannot represent every independent rendition or track.
Keep the legacy annotation tokens `Generic`, `Comments`, `QualityControlMarker`, and `Transcription` literally.
Absent `annotation_type` remains absent. It does not become an emitted `Generic` value.
Mappings must explain uncertainty rather than assigning a universal destination meaning to those tokens.

## Proposed profiles

### `legacy-1x`

Validate the selected baseline schema and its dependencies.
Record whether date-time formats were checked.
Return structural results without semantic diagnostics.
Do not infer version routing, value constraints, completeness, import permission, or preservation.
Unchecked historical format mode is permitted only as an explicitly labelled baseline comparison.
The ordinary documented mode requires a working date-time checker. Missing support is a setup failure.

### `exchange-1x`

Use the same structural entry points for the seven interchange schemas.
Exclude the application-specific migration report.
Run upgraded version routing, structural validation, and the bounded rules below.
Run semantic checks only when routing succeeds and the document is structurally valid.
Warnings do not make structural acceptance false. Errors block this selected profile.
No profile result authorizes a production import.

This profile inspects risk and preserves opaque data.
It does not prove that every accepted field has portable business meaning.
Unsupported value semantics, timing conversions, references, rights, and completeness stay visible in results.

## Input, formats, and outcome order

Inputs MUST be UTF-8 JSON under [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259.html), with unique object member names and valid Unicode scalar values.
Reject a byte-order mark, duplicate member names, NaN, Infinity, malformed encoding, and unpaired surrogate escapes as `INPUT_INVALID` at the root.
These are selected transport parsing rules. Frozen schema bytes remain unchanged.
This parsing policy does not claim acceptance equivalence with every historical parser.
Preserve exact finite JSON numbers before conversion into runtime numeric types.
Numeric schema assertions and semantic comparisons MUST use the original mathematical values, including integers beyond binary64 precision.
Complete strict syntax and Unicode checks before reporting a per-input numeric resource refusal.
Retain lossless number tokens during this check; defer expensive exact-number construction until resource checks pass.
After strict parsing and before routing, check the selected engine's numeric capability.
An adapter incapable of exact evaluation for this input fails setup with a stated limitation. It MUST NOT silently round and report conformance.
Do not impose an integer-size limit that the selected schema does not contain.
An engine capability failure is not a structural rejection or an exception to mathematical comparison.
Record engine-specific setup limitations separately from the normative structural expectation.
Both proposed structural adapters must cover ordinary decimal seconds, rates such as 23.976, 29.97, and 59.94, and exact large integers.
The proposed Go adapter retains lossless numeric tokens and uses exact rational arithmetic.
Strict parsing must inspect original bytes before any decoder can replace invalid Unicode or discard duplicate members.
An adapter may refuse an input for a declared resource limit before numeric conversion.
Such refusal reports `setup-failed`, `structural: not-run`, and no document diagnostics; it does not narrow OASIS acceptance.
Report the configured resource limits and the exceeded limit without echoing input values.
No resource thresholds or broad executed portability claim are established by this draft.
Any engine exclusion requires explicit approval before it can qualify a coverage claim.

Schema `pattern` and `patternProperties` use ECMA-262 semantics without flags. For the bundled patterns, `\d` matches ASCII digits only and `$` matches only the absolute end of the string.
Apply this in both format modes; historical-unchecked disables date-time assertions only.
A metadata field's stored `pattern` string is data, not a schema assertion to execute.
Native-engine deviations must be recorded separately, not silently accepted as conformance.

Required-format mode uses the following common date-time configuration for both structural engines.
This configuration is explicit; it does not claim equivalence with every historical validator configuration.
Use the calendar and offset grammar in [RFC 3339 section 5.6](https://www.rfc-editor.org/rfc/rfc3339.html#section-5.6), with these selected limits:
four-digit years 0001-9999; valid Gregorian dates; hours 00-23; minutes and seconds 00-59;
`T` or `t` separator; optional decimal fraction with at least one digit; and `Z`, `z`, or signed `HH:MM` offset.
Offset hours are 00-23 and offset minutes are 00-59. Preserve `-00:00` literally without inferring a known local offset.
Do not accept a space separator, an offset without its colon, or leap-second labels in this selected configuration.
The latter is an explicitly selected subset, not a claim that RFC 3339 forbids leap seconds.
Apply format checking only at schema-declared `format: date-time` properties, including their declared embedded copies.
Do not inspect custom timestamp-like strings or metadata values.
Python MUST pass a format checker and verify `date-time` registration. Go MUST explicitly register the common date-time checker.
In historical-unchecked mode, Go MUST override its Draft 7 date-time assertion with a no-op checker.
Both adapters MUST enforce this same grammar instead of accepting any extra syntax their native checkers permit.
Native-checker differences are separate portability evidence, not silently accepted conformance exclusions.
`exchange-1x` requires `format_mode: required`; unchecked mode is only a labelled `legacy-1x` historical comparison.

For every direction, the profile outcomes below describe the input document.
Run setup, parse the input, check numeric capability and resources, determine routing, and always run structural validation on a successfully parsed input after successful setup.
Run semantic checks only for selected, structurally valid `exchange-1x` input.
Routing failures suppress semantic checks, but do not suppress the independent structural result.
For excluded entry points, report only the profile routing error, not additional version errors.

| Condition, in precedence order | Routing | Structural | Execution status | Diagnostics |
| --- | --- | --- | --- | --- |
| Missing resource, unknown profile, or other environment setup failure | `not-applied` | `not-run` | `setup-failed` | Empty; setup explanation is in limitations. |
| Invalid input bytes or JSON parsing policy | `not-applied` | `not-run` | `input-invalid` | `INPUT_INVALID` at root. |
| Strictly parsed input outside exact-number capability or declared numeric resources, before routing | `not-applied` | `not-run` | `setup-failed` | Empty; engine or resource limitation is recorded. |
| Parsed `legacy-1x`, valid or invalid | `not-applied` | Actual `valid` or `invalid` | `complete` | Empty semantic list. |
| `exchange-1x` on an excluded entry point | `unsupported` | Actual `valid` or `invalid` | `unsupported` | `PROFILE_UNSUPPORTED` at root. |
| Unsupported interchange selector, including a non-string value | `unsupported` | Actual `valid` or `invalid` | `unsupported` | `VERSION_UNSUPPORTED` at each offending declared selector. |
| Selected `exchange-1x` with structural rejection | `selected` | `invalid` | `blocked` | No semantic diagnostics. |
| Selected and structurally valid `exchange-1x` with any semantic error | `selected` | `valid` | `blocked` | All applicable semantic diagnostics. |
| Selected and structurally valid `exchange-1x` with warnings or no diagnostics | `selected` | `valid` | `complete` | All applicable semantic diagnostics. |

`complete` means the inspection ran. It does not mean import success, preservation, or the absence of warnings.
`not-run` is permitted only for setup or input-parsing failure.

## Version selection

The caller MUST select an entry point, bundled schema revision, and profile before validation.
No record label triggers remote schema retrieval.
Record the chosen revision independently of wire labels.

For `exchange-1x`, declared interchange `schema_version` values `1.0.0`, `1.1.0`, `1.1.1`, and proposed `1.2.0-draft.1` route to the caller-selected bundled contract.
The pre-release label distinguishes this DRAFT from a future final release.
Published 1.1.x descriptions and examples also use `1.0.0` as an individual-schema version example.
Accept that documented label without changing the record or selecting historical schema bytes automatically.
None of these labels alone establishes the producer's release, export history, or intended file-grouping meaning.
The caller records its explicit bundle and profile selection; no label alone authorizes a business interpretation.
Original 1.0 schemas differ in descriptions and identifiers; the report also has different declared properties.
Selecting this bundle does not assert that every historical 1.0 meaning matches its guidance.
Legacy structural validation remains available without reinterpreting labels.
New producers using these DRAFT rules SHOULD emit `1.2.0-draft.1` only where the selected shape declares `schema_version`.
Preservation and replay MUST keep an existing selector or its absence unchanged.
An absent selector uses the caller's explicit selection. Do not write it into the record.
Any other value, including a non-string, produces `VERSION_UNSUPPORTED` at its selector path.
Accepted 1.0, 1.1, and DRAFT labels may coexist within a batch under the same explicitly selected bundle.
Inspection preserves their literal labels and values; it does not infer different business meanings from them.
A supported 1.x label combined with any unsupported label blocks routing.

Inspect only declared interchange selectors: asset, collection, metadata-set, storage-location, and batch root `schema_version` properties.
Also inspect those properties on standalone assets and collections inside their batch arrays.
Do not treat arbitrary custom objects as record selectors.
Embedded definitions do not acquire new selectors.
Standalone temporal annotations have no declared interchange version field; their revision comes from caller selection.
Do not repurpose a custom annotation `schema_version` value as a newly reserved field.
An asset's `version` is a free legacy field, not a contract selector.
The report's `report_version` and `database_info.schema_version` describe the report and source database, not this interchange contract.
Legacy validation may accept v2-labelled inputs. Delivery to an unmodified 1.x consumer is not safe version routing.

## Rule locations

Resolve these templates from the selected entry point, not from arbitrary matching keys or the fixture context label.
`<i>` denotes an array index. Only existing, schema-declared relationships are traversed.

| Entity template | Locations |
| --- | --- |
| `{A}` asset | Asset root, or `/assets/<i>` in an asset batch. |
| `{C}` collection | Collection root, `/collections/<i>` in a collection batch, or `{A}/collections/<i>`. |
| `{F}` file | `{A}/files/<i>`, recursively followed by any number of `/derivatives/<i>` components. |
| `{S}` storage | Storage root, `{F}/storage_location`, or `{C}/parent_storage`. |
| `{M}` metadata set | Metadata-set root, `{A}/metadata_sets/<i>`, or `{C}/metadata_sets/<i>`. |
| `{T}` annotation | Temporal-annotation root, or `{A}/temporal_annotations/<i>`. |

| Rule family | Exact locations |
| --- | --- |
| Identity | `{A}/asset_id`, `{C}/collection_id`, `{S}/storage_id`, `{M}/set_id`, `{M}/fields/<i>/name`, `{T}/source_id`. |
| Version routing | Declared standalone root `schema_version`, batch root `schema_version`, and batch-contained standalone assets/collections. No embedded or custom selectors. |
| Duplicates | `/assets/<i>/asset_id` or `/collections/<i>/collection_id` in the respective top-level batch. |
| Parent references and cycles | `{C}/parent`; multi-record cycles only in a top-level collection batch. |
| String membership references | `{C}/assets/<i>`, including embedded collections. |
| Opaque membership | Non-string `{C}/assets/<i>` items. |
| Size and integrity | `{F}/size`, `{F}/checksum`, or `{F}` for missing/empty checksum. |
| Metadata values | `{M}/fields/<i>/value` when present. |
| Annotation checks | Declared timing and rate properties under `{T}`. |
| Connection data | `{S}/connection_details`. |
| Rights | `{A}/rights_information`, `{C}/permissions`, `{S}/security`. |
| Completeness | Document root for either batch entry point. |

Do not recurse into opaque `extensions`, `technical_metadata`, annotation `metadata`, connection data, security, permissions, unknown open-object properties, or non-string membership items.
Their contents are preserved without acquiring identity, timing, rights, or selector semantics from matching key names.

## Identity and relationships

The profile MUST preserve explicit identifiers without trimming or rewriting them.
An explicitly present `asset_id`, `collection_id`, `storage_id`, `set_id`, annotation `source_id`, or metadata field `name` is unusable if it contains only whitespace or is empty.
For this bounded check, whitespace means the ASCII characters space, tab, carriage return, line feed, form feed, and vertical tab.
Report `IDENTITY_UNUSABLE` at the exact value path.
Do not add a required identity where the selected legacy shape permits absence.
Do not treat titles or labels as identifiers.

Within a top-level asset or collection batch, repeated primary IDs produce `IDENTITY_DUPLICATE` on each repeated occurrence after the first.
Its path is the repeated identifier property, not the containing record.
Compare strings exactly. Do not case-fold, trim, or infer a global source namespace.
Repeated embedded entities are preserved; this profile does not resolve their cross-record authority.
Retry, merge, and global deduplication behavior are outside the profile.

The caller context has exactly `asset_ids` and `collection_ids`, each a list of nonblank strings; malformed context fails setup.
Repeated context IDs are treated as a set. They do not introduce graph edges or authority over records.
For a standalone collection, known collection IDs are its usable own ID plus context IDs; known assets come from context.
For a collection batch, known collection IDs are usable top-level IDs occurring exactly once plus context IDs; known assets come from context.
For an asset, known assets include its usable own ID plus context IDs; known collections include usable IDs occurring exactly once in that asset's embedded collection list plus context IDs.
For each asset in an asset batch, known assets include usable top-level batch IDs occurring exactly once plus context IDs; known collections are local to that asset's embedded list plus context IDs.
Within each applicable input list, unusable or repeated IDs are excluded from resolution and graphs; caller context MUST NOT override their exclusion.
Repeated embedded entities remain preserved and do not acquire cross-record authority.
Other entry points have no collection-reference checks.
Resolve both embedded and standalone collection parents and string memberships against these sets.
An absent or null parent means no parent link; it does not imply a removal operation.
Do not fetch missing targets.
An unknown parent or string membership target produces `REFERENCE_UNRESOLVED` at the reference path.
An embedded collection item that is not a string produces `MEMBERSHIP_UNINTERPRETED` at that item path.
Its legacy structural acceptance remains unchanged.
Do not extract or assume an authoritative asset identity from arbitrary embedded membership objects.

For a collection batch, detect parent cycles only among usable top-level collection IDs occurring exactly once.
Exclude edges whose source or target is excluded. Do not use first-wins or last-wins duplicate maps.
Also report a self-parent link on any usable, nonexcluded standalone or embedded collection.
Report `COLLECTION_CYCLE` at the full `{C}/parent` path for each included parent edge belonging to a cycle or self-loop.
Do not diagnose a cycle that depends on unknown external records.
Ordering is not required. Missing parents are not fabricated.
Omitted, empty, partial, and unresolved membership MUST NOT imply deletion or removal.
Neither an asset-side nor collection-side list is declared the complete authoritative snapshot.

## Files, storage, and integrity

Keep the required embedded storage record and all accepted locator strings.
Validation MUST NOT open a locator, resolve credentials, hash media, or connect to a storage provider.
The recorded location need not be exhaustive. Multiple physical copies are not inferred.
Preserve file order and role strings. Do not split or create groups during inspection.
The equal-role grouping guidance is published 1.1 meaning; no wire label alone establishes that meaning for an older producer.
Apply file rules recursively to `derivatives` in their original array order.

A negative declared file `size` produces `SIZE_UNUSABLE` at the size path in this profile.
An absent size remains absent. Do not replace it with zero.
An absent or empty checksum produces `INTEGRITY_UNVERIFIED` at the file-object path.
A nonempty checksum produces `CHECKSUM_UNINTERPRETED` at its property path.
The legacy string does not define the algorithm, trusted expected value, or covered bytes.
Neither diagnostic certifies media integrity or corruption.

Every batch produces `COMPLETENESS_UNVERIFIED` at the document root.
Array length, optional custom counts, and custom checksum strings do not establish the source export's complete scope.
No new batch count, checksum, source identity, or stream manifest field is introduced.
Streaming and newline-delimited framing are outside this DRAFT.

## Metadata and annotations

Keep metadata field definitions and values as recorded.
Do not execute a field's `required`, `type`, `pattern`, `minimum`, `maximum`, `minLength`, `maxLength`, `enum_values`, or `multi_select` declarations as JSON Schema keywords over its value.
A present field `value` produces `VALUE_SEMANTICS_UNSPECIFIED` at that property path.
This reports the lack of a fully selected value-representation contract; it does not assert the value is wrong.
Do not coerce values, choose enum precedence, insert defaults, or invent missing set identifiers.

Preserve annotation classification, raw categories, and timing fields.
A supplied zero `frame_rate` produces `RATE_UNUSABLE` at its property path.
For each complete numeric pair, frames or seconds, report `RANGE_REVERSED` at its end path when end is less than start.
This check applies to complete pairs even on point markers. A contradictory supplied end is reported; it is not discarded.
Do not compare fields across units or convert timecode.
If timing uses both frames and seconds, or any timecode field, produce `TIMING_UNINTERPRETED` at the annotation-object path.
Frame timing means a present `start_frame` or `end_frame`; seconds timing means a present `start_seconds` or `end_seconds`.
`frame_rate` alone does not count as a frame position or mixed units.
The warning applies even when a rate is supplied because origins, conversion, and endpoint conventions remain unspecified.

If a range marker does not have a complete same-unit numeric pair and has no timecode fields, report `TIMING_UNINTERPRETED`.
Treat explicit `is_point_marker: true` as a point only when deciding whether a complete range is missing; otherwise require a complete pair for that warning check.
A point with no start position also produces `TIMING_UNINTERPRETED`.
Frame positions without an explicit positive rate produce `TIMING_UNINTERPRETED`, unless already reported at that annotation path.
Produce at most one timing warning per annotation.
A positive legacy decimal rate is retained literally. It is not converted into an exact rational rate.
This profile does not define valid drop-frame numbering, absolute clock origin, endpoint inclusivity, duration, or edit-sequence preservation.

## Connection data and rights

Nonempty declared `connection_details` produces `CONNECTION_DATA_UNREVIEWED` at that object path.
The profile blocks such data until a separately approved connection policy exists.
An empty object is permitted; it does not establish access rights.
Do not attempt to identify secrets by guessed field names or publish their values in diagnostics.
No result certifies that arbitrary custom data is secret-free.

Nonempty declared asset `rights_information`, collection `permissions`, or storage `security` produces `RIGHTS_UNSUPPORTED` at its property path.
This DRAFT does not map principals, grants, denials, inheritance, or legal permissions.
Applications MUST NOT silently broaden access or drop restrictions to proceed.
The validator only reports the blocked profile outcome. Application enforcement is separate.

## Extension and preservation rules

Preserve every schema-accepted property, including unknown open-object properties, and keep field absence distinct from null or empty values.
Do not add extensions to closed file or embedded objects.
Prefixes mentioned in legacy descriptions are guidance, not a new universal rejecting constraint.
Do not reserve an existing custom key by adding an optional typed field.

For producer/consumer comparisons, compare decoded JSON trees recursively.
Ignore object-key order and serialization whitespace.
Keep array order, keys, strings, null, booleans, numbers, and property absence.
Booleans are distinct from numbers. Mathematically equal JSON numbers MUST compare equal when parsed without precision loss, including `25`, `25.0`, and `2.5e1`.
Do not round numbers to fit a runtime. A consumer that cannot preserve a value must report unsupported preservation.
Unicode normalization, date rewriting, path normalization, default insertion, and token replacement are not permitted transformations.
No media bytes or production import side effects are covered by this comparison.

## Diagnostic catalog

Paths use [JSON Pointer, RFC 6901](https://www.rfc-editor.org/rfc/rfc6901.html).
The root path is the empty string. Escape `~` as `~0` and `/` as `~1` in object keys.
Array components use zero-based indexes.
Sort pointer strings in their RFC 6901 escaped form by Unicode scalar value, then code by ASCII character value.
Compare Unicode scalar values, not UTF-16 code units; do not unescape `~0` or `~1` for sorting. Array index components sort lexically, not numerically.
For example `/assets/10/asset_id` precedes `/assets/2/asset_id`.
Deduplicate equal code/path pairs. Compare the resulting sorted lists, not insertion order or message text.
Severity is fixed by code. Messages are informative and must not echo input values.
Schema errors appear separately as structural acceptance and do not become unspecified semantic codes.

| Code | Severity | Meaning |
| --- | --- | --- |
| `INPUT_INVALID` | error | Input bytes cannot be parsed under the explicit JSON transport policy. |
| `VERSION_UNSUPPORTED` | error | An explicit interchange version cannot route under this profile. |
| `PROFILE_UNSUPPORTED` | error | The known selected profile does not include this entry point. |
| `IDENTITY_UNUSABLE` | error | An explicit identity is empty or only defined whitespace. |
| `IDENTITY_DUPLICATE` | error | A top-level batch repeats its primary ID. |
| `COLLECTION_CYCLE` | error | An included collection parent edge belongs to a known batch cycle or self-loop. |
| `SIZE_UNUSABLE` | error | A declared file size is negative. |
| `RATE_UNUSABLE` | error | A supplied annotation frame rate is zero. |
| `RANGE_REVERSED` | error | A complete numeric timing pair ends before it starts. |
| `CONNECTION_DATA_UNREVIEWED` | error | Nonempty connection data needs an approved policy. |
| `RIGHTS_UNSUPPORTED` | error | Nonempty declared restrictions cannot be mapped by this profile. |
| `REFERENCE_UNRESOLVED` | warning | A collection reference cannot resolve within explicit context. |
| `MEMBERSHIP_UNINTERPRETED` | warning | Embedded membership has no selected portable interpretation. |
| `VALUE_SEMANTICS_UNSPECIFIED` | warning | A recorded metadata value lacks the selected representation contract. |
| `TIMING_UNINTERPRETED` | warning | Timing meaning or conversion remains unsupported. |
| `INTEGRITY_UNVERIFIED` | warning | No usable expected file checksum is present. |
| `CHECKSUM_UNINTERPRETED` | warning | A checksum string lacks defined verification context. |
| `COMPLETENESS_UNVERIFIED` | warning | Source export completeness has not been established. |

An unknown profile ID or missing fixture resource is a setup failure, not a document diagnostic.
A structural rejection blocks `exchange-1x` without running semantic checks; structural diagnostics remain in the validator result.
A known profile used on an excluded entry point produces `PROFILE_UNSUPPORTED` and no semantic inspection.
Its path is the root. All other code paths are the exact locations specified by their rule paragraphs and location table.
Unsupported routing precedes semantic checks; no semantic diagnostics are emitted after a routing failure.

## Proposed fixture manifest

The corpus has `manifest_version`, `status`, `profiles`, `provenance`, and a `cases` array.
It also has `contract_revision`, identifying the selected DRAFT proposal, and `baseline_public_commit`, identifying the frozen public schema source.
`context` vocabulary is `standalone`, `asset-embedded`, `asset-batch`, `collection-batch`, or `asset-batch-embedded`.
Batch-root records use the appropriate batch label. The placement of the feature being tested selects an embedded label.
Context is descriptive only; the entry point and profile determine which rules execute.
Each case has these fields:

| Field | Meaning |
| --- | --- |
| `id` | Stable fixture ID, independent of file ordering. |
| `schema_name` | One of the eight bundled schema filenames. |
| `path` | Relative input file path beneath the fixture directory. |
| `profile` | Required selected profile ID. |
| `context` | Structural placement label; never profile selection. |
| `expected_valid` | Expected normal-mode structural acceptance, independent of routing outcome; null only for input-parse failure. |
| `validator_expectations` | Each engine has `required` and `historical-unchecked` structural booleans or null, `adapter_status` (`complete`, `input-invalid`, or `setup-failed`), and `limitation` string or null. Null structural values mean no engine evaluation. |
| `expected_diagnostics` | Code/path pairs; severity comes from this catalog. Structural-only cases use an empty list. |
| `expected_execution_status` | Outcome-table status for the selected profile. |
| `expected_routing` | Outcome-table routing value. |
| `input_kind` | `json` or `raw-json` for strict-parser failure cases. |
| `reference_context` | Known asset and collection IDs supplied separately from the document. Empty context is explicit. |
| `provenance` | Synthetic authorship, source, and pending or approved reuse terms. |
| `exclusions` | Engine limitations with `validator`, `status` (`proposed` or `approved`), and `reason`; an empty list means none. Proposed exclusions do not authorize a conformance claim. |

The optional `preservation_comparisons` array declares comparator examples, not executed producer/consumer evidence.
Each example has a unique `id`, `source_case_id`, `output_case_id`, `expected_status` (`preserved` or `changed`), and sorted `paths`.
Both case references MUST exist and name parseable inputs. Compare their trees under the preservation rules below.
These expected outputs are synthetic comparator inputs, not claimed implementation output.

Manifest loading MUST reject unknown profiles, missing inputs, duplicate fixture IDs, unknown diagnostic codes, and invalid pointers.
A case's `expected_valid`, routing, diagnostics, and execution status describe a fully capable selected-profile adapter.
Engine `adapter_status: setup-failed` overrides that case outcome for the limited engine: routing `not-applied`, structural `not-run`, execution `setup-failed`, and empty diagnostics.
`adapter_status: complete` means structural checking ran; it does not override semantic blocked or unsupported case status.
For raw-input rejection, both engine mode values are null and adapter status is `input-invalid`.
Engine limitations apply equally to both format modes. Historical-unchecked disables only date-time checks, not strict parsing or exact-number policy.

Fixtures for the same document may select different profiles and must retain those selections through result serialization.
Schema checks MUST run independently to record `expected_valid` on parsed input, even when profile routing blocks semantic inspection.

## Proposed result protocol

The future `result.schema.json` will use Draft 7 and reject undeclared result fields.
Require `protocol_version: "1.0.0"` and the following fields on each result:

- `implementation`: object with `id`, `version`, `source_revision`, `authors`, `dependencies`, and `independence_claim`.
- `fixture_id`, `schema_name`, `schema_revision`, `profile`, and `context`: strings identifying the exact case and bundled artifacts.
- `direction`: `validate`, `produce`, `consume`, or `round-trip`.
- `format_mode`: `required` or `historical-unchecked`.
- `routing`: `selected`, `unsupported`, or `not-applied`.
- `structural`: `valid`, `invalid`, or `not-run`.
- `diagnostics`: array of objects with `code`, `path`, `severity`, and `message`.
- `execution_status`: `complete`, `blocked`, `unsupported`, `setup-failed`, or `input-invalid`.
- `preservation`: object with `status` set to `not-tested`, `preserved`, `unsupported`, or `changed`, plus an array of changed JSON Pointer paths.
- `output`: the decoded produced or retained document, or null when no output is emitted.
- `reproduction`: object with `command`, `input_sha256`, `artifact_sha256`, and explicit limitations.

Require SHA-256 digests as 64 lowercase hexadecimal characters and source revisions as nonempty immutable identifiers.
The input digest covers the exact UTF-8 input-file bytes.
The artifact digest covers the exact schema-bundle manifest bytes; that manifest lists each schema digest and its local resolution identity.
The proposed bundle manifest has `manifest_version: "1.0.0"`, `bundle_revision`, and a `schemas` array.
`bundle_revision` is a nonempty string matching `[A-Za-z0-9][A-Za-z0-9._-]*`, without URI separators or escape sequences.
Each schema entry has `name`, a bundle-relative `path`, `sha256`, its existing `id` or null, absolute `base_uri`, and `aliases` used for local registration.
For schemas with an absolute root `$id`, `base_uri` equals that existing identifier.
Otherwise use `https://schemas.oasis.invalid/bundles/<bundle_revision>/<name>` as the absolute loader base.
Register each schema under its base, its bundle URI, and declared aliases; resolve relative references by RFC 3986 against that base.
Compile each entry point by its manifest `base_uri`, not an arbitrary alias.
Use separate registries for frozen and current bundles. Reject alias collisions, unknown resources, and retrieval fallback.
Each manifest path MUST stay within its bundle; reject absolute paths and parent traversal during setup.
Create both the frozen `tests/conformance/baseline/bundle-manifest.json` and current `definitions/bundle-manifest.json` before serializing any result samples.
Verify packaging and refresh the current manifest after approved schema edits. Keep the frozen manifest unchanged.
Pin schema, fixture, and bundle-manifest JSON bytes with repository attributes disabling text conversion and filters.
Aliases are identifiers only. None is retrieved from a network.
The bundle manifest is distribution metadata, not a new OASIS record or export-completeness claim.
Do not hash the result object into one of its own fields.
Local reference-harness results MUST declare `independence_claim: false`.
For `direction: validate`, preservation is `not-tested` and output is null.
A blocked, unsupported, input-invalid, or setup-failed case MUST NOT claim a successful import.
Inspection and opaque retention are distinct: blocked data may still be retained unchanged without execution or access.
For directions other than validation, record real preservation evidence even when the semantic profile is blocked.
If there is no comparable emitted or retained output, use `preservation.status: unsupported`, not `not-tested`.
For validation, use `not-tested` and output null regardless of profile outcome.
A valid structural result can coexist with a blocked semantic profile.
Actual diagnostic severities must match the code catalog; validate that cross-field rule in the harness if the result schema cannot express it simply.

| Direction | Input and operation | Output and preservation comparison |
| --- | --- | --- |
| `validate` | The fixture's serialized JSON input; inspect it under the selected profile. | Output null and preservation `not-tested`. |
| `produce` | The exact decoded fixture tree as neutral source state; emit a serialized record under the selected entry point. | Parse the emitted record under the same strict input policy and compare its tree against that source tree. |
| `consume` | The serialized fixture record; retain it in application or quarantine state without unauthorized execution. | Export a snapshot of the actual retained state and compare against the original parsed fixture tree. |
| `round-trip` | The decoded fixture source tree; produce, consume, then export retained state. | Compare the final exported tree against the original source tree. |

Any serialized emitted or exported output MUST use the same strict parsing policy before comparison.
If output parsing fails, report preservation `unsupported`, output null, empty paths, and an explicit limitation; input inspection outcomes remain separate.
All directions MUST run input inspection under the selected profile and report its routing, structural, and semantic outcomes.
No direction changes a blocked inspection into successful import authorization.
Retention may use quarantine; a snapshot must reflect actual retained state, not return the original input while ignoring losses.
For comparable output, preservation is `preserved` exactly when trees compare equal; otherwise `changed` with the changed leaf paths.
Report missing or added members at their member path, array-length differences at the array path, and scalar/type differences at the differing value path.
When array lengths differ, also compare every shared-prefix index recursively; do not report individual missing or added tail indexes.
Sort and deduplicate changed paths using the same lexical pointer order as diagnostics.
The preservation `paths` array is empty for `preserved`, `unsupported`, or `not-tested`.
Use null output for no output; distinguish a successfully emitted JSON null by its preservation status and comparison result.
Primitive field shapes in implementation metadata are: nonempty strings for ID, version, and source revision; string arrays for authors and dependencies; a boolean for independence claim.
Reproduction commands MUST be repository-relative and free of credentials. Result files remain as sensitive as their input and output.
Only approved synthetic-corpus results may be proposed for public distribution; private-input results remain private.
Protocol 1.0.0 rejects unknown fields. A later additive contract needs a new reviewed protocol minor version and its own result schema; it must not silently extend 1.0.0.

Compare results by fixture ID, selected profile, format mode, direction, routing, execution status, structural outcome, sorted diagnostic code/path/severity, and preservation outcome.
Do not compare exact message prose.
Do not use agreement between two validators as independent implementation evidence.

## Evidence and claims

The corpus is synthetic. It describes declared expectations until a runner executes them.
Format-checker differences must be recorded per validator and fixture, not hidden by changing expected acceptance.
Independent producer/consumer evidence is incomplete for this DRAFT.
No adopter, vendor, or standards body is represented as endorsing the draft.
The scope covers small synthetic records and batches only. Scale and operational limits are untested.
The license is in LICENSE. Contribution rules are in CONTRIBUTING.md. Governance is in docs/GOVERNANCE.md. Promotion to a final release requires separate approval.
