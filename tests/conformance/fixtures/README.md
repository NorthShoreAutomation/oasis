# OASIS 2.0 conformance fixtures

## Provenance and terms

Every file in this directory is synthetic. The fixtures are newly authored OASIS conformance examples.
They contain no customer data and no data from any real system.
Any host name in a fixture uses the reserved `.invalid` top-level domain.
The fixtures are distributed with the project under the Apache License 2.0.

## Layout

- `records/`: one JSON document per case. The file name without `.json` is the case id.
- `manifest.json`: the expected outcome of every case. It is the expectation authority.

Every file in `records/` has exactly one manifest case, and every case names one file.
`tests/conformance/corpus.py` loads the manifest and fails setup on any shape problem.

## Manifest shape

```json
{
  "manifest_version": "2.0.0",
  "contract": "2.0.0-draft.2",
  "provenance": {"kind": "synthetic", "source": "...", "reuse_terms": "Apache License 2.0"},
  "cases": [
    {
      "id": "relationship-self",
      "path": "records/relationship-self.json",
      "expected_status": "complete",
      "expected_structural": "valid",
      "expected_diagnostics": [["RELATIONSHIP_SELF", "/relationships/0/target"]],
      "rules": ["REL-3"],
      "note": "A relationship targets its own asset."
    }
  ]
}
```

## How expectations are read

The sweep in `test_corpus.py` runs each case through the pipeline in order: strict parse, routing, structural validation, semantic checks.

- `expected_status` is `input-invalid` when the strict parse refuses the bytes, `unsupported` when routing selects no schema, and `complete` otherwise.
- `expected_structural` is `not-run` when the status is not `complete`, `invalid` when the document has at least one structural error, and `valid` otherwise.
- `expected_diagnostics` is the complete list of `[code, path]` pairs, sorted by path and then by code. Paths are JSON Pointers.
  An `input-invalid` case lists only `["INPUT_INVALID", ""]`. An `unsupported` case lists its routing diagnostics.
  A structurally invalid case lists nothing, because semantic checks run only on a structurally valid document.
  A `complete` and `valid` case lists every error and warning, and an empty list means no finding at all.
- `rules` names the contract rules the case covers.

A document whose bytes are not UTF-8 is not stored here. The tests build those bytes in memory.

## Seeds

Each record fixture starts from a small seed, not from a full example, so that no unrelated field adds a diagnostic.
A fixture adds only the fields its case needs.

- Seed A: the minimal asset with `timing` at rate `25/1`, no drop frame, and `duration_frames` 750.
- Seed B: seed A with `source_timecode` `10:00:00:00`.
- Seed C: a minimal standalone annotation or collection.
- Seed D: the minimal metadata definition with `value_type` `enum` and options `a` and `b`.

Package fixtures wrap these records in a minimal package with a manifest whose counts and completeness fit the case.
Structural fixtures carry exactly one structural defect each.
