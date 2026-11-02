# OASIS 2.0 conformance fixtures

## Provenance and terms

Every file in this directory is synthetic. The fixtures are newly authored OASIS conformance examples.
They contain no customer data and no data from any real system.
Titles, ids, paths, and storage names are neutral placeholders, such as `a-0001`, "Example Clip", and "Example Share A".
No fixture content or fixture name carries a product or camera brand.
Any host name in a fixture uses the reserved `.invalid` top-level domain.
The fixtures are distributed with the project under the Apache License 2.0.

## Layout

- `records/`: one JSON document per case. The file name without `.json` is the case id.
- `manifest.json`: the expected outcome of every case. It is the expectation authority.

Every file in `records/` has exactly one manifest case, and every case names one file.
`tests/conformance/corpus.py` loads the manifest and fails setup on any shape problem.

A package is the only exchange document in `2.0.0-draft.3`. Most fixtures are strict JSON packages with `spec_version` `2.0.0-draft.3`.
Some fixtures break this on purpose. The `input-` fixtures for malformed input are not strict JSON. Some routing fixtures have a root that is not a package, and others are packages with another `spec_version` or none.

## Manifest shape

```json
{
  "manifest_version": "2.0.0",
  "contract": "2.0.0-draft.3",
  "provenance": {"kind": "synthetic", "source": "...", "reuse_terms": "Apache License 2.0"},
  "cases": [
    {
      "id": "relationship-self",
      "path": "records/relationship-self.json",
      "expected_status": "complete",
      "expected_structural": "valid",
      "expected_diagnostics": [["RELATIONSHIP_SELF", "/assets/0/relationships/0/target"]],
      "rules": ["REL-3", "DOC-3"],
      "note": "An asset is derived from itself."
    },
    {
      "id": "file-status",
      "path": "records/file-status.json",
      "expected_status": "complete",
      "expected_structural": "invalid",
      "expected_diagnostics": [],
      "expected_schema_error": {"keyword": "additionalProperties", "path": "/assets/0/files/0"},
      "rules": ["FILE-1", "REC-7"],
      "note": "A file with the removed status key."
    }
  ]
}
```

## How expectations are read

The sweep in `test_corpus.py` runs each case through the pipeline in order: strict parse, root checks, number checks, structural validation, semantic checks.

- `expected_status` is `input-invalid` when the strict parse refuses the bytes (`DOC-1`) or a number fails `DOC-4`.
  It is `unsupported` when the root checks of `REC-2` stop the document, and `complete` otherwise.
- `expected_structural` is `not-run` when the status is not `complete`, `invalid` when the document has at least one structural error, and `valid` otherwise.
- `expected_diagnostics` is the complete list of `[code, path]` pairs, sorted by path and then by code. Paths are JSON Pointers.
  - A `DOC-1` case lists only `["INPUT_INVALID", ""]`.
  - A `DOC-4` case lists `NUMBER_OUT_OF_RANGE` or `NUMBER_TOO_PRECISE` at each failing number. Inside `extensions`, the path stops at the `extensions` member.
  - An `unsupported` case lists `NOT_EXCHANGE_DOCUMENT` or `VERSION_UNSUPPORTED` at the path that `REC-2` gives.
  - A structurally invalid case lists nothing, because semantic checks run only on a structurally valid document.
  - A `complete` and `valid` case lists every finding. An empty list means no finding at all.
- `rules` names the contract rules the case covers. Every structurally valid case also names `DOC-3`.

Every diagnostic code has severity `error`.
Each structurally invalid case has `expected_schema_error`: the keyword and the pointer of one error that the schema stage reports.
Only a structurally invalid case has this field.
The schema sometimes reports a closed-object failure on the parent object, not on the field. The manifest records the pointer that the validator reports.
A `false` subschema has no keyword. The harness names it `false`.

A document whose bytes are not UTF-8 is not stored here. The tests build those bytes in memory.

## Seeds

Each fixture starts from a small seed, not from a full example, so that no unrelated field adds a diagnostic.
A fixture adds only the fields its case needs.

- The minimal package: `spec_version`, `type` `package`, an `id`, and a manifest with `producer`, `produced_at`, `counts`, and `namespaces`.
  The counts always match the record arrays. A storage location is added only when a file copy refers to it.
- The minimal asset: `a-0001` with the title "Example Clip".
- The frame-form timeline: rate `25/1`, no drop frame, and `duration_frames` 750.
- The minimal metadata definition: `value_type` `string` and `cardinality` `single`, with `list_type` and `options` added for `enum`.

Structural fixtures carry one structural defect each. The validator can report that one defect more than once.
