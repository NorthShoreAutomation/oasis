# OASIS 1.x glossary

Status: DRAFT 1.2.0-draft.1. Approved for publication as a draft. Not a final release. Interoperability between independent implementations is not yet demonstrated.
OASIS means Open Asset Standard Interchange Schema.
This glossary defines concepts. It does not rename serialized legacy fields or assign destination behavior.

| Term | Meaning and boundary |
| --- | --- |
| Asset | A described media or content item. Its record may contain file, metadata, collection, or annotation information. A record alone does not prove the referenced media exists. |
| File record | A description of media bytes or companion data associated with an asset. The 1.x record has a locator and an embedded storage location. It is not a globally identified physical file. |
| Storage location | A recorded storage context and locator. One recorded location does not establish that it is the only copy. |
| Locator | A string used to describe where data may be found. Legacy locators may be paths, uniform resource identifiers, or container references. Validation never dereferences one. |
| File purpose | The intended use of a file, such as primary media, a preview, a thumbnail, or companion metadata. The legacy `role` field has a separate published grouping rule. |
| File group | Related file records treated together. Published 1.x treats equal `role` values within an asset as one logical group. Do not use that rule to infer independently identified renditions or tracks. |
| Derivative | A file represented within another file's `derivatives` list. The nesting does not define a processing recipe or a complete edit history. |
| Collection | A logical grouping of assets. It need not correspond to a storage directory. Embedded and standalone 1.x membership shapes differ. |
| Membership | A recorded association between an asset and a collection. The DRAFT does not make either side a complete authoritative snapshot. |
| Metadata field definition | Recorded information about a field, such as its name, declared type, or permitted values. These declarations are document data, not automatically executed JSON Schema rules. |
| Metadata value | Data associated with a field. The baseline permits unconstrained embedded values and accepts standalone values through open properties. A structural result does not prove value semantics. |
| Annotation | Information associated with a media item or time position. Its purpose is separate from a destination-specific annotation type. |
| Legacy annotation type | A published 1.x token: `Generic`, `Comments`, `QualityControlMarker`, or `Transcription`. Preserve tokens and absence literally. Do not assume equivalent meanings in other systems. |
| Frame position | A numeric position expressed in frames. Meaningful conversion requires a defined rate and origin. The DRAFT does not invent them. |
| Timecode | A formatted label for a time position. A matching legacy pattern does not prove valid clock fields, drop-frame numbering, rate, or origin. |
| Provenance | Information about a record's source, creation, or changes. Unspecified legacy identifiers do not establish a universal source namespace. |
| Identity scope | The context in which an identifier distinguishes an entity. The DRAFT never assumes identifiers from separate exchanges share a global namespace. |
| Extension | Data outside the core declared fields where the selected schema permits it. An open asset root does not make every embedded object open. |
| Batch | An envelope containing asset or collection records. Its length does not prove that the export includes every requested source record. |
| Completeness | Whether a transfer contains the entire intended scope. This requires a defined scope and reconciliation evidence beyond a count or checksum. |
| Integrity | Whether data matches an expected byte sequence or digest. It does not establish completeness, permission, or correct import. |
| Preservation | Retention of the selected information across a producer/consumer operation under an explicit comparison rule. Schema validity alone is not preservation evidence. |
| Profile | An explicitly selected set of structural and semantic rules. Profile selection is separate from structural placement and wire-version labels. |
| Structural context | The placement in which data is checked, such as standalone, asset-embedded, or batch-contained. Context is not profile selection. |
| Schema acceptance | Agreement with a selected JSON Schema and declared validator configuration. It is one result, not permission to execute an import. |
| Semantic outcome | The result of checking approved meaning and relationship rules beyond structural validation. Unresolved or unsupported meaning must remain visible. |
| Diagnostic | A code, document path, severity, and informative message describing an outcome. Messages must not reproduce confidential values. |
| Producer | An implementation that emits records for the selected profile. A validator alone is not a producer. |
| Consumer | An implementation that reads records and produces a declared outcome while meeting the selected preservation rules. A validator alone is not a consumer. |
| Independent implementation | A producer/consumer implementation with separately authored semantic and preservation logic, documented dependencies, and source provenance. |
| DRAFT | A published specification that is not final, with explicit evidence gaps. It does not claim certification, demonstrated interoperability, or production readiness. |
