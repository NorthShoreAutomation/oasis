# OASIS 2.0 data model

Status: DRAFT 2.0.0-draft.2. Informative. The [contract](CONTRACT.md) and the [schema files](../../../definitions/) are normative. If a diagram and the contract disagree, the contract wins.
OASIS means Open Asset Standard Interchange Schema.

This document shows the shape of the model in pictures. Each diagram names the contract section it draws. Field lists show the field name and its JSON type. A field marked `req` is required. Dates are RFC 3339 strings. `ref` means a string that names another record's `id`.

## 1. The package

A package is one JSON document. It carries a manifest, three registries, and the asset records. Records point at registry entries by id and do not copy them, with one exception: an asset may carry a read-only copy of a collection record without `members`, which must equal the registry record. (Contract sections 3 and 4.)

```mermaid
erDiagram
    PACKAGE ||--|| MANIFEST : "manifest (req)"
    PACKAGE ||--o{ STORAGE_LOCATION : "storage_locations[]"
    PACKAGE ||--o{ METADATA_DEFINITION : "metadata_definitions[]"
    PACKAGE ||--o{ COLLECTION : "collections[]"
    PACKAGE ||--o{ ASSET : "assets[]"
    MANIFEST ||--o{ NAMESPACE_DECLARATION : "namespaces[]"
    ASSET }o--o{ STORAGE_LOCATION : "files[].storage_location (ref)"
    ASSET }o--o{ METADATA_DEFINITION : "metadata[].definition (ref)"
    ASSET }o--o{ COLLECTION : "collections[] (ref or snapshot)"
    COLLECTION }o--o{ ASSET : "members.assets[] (ref)"
    COLLECTION }o--o| COLLECTION : "parent (ref)"
    COLLECTION }o--o| STORAGE_LOCATION : "storage.storage_location (ref)"
    COLLECTION }o--o{ METADATA_DEFINITION : "metadata[].definition (ref)"
    ASSET }o--o{ ASSET : "relationships[].target (ref)"

    PACKAGE {
        string type "const package, req"
        string spec_version "req"
        string id "req"
        object source
        object extensions
    }
    MANIFEST {
        object producer "name, version, req"
        datetime produced_at "req"
        object counts "one integer per registry, req"
        object completeness "complete or partial per registry, req"
        array namespaces "req, may be empty"
        string description
    }
    NAMESPACE_DECLARATION {
        string token "req"
        string owner "req"
        string schema "uri"
        string description
    }
```

Every record type shares one envelope (contract section 3):

```mermaid
classDiagram
    class Record {
        type : string (req)  one of package, asset, collection, storage_location, metadata_definition, annotation
        spec_version : string (req)  "2.0.0-draft.2"
        id : string (req)  unique within its record type in a package
        source : Source
        extensions : Extensions
    }
    class Source {
        system : string (req)
        instance : string
        id : string (req)
    }
    class Extensions {
        namespace token : object  one key per declared namespace
    }
    Record --> Source : provenance, never used to resolve references
    Record --> Extensions : the only open slot
```

## 2. A complete asset

Everything that can appear on one asset record. Nested objects belong to the asset and have ids unique inside it. The only outward links are references to registry records and to other assets. (Contract sections 7 to 13.)

