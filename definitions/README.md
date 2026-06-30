# Lodestar Schema Definitions

JSON Schema definitions for universal media asset management operations.

## Overview

These schemas define the data structures for platform-agnostic DAM/MAM migrations and operations. They are embedded into the exodus binary at build time via Go's `embed` package.

## Schema Files

| File | Purpose | Used By |
|------|---------|---------|
| `asset.schema.json` | Individual asset structure with files and metadata | Asset validation |
| `asset_batch_import.schema.json` | Batch asset import format | `exodus assets ingest` |
| `collection.schema.json` | Collection hierarchy structure | Collection operations |
| `collection_batch_import.schema.json` | Batch collection import format | `exodus collections import` |
| `metadata_set.schema.json` | Metadata field definitions | `exodus metadata import/export` |
| `storage_location.schema.json` | Storage location references | Asset file tracking |
| `migration-report-output.schema.json` | Migration reporting format | Migration operations |

## Usage in Go Code

Schemas are automatically embedded and validated at runtime:

```go
import "github.com/NorthShoreAutomation/exodus/internal/schema"

// Schemas are available via the embedded package
reader, err := schema.GetEmbeddedSchema("asset.schema.json")

// List all embedded schemas
schemas, err := schema.ListEmbeddedSchemas()

// Check if a schema exists
if schema.HasEmbeddedSchema("asset.schema.json") {
    // Schema is available
}
```

## Usage in External Tools (Python, etc.)

**Note**: Python utilities in `utils/` are planned for deprecation and will be ported to Go. For now, they can reference schemas directly:

```python
from pathlib import Path

# Reference schemas from internal/schema/definitions/
schema_dir = Path(__file__).parent.parent / "internal" / "schema" / "definitions"
asset_schema = schema_dir / "asset.schema.json"

# Load and use schema
with open(asset_schema) as f:
    schema_data = json.load(f)
```

## Schema Validation

Schemas are validated automatically during:
- **Asset Ingestion**: `exodus assets ingest --input batch.json`
- **Collection Import**: `exodus collections import --input collections.json`
- **Metadata Import**: `exodus metadata import --input metadata.json`

Validation errors are captured with detailed messages and suggestions for fixes.

## Schema Structure Examples

### Asset Batch Format
```json
{
  "schema_version": "1.0.0",
  "assets": [
    {
      "asset_id": "unique-id",
      "title": "Asset Title",
      "type": "video",
      "files": [...],
      "metadata_sets": [...]
    }
  ]
}
```

### Collection Batch Format
```json
{
  "schema_version": "1.0.0",
  "collections": [
    {
      "collection_id": "collection-id",
      "label": "Collection Name",
      "parent": "parent-id-or-null",
      "extensions": { "full_name": "Projects/2024/Launch" }
    }
  ]
}
```

