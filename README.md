# OASIS

**Open Asset Standard Interchange Schema**

> **DRAFT 2.0.0-draft.3, not a final release.**
> These rules are a draft and can change before the final release.

## What OASIS is

OASIS is a neutral JSON format for exchanging media asset records between systems.
Version 2.0 is the current major version.

- **One package.** A package is one JSON document. It is the only exchange document. Standalone records do not exist.
- **Record lists.** A package holds storage locations, metadata definitions, and collections once. Records point at each other by id, and every reference resolves inside the package.
- **Records.** The package root carries `type` and `spec_version`. Records inside a package carry neither field.
- **Exact time.** Rates are rational numbers. Timing is in whole frames or in seconds. Timecode labels are optional, and they must agree with the frames.
- **Versions and file copies.** Each version owns its files, file groups, and annotations. A file lists its copies in `locations`.
- **Explicit file groups.** Files that belong together are listed in a file group with tracks. Grouping is never guessed.
- **Namespaced extensions.** Custom data goes in a declared namespace. Unknown keys anywhere else are rejected.
- **Optional access summary.** An asset or collection may state `none` or `restricted`. An absent summary means unknown. An annotation may state `public` or `private` visibility. An absent visibility means unknown.

The schemas use JSON Schema 2020-12. They are in [definitions/](definitions/README.md).

Interoperability between independent implementations is not demonstrated.
OASIS makes no claim of certification, production readiness, or endorsement by any organization.

## Document root

The only document root is a package.

| Type | Schema file | Describes |
| --- | --- | --- |
| `package` | `package.schema.json` | One exchange: a manifest, the record lists, and the assets. |

The asset, collection, storage location, and metadata definition schemas describe records inside a package. They are not document roots.

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
- [Examples](definitions/examples/README.md): synthetic example packages.
- [Contract](docs/specification/2.0.0-draft.3/CONTRACT.md): the normative rules for this draft.
- [Glossary](docs/specification/2.0.0-draft.3/GLOSSARY.md): the terms used in the documents.
- [Data model](docs/specification/2.0.0-draft.3/DATA-MODEL.md): diagrams of the model. Informative.
- [Conformance harness](tests/conformance/README.md): setup, test commands, and the diagnostic catalog.

## Version history

- 2.0.0-draft.3 is a draft. It is not a final release.
- 2.0.0-draft.3 follows 2.0.0-draft.2. The contract lists the changes between the two drafts.

See [CHANGELOG.md](CHANGELOG.md) for the details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Every commit needs a Developer Certificate of Origin sign-off (`git commit -s`).

## License

OASIS is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
Copyright 2026 North Shore Automation, LLC.
The license covers the schemas, documentation, examples, and the synthetic conformance corpus.
