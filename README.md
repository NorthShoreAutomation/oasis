# OASIS

**Open Asset Standard Interchange Schema**

> **DRAFT 1.2.0-draft.1, not a final release.**
> These rules are approved as a draft and can change before the final release.

## What OASIS is

OASIS is a set of JSON Schema (Draft 7) files that describe media asset records.
A record can describe an asset, its files, where those files are stored, its metadata, the collections it belongs to, and timed annotations.
The goal is a neutral format that any media asset management system can read and write.

OASIS makes no claim of certification, demonstrated interoperability, production readiness, or endorsement by any organization.

## Schemas

The schema files are in [definitions/](definitions/README.md).
Seven are interchange entry points. The eighth is an application report.

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

## Quick start

The conformance harness checks the schemas and the example records.
It needs Python 3 and works offline after the packages are installed.
Run these commands from the repository root.

```sh
git clone https://github.com/NorthShoreAutomation/oasis.git
cd oasis
python3 -m venv tmp/oasis-conformance
. tmp/oasis-conformance/bin/activate
python3 -m pip install -r tests/conformance/requirements-lock.txt
python3 -W error -m unittest discover -s tests/conformance -t . -p 'test_*.py'
```

The conformance README describes a script for setup, other test commands, and the Go adapter.

## Documentation

- [Adopter guide](docs/ADOPTION.md): how to read, validate, and exchange OASIS 1.x records.
- [Schema definitions](definitions/README.md): the schema files and the bundle manifest.
- [Examples](definitions/examples/): synthetic example records for the seven entry points.
- [Contract](docs/specification/1.2.0-draft.1/CONTRACT.md): the normative rules for this draft.
- [Glossary](docs/specification/1.2.0-draft.1/GLOSSARY.md): the terms used in the documents.
- [Conformance harness](tests/conformance/README.md): how the schemas are tested.

## Version history

- The frozen schema baseline is v1.1.1. The harness keeps a copy of it for comparison.
- 1.2.0-draft.1 is a draft. It is not a release.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Every commit needs a Developer Certificate of Origin sign-off (`git commit -s`).

## License

OASIS is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
Copyright 2026 North Shore Automation, LLC.
The license covers the schemas, documentation, examples, and the synthetic conformance corpus.
