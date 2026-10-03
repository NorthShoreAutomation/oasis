# OASIS schema definitions

Status: DRAFT `1.2.0-draft.1`. These files are not a release.

This directory holds the JSON Schema (Draft 7) files of OASIS 1.x.
OASIS means Open Asset Standard Interchange Schema.
The schemas describe media asset records, collections, metadata, storage locations, and timed annotations.

For how to validate and exchange records, read the [adopter guide](../docs/ADOPTION.md).
For synthetic example records, see [examples/](examples/README.md).

## Schema files

Seven files are interchange entry points.
The eighth file, `migration-report-output.schema.json`, is an application report.
It is outside the exchange profile.

| File | Purpose |
| --- | --- |
| `asset.schema.json` | One asset, with its files and metadata. |
| `asset_batch_import.schema.json` | A batch of assets. |
| `collection.schema.json` | One collection. |
| `collection_batch_import.schema.json` | A batch of collections. |
| `metadata_set.schema.json` | Metadata field definitions. |
| `storage_location.schema.json` | One storage location. |
| `temporal_annotation.schema.json` | One timed annotation. |
| `migration-report-output.schema.json` | An application report. It is not part of the exchange profile. |

## Entry points

Each of the seven interchange files is a complete entry point.
Use a standalone file to check one record.
Use a batch file to check a list of records in one document.

Some schemas also appear embedded inside others.
For example, an asset can carry embedded storage locations, a collection, and annotations.
The embedded copy follows the rules of its parent schema.
The adopter guide explains the differences between embedded and standalone use.

## Bundle manifest

`bundle-manifest.json` lists every schema file in this bundle.
For each file it gives the name, the relative path, a SHA-256 digest, and the base URI used to register the schema.
Two schemas carry their own absolute identifiers. The manifest lists them, with the extra alias for each.

A validator must load only the files that the manifest lists.
It must not fetch any other resource.
If you change a schema, refresh its digest in the manifest.
The manifest is distribution metadata. It is not an OASIS record.

## Related documents

- [Adopter guide](../docs/ADOPTION.md)
- [Examples](examples/README.md)
- [Conformance harness](../tests/conformance/README.md)