```mermaid
classDiagram
    class Asset {
        type : "asset" (req)
        spec_version : string (req)
        id : string (req)
        source : Source
        title : string (req)
        category : string
        description : string
        status : string
        created : datetime
        modified : datetime
        deleted : datetime  tombstone when present
        timing : Timing
        versions : Version[]
        files : File[]
        file_groups : FileGroup[]
        relationships : Relationship[]
        metadata : MetadataValue[]
        annotations : Annotation[]
        collections : CollectionEntry[]
        access : Access (req)
        extensions : Extensions
    }
    class Timing {
        time_base : TimeBase (req)
        source_timecode : string  label of frame 0
        duration_frames : integer
    }
    class TimeBase {
        rate : Rate (req)
        drop_frame : boolean (req)
    }
    class Rate {
        numerator : integer (req)
        denominator : integer (req)
    }
    class Version {
        id : string (req)
        ordinal : integer (req)  greatest is current
        label : string
        created : datetime
        modified : datetime
        extensions : Extensions
    }
    class File {
        id : string (req)
        storage_location : ref StorageLocation (req)
        path : string (req)
        size_bytes : integer
        checksum : Checksum
        media_type : string
        version : ref Version
        created : datetime
        modified : datetime
        status : string
        role : master mezzanine preview thumbnail sidecar other
        label : string
        extensions : Extensions
    }
    class Checksum {
        algorithm : md5 sha1 sha256 sha512 blake3 (req)
        value : hex string (req)
    }
    class FileGroup {
        id : string (req)
        role : primary preview thumbnail companion other (req)
        label : string
        complete : boolean (req)
        version : ref Version
        members : Member[] (req, 1 or more)
        extensions : Extensions
    }
    class Member {
        file : ref File (req)
        track_type : video audio image data other (req)
        track_index : integer (req)
        channel_count : integer
        sequence_range : SequenceRange
        segment_index : integer  order within a spanned recording
        extensions : Extensions
    }
    class SequenceRange {
        start : integer (req)  inclusive
        end : integer (req)  exclusive
    }
    class Relationship {
        kind : derived_from subclip_of variant_of (req)
        target : ref Asset (req)
        range : FrameRange  on the target timeline
        description : string
        extensions : Extensions
    }
    class FrameRange {
        start_frame : integer (req)
        end_frame : integer (req)
    }
    class MetadataValue {
        definition : ref MetadataDefinition (req)
        value : per definition value_type and cardinality (req)
        extensions : Extensions
    }
    class Annotation {
        id : string (req)
        source : Source
        purpose : note review quality transcript chapter keyword other (req)
        title : string
        text : string
        category : string
        author : string
        language : string
        created : datetime
        modified : datetime
        start_frame : integer
        end_frame : integer
        start_seconds : number  derived
        end_seconds : number  derived
        start_timecode : string  derived
        end_timecode : string  derived
        version : ref Version
        metadata : MetadataValue[]
        extensions : Extensions
    }
    class CollectionEntry {
        either : ref Collection
        or : Collection snapshot without members
    }
    class Access {
        status : none restricted unknown (req)
    }

    Asset *-- Timing
    Timing *-- TimeBase
    TimeBase *-- Rate
    Asset *-- "0..*" Version
    Asset *-- "0..*" File
    File *-- Checksum
    Asset *-- "0..*" FileGroup
    FileGroup *-- "1..*" Member
    Member *-- SequenceRange
    Member ..> File : file ref
    File ..> Version : version ref
    FileGroup ..> Version : version ref
    Asset *-- "0..*" Relationship
    Relationship *-- FrameRange
    Asset *-- "0..*" MetadataValue
    Asset *-- "0..*" Annotation
    Annotation ..> Version : version ref
    Annotation *-- "0..*" MetadataValue
    Asset *-- "0..*" CollectionEntry
    Asset *-- Access
```

How the pieces of one asset relate:

- **Files** are the bytes. Each file is in exactly one storage location at one path. A file may carry a role, such as master or preview, and a label. The role describes the file on its own and does not group it.
- **File groups** say which files belong together and why. A primary file group might hold one video file and two audio files, each a member with a track type and index. When one recording is split across several files, each file is a member with the same track type and index and its own segment index. A file can be in several file groups or none. Nothing is grouped by guesswork.
- **Versions** are states of the asset over time. Files, file groups, and annotations may say which version they belong to. A file with no version belongs to all of them.
- **Timing** gives the asset its timeline: a rational rate, a drop-frame flag, an optional source timecode for frame 0, and an optional length. Annotations and incoming subclip ranges are measured on it.
- **Annotations** are statements about the asset, optionally about a frame range or point.
- **Relationships** link this asset to another asset: derived from, subclip of, or variant of.
- **Metadata** values point at a definition in the registry and carry a value shaped by that definition.
- **Collections** on the asset are a convenience list. The collection record owns membership.
- **Access** is the one required access field: none, restricted, or unknown.

## 3. The registry records

Three record types live in the package registries and are referenced by assets and collections. (Contract sections 8, 10, 11.)

```mermaid
classDiagram
    class StorageLocation {
        type : "storage_location" (req)
        spec_version : string (req)
        id : string (req)
        source : Source
        name : string (req)
        system : token (req)  filesystem, object_store, tape, ...
        root : string  opaque base locator
        connection : Connection
        status : string
        description : string
        created : datetime
        modified : datetime
        extensions : Extensions
    }
    class Connection {
        method : token (req)
        credential_reference : string  opaque, never a secret
    }
    class MetadataDefinition {
        type : "metadata_definition" (req)
        spec_version : string (req)
        id : string (req)  names the field
        source : Source
        label : string
        description : string
        value_type : string integer number boolean date datetime enum asset_reference collection_reference (req)
        cardinality : single multiple (req)
        options : Option[]  required for enum, 1 or more
        constraints : Constraints  informative only
        required : boolean  hint only
        extensions : Extensions
    }
    class Option {
        id : string (req)
        label : string
        extensions : Extensions
    }
    class Constraints {
        minimum : number
        maximum : number
        min_length : integer
        max_length : integer
        pattern : string
    }
    class Collection {
        type : "collection" (req)
        spec_version : string (req)
        id : string (req)
        source : Source
        title : string (req)
        collection_kind : logical storage query other (req)
        description : string
        parent : ref Collection
        storage : CollectionStorage  required when collection_kind is storage
        members : Members
        created : datetime
        modified : datetime
        metadata : MetadataValue[]
        access : Access (req)
        extensions : Extensions
    }
    class CollectionStorage {
        storage_location : ref StorageLocation (req)
        path : string (req)
    }
    class Members {
        complete : boolean (req)
        assets : ref Asset[] (req)
    }
    StorageLocation *-- Connection
    MetadataDefinition *-- "0..*" Option
    MetadataDefinition *-- Constraints
    Collection *-- CollectionStorage
    Collection *-- Members
    Collection ..> Collection : parent ref
    CollectionStorage ..> StorageLocation : ref
```

