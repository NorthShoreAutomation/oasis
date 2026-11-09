# OASIS 2.0 data model

Status: DRAFT 2.0.0-draft.4. Informative. The [contract](CONTRACT.md) and the [schema files](../../../definitions/) are normative. If a diagram and the contract disagree, the contract wins.
OASIS means Open Asset Standard Interchange Schema.
The [glossary](GLOSSARY.md) defines the terms used here.

This document shows the shape of the model in pictures. Each diagram names the contract section it draws. Field lists show the field name and its JSON type. A field marked `req` is required. Dates are RFC 3339 strings. `ref` means a string that names the `id` of another record or of a nested object.

## 1. The package

A package is the only exchange document. It has a manifest and four record lists: `storage_locations`, `metadata_definitions`, `collections`, and `assets`. Each record list is optional. A single-document package is one JSON document, and the diagrams in this section draw it. A multi-file package holds the same parts in a package folder (section 9). Every reference resolves inside the package, so a package holds every record that its references need. Records point at other records by id and never copy them. (Contract sections 3, 4, and 5.)

```mermaid
erDiagram
    PACKAGE ||--|| MANIFEST : "manifest (req)"
    PACKAGE ||--o{ STORAGE_LOCATION : "storage_locations[]"
    PACKAGE ||--o{ METADATA_DEFINITION : "metadata_definitions[]"
    PACKAGE ||--o{ COLLECTION : "collections[]"
    PACKAGE ||--o{ ASSET : "assets[]"
    MANIFEST ||--o{ NAMESPACE_DECLARATION : "namespaces[]"
    ASSET }o--o{ STORAGE_LOCATION : "files[].locations[].storage_location (ref)"
    ASSET }o--o{ METADATA_DEFINITION : "metadata[].definition (ref)"
    ASSET }o--o{ COLLECTION : "member_of[].collection (ref)"
    COLLECTION }o--o{ COLLECTION : "member_of[].collection (ref)"
    COLLECTION }o--o| STORAGE_LOCATION : "storage.storage_location (ref)"
    COLLECTION }o--o{ METADATA_DEFINITION : "metadata[].definition (ref)"
    ASSET }o--o{ ASSET : "relationships[].target (ref)"

    PACKAGE {
        string type "const package, req"
        string spec_version "2.0.0-draft.4, req"
        string id "req"
        object source
        object extensions
    }
    MANIFEST {
        object producer "name, version, req"
        datetime produced_at "req"
        object counts "one integer per record list, req"
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

The edges show references. The membership edges start at the member: an asset or a collection names the collections it belongs to. A collection does not list its members.

Only the package root carries `type` and `spec_version`. A record inside a package carries neither field. The record list that holds a record states its type. A `type` or `spec_version` key on a record is an unknown key, and the schema rejects it. (Contract section 3, `REC-1`, `REC-2`, `REC-7`.)

```mermaid
classDiagram
    class Package {
        type : "package" (req)
        spec_version : "2.0.0-draft.4" (req)
        id : string (req)
        manifest : Manifest (req)
        storage_locations : StorageLocation[]
        metadata_definitions : MetadataDefinition[]
        collections : Collection[]
        assets : Asset[]
        source : Source
        extensions : Extensions
    }
    class Record {
        id : string (req)  unique within its record list
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
    Package *-- "0..*" Record : four record lists
    Record --> Source : provenance, never used to resolve references
    Record --> Extensions : the only open slot
```

The package describes its records as they stood at `produced_at`. It carries no command. A missing record, field, or value is not an instruction to delete or clear anything (`PKG-9`).

## 2. A complete asset

Everything that can appear on one asset record. Nested objects belong to the asset. Their ids are unique inside the asset, across the asset level, every version, and `unassigned`. The outward links are references to other records in the package. (Contract sections 6 to 13.)

### 2.1 Asset, versions, and holders

An asset with no versions holds its items at the asset level. An asset with versions places each item with its owner: a version, the asset level, or `unassigned`. The object that holds an item is its holder, and the holder states the version. No item carries a version field. (Contract section 9, `VER-1` to `VER-7`.)

```mermaid
classDiagram
    class Asset {
        id : string (req)
        source : Source
        title : string (req)
        category : string
        description : string
        status : string
        created : datetime
        modified : datetime
        deleted : datetime  the source reported a deletion
        timing : Timing  only on an asset with no versions
        versions : Version[]
        current_version : ref Version
        unassigned : Unassigned
        files : File[]
        file_groups : FileGroup[]
        relationships : Relationship[]
        metadata : MetadataValue[]
        annotations : Annotation[]
        member_of : MembershipEntry[]
        access : Access
        extensions : Extensions
    }
    class Version {
        id : string (req)
        ordinal : integer (req)  order in the source only
        label : string
        created : datetime
        modified : datetime
        timing : Timing
        files : File[]
        file_groups : FileGroup[]
        metadata : MetadataValue[]
        annotations : Annotation[]
        relationships : Relationship[]
        extensions : Extensions
    }
    class Unassigned {
        files : File[]
        file_groups : FileGroup[]  no part starts
        metadata : MetadataValue[]
        annotations : Annotation[]  no positions
        relationships : Relationship[]  no subclip_of
    }
    class Relationship {
        type : derived_from subclip_of variant_of (req)
        target : ref Asset (req)
        target_version : ref Version of the target
        range : TimeRange  on the target timeline
        description : string
        extensions : Extensions
    }
    class TimeRange {
        start_frame : integer
        end_frame : integer
        start_seconds : number
        end_seconds : number
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
        visibility : public private
        language : string
        created : datetime
        modified : datetime
        start_frame : integer
        end_frame : integer
        start_seconds : number
        end_seconds : number
        start_timecode : string  restates a frame field
        end_timecode : string  restates a frame field
        start_sample : integer  restates start_seconds
        end_sample : integer  restates end_seconds
        metadata : MetadataValue[]
        extensions : Extensions
    }
    class MembershipEntry {
        collection : ref Collection (req)
        position : integer  order in that collection
        extensions : Extensions
    }
    class Access {
        status : none restricted (req)
    }

    Asset *-- "0..*" Version
    Asset ..> Version : current_version ref
    Asset *-- "0..1" Unassigned
    Asset *-- "0..*" Relationship
    Asset *-- "0..*" MetadataValue
    Asset *-- "0..*" Annotation
    Asset *-- "0..*" MembershipEntry
    Asset *-- "0..1" Access
    Version *-- "0..*" Relationship
    Version *-- "0..*" MetadataValue
    Version *-- "0..*" Annotation
    Unassigned *-- "0..*" Relationship
    Unassigned *-- "0..*" MetadataValue
    Unassigned *-- "0..*" Annotation
    Relationship *-- "0..1" TimeRange
    Annotation *-- "0..*" MetadataValue
```

The asset, each version, and `unassigned` also hold `files` and `file_groups`. Section 2.2 draws them. `timing` sits on an asset with no versions or on a version. Section 5 draws it.

### 2.2 Files, copies, and file groups

A file is one content item. Its `locations` list the stored copies that the source reports. A file group selects files of the same holder and states the track of each one. (Contract section 8.)

```mermaid
classDiagram
    class File {
        id : string (req)
        locations : FileLocation[]
        size_bytes : integer  absent with sequence
        checksum : Checksum  absent with sequence
        media_type : string
        created : datetime
        modified : datetime
        role : master mezzanine preview thumbnail sidecar other
        label : string
        reel_name : string
        duration_seconds : number
        bit_rate : integer
        sequence : ImageSequence
        extensions : Extensions
    }
    class FileLocation {
        storage_location : ref StorageLocation (req)
        path : string (req)
        availability : online nearline offline
        missing_frames : integer[]  only with sequence
        extensions : Extensions
    }
    class Checksum {
        algorithm : md5 sha1 sha256 sha512 blake3 (req)
        value : hex string (req)
    }
    class ImageSequence {
        first_frame : integer (req)  inclusive
        last_frame : integer (req)  inclusive
        step : integer (req)
        padding : integer (req)
        images : SequenceImage[]
    }
    class SequenceImage {
        frame : integer (req)
        size_bytes : integer
        checksum : Checksum
    }
    class FileGroup {
        id : string (req)
        role : primary preview thumbnail companion other (req)
        label : string
        members : Member[] (req, 1 or more)
        extensions : Extensions
    }
    class Member {
        file : ref File (req)  in the same holder
        track_type : video audio image data other (req)
        track_index : integer (req)
        stream_index : integer
        segment_index : integer  part of a split recording
        start_frame : integer  part start
        start_seconds : number  part start
        sequence_frame : integer  image only
        label : string
        language : string
        codec : string
        bit_rate : integer
        duration_seconds : number
        width : integer  video, image
        height : integer  video, image
        display_aspect_ratio : Ratio  video, image
        bit_depth : integer  video, image, audio
        frame_rate : Rate  video
        capture_frame_rate : Rate  video
        frame_count : integer  video
        scan_type : progressive interlaced  video
        sample_rate : integer  audio
        channel_count : integer  audio
        channel_layout : string[]  audio
        extensions : Extensions
    }
    class Ratio {
        numerator : integer (req)
        denominator : integer (req)
    }

    File *-- "0..*" FileLocation
    File *-- "0..1" Checksum
    File *-- "0..1" ImageSequence
    ImageSequence *-- "0..*" SequenceImage
    SequenceImage *-- "0..1" Checksum
    FileGroup *-- "1..*" Member
    Member ..> File : file ref
    Member *-- "0..1" Ratio
```

How the pieces of one asset relate:

- **Files** are content items. A file lists its stored copies in `locations`. Each entry names one storage location and the `path` of the copy there, and may state its `availability`. Several entries claim identical bytes, so `size_bytes`, `checksum`, and the technical fields describe every copy. A copy is not a rendition and not a version. A file may carry a role, such as master or preview, and a label. The role describes the file on its own and does not group it. An absent or empty `locations` means that no copy is known (`FILE-6`).
- **Image sequences** have two forms. A compact sequence is one file with `sequence`: it stands for the images from `first_frame` to `last_frame` in steps of `step`, with both ends included. Each `path` holds the text `{frame}` once. Such a file has no `size_bytes` and no `checksum` (`FILE-8`). An explicit sequence is one file per image, and each image is a member with `sequence_frame` (`GRP-12`).
- **File groups** say which files belong together and why. A primary file group might hold one video file and two audio files, each a member with a track type and index. A member may name the stream in its file with `stream_index` and describe that stream with the track fields (`GRP-10`, `GRP-11`). When one recording is split across several files, each file is a member with the same track type and index and its own segment index. A segment may state its part start on the holder timeline (`GRP-7`). A file group names files of its own holder only. A file can be in several file groups or none. Nothing is grouped by guesswork.
- **Versions** are states of the asset in the source. A version holds its own timing, files, file groups, metadata, annotations, and relationships. `ordinal` gives the order in the source only and never selects the current version. `current_version` names the current version when the source states it. When it is absent, the current version is unknown (`VER-6`). An asset with no versions has one implied original version.
- **Unassigned** holds what the source holds for one of the versions without naming which. It is not a version and has no timeline (`VER-5`).
- **Timing** gives a timeline to an asset with no versions, or to a version. It has a frame form and a seconds form (section 5). Annotation positions and part starts are measured on the timeline of their holder.
- **Annotations** are statements about the asset, optionally about a point or a range on the holder timeline. `visibility` states who can see the annotation in the source: `public` or `private`. Absence means unknown (`ANN-4`).
- **Relationships** link this asset to another asset: derived from, subclip of, or variant of. A `range` lies on the target timeline: the timeline of the version that `target_version` names, or of the target asset when it has no versions (`REL-6`).
- **Metadata** values point at a definition in the `metadata_definitions` record list and carry a value shaped by that definition. One metadata field sits at one level of an asset only (`VER-7`).
- **Membership** is on the member. `member_of` lists the collections that the asset belongs to, each with an optional `position` (section 4).
- **Access** is optional: `none` or `restricted`. An absent `access` means that the package supplies no access information. Absence never means `none` (`ACC-1`, `ACC-2`).
- **Deleted** states that the source reported the asset deleted at that date-time. It is a fact about the source, not an instruction to delete (`AST-3`).

## 3. Storage locations, metadata definitions, and collections

Three record lists hold the records that assets and collections reference. (Contract sections 8, 10, and 11.)

```mermaid
classDiagram
    class StorageLocation {
        id : string (req)
        source : Source
        name : string (req)
        system : source_local network_share s3 gcs azure_blob tape other (req)
        root : string  required for network_share s3 gcs azure_blob tape
        status : string
        description : string
        created : datetime
        modified : datetime
        extensions : Extensions
    }
    class MetadataDefinition {
        id : string (req)  names the field
        source : Source
        label : string
        description : string
        value_type : string integer number boolean date datetime enum asset_reference collection_reference (req)
        cardinality : single multiple (req)
        list_type : fixed open  required for enum
        options : Option[]  required for enum, 0 or more
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
        id : string (req)
        source : Source
        title : string (req)
        collection_type : logical storage other (req)
        description : string
        storage : CollectionStorage  required when collection_type is storage
        member_of : MembershipEntry[]
        created : datetime
        modified : datetime
        deleted : datetime  the source reported a deletion
        metadata : MetadataValue[]
        access : Access
        extensions : Extensions
    }
    class CollectionStorage {
        storage_location : ref StorageLocation (req)
        path : string (req)
    }
    class MembershipEntry {
        collection : ref Collection (req)
        position : integer
        extensions : Extensions
    }
    MetadataDefinition *-- "0..*" Option
    MetadataDefinition *-- Constraints
    Collection *-- "0..1" CollectionStorage
    Collection *-- "0..*" MembershipEntry
    MembershipEntry ..> Collection : collection ref
    CollectionStorage ..> StorageLocation : ref
```

A storage location record describes one place. It has no connection settings and no credential fields (`STO-2`). `root` and `path` join under the `STO-3` table. Two places on one storage system are two records.

A saved search is not a collection in OASIS (`COL-2`).

A collection may carry `deleted`. As on an asset, it states that the source reported the collection deleted at that date-time. It is a fact about the source, not an instruction to delete the collection or its members (`COL-8`).

## 4. Membership: the member owns the truth

Membership is recorded on the member. An asset or a collection lists the collections it belongs to in `member_of`. A collection record does not list its members. The members of a collection are the assets and collections in the package that name it. (Contract section 10, `COL-3`, `COL-4`, `COL-7`.)

```mermaid
flowchart TD
    A[Consumer reads asset or collection X] --> B{Does X name collection C in member_of?}
    B -- no --> C1[No membership in C is stated. Absence is not removal]
    B -- yes --> D{Is C in the collections record list?}
    D -- no --> E1[Reject, unresolved reference PKG-6]
    D -- yes --> F{Does the entry carry position?}
    F -- yes --> G[X is a member of C at that position]
    F -- no --> H[X is a member of C with no known place in the order]
    G --> P{Does another entry for C share the position?}
    P -- yes --> P1[Reject, positions are unique per collection COL-7]
    P -- no --> OK[Accept]
    H --> Q{Does X name C again in member_of?}
    Q -- yes --> Q1[Reject, a repeated entry needs a position on each entry COL-7]
    Q -- no --> OK
```

- A collection may belong to several collections. Membership among collections never forms a cycle. A collection that names itself is a cycle (`COL-4`).
- All entries that name one collection, from assets and collections together, share one position scope. Positions are integers, compare by value, and need not be consecutive. Array order and record order give no order (`COL-7`, `PKG-8`).
- An absent and an empty `member_of` both state no membership. Neither states non-membership. The collection may have other members in the source that this package does not hold (`COL-3`).

```mermaid
flowchart LR
    A1["asset a-0001<br/>member_of: c-0002 position 1"]
    A2["asset a-0002<br/>member_of: c-0002 position 2"]
    C2["collection c-0002<br/>member_of: c-0001"]
    C1["collection c-0001"]
    A1 -- member_of --> C2
    A2 -- member_of --> C2
    C2 -- member_of --> C1
```

## 5. Time: two forms of timing

A `timing` object defines one timeline. It has one of two forms. In the frame form, frames define each position, and seconds and timecode labels restate them. In the seconds form, elapsed seconds define each position. Either form may declare `sample_rate`, and sample positions then restate seconds. (Contract section 6.)

### 5.1 Frame form

```mermaid
flowchart LR
    subgraph timing
        TB[time_base: rate 24000/1001, drop_frame false]
        ST[source_timecode: 01:00:00:00, label of frame 0]
        DU[duration_frames: 7200]
        DS[duration_seconds: 300.3, restates 7200]
    end
    subgraph annotation
        SF[start_frame: 100]
        EF[end_frame: 150, excluded]
        SS[start_seconds: 4.170833]
        STC[start_timecode: 01:00:04:04]
    end
    SF -- "nearest frame to seconds x numerator / denominator must be 100" --> SS
    SF -- "anchor + 100 frames at 24 labels per second" --> STC
    ST --> STC
    TB --> SS
    TB --> STC
    DU -- "range: 0 <= start < end <= 7200; point: 0 <= start <= 7200" --> SF
```

### 5.2 Seconds form

```mermaid
flowchart LR
    subgraph timing
        D2[duration_seconds: 95.5, required]
        TCB[timecode_base: rate 25/1, drop_frame false]
        ST2[source_timecode: 10:00:00:00, label of the start]
        SR[sample_rate: 48000]
        DSM[duration_samples: 4584000, restates 95.5]
    end
    subgraph annotation
        S2[start_seconds: 12.25]
        E2[end_seconds: 14.5, excluded]
        SS2[start_sample: 588000]
        ES2[end_sample: 696000]
    end
    S2 -- "nearest integer to seconds x sample_rate" --> SS2
    E2 -- "nearest integer to seconds x sample_rate" --> ES2
    SR --> SS2
    SR --> ES2
    TCB --> ST2
    D2 -- "range: 0 <= start < end <= 95.5; point: 0 <= start <= 95.5" --> S2
```

Rules in one line each:

- There is no default rate. A frame field needs frame-form timing on its holder.
- The frame form has `time_base`. `duration_frames` is optional, and `duration_seconds` restates it. The seconds form has no `time_base` and requires `duration_seconds`.
- A variable-frame-rate asset uses the seconds form, with no frame fields (`TIME-10`).
- A range includes its start and excludes its end, in either unit. A point has no end.
- A position equal to the length is the end boundary. A point may sit there. A range ends there at the latest. A part start is strictly less than the length.
- Drop-frame is allowed only at 30000/1001 and 60000/1001.
- Timecode labels on markers need a frame field and a `source_timecode`, and only at the rates in the contract table. In the seconds form, `source_timecode` needs `timecode_base`, and markers carry no labels.
- A restated value that names a different frame or sample is rejected.
- The asset level of an asset with versions and `unassigned` have no timeline. They hold no position, no part start, and no `subclip_of`.

## 6. Metadata: definitions apart from values

A definition is written once in the `metadata_definitions` record list. Values on assets, versions, `unassigned`, collections, and annotations point at it. The definition's value_type and cardinality decide the JSON shape of each value. An `enum` definition has a list type. A `fixed` list accepts only option ids. An `open` list accepts any string, and an item equal to an option id is that option. In a `multiple` value, each item appears at most once. (Contract section 11, `MD-7`, `MD-8`.)

```mermaid
flowchart LR
    MD["metadata_definition md-approval<br/>value_type enum, cardinality single<br/>list_type fixed<br/>options: appr Approved, rej Rejected"]
    MK["metadata_definition md-keywords<br/>value_type string, cardinality multiple"]
    A1["asset a-0001<br/>metadata:<br/>definition md-approval, value appr<br/>definition md-keywords, value [news, sport]"]
    A2["asset a-0002<br/>metadata:<br/>definition md-approval, value rej"]
    A1 -- ref --> MD
    A1 -- ref --> MK
    A2 -- ref --> MD
```

## 7. Extensions and namespaces

Every record and most nested entities carry one `extensions` object. This includes file location entries and membership entries. Its keys are namespace tokens. Every token used in a package is declared in the manifest with an owner. Unknown keys anywhere else are rejected. A consumer that re-emits a record keeps every extension value that it does not interpret, by value (`EXT-4`). (Contract section 13.)

```mermaid
flowchart TD
    M["manifest.namespaces<br/>token vendor_a, owner Vendor A<br/>token archive_b, owner Example Archive"]
    R["asset a-0001<br/>extensions:<br/>vendor_a: { ... any JSON ... }<br/>archive_b: { ... any JSON ... }"]
    F["file f-01, location entry<br/>extensions:<br/>vendor_a: { ... }"]
    X["asset a-0003<br/>extensions:<br/>vendor_c: { ... }"]
    R -- declared --> M
    F -- declared --> M
    X -- "not declared: rejected" --> M
```

## 8. The package and its record lists at a glance

| Type | Lives in | Required beyond `id` | Points at |
| --- | --- | --- | --- |
| `package` | document root | `type`, `spec_version`, `manifest` | everything below |
| asset | `assets[]` | `title` | storage locations, metadata definitions, collections, other assets and their versions |
| collection | `collections[]` | `title`, `collection_type` | collections it belongs to, storage location, metadata definitions |
| storage location | `storage_locations[]` | `name`, `system` | nothing |
| metadata definition | `metadata_definitions[]` | `value_type`, `cardinality` | nothing |

An annotation is a nested object, never a record. It sits in an `annotations` list at the asset level, in a version, or in `unassigned` (`ANN-1`).

## 9. The multi-file package

A multi-file package holds one package in a package folder. The manifest file `oasis-package.json` holds the package root. Its manifest lists the member files in `members`. The root has none of the four record arrays. Member files hold the records, one complete record on each line. Each record folder holds the member files of one record type. The records are the same as in a single document. (Contract section 16, `MFP-1` to `MFP-9`.)

```mermaid
flowchart TD
    F["package folder"]
    M["oasis-package.json<br/>the manifest file: package root, manifest, members[]<br/>no record arrays"]
    SL["storage_locations/<br/>part-00001.jsonl"]
    MD["metadata_definitions/<br/>part-00001.jsonl"]
    C["collections/<br/>part-00001.jsonl"]
    A["assets/<br/>part-00001.jsonl<br/>part-00002.jsonl.gz<br/>source=a/part-00001.jsonl"]
    F --> M
    F --> SL
    F --> MD
    F --> C
    F --> A
```

A record folder may hold subfolders. Member file names are free, but each name ends in `.jsonl` or `.jsonl.gz`. A record folder may be absent when its list is absent. A file in a record folder that the manifest does not list makes the package invalid (`MFP-3`).

```mermaid
erDiagram
    MANIFEST_FILE ||--|| MANIFEST : "manifest (req)"
    MANIFEST ||--o{ NAMESPACE_DECLARATION : "namespaces[]"
    MANIFEST ||--o{ MEMBER_ENTRY : "members[]"
    MEMBER_ENTRY ||--|| MEMBER_FILE : "path names one file"
    MEMBER_FILE ||--o{ RECORD : "one record on each line"

    MANIFEST_FILE {
        string type "const package, req"
        string spec_version "2.0.0-draft.4, req"
        string id "req"
        object source
        object extensions
    }
    MANIFEST {
        object producer "name, version, req"
        datetime produced_at "req"
        object counts "total per record list, across all member files, req"
        array namespaces "req, every token used in any member file"
        array members "marks the multi-file form"
        string description
    }
    MEMBER_ENTRY {
        string path "req, relative to the package folder"
        string record_type "req, equals the first segment of path"
        integer count "req, number of lines in the file"
        integer size_bytes "req, size as stored"
        string sha256 "req, 64 lowercase hex digits, of the stored bytes"
    }
    MEMBER_FILE {
        bytes content "JSON Lines, plain or gzip"
    }
    RECORD {
        string id "req, unique per record type in the whole package"
    }
```

Rules that the diagrams show:

- `record_type` states the type of every record in the file. A line carries no `type` and no `spec_version` (`MFP-2`, `REC-1`).
- Every line ends with one LF, the last line too. No CR, no blank line, no byte-order mark, and no space (U+0020) or tab (U+0009) before or after the object (`MFP-4`).
- A `.jsonl.gz` file is a gzip stream. Its compressed size is `size_bytes`, and its compressed bytes give `sha256` (`MFP-2`, `MFP-4`).
- Each `counts` value is the sum of the member counts of its record type (`MFP-5`, `PKG-3`).
- A list is absent when no member entry has its record type. It is empty when its member counts total 0 (`MFP-6`).
- References, identifier uniqueness, collection positions, and namespace declarations apply across all member files. A record may reference a record in a later file (`MFP-7`).
- The order of `members` and of lines carries no meaning. A checker uses manifest order, then line order, only to choose which repeat it reports (`MFP-7`, `PKG-8`).
- The producer writes the member files first and the manifest file last (`MFP-8`).

A single document and a multi-file package with the same root, the same present and absent lists, and the same records are equivalent. When each record list keeps its record order, a checker gives both the same outcome and the same findings (`MFP-9`).
