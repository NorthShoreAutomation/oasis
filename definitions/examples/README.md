# OASIS 2.0.0-draft.3 examples

Status: DRAFT 2.0.0-draft.3, not a final release. These examples can change before the final release.
Interoperability between independent implementations is not demonstrated.

Every example is synthetic. Names such as "Example Archive" and `vendor_a` are placeholders. No example describes a real organization, product, or person. Checksum values are test values, not checksums of real media.

Only a package is an exchange document. Each example is one package: its root `type` is `package`, and it validates against [`package.schema.json`](../package.schema.json). Records inside a package carry no `type` and no `spec_version`.

There are three examples:

| Example | Purpose |
| --- | --- |
| `package-minimal.json` | The smallest valid package. |
| `package-full.json` | Every field of every record type and nested object, at least once. Not a realistic package. |
| `package-complete.json` | A realistic package with several assets that use the main record features together. |

Each example:

- passes the strict JSON input policy;
- is structurally valid against the 2.0 schema bundle, with format checking on;
- satisfies every checkable rule of the contract, so the semantic checks give no diagnostic.

To check one example yourself, run this from the repository root after setup:

```sh
python3 -m tests.conformance.validate definitions/examples/package-complete.json
```

## Minimal package

`package-minimal.json` holds the four required root fields: `type`, `spec_version`, `id`, and `manifest`. The manifest gives the producer, the production date-time, zero counts, and an empty namespace list. All four record lists are absent. An absent list counts as 0.

## Full package

`package-full.json` shows every field that the schema defines, at least once, with valid values. One asset cannot show every form, so the package holds three assets:

- `a-0001` has versions. It shows the frame form of timing, every file and member field except `sequence` and `sequence_frame`, `current_version`, `unassigned`, and the items that sit at the asset level of an asset with versions.
- `a-0002` has no versions. It shows the seconds form of timing, with `timecode_base` and sample fields, a `subclip_of` with a range, and `deleted`.
- `a-0003` has no versions and runs at `24/1`. It shows a compact image sequence, a thumbnail group with sequence frames, and a collection position.

Each JSON pointer below names one place where the record or object appears. Some objects appear in more places.

### Records

| Record or root object | Pointer |
| --- | --- |
| Package root, with `source` and `extensions` | `""` (the empty pointer) |
| Manifest, with `description` | `/manifest` |
| Producer | `/manifest/producer` |
| Counts | `/manifest/counts` |
| Namespace declaration, with `schema` and `description` | `/manifest/namespaces/0` |
| Storage location, every field | `/storage_locations/0` |
| Storage location of system `s3` | `/storage_locations/1` |
| Metadata definition of type `enum`, every field except `constraints` | `/metadata_definitions/0` |
| Option, with `extensions` | `/metadata_definitions/0/options/0` |
| Constraints for a `string` | `/metadata_definitions/1/constraints` |
| Constraints for an `integer` | `/metadata_definitions/2/constraints` |
| Collection of type `logical`, with `metadata`, `access`, `source`, and `extensions` | `/collections/0` |
| Collection of type `storage` | `/collections/1` |
| Collection storage | `/collections/1/storage` |
| Asset with versions, every asset field except `timing` and `deleted` | `/assets/0` |
| Asset in the seconds form, with `deleted` | `/assets/1` |
| Asset with an image sequence | `/assets/2` |

### Nested objects

