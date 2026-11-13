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
- `packages/`: one folder per multi-file package case. The folder name is the case id.
  The folder holds the manifest file `oasis-package.json` and the member files of the package.
- `manifest.json`: the expected outcome of every case. It is the expectation authority.

Every file in `records/` and every folder in `packages/` has exactly one manifest case.
Every case names one file or one folder.
`tests/conformance/corpus.py` loads the manifest and fails setup on any shape problem.
A single-document case has the path `records/<id>.json`. A package case has the path `packages/<id>/`.

A package is the only exchange document in `2.0.0-draft.4`. Most fixtures are strict JSON packages with `spec_version` `2.0.0-draft.4`.
Some fixtures break this on purpose. The `input-` fixtures for malformed input are not strict JSON. Some routing fixtures have a root that is not a package, and others are packages with another `spec_version` or none.

## Manifest shape

```json
{
  "manifest_version": "2.0.0",
  "contract": "2.0.0-draft.4",
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
      "id": "package-id-duplicate-across-members",
      "path": "packages/package-id-duplicate-across-members/",
      "expected_status": "complete",
      "expected_structural": "valid",
      "expected_diagnostics": [
        ["MEMBERS_SMALL", "/manifest/members", null, null],
        ["ID_DUPLICATE", "/id", 1, 1]
      ],
      "rules": ["MFP-7", "ID-1"],
      "note": "Two member files in the assets list hold an asset with the id a-0001."
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
- `expected_diagnostics` is the complete list of findings. Paths are JSON Pointers.
  A single-document case gives each finding as a `[code, path]` pair, sorted by path and then by code.
  A package case gives each finding as `[code, path, member, line]`. The two-item form `[code, path]` also works and means that `member` and `line` are both `null`.
  - A `DOC-1` case lists only `["INPUT_INVALID", ""]`.
  - A `DOC-4` case lists `NUMBER_OUT_OF_RANGE` or `NUMBER_TOO_PRECISE` at each failing number. Inside `extensions`, the path stops at the `extensions` member.
  - An `unsupported` case lists `NOT_EXCHANGE_DOCUMENT` or `VERSION_UNSUPPORTED` at the path that `REC-2` gives.
  - A structurally invalid case lists nothing, because semantic checks run only on a structurally valid document.
  - A `complete` and `valid` case lists every finding. An empty list means no finding at all.
- `rules` names the contract rules the case covers. Every structurally valid case also names `DOC-3`.

Every diagnostic code has severity `error`, with two exceptions.
`MEMBERS_SMALL` and `FILE_UNLISTED` have severity `warning`. A case lists a warning like any other finding.
Each structurally invalid case has `expected_schema_error`: the keyword and the pointer of one error that the schema stage reports.
Only a structurally invalid case has this field.
The schema sometimes reports a closed-object failure on the parent object, not on the field. The manifest records the pointer that the validator reports.
A `false` subschema has no keyword. The harness names it `false`.

A document whose bytes are not UTF-8 is not stored here. The tests build those bytes in memory.

## Package cases

A package case is a folder in `packages/`. The sweep in `test_corpus.py` runs `evaluate_folder` on `packages/<id>/oasis-package.json`, with the folder form of the check, and compares the result with the manifest.
A package case uses the same `expected_status`, `expected_structural`, `expected_schema_error`, and `rules` fields as a single-document case.
The `DOC-` rules describe the single-document pipeline, so a package case names `MFP-` rules and the rules of the records that it breaks.

- `member` in a finding is the index of the member entry in `manifest.members`. The result of the checker names it as `/manifest/members/<n>`.
- `line` is the line number in that member file. The first line is 1.
- Either value is `null` when the finding has none. A finding about a whole member file has a `member` and no `line`.
  A finding about the list as a whole, such as `MEMBERS_SMALL`, has neither.
- The path of a finding that has a `line` is a JSON Pointer into the record on that line. A finding without a `line` has a path into the manifest file.
- An unlisted file has no `member` and no `line`, and its path is empty. The checker also gives the relative path of the file. The corpus does not hold that path.
- Findings are sorted as the checker sorts them: a finding with no `member` first, then by `member`, `line`, path, and code.

A fixture is the smallest package that shows its case. Each record is the smallest record that passes the schemas.
The case that crosses member files puts the related records in two different `assets/` member files.

| Case | Outcome | What it shows |
| --- | --- | --- |
| `package-ok-two-asset-members` | complete, valid | Two asset member files. The list is small, so it gets the `MEMBERS_SMALL` warning. |
| `package-ok-gzip-member` | complete, valid | One plain and one gzip member file in one list. |
| `package-ok-empty-list` | complete, valid | One member file with 0 bytes and a count of 0. |
| `package-member-missing` | input-invalid | A listed member file is not in the folder. |
| `package-member-unlisted` | input-invalid | The record folder holds a file that the manifest does not list. |
| `package-member-size` | input-invalid | The `size_bytes` of an entry is wrong. |
| `package-member-checksum` | input-invalid | The `sha256` of an entry is wrong. |
| `package-member-count` | input-invalid | The `count` of an entry is not the number of lines. |
| `package-member-type` | complete, valid | The `record_type` of an entry is not the first segment of its path. |
| `package-line-no-final-lf` | input-invalid | The last line of a member file has no LF. |
| `package-line-crlf` | input-invalid | A line ends with CR and LF. |
| `package-id-duplicate-across-members` | complete, valid | One id in two member files of one list (`ID-1`). |
| `package-reference-across-members` | complete, valid | A reference to a record in a later member file resolves. One to a missing record does not (`PKG-6`). |
| `package-position-duplicate-across-members` | complete, valid | One position in one collection from two member files (`COL-7`). |
| `package-records-with-arrays` | complete, invalid | The manifest file lists members and also holds a record array. |

A link, a special file, a file that the user cannot read, two paths that differ only in letter case, and a decompression limit are not stored here.
Git cannot keep them on every file system, so the tests of the checker build them in a temporary folder.
`test_corpus.py` checks that every diagnostic code of an `MFP-` rule has a package case or a named test of that kind.

The files in `packages/` keep their exact bytes. `.gitattributes` turns off line-ending changes and filters for them.

## Seeds

Each fixture starts from a small seed, not from a full example, so that no unrelated field adds a diagnostic.
A fixture adds only the fields its case needs.

- The minimal package: `spec_version`, `type` `package`, an `id`, and a manifest with `producer`, `produced_at`, `counts`, and `namespaces`.
  The counts always match the record arrays. A storage location is added only when a file copy refers to it.
- The minimal asset: `a-0001` with the title "Example Clip".
- The frame-form timeline: rate `25/1`, no drop frame, and `duration_frames` 750.
- The minimal metadata definition: `value_type` `string` and `cardinality` `single`, with `list_type` and `options` added for `enum`.

Structural fixtures carry one structural defect each. The validator can report that one defect more than once.
