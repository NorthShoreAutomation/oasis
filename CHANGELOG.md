# Changelog

All notable changes to this project are recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

The planned label for the next publication is `2.0.0-draft.3`.
It is a draft. It is not a final release.
The published `2.0.0-draft.2` draft is the version before it. The contract lists the changes between the two drafts.
Interoperability between independent implementations is not demonstrated.

### Added

- The OASIS 2.0 schema bundle in `definitions/`: six JSON Schema 2020-12 files and a bundle manifest with stable identifiers and SHA-256 digests.
- The 2.0 contract, glossary, and data model, in `docs/specification/2.0.0-draft.3/`.
- Synthetic example packages in `definitions/examples/`.
- File roles on files (`FILE-5`) and a `segment_index` on file group members for one recording split across several files (`GRP-6`), both added in 2.0.0-draft.2.
- 2.0.0-draft.3 changes: the package is the only exchange document, timing in frames or seconds, versions that own their files and annotations, file copies in `locations`, membership on the member, metadata `list_type`, annotation `visibility`, optional `access`, exact number limits, and an exact version check. See the contract section "Changes in 2.0.0-draft.3".
- A conformance harness for 2.0 with a synthetic fixture corpus, in `tests/conformance/`.
- The `validate` command, which checks one document file and reports one result record in text or JSON.
- The adopter guide, governance, contribution, and license files.

### Changed

- The compatibility promise in `CONTRIBUTING.md` and `docs/GOVERNANCE.md` starts at the first final release of a major version. Before that release, a draft can make breaking changes, and each draft lists its changes in its contract.

### Removed

- The 2.0.0-draft.2 folder, `docs/specification/2.0.0-draft.2/`, with the draft.2 contract, glossary, and data model. The draft.2 text stays at the `v2.0.0-draft.2` tag and its pre-release.

[Unreleased]: https://github.com/NorthShoreAutomation/oasis/commits/main
