# OASIS schema definitions

Status: DRAFT 2.0.0-draft.2, not a final release. These files can change before the final release.
Interoperability between independent implementations is not demonstrated.

This directory holds the OASIS 2.0 schema bundle.
OASIS means Open Asset Standard Interchange Schema.
The schemas use JSON Schema 2020-12.
The [contract](../docs/specification/2.0.0-draft.2/CONTRACT.md) is the normative text. It also states the rules that a schema cannot express.

For how to validate and exchange documents, read the [adopter guide](../docs/ADOPTION.md).
For synthetic example documents, see [examples/](examples/README.md).

## Schema files

The bundle has seven schema files.

| File | Purpose |
| --- | --- |
| `common.schema.json` | Shared definitions, such as the record fields, time base, ranges, access summary, extensions, and date and date-time strings. It is not a document root. |
| `package.schema.json` | A package: the manifest, the registries, and the assets. |
| `asset.schema.json` | One asset, with its files, file groups, versions, relationships, metadata values, and annotations. |
| `collection.schema.json` | One collection and its membership. |
| `storage_location.schema.json` | One storage location. |
| `metadata_definition.schema.json` | One metadata definition. |
| `annotation.schema.json` | One standalone annotation. |

## Document roots

A document root is one of six record types: `package`, `asset`, `collection`, `storage_location`, `metadata_definition`, and `annotation`.
Each type has the schema file of the same name.
A reader reads `type` and `spec_version` first, then selects the schema.
`spec_version` is `2.0.0-draft.2` in this draft.
This draft's checker reports any `spec_version` other than `2.0.0-draft.2` as unsupported, and it never validates such a document against these schemas.
A document whose `spec_version` major is not 2 is never routed to a 2.x schema, and a document with no supported `type` is also reported as unsupported.

## Bundle manifest

`bundle-manifest.json` describes the bundle. It is distribution metadata, not an OASIS record.

| Field | Meaning |
| --- | --- |
| `id_base` | The base of every schema identifier: `https://www.northshoreautomation.com/schemas/oasis/2/`. |
| `document_roots` | The six record types that can be the root of a document. |
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

## Freeze digest

The bundle for 2.0.0-draft.2 is frozen. Its files do not change within this draft.
The SHA-256 digest of `bundle-manifest.json` is:

```text
2f3af80fd1843180da249bb8b33b525f040328fbc57f36440d8fa1f9a36bfc30
```

The manifest holds the digest of every schema file, so this one digest fixes the whole bundle.
The validate command reports the same value as `bundle_manifest_sha256` in its result record.
