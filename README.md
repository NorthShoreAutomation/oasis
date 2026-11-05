# OASIS

**Open Asset Standard Interchange Schema**

> **DRAFT 2.0.0-draft.4, not a final release.**
> These rules are a draft and can change before the final release.

## What OASIS is

OASIS is a neutral JSON format for exchanging media asset records between systems.
Version 2.0 is the current major version.

- **Two package forms.** A package can be one JSON document or a folder with a manifest file and member files. Use the folder form for very large exports. Standalone records are not exchange documents.
- **Record lists.** A package holds storage locations, metadata definitions, collections, and assets. A multi-file package splits these lists into member files. Every reference resolves inside the package.
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
| `package` | `package.schema.json` | One exchange: a manifest and record lists, stored in one document or across member files. |

The asset, collection, storage location, and metadata definition schemas describe records inside a package. They are not document roots.

## Quick start

The conformance harness checks both OASIS package forms.
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

The last command checks a single-document package. It prints `PASS`, `FAIL`, or `ERROR` and the findings.
To check the same records in a multi-file package, name its folder:

```sh
python3 -m tests.conformance.validate definitions/examples/multi-file-complete
```

You can also name the folder's `oasis-package.json` manifest file.
The command checks member files and reports one result for the whole package.
It does not unpack archives. Unpack them first using the [adopter guide](docs/ADOPTION.md#unpack-a-tgz-file-safely).
Use the command on your own packages. The [adopter guide](docs/ADOPTION.md#validate-a-document) explains the output.
To run the full test suite, see the [conformance harness README](tests/conformance/README.md).

## Documentation

- [Adopter guide](docs/ADOPTION.md): how to produce, validate, and receive OASIS 2.0 documents.
- [Schema definitions](definitions/README.md): the schema files and the bundle manifest.
- [Examples](definitions/examples/README.md): synthetic example packages.
- [Contract](docs/specification/2.0.0-draft.4/CONTRACT.md): the normative rules for this draft.
- [Glossary](docs/specification/2.0.0-draft.4/GLOSSARY.md): the terms used in the documents.
- [Data model](docs/specification/2.0.0-draft.4/DATA-MODEL.md): diagrams of the model. Informative.
- [Conformance harness](tests/conformance/README.md): setup, test commands, and the diagnostic catalog.

## Version history

- 2.0.0-draft.4 is a draft. It is not a final release.
- 2.0.0-draft.4 follows 2.0.0-draft.3 and adds the multi-file package. Record fields are unchanged.
- The published [draft.3 specification](docs/specification/2.0.0-draft.3/CONTRACT.md) remains at its original paths.
- Each draft lists its changes in its contract. The current checker supports exactly `2.0.0-draft.4`.

See [CHANGELOG.md](CHANGELOG.md) for the details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Every commit needs a Developer Certificate of Origin sign-off (`git commit -s`).

## License

OASIS is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
Copyright 2026 North Shore Automation, LLC.
The license covers the schemas, documentation, examples, and the synthetic conformance corpus.