See [Collection file roles](#collection-file-roles) for the difference between
logical and mapped collection files.

### Metadata Set Format
```json
{
  "set_id": "custom_metadata",
  "label": "Custom Fields",
  "schema_version": "1.0.0",
  "fields": [
    {
      "name": "field_name",
      "label": "Display Label",
      "type": "string",
      "required": false
    }
  ]
}
```

## Collection file roles

A collection-batch file (`collection_batch_import.schema.json`, records under the
`collections` key) plays **one of two roles**. Both use the same `Collection`
schema; the role is determined by which marker each record carries. Exodus
auto-detects the role from the data (`CollectionTypeFromData`: `full_path` =>
mapped, `full_name` => logical) or you can force it with
`collections import --type collections|mapped_collections`.

> **Where the markers live:** Exodus reads `full_name` and `full_path` from
> **`extensions`** (`extensions.full_name` / `extensions.full_path`). A
> top-level `full_name` is also defined on the schema as an optional
> human-readable mirror, but the importer's type detection and path resolution
> read the `extensions` values — put the marker under `extensions`.

### 1. Logical collections file

A named catalog hierarchy. Each record carries `extensions.full_name` (the full
slash-delimited name path). `parent` is the parent collection's `collection_id`.

```json
{
  "schema_version": "1.0.0",
  "collections": [
    {
      "collection_id": "4808",
      "label": "Launch",
      "parent": "4807",
      "extensions": { "full_name": "Projects/2024/Launch" }
    }
  ]
}
```

### 2. Mapped collections file

A storage-mirror tree that recreates the source storage's physical folder
hierarchy as Iconik collections, **one record per folder**. Each record carries
`extensions.full_path` (the real source storage path of that folder).
`label` is the **leaf folder name** and `parent` is the **parent folder's
`collection_id`**. At import, Exodus binds each folder to an Iconik storage via
the config's `unified_mappings` (source path prefix => `iconik_storage_id`),
keyed by the normalized `full_path` — the `storage_id` is therefore NOT carried
in the file.

```json
{
  "collections": [
    {
      "collection_id": "Vm9sdW1lcy9Qcm9kdWN0aW9uLU5BUy9DYXRhbG9ncw==",
      "label": "Catalogs",
      "parent": "Vm9sdW1lcy9Qcm9kdWN0aW9uLU5BUw==",
      "extensions": { "full_path": "Volumes/Production-NAS/Catalogs" }
    },
    {
      "collection_id": "Vm9sdW1lcy9Qcm9kdWN0aW9uLU5BUy9DYXRhbG9ncy8yMDI0",
      "label": "2024",
      "parent": "Vm9sdW1lcy9Qcm9kdWN0aW9uLU5BUy9DYXRhbG9ncw==",
      "extensions": { "full_path": "Volumes/Production-NAS/Catalogs/2024" }
    }
  ]
}
```

`collection_id` here is conventionally a stable, deterministic id derived from
the folder's `full_path` (e.g. base64 of the path), so a child's `parent` can be
computed from its parent folder's path without a second pass.

### Anti-pattern (NOT a mapped collections file)

A flat **asset-to-folder junction table** is **not** a mapped collections file.
The following is wrong: it is one row per asset (not one per folder), has no
`extensions.full_path`, and encodes membership inline.

```json
{
  "mapped_collections": [
    { "asset_id": "a1", "collection_id": "c1", "label": "Catalogs" },
    { "asset_id": "a2", "collection_id": "c1", "label": "Catalogs" }
  ]
}
```

A mapped file defines **folders** (one record per folder, with
`extensions.full_path`). Asset placement is resolved separately, at
`assets import`, by matching each asset's file path to a folder record.

### Membership is not a junction file

Which assets belong to a collection is expressed on the entities themselves —
via the asset's `collections[]` (references by `collection_id`) and/or the
collection's `assets[]` (array of asset ids) — **not** as a standalone
`{asset_id, collection_id, label}` junction file.

## Modifying Schemas

1. **Edit schema file**: Make changes to the appropriate `.schema.json` file
2. **Validate syntax**: Use `jq` or JSON validator to check syntax
3. **Rebuild**: Run `make build` to embed updated schemas
4. **Test**: Run tests to ensure backward compatibility

```bash
# Validate schema syntax
jq . internal/schema/definitions/asset.schema.json > /dev/null

# Rebuild with updated schemas
make clean build

# Test with updated schemas
make test
```

## Schema Ownership

These schemas are now maintained as part of the exodus project. They were originally sourced from the lodestar-schema-design repository but are now independently managed here.

**Migration History**:
- Previously synced from external `lodestar-schema-design` repository
- Migrated to `internal/schema/definitions/` on 2025-11-05
- Now version-controlled as part of exodus source tree

## Adding New Schemas

1. Create new `.schema.json` file in this directory
2. Follow JSON Schema Draft 7 specification
3. Add documentation to this README
4. Update validation code in `internal/schema/validator.go` if needed
5. Rebuild and test

## Related Documentation

- [Main README](../../../README.md) - Project overview
- [Schema Package](../embedded.go) - Go embed implementation
- [Validation Code](../validator.go) - Schema validation logic
- [Asset Ingestion Guide](../../../docs/ASSET_INGESTION.md) - Usage examples

## Support

For schema-related issues:
1. Check validation error messages for specific schema violations
2. Review schema file for field requirements and types
3. See main project documentation for usage examples
4. File issues at project repository for schema bugs or improvements
