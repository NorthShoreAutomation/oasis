# OASIS Schema Definitions

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
      "path": "/full/path"
    }
  ]
}
```

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

These schemas are now maintained as part of the exodus project. They were originally sourced from an external schema-design repository but are now independently managed here.

**Migration History**:
- Previously synced from an external schema-design repository
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
