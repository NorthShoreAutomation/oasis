# OASIS 2.0.0-draft.2 examples

Status: DRAFT 2.0.0-draft.2, not a final release. These examples can change before the final release.
Interoperability between independent implementations is not demonstrated.

Every example is synthetic. Names such as "Example Archive" and `vendor_a` are placeholders. No example describes a real organization, product, or person.

Each example is one JSON document. Its root `type` selects the schema of the same name in [`definitions/`](../README.md).
`tests/conformance/test_examples.py` checks every example. Each example:

- passes the strict JSON input policy;
- is structurally valid against its 2.0 schema, with format checking on;
- passes the semantic checks with exactly the diagnostics listed in [Declared warnings](#declared-warnings), and no error.

To check one example yourself, run this from the repository root after setup:

```sh
python3 -m tests.conformance.validate definitions/examples/package-complete.json
```

## Minimal examples

`asset-minimal.json` shows the smallest valid asset: `type`, `spec_version`, `id`, `title`, and the required `access` summary. The access status is `unknown`.

`collection-minimal.json` shows the smallest valid collection: a `logical` collection with a title and an access summary. It has no `members` object, so membership is unknown.

`storage_location-minimal.json` shows the smallest valid storage location: a name and a `system` token.

`metadata_definition-minimal.json` shows the smallest valid metadata definition: an id, the `string` value type, and `multiple` cardinality.

`annotation-minimal.json` shows the smallest valid standalone annotation: the `asset` reference and a `purpose`. With no frame fields, the annotation is about the whole asset.

`package-minimal.json` shows the smallest valid package: a manifest with zero counts, all kinds `complete`, and an empty namespace list. All four registry arrays are absent.

## Full examples

`asset-full.json` shows every asset field. The asset runs at `25/1` with source timecode anchor `10:00:00:00` and 750 frames. It has a two-version chain, files with checksums of two algorithms, each file with a `role` and two with a `label`, a primary file group with video and stereo audio and a thumbnail file group, both with a `label`, a `derived_from` and a `subclip_of` relationship, three metadata values, one annotation with a title, source provenance, derived seconds, and timecode labels, a collection reference and a collection snapshot, a `restricted` access summary, and extensions. It also carries `deleted`, so it is a tombstone. As a standalone record, its references are not checked.

`collection-full.json` shows every collection field. It is a `storage` collection, so it declares the storage location and path it mirrors. It has a parent, an incomplete member list, metadata, provenance, and extensions.

`storage_location-full.json` shows every storage location field, including a description, created and modified dates, and a `connection` with a method token and an opaque credential reference. No secret value appears. A connection may also carry only the method.

`metadata_definition-full.json` shows every field that a `string` definition may carry: label, description, the `required` hint, and informative constraints. `options` is absent because only an `enum` definition has options. `package-complete.json` shows an `enum` definition with options.

`annotation-full.json` shows every standalone annotation field, including `title`. Its frames, seconds, and labels assume the timeline of `asset-full.json`: frames 250 to 300 at `25/1` from anchor `10:00:00:00` give 10 and 12 seconds and labels `10:00:10:00` and `10:00:12:00`.

`package-full.json` shows every package field: provenance, a manifest with a description and one declared namespace, one record in each registry, one asset with a labelled file and file group, and package extensions. The `assets` kind is marked `partial`.

## Complete package

`package-complete.json` shows one package with every registry populated.

- Completeness: storage locations, collections, and assets are `complete`. Metadata definitions are `partial`.
- Storage: a filesystem location and an object store with a connection block.
- Metadata: an `enum` definition with two options, a `multiple` string definition with an informative constraint, and a `date` definition. Asset `a-0001` carries an enum value, a multiple string value, and a date value.
- Collections: a `logical` collection with a complete member list, and a `storage` collection with a parent, a storage object, and a partial member list.
- Asset-side collections: `a-0001`, `a-0002`, and `a-0003` reference `col-01` by id. `a-0004` carries a snapshot of `col-02` that equals the registry record without `members`.
- Versions: `a-0001` has versions `v1` (ordinal 0) and `v2` (ordinal 1). Files and file groups name their version.
- File groups: `a-0001` has a primary file group for `v2` with one video track and two stereo audio tracks, a primary file group for `v1`, and a labelled preview file group. Its files carry the roles `master`, `mezzanine`, and `preview`. `a-0002` has a primary file group for one recording split across two files: both members are video track 0, with `segment_index` 0 and 1. `a-0004` has a primary file group whose member is an image sequence with numbers 1000 to 1250.
- Timing at `24000/1001`: annotation `ann-1` on `a-0001` covers frames 100 to 150. The seconds 4.170833 and 6.25625 name frames 100 and 150 under the nearest-frame rule. The labels `01:00:04:04` and `01:00:06:06` are the anchor `01:00:00:00` plus 100 and 150 frames. Annotation `ann-2` is a chapter point at frame 0.
- Drop-frame at `30000/1001`: asset `a-0002` has anchor `01:00:59;00`. Frame 30 crosses into minute 01, where labels `;00` and `;01` are skipped, so its label is `01:01:00;02`. Frame 60 is `01:01:01;02`. The seconds 1.001 and 2.002 are exact.
- Relationships: `a-0003` is a `subclip_of` `a-0001` with range 240 to 480 on the timeline of `a-0001`. Tombstone `a-0005` is `derived_from` `a-0001`.
- Access: `a-0004` is `restricted`. `a-0002` and `a-0005` are `unknown`. The others are `none`.
- Tombstone: `a-0005` carries `deleted`.
- Extensions: the manifest declares `vendor_a` and `archive_b`. Both are used on records in the package. `vendor_a` also appears on an enum option, which shows that options and metadata values carry extensions.

## Declared warnings

A standalone record is checked without the rest of a package.
It cannot see its owning asset or the metadata definitions it uses, so some checks give a warning instead of a result.
A warning here does not mean the example is wrong. It means the check needs package context.
The validate command still exits 0 for every example.

| Example | Warnings (code at path) |
| --- | --- |
| `annotation-full.json` | `TIMELINE_UNAVAILABLE` at the root; `DEFINITION_UNAVAILABLE` at `/metadata/0` |
| `asset-full.json` | `DEFINITION_UNAVAILABLE` at `/annotations/0/metadata/0`, `/metadata/0`, `/metadata/1`, and `/metadata/2`; `TIMELINE_UNAVAILABLE` at `/relationships/1/range` |
| `collection-full.json` | `DEFINITION_UNAVAILABLE` at `/metadata/0` |
| All other examples | None |

The three package examples resolve every reference inside themselves, so they give no diagnostic.
The [adopter guide](../../docs/ADOPTION.md#packages-and-standalone-records) explains the two standalone warnings.
