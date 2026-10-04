# OASIS examples

Status: DRAFT `1.2.0-draft.1`. These examples are not a release.

These files are synthetic example records for the seven OASIS interchange entry points.
All names, identifiers, and locators are invented. Locators use the reserved `example.invalid` domain, so they cannot point to real data.

Each example is checked by `tests/conformance/test_examples.py`. The test confirms that each example:

- passes the strict JSON input policy;
- is structurally valid against the current schemas in `definitions/`, with date-time formats checked (`required` format mode);
- completes under the `exchange-1x` profile with an empty reference context, with only the warnings listed below.

A warning does not mean the example is wrong.
It shows that a meaning is not yet defined by the profile, so a receiver must decide how to treat it.
See [the adopter guide](../../docs/ADOPTION.md) for the meaning of each diagnostic code.

The examples contain no `connection_details`, `security`, `permissions`, or `rights_information` with content.
Those properties block the `exchange-1x` profile in this DRAFT.

## Examples

| File | Entry point | What it shows |
| --- | --- | --- |
| `asset.json` | `asset.schema.json` | One asset with a primary file, a nested proxy derivative, embedded storage locations, a metadata set with values, an embedded collection, a timed annotation, and an extension. |
| `asset-batch.json` | `asset_batch_import.schema.json` | Two assets in one batch. An embedded collection lists both assets, and both references resolve inside the batch. |
| `collection.json` | `collection.schema.json` | One standalone collection with a parent storage location, a metadata field definition, asset membership, and an extension. |
| `collection-batch.json` | `collection_batch_import.schema.json` | Three collections. Two child collections name a parent collection in the same batch. |
| `metadata-set.json` | `metadata_set.schema.json` | Standalone metadata field definitions with no recorded values. |
| `storage-location.json` | `storage_location.schema.json` | One storage location with no connection or security data. |
| `temporal-annotation.json` | `temporal_annotation.schema.json` | One range annotation with a frame range and an explicit positive frame rate. |

## Expected `exchange-1x` warnings

Paths are JSON Pointers ([RFC 6901](https://www.rfc-editor.org/rfc/rfc6901.html)). The empty path is the document root.

| File | Code | Path | Why |
| --- | --- | --- | --- |
| `asset.json` | `CHECKSUM_UNINTERPRETED` | `/files/0/checksum` | The checksum string does not say which algorithm or bytes it covers. |
| `asset.json` | `INTEGRITY_UNVERIFIED` | `/files/0/derivatives/0` | The proxy file has no checksum. |
| `asset.json` | `VALUE_SEMANTICS_UNSPECIFIED` | `/metadata_sets/0/fields/0/value` | A recorded metadata value has no selected representation contract. |
| `asset.json` | `VALUE_SEMANTICS_UNSPECIFIED` | `/metadata_sets/0/fields/1/value` | Same as above. |
| `asset-batch.json` | `COMPLETENESS_UNVERIFIED` | (root) | A batch never proves that it contains the full source export. |
| `asset-batch.json` | `CHECKSUM_UNINTERPRETED` | `/assets/0/files/0/checksum` | See above. |
| `asset-batch.json` | `CHECKSUM_UNINTERPRETED` | `/assets/1/files/0/checksum` | See above. |
| `collection.json` | `REFERENCE_UNRESOLVED` | `/assets/0` | The referenced asset is not in the document or in the reference context. |
| `collection.json` | `REFERENCE_UNRESOLVED` | `/assets/1` | Same as above. |
| `collection-batch.json` | `COMPLETENESS_UNVERIFIED` | (root) | See above. |

`metadata-set.json`, `storage-location.json`, and `temporal-annotation.json` produce no diagnostics.

The `collection.json` warnings go away when the caller supplies the asset identifiers `asset-0001` and `asset-0002` in the reference context.
The adopter guide shows how to supply that context.
