# OASIS

**Open Asset Standard Interchange Schema**

> **DRAFT 2.0.0-draft.2, not a final release.**
> These rules are a draft and can change before the final release.

## What OASIS is

OASIS is a neutral JSON format for exchanging media asset records between systems.
Version 2.0 is the current major version.

- **One package.** A package is one JSON document. It is the unit of exchange.
- **Registries.** A package holds shared storage locations, metadata definitions, and collections once. Records point at them by id.
- **Records.** Every record carries `type`, `spec_version`, and `id`. A record can also stand alone as its own document.
- **Exact time.** Rates are rational numbers. Positions are whole frames from the first frame. Seconds and timecode labels are optional, and they must agree with the frames.
- **Explicit file groups.** Files that belong together are listed in a file group with tracks. Grouping is never guessed.
- **Namespaced extensions.** Custom data goes in a declared namespace. Unknown keys anywhere else are rejected.
- **Access summary.** Every asset and collection states `none`, `restricted`, or `unknown`. A receiver that cannot keep a restriction blocks or quarantines the entity.

The schemas use JSON Schema 2020-12. They are in [definitions/](definitions/README.md).

Interoperability between independent implementations is not demonstrated.
OASIS makes no claim of certification, production readiness, or endorsement by any organization.

## Record types

A document root is one of six record types.

| Type | Schema file | Describes |
| --- | --- | --- |
| `package` | `package.schema.json` | One exchange: a manifest, the registries, and the assets. |
| `asset` | `asset.schema.json` | One content item, with its files, file groups, versions, relationships, metadata values, and annotations. |
| `collection` | `collection.schema.json` | A named grouping of assets, with its membership. |
| `storage_location` | `storage_location.schema.json` | A place where files live. Validation never connects to it. |
| `metadata_definition` | `metadata_definition.schema.json` | One metadata field: its value type, cardinality, and options. |
| `annotation` | `annotation.schema.json` | A statement about an asset, optionally about a frame range of it. |

## Quick start

The conformance harness checks OASIS documents.
It needs Python 3 and works offline after the packages are installed.
Run these commands from the repository root.

```sh
git clone https://github.com/NorthShoreAutomation/oasis.git
cd oasis
python3 -m venv tmp/oasis-conformance
. tmp/oasis-conformance/bin/activate
python3 -m pip install -r tests/conformance/requirements-lock.txt
python3 -m tests.conformance.validate definitions/examples/package-complete.json
```

The last command checks one document file. It prints `PASS`, `FAIL`, or `ERROR` and the findings.
Use it on your own documents. The [adopter guide](docs/ADOPTION.md#validate-a-document) explains the output.
To run the full test suite, see the [conformance harness README](tests/conformance/README.md).

## Documentation

- [Adopter guide](docs/ADOPTION.md): how to produce, validate, and receive OASIS 2.0 documents.
- [Schema definitions](definitions/README.md): the schema files and the bundle manifest.
- [Examples](definitions/examples/README.md): synthetic example documents for every record type.
- [Contract](docs/specification/2.0.0-draft.2/CONTRACT.md): the normative rules for this draft.
- [Glossary](docs/specification/2.0.0-draft.2/GLOSSARY.md): the terms used in the documents.
- [Data model](docs/specification/2.0.0-draft.2/DATA-MODEL.md): diagrams of the model. Informative.
- [Conformance harness](tests/conformance/README.md): setup, test commands, and the diagnostic catalog.

## Version history

- 2.0.0-draft.2 is a draft. It is not a final release.
- 2.0.0-draft.2 replaces the 2.0.0-draft.1 review candidate, which was not released. The contract lists the field changes between the two drafts.

See [CHANGELOG.md](CHANGELOG.md) for the details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Every commit needs a Developer Certificate of Origin sign-off (`git commit -s`).

## License

OASIS is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
Copyright 2026 North Shore Automation, LLC.
The license covers the schemas, documentation, examples, and the synthetic conformance corpus.
