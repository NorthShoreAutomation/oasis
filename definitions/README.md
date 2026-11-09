# OASIS schema definitions

Status: DRAFT 2.0.0-draft.4, not a final release. These files can change before the final release.
Interoperability between independent implementations is not demonstrated.

This directory holds the OASIS 2.0 schema bundle.
OASIS means Open Asset Standard Interchange Schema.
The schemas use JSON Schema 2020-12.
The [contract](../docs/specification/2.0.0-draft.4/CONTRACT.md) is the normative text. It also states the rules that a schema cannot express.

For how to validate and exchange documents, read the [adopter guide](../docs/ADOPTION.md).
For synthetic example documents, see [examples/](examples/README.md).

## Schema files

The bundle has six schema files.

| File | Purpose |
| --- | --- |
| `common.schema.json` | Shared definitions, such as the record fields, time base, ranges, access summary, extensions, and date and date-time strings. It is not a document root. |
| `package.schema.json` | A package in either form. For a single-document package, the root with the manifest and the record lists. For a multi-file package, the root in the manifest file, with `manifest.members` and no record lists. It is the only document root. |
| `asset.schema.json` | The asset record inside a package, with its versions, files, file groups, relationships, metadata values, and annotations. It also checks each line of an asset member file. It is not a document root. |
| `collection.schema.json` | The collection record inside a package. It is not a document root. |
| `storage_location.schema.json` | The storage location record inside a package. It is not a document root. |
| `metadata_definition.schema.json` | The metadata definition record inside a package. It is not a document root. |

## Document root

The only document root is a package. Its schema is `package.schema.json`.
There are no standalone records. Annotations live inside assets, and there is no `annotation.schema.json`.
The package root carries `type` and `spec_version`. Records inside a package carry neither field.
A package has two forms. A single-document package is one JSON document.
A multi-file package is a package folder: the manifest file `oasis-package.json` holds the root, and member files hold the records, one on each line.
`package.schema.json` checks the manifest file. Each line of a member file is checked against the record schema of its record type, for example `asset.schema.json` for a file in `assets/`.
`spec_version` is `2.0.0-draft.4` in this draft.
A checker compares `spec_version` exactly with `2.0.0-draft.4`.
It reports any other value as unsupported, and it never validates such a document against these schemas.

## Bundle manifest

`bundle-manifest.json` describes the bundle. It is distribution metadata, not an OASIS record. It is not the manifest file `oasis-package.json` of a multi-file package.

| Field | Meaning |
| --- | --- |
| `id_base` | The base of every schema identifier: `https://www.northshoreautomation.com/schemas/oasis/2/`. |
| `document_roots` | The record types that can be the root of a document. In this draft the only one is `package`. |
| `schemas[]` | One entry per schema file, with its `name` and `path`. |
| `schemas[].$id` | The stable absolute identifier of the file. It equals the `$id` inside the file. |
| `schemas[].sha256` | The SHA-256 digest of the file bytes. A loader refuses a file whose digest differs. |
| `namespace_declaration` | Where extension namespaces are declared (`manifest.namespaces` in a package), the declaration fields, and the reserved tokens. The only reserved token is `oasis`. Producers never declare or use it. |

The manifest also states the `json_schema_dialect`, the `spec_version`, and the `bundle_revision`.

## Identifiers never resolve

Each schema `$id` is a name, not a location.
A validator never fetches an identifier from the network.
Load every schema from this bundle, and check each file against its digest in the manifest.
A reference to any resource outside the bundle is a setup failure.

## Bundle digest

The digests below pin the current bytes of the 2.0.0-draft.4 bundle.
Any schema change updates them, until the draft is published.
The SHA-256 digest of `bundle-manifest.json` is:

```text
4c7e5b3ce2f6a341c06e3c22c8a643af8e33b50e3e737242fb4569a0bcac5673
```

The bundle manifest holds the digest of every schema file, so this one digest fixes the whole bundle.
The validate command reports the same value as `bundle_manifest_sha256` in its result record, for both package forms.
This digest is not a member file digest. The manifest file of a multi-file package lists the SHA-256 of each member file in `manifest.members`.