| Nested object | Pointer |
| --- | --- |
| Version, every field | `/assets/0/versions/1` |
| Version with a relationship range | `/assets/0/versions/0` |
| Current version reference | `/assets/0/current_version` |
| Unassigned information | `/assets/0/unassigned` |
| Timing, frame form, with `duration_seconds`, `source_timecode`, and sample fields | `/assets/0/versions/1/timing` |
| Timing, seconds form, with `timecode_base` | `/assets/1/timing` |
| File, every field except `sequence` | `/assets/0/versions/1/files/0` |
| File location entry, every field except `missing_frames` | `/assets/0/versions/1/files/0/locations/0` |
| Checksum | `/assets/0/versions/1/files/0/checksum` |
| Image sequence | `/assets/2/files/0/sequence` |
| Sequence image, with `size_bytes` and `checksum` | `/assets/2/files/0/sequence/images/1` |
| Missing frames on a location | `/assets/2/files/0/locations/0/missing_frames` |
| File group, every field | `/assets/0/versions/1/file_groups/0` |
| Member of track type `video`, every video field | `/assets/0/versions/1/file_groups/0/members/0` |
| Member of track type `audio`, every audio field | `/assets/0/versions/1/file_groups/0/members/1` |
| Member of track type `data` | `/assets/0/versions/1/file_groups/1/members/0` |
| Member of track type `image`, with `width`, `height`, and `bit_depth` | `/assets/2/file_groups/0/members/0` |
| Member of track type `other` | `/assets/0/file_groups/0/members/0` |
| Members of a split recording, with `segment_index`, `start_frame`, and `start_seconds` | `/assets/0/versions/0/file_groups/0/members/1` |
| Members with `sequence_frame` | `/assets/2/file_groups/1/members/0` |
| Relationship with `target_version` and a range in frames and seconds | `/assets/1/relationships/0` |
| Relationship with `description` and `extensions` | `/assets/0/versions/1/relationships/0` |
| Time range in frames only | `/assets/0/versions/0/relationships/0/range` |
| Membership entry with `position` and `extensions` | `/collections/1/member_of/0` |
| Membership entry with `position` on an asset | `/assets/2/member_of/0` |
| Metadata value with `extensions` | `/assets/0/versions/1/metadata/0` |
| Metadata value with several items | `/assets/0/metadata/0` |
| Annotation, every field, with `visibility` | `/assets/0/versions/1/annotations/0` |
| Annotation in the seconds form, with sample positions | `/assets/1/annotations/0` |
| Annotation with no position | `/assets/0/annotations/0` |
| Access | `/assets/0/access` |
| Source | `/assets/0/source` |
| Extensions on a record | `/assets/0/extensions` |

## Complete package

`package-complete.json` shows one realistic package with every record list populated.

- Storage: `sl-01` is a `network_share` with the share in `root`. `sl-02` is an `s3` bucket. Its `root` holds the bucket name only, and each file path holds the full object key.
- Metadata: an `enum` definition on a `fixed` list with two options, a `multiple` string definition with a constraint, and a `date` definition. Asset `a-0001` carries an enum value, a multiple string value, and a date value.
- Collections: `col-01` is a `logical` collection. `col-02` is a `storage` collection that mirrors a folder on `sl-01`. It is a member of `col-01`. Assets `a-0001`, `a-0002`, and `a-0003` are members of `col-01`, and `a-0004` is a member of `col-02`. Membership is recorded on the member in `member_of`.
- Versions: `a-0001` has versions `v1` (ordinal 0) and `v2` (ordinal 1). Each version has its own timing, files, and file groups. Version `v2` also holds the web proxy, its preview group, and both annotations. Asset metadata stays at the asset level.
- File groups: version `v2` of `a-0001` has a primary group with one video track and two stereo audio tracks, and a labelled preview group. Its files carry the roles `master`, `mezzanine`, and `preview`. `a-0002` has a primary group for one recording split across two files: both members are video track 0, with `segment_index` 0 and 1. `a-0004` has a primary group whose member is an image sequence with images 1000 to 1249.
- Timing at `24000/1001`: annotation `ann-1` in version `v2` of `a-0001` is a `private` review comment that covers frames 100 to 150. The seconds 4.170833 and 6.25625 name frames 100 and 150 under the nearest-frame rule. The labels `01:00:04:04` and `01:00:06:06` are the anchor `01:00:00:00` plus 100 and 150 frames. Annotation `ann-2` is a chapter point at frame 0.
- Drop-frame at `30000/1001`: asset `a-0002` has anchor `01:00:59;00`. Frame 30 crosses into minute 01, where labels `;00` and `;01` are skipped, so its label is `01:01:00;02`. Frame 60 is `01:01:01;02`. The seconds 1.001 and 2.002 are exact.
- Relationships: `a-0003` is a `subclip_of` `a-0001`. The range 240 to 480 is on the timeline of version `v2`, which `target_version` names. The subclip has 240 frames at the same rate, so the lengths agree. Asset `a-0005` is `derived_from` `a-0001`.
- Access: `a-0004` is `restricted`. `a-0002` and `a-0005` carry no `access`, so their access state is unknown. The other assets and both collections are `none`.
- Deletion: `a-0005` carries `deleted`. The source reported it deleted at that date-time. It is a full record and a fact about the source, not an instruction to a receiving system.
- Extensions: the manifest declares `vendor_a` and `archive_b`. Both are used on records in the package. `vendor_a` also appears on an enum option.
