# Changelog

All notable changes to this project are recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

The planned label for the next publication is `2.0.0-draft.4`.
It is a draft. It is not a final release.
It follows the published `2.0.0-draft.3` draft.
Interoperability between independent implementations is not demonstrated.

### Added

- File role `original` for an original recording or capture.
- A multi-file package for very large exports: an `oasis-package.json` manifest file and member files in a package folder. Member files use JSON Lines, optionally compressed with gzip. The manifest lists each member's record type, byte size, SHA-256 digest, and record count.
- Rules `MFP-1` to `MFP-9` for member paths, folder contents, line framing, compression, counts, cross-file references, ordering, and equivalence with a single-document package.
- A checker that accepts a package folder or its manifest file. It checks member integrity and records across files. Working indexes use SQLite files. The options `--work-dir`, `--max-line-bytes`, and `--max-gzip-ratio` control working storage and reader limits.
- The multi-file example `definitions/examples/multi-file-complete/`, multi-file conformance tests, and adopter guidance for producing, validating, and safely unpacking packages.
- A separate draft.4 contract, glossary, and data model in `docs/specification/2.0.0-draft.4/`. The published draft.3 specification stays unchanged at its original paths.
- An optional `deleted` date-time on collections, with new rule `COL-8`. It states that the source reported the collection deleted. Like an asset's `deleted` (`AST-3`), it is a fact about the source, never an instruction.

### Changed

- File role `master` now means a finished master rendition. Original recordings use `original`; file group roles are unchanged.
- The current schema bundle, examples, checker, and guidance now use `2.0.0-draft.4`. The checker supports exactly that version. The optional collection `deleted` is added, and file roles now distinguish original recordings from finished masters.
- The package schema accepts a manifest member list for the multi-file form. Existing package and safety rules now cover both forms. See [Changes in 2.0.0-draft.4](docs/specification/2.0.0-draft.4/CONTRACT.md#changes-in-200-draft4).

## [2.0.0-draft.3] - 2026-11-02

This draft followed `2.0.0-draft.2`. It was not a final release.
Interoperability between independent implementations was not demonstrated.

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

[Unreleased]: https://github.com/NorthShoreAutomation/oasis/compare/v2.0.0-draft.3...HEAD
[2.0.0-draft.3]: https://github.com/NorthShoreAutomation/oasis/compare/v2.0.0-draft.2...v2.0.0-draft.3
