# Changelog

All notable changes to this project are recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

The planned label for the next publication is `2.0.0-draft.2`.
It is a draft. It is not a final release.
The earlier `2.0.0-draft.1` review candidate was superseded by this draft before release and is not a published version.
Interoperability between independent implementations is not demonstrated.

### Added

- The OASIS 2.0 schema bundle in `definitions/`: seven JSON Schema 2020-12 files and a bundle manifest with stable identifiers and SHA-256 digests.
- The 2.0 contract, glossary, and data model, in `docs/specification/2.0.0-draft.2/`.
- Synthetic examples for every record type, including three packages, in `definitions/examples/`.
- File roles on files (`FILE-5`) and a `segment_index` on file group members for one recording split across several files (`GRP-6`), both added in 2.0.0-draft.2.
- A conformance harness for 2.0 with a synthetic fixture corpus, in `tests/conformance/`.
- The `validate` command, which checks one document file and reports one result record in text or JSON.
- The adopter guide, governance, contribution, and license files.

[Unreleased]: https://github.com/NorthShoreAutomation/oasis/commits/main
