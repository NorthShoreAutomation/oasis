# Changelog

All notable changes to this project are recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

The planned label for the next publication is `1.2.0-draft.1`.
It is a draft. It is not a final release.
Interoperability between independent implementations is not yet demonstrated.
Schema acceptance did not change. Records that the 1.1.1 schemas accept are still accepted, and records that they reject are still rejected.

### Added

- Neutral descriptions in the schema files.
- A bundle manifest that lists the schema files.
- A conformance harness and a synthetic test corpus.
- An exchange profile checker.
- An adopter guide and synthetic example records.
- The contract and glossary for the draft, in `docs/specification/1.2.0-draft.1/`.
- Governance, contribution, and license files.

## [1.1.1] - 2026-07-22

### Changed

- Re-cut of 1.1.0 as a signed tag. The schema files are identical to 1.1.0.

## [1.1.0] - 2026-07-04

### Added

- Readiness fields for non-migratable items in the migration report output schema.

### Changed

- Documented conventional file role values in `asset.schema.json`.
- Removed a legacy name from the schema identifiers and the definitions README.

## [1.0.0] - 2026-01-24

### Added

- Initial release of the OASIS schema definitions.

[Unreleased]: https://github.com/NorthShoreAutomation/oasis/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/NorthShoreAutomation/oasis/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/NorthShoreAutomation/oasis/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/NorthShoreAutomation/oasis/releases/tag/v1.0.0