## 4. Membership: who owns the truth

The collection record owns membership. The asset-side list is a convenience that must agree. The completeness flags decide what absence means. (Contract section 10, rules COL-3 and COL-5.)

```mermaid
flowchart TD
    A[Consumer reads asset X] --> B{Does X list collection C?}
    B -- no --> C1[X is not claimed as a member by X]
    B -- yes --> P{Is X inside a package?}
    P -- no --> P1[Standalone record, references are not checked, entry is informative]
    P -- yes --> D{Collection C in the collections registry?}
    D -- no --> E{Manifest says collections complete?}
    E -- yes --> E1[Reject, unresolved reference PKG-6. An absent array counts as empty]
    E -- no --> E2[Warning, partial registry, entry is informative]
    D -- yes --> F{C.members present?}
    F -- no --> G[Membership unknown, entry is informative]
    F -- yes --> H{C.members.complete?}
    H -- true --> I{X in C.members.assets?}
    I -- yes --> J[Agree, X is a member]
    I -- no --> K[Reject, asset side contradicts a complete list]
    H -- false --> L[Partial list, entry is informative, absence is not removal]
```

## 5. Time: frames, anchor, derived labels

Frame numbers are the authority. Seconds and timecode labels are derived for readers and must name the same frame. (Contract section 6.)

```mermaid
flowchart LR
    subgraph asset timing
        TB[time_base: rate 24000/1001, drop_frame false]
        ST[source_timecode: 01:00:00:00, label of frame 0]
        DU[duration_frames: 7200]
    end
    subgraph annotation
        SF[start_frame: 100]
        EF[end_frame: 150, exclusive]
        SS[start_seconds: 4.170833]
        STC[start_timecode: 01:00:04:04]
    end
    SF -- "frames x denominator / numerator, nearest frame must be 100" --> SS
    SF -- "anchor + 100 frames at 24 labels per second" --> STC
    ST --> STC
    TB --> SS
    TB --> STC
    DU -- "0 <= start < end <= 7200" --> SF
```

Rules in one line each: no default rate; a point has no end frame; start is inclusive and end is exclusive; drop-frame only at 30000/1001 and 60000/1001; labels only when an anchor exists and only at the rates in the contract table; a derived value that names a different frame is rejected.

## 6. Metadata: definitions apart from values

A definition is written once in the registry. Values on assets and collections point at it. The definition's value_type and cardinality decide the JSON shape of each value. (Contract section 11.)

```mermaid
flowchart LR
    MD["metadata_definition md-approval<br/>value_type enum, cardinality single<br/>options: appr Approved, rej Rejected"]
    MK["metadata_definition md-keywords<br/>value_type string, cardinality multiple"]
    A1["asset a-0001<br/>metadata:<br/>definition md-approval, value appr<br/>definition md-keywords, value [news, sport]"]
    A2["asset a-0002<br/>metadata:<br/>definition md-approval, value rej"]
    A1 -- ref --> MD
    A1 -- ref --> MK
    A2 -- ref --> MD
```

## 7. Extensions and namespaces

Every record and most nested entities carry one `extensions` object. Its keys are namespace tokens. Every token used in a package is declared in the manifest with an owner. Unknown keys anywhere else are rejected. (Contract section 13.)

```mermaid
flowchart TD
    M["manifest.namespaces<br/>token vendor_a, owner Vendor A<br/>token archive_b, owner Example Archive"]
    R["asset a-0001<br/>extensions:<br/>vendor_a: { ... any JSON ... }<br/>archive_b: { ... any JSON ... }"]
    F["file f-01<br/>extensions:<br/>vendor_a: { ... }"]
    X["asset a-0003<br/>extensions:<br/>vendor_c: { ... }"]
    R -- declared --> M
    F -- declared --> M
    X -- "not declared: rejected" --> M
```

## 8. The six record types at a glance

| Type | Lives in | Required beyond the envelope | Points at |
| --- | --- | --- | --- |
| `package` | document root | `manifest` | everything below |
| `asset` | `assets[]` or standalone | `title`, `access` | storage locations, metadata definitions, collections, other assets |
| `collection` | `collections[]` or standalone | `title`, `collection_kind`, `access` | parent collection, storage location, assets, metadata definitions |
| `storage_location` | `storage_locations[]` or standalone | `name`, `system` | nothing |
| `metadata_definition` | `metadata_definitions[]` or standalone | `value_type`, `cardinality` | nothing |
| `annotation` | `asset.annotations[]` as a nested object, or standalone | `purpose`, and `asset` when standalone | its asset, a version, metadata definitions |
