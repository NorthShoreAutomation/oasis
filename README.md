# OASIS

**Open Asset Standard Interchange Schema**

Universal JSON Schema definitions for media asset management (MAM/DAM) operations.

## Overview

OASIS provides platform-agnostic schema definitions for asset migration, metadata handling, and collection management across MAM/DAM systems. Think of it as an oasis in the desert of vendor lock-in—a universal interchange format that lets you migrate between CatDV, Dalet, EditShare, Iconik, and other media asset management platforms.

Used by the [exodus](https://github.com/NorthShoreAutomation/exodus) migration tool.

## Schemas

See [definitions/README.md](definitions/README.md) for detailed documentation.

| Schema | Purpose |
|--------|---------|
| `asset.schema.json` | Individual asset structure with files and metadata |
| `asset_batch_import.schema.json` | Batch asset import format |
| `collection.schema.json` | Collection hierarchy structure |
| `collection_batch_import.schema.json` | Batch collection import format |
| `metadata_set.schema.json` | Metadata field definitions |
| `storage_location.schema.json` | Storage location references |
| `temporal_annotation.schema.json` | Time-based annotations for video/audio |
| `migration-report-output.schema.json` | Migration reporting format |

## Usage

### As Git Submodule (Recommended)

```bash
git submodule add https://github.com/NorthShoreAutomation/oasis.git schemas
```

### Direct Download

```bash
curl -L https://github.com/NorthShoreAutomation/oasis/archive/main.tar.gz | tar xz
```

### Validation Example

```bash
# Using jq to validate syntax
jq . definitions/asset.schema.json > /dev/null && echo "Valid JSON"
```

## Contributing

We welcome contributions! Please:

1. Fork this repository
2. Create a feature branch (`git checkout -b feature/my-change`)
3. Make your changes to schema files
4. Validate JSON syntax: `jq . definitions/*.schema.json`
5. Submit a pull request

### Schema Guidelines

- Follow [JSON Schema Draft 7](https://json-schema.org/draft-07/schema) specification
- Use descriptive field names and documentation
- Include examples in schema descriptions
- Maintain backward compatibility when possible
- Document breaking changes in PR description

## Version History

- **v1.0.0** (2026-01-24) - Initial release extracted from exodus repository

## License

Apache 2.0

## Support

- Issues: [GitHub Issues](https://github.com/NorthShoreAutomation/oasis/issues)
- Main Project: [exodus](https://github.com/NorthShoreAutomation/exodus)
