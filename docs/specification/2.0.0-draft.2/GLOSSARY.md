# OASIS 2.0 glossary

Status: DRAFT 2.0.0-draft.2. Not a final release. Interoperability between independent implementations is not demonstrated.
OASIS means Open Asset Standard Interchange Schema.

Each term is defined by what can be observed in a document, with two examples from different kinds of system. The examples are illustrations, not vocabulary. No product name is part of any definition.

| Term | Meaning | Example one | Example two |
| --- | --- | --- | --- |
| Package | One JSON document that carries a manifest, registries, and asset records for one exchange. The unit of exchange. | A nightly export of a newsroom's archive. | A hand-picked set of ten assets sent to a post house. |
| Manifest | The part of a package that states who produced it, when, how many records of each kind it holds, whether each kind is complete, and which extension namespaces it uses. | Counts show 1,200 assets and 40 collections, all complete. | Counts show 3 assets, collections partial. |
| Registry | A package array holding shared definitions that records reference by id: storage locations, metadata definitions, or collections. | Twelve storage locations referenced by 50,000 files. | One metadata definition used by every asset. |
| Record | A JSON object with `type`, `spec_version`, and `id`. The six record types are package, asset, collection, storage location, metadata definition, annotation. | An asset record inside a package. | A standalone collection record saved to disk. |
| Standalone record | A record that is the root of its own document. It validates structurally on its own. Its references are not checked. | One asset exported for a support ticket. | One annotation sent as a message. |
| Record type | The record type token in the `type` field. Read before any schema is chosen. | `asset` | `storage_location` |
| Specification version | The `spec_version` string on every record. It selects the 2.x schema set. It is not an asset version. | `2.0.0-draft.2` | a future `2.1.0` |
| Identifier | The `id` string of a record, unique within its record type inside one package, or of a nested object (file, file group, version, annotation, option), unique within its containing record. Not meaningful across packages without `source`. | `a-0001` | `9f3c...` |
| Source | Provenance of a record: the producing system, optionally one deployment of it, and the entity's identifier there. Never used to resolve references. | system `catalog-x`, instance `london`, id `4471` | system `archive-y`, id `urn:...` |
| Reference | A string naming the id of a record of a known type, or of a file or version inside the same asset. Record references resolve only inside a package. File and version references resolve inside the asset. | a file's `storage_location` | a file group member's `file` |
| Snapshot | A read-only copy of a registry collection record, without `members`, placed where this contract allows. Every other field equals the registry record. | a collection without members inside an asset's `collections` | the same, for a standalone asset |
| Completeness | The manifest's statement, per kind, that the array holds every entity the producer has for the exchanged scope. `partial` means some are missing and absence is not removal. | collections complete | metadata definitions partial |
| Asset | A described content item: the thing a system catalogs, with its files, versions, metadata, annotations, and collection memberships. | A news story's video. | A photograph with three renditions. |
| Tombstone | An asset with a `deleted` date. It records that the source system considers the asset deleted. | an asset deleted last week, still exported for audit | a purged clip |
| File | The recorded bytes of an asset in one storage location at one path. One file has one location. | `clip.mov` on a shared volume | `clip.mov` in an object store bucket |
| Storage location | A named place where files live, with a storage kind and an opaque root. Validation never connects to it. | a mounted volume | a cloud bucket |
| Locator | An opaque string that says where a file is within a storage location. Validation never opens it. | `projects/2026/clip.mov` | an object key |
| Connection | Optional non-secret information about how a system reaches a storage location: a method token and an optional opaque credential reference. | method `network_share`, credential reference `store:share-01` | method `object_api`, credential reference `keystore:key-7` |
| Credential reference | An opaque string that names a credential held outside the package. Never the credential itself. | `store:share-01` | `keystore:key-7` |
| Checksum | A producer's declared digest of a file's bytes, with the algorithm named. Validation never computes it. | `sha256` and 64 hex characters | `md5` and 32 hex characters |
| File role | What one file is on its own: master, mezzanine, preview, thumbnail, sidecar, other. Optional. It does not group files. | `master` for a camera original | `sidecar` for a caption file |
| File group | An explicit set of files that belong together for one purpose, with a role, an optional label, a completeness flag, and ordered members. Grouping is never inferred. | primary file group: one video file and two audio files | thumbnail file group: one still |
| File group role | The purpose of a file group: primary, preview, thumbnail, companion, other. Purpose, not format. | `primary` | `companion` for a caption file |
| Member | One file's place in a file group: track type, track index, optional channel count, optional image-sequence range, optional segment index. | video track 0 | audio track 1, 2 channels |
| Track | One stream within a file group, identified by track type and index. | video 0 | audio 3 |
| Segment index | The order of one file within a recording that is split across several files. Sequence order only, never frame arithmetic. | segment 0 and segment 1 of one camera recording | segments 0 to 3 of a long take |
| Image sequence | A file group member whose file is a numbered series of still images, described by an inclusive start and exclusive end frame number. | frames 1000 to 1250 | frames 0 to 48 |
| Version | One state of an asset over time, with an ordinal. The greatest ordinal is current. Files, file groups, and annotations may belong to a version. | version ordinal 3 of an edited clip | ordinal 0, the original upload |
| Ordinal | The integer that orders versions within an asset. Unique within the asset. Array position carries no meaning. | 0 | 3 |
| Relationship | A typed link from one asset to another: derived from, subclip of, or variant of, with an optional time range on the target. | subclip of a master, frames 240 to 480 | variant of a primary in another language |
| Time base | A rational frame rate and a drop-frame flag. Every frame number is read against the time base of its timeline. | 24000/1001, non-drop | 30000/1001, drop |
| Rate | A frame rate as integer numerator over denominator in lowest terms. | 25/1 | 60000/1001 |
| Timeline | The frame axis that a frame number belongs to. An asset owns one. Annotations use their asset's. A relationship range uses the target asset's. | an asset of 7,200 frames | the target of a subclip relationship |
| Source timecode anchor | The optional timecode label of frame 0 in the source material. Lets labels be derived from frame numbers. Assumes continuous timecode. | `01:00:00:00` | `09:59:30;00` |
| Frame position | An integer count of frames from the first presented frame of the timeline. Start is inclusive, end is exclusive. | start 100, end 150 | a point at 7200 |
| Point | A frame position with no end. Marks an instant. | a chapter marker | a quality flag at one frame |
| Derived time value | Optional seconds or timecode label that restate a frame value for readers. Seconds are elapsed time from frame 0. A label is anchor plus offset. Each must name the same frame as the frame value. | `4.170833` seconds for frame 100 at 24000/1001 | `01:00:04:04` for frame 100 with anchor `01:00:00:00` |
| Drop-frame | Timecode numbering that skips frame labels so the label tracks clock time at 30000/1001 or 60000/1001. Allowed only at those rates. | `00:01:00;02` | `00:10:00;00` |
| Timecode label | A `HH:MM:SS:FF` or `HH:MM:SS;FF` string at one of the supported label rates. A label, never the authority. Allowed only when the asset declares a source timecode anchor. | `01:02:03:04` | `00:59:59;29` |
| Collection | A named grouping of assets with a kind, an optional parent, and membership that the collection record owns. | a project folder | a saved search |
| Collection kind | The `collection_kind` field: logical, storage, query, or other. A storage collection declares the storage location and path it mirrors. Distinct from `type`, which is always `collection`. | `storage` for a folder on a volume | `query` for a saved search |
| Membership | The list of asset ids a collection holds and whether that list is complete. The collection record is the authority. Absence in an incomplete list is not removal. | complete list of 12 assets | partial list of 3 of 900 |
| Asset-side collections | A convenience list on an asset of the collections it belongs to, as references or snapshots. It must agree with the collection records and never adds a membership. | two references | one snapshot for standalone reading |
| Metadata definition | A registry record that describes a field: its id, an optional label, the value type, cardinality, options, and informative constraints. | `md-shoot-date`, date, single | `md-keywords`, string, multiple |
| Metadata value | A `definition` reference and a `value` whose JSON shape follows the definition's value type and cardinality. | `"2026-03-04"` | `["news", "sport"]` |
| Option | One allowed value of an enum definition: an id and an optional label. Values carry option ids. | id `appr`, label `Approved` | id `rej`, no label |
| Cardinality | Whether a definition takes one value (`single`) or an array of values (`multiple`). | `single` for a shoot date | `multiple` for keywords |
| Constraint | Informative data about a source field's limits. Not executed by validators. | min 0, max 100 | pattern `^[A-Z]{3}$` |
| Annotation | A statement about an asset, optionally about a frame range of it, with a purpose. | a reviewer's note on frames 100 to 150 | a chapter point |
| Purpose | What an annotation is for: note, review, quality, transcript, chapter, keyword, other. Not a system's type name. | `review` | `transcript` |
| Author | A neutral name or identifier for who made an annotation. Not an access principal. | `j.smith` | `auto-transcriber-2` |
| Extension | A namespaced object of producer or vendor data that the standard does not define. The only place for undeclared keys. | namespace `vendor_a` | namespace `broadcaster_internal` |
| Namespace token | A lowercase key that names an extension owner, declared in the manifest. | `vendor_a` | `broadcaster_internal` |
| Namespace declaration | The manifest entry for a token: owner, optional schema link, optional description. | owner `Vendor A Ltd` | owner `Example Broadcaster` |
| Access summary | The `access.status` of an asset or collection: none, restricted, or unknown. The whole of access in this draft. | `none` | `restricted` |
| Block or quarantine | What a consumer must do with a restricted or unknown entity it cannot represent: refuse it or hold it without granting access. | hold in a review queue | reject the record |
| Closed object | An object whose allowed keys are all declared. Undeclared keys outside `extensions` make the record invalid. | an asset root | a file object |
| Schema identifier | The stable absolute `$id` of each schema file. Never fetched; loaded from the bundle. | the asset schema id | the package schema id |
| Bundle | The set of schema files for one specification version with a manifest of identifiers and digests. Loaded offline. | the 2.0.0-draft.2 bundle | a future 2.1.0 bundle |
| Producer | Software that writes OASIS documents. | an archive exporter | a backup tool |
| Consumer | Software that reads OASIS documents and produces a declared outcome. | an importer | a catalog indexer |
| Structural validity | Agreement with the selected schema. One result among several. | the package parses and matches the schemas | a record fails a required field |
| Semantic conformance | Agreement with the rules a schema cannot express, checked by a conformance checker. | all references resolve, counts match | a reversed range is reported |
| Draft | A published specification that is not final, with stated gaps. It claims no interoperability or readiness. | `2.0.0-draft.2` | a later `2.0.0-draft.3` |
