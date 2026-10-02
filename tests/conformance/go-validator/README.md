# Go structural adapter

This module is the second, independent structural engine of the offline OASIS conformance harness.
It uses `github.com/santhosh-tekuri/jsonschema/v6 v6.0.3` with `golang.org/x/text v0.42.0`.
It keeps every JSON number as its original lexeme and uses exact rational arithmetic.

## Limits

- Structural validation only. It runs no semantic checks, profile routing, or diagnostics.
- It is not interoperability evidence. It makes no producer or consumer portability claim.
- It is a DRAFT 1.2.0-draft.1 conformance tool, not a production validator. Input size has no separate limit here.
- Nesting: the strict scan is iterative, but the lossless decoder refuses nesting depth over 10,000. That refusal is `setup-failed` with `structural: not-run`.

## Setup

Use only the pinned toolchain under `tmp/go1.27.1/`. Never use the system Go.
From the repository root, set these variables before any `go` command:

```sh
R=$PWD
export GOROOT=$R/tmp/go1.27.1/go PATH=$R/tmp/go1.27.1/go/bin:$PATH GOTOOLCHAIN=local
export GOPATH=$R/tmp/gopath GOMODCACHE=$R/tmp/gomodcache GOCACHE=$R/tmp/gocache
export GOPROXY=https://proxy.golang.org GOSUMDB=sum.golang.org
unset GOFLAGS
go version   # must print go1.27.1
```

These proxy settings are needed only to fill `tmp/gomodcache` the first time.
After the module cache exists, run offline and keep `go.mod` and `go.sum` unchanged:

```sh
export GOFLAGS=-mod=readonly GOPROXY=off
```

`go.mod` keeps both modules as direct requirements.
`x/text v0.42.0` is an approved override of the library's older minimum.
`go mod tidy` marks it indirect; restore the explicit line after any tidy.

## Build and test

From `tests/conformance/go-validator`:

```sh
go vet ./...
go test ./...
go build -o ../../../tmp/go-validator .
```

`go test` includes the corpus sweep.
It runs every case in `../fixtures/manifest.json` against `../baseline` and `../../../definitions` in both format modes.
It compares each run with `validator_expectations["go-jsonschema"]` and reports all mismatches by fixture ID, root, and mode.

## Command line

```sh
go-validator --bundle <dir> --schema <name> --format-mode required|historical-unchecked --input <file>
```

The command prints one JSON object:

| Field | Values |
| --- | --- |
| `adapter_status` | `complete`, `input-invalid`, or `setup-failed` |
| `structural` | `valid`, `invalid`, or `not-run` |
| `limitation` | A fixed explanation, or `null` |
| `errors` | Sorted JSON Pointer instance locations of the leaf errors |

The exit status is 0 whenever a result is printed. It is 2 only for a command line usage error.
Output never contains library message text or input values.

## Behavior

Outcome order:

1. Setup: load `<bundle>/bundle-manifest.json`, verify each schema digest, and compile every entry.
   Any failure is `setup-failed`.
2. Strict input policy on the original bytes: byte-order mark, invalid UTF-8, malformed JSON, duplicate member names, NaN and Infinity, and unpaired surrogate escapes.
   Any failure is `input-invalid`. The whole scan finishes before the numeric guards run.
3. Numeric resource guards on every number lexeme, before any exact-number construction.
   A refusal is `setup-failed` with `structural: not-run`. The limitation names all three limits and the exceeded one.
4. Lossless decoding, then Draft 7 structural validation.

Numeric guards (operational, not OASIS ranges), identical to the Python adapter:

- Token length: at most 1,024 bytes, including sign, decimal point, and exponent syntax.
- Exponent: more than 5 significant exponent digits is refused before integer conversion. The absolute exponent must be at most 10,000.
- Expansion budget: every written coefficient digit plus the absolute exponent, summed over all tokens in one document, at most 100,000.

Schema loading is offline:

- Each manifest schema is registered with `AddResource` under its `base_uri` and each alias. Entry points compile by `base_uri`.
- `UseLoader(nil)` disables the library's default file loader. Any unknown `file://`, `https://`, or unlisted bundle reference fails setup without I/O.
- Manifest paths must be bundle-relative and must resolve inside the bundle.
- Schema files use the same strict policy and numeric guards.

Schema audit at setup:

- `pattern` and `patternProperties` must use one of the four bundle expressions.
  The compiler's regular expression engine also refuses any other expression.
- `multipleOf` is refused, as in the Python adapter.
- `format` must be `date-time`, and any `$schema` must be Draft 7.
- The static walk visits every Draft 7 subschema position, `definitions`, and `$defs`.
  A registered compiler vocabulary applies the same keyword checks to every schema the compiler compiles.
  So a schema reached only through `$ref`, in the same file or another bundle file, is audited too.

Patterns use Go's standard RE2 engine without flags, the library default.
There, `\d` matches ASCII digits only and `$` matches only at the absolute end of the text.

Formats: `required` mode registers the contract's common `date-time` grammar and calls `AssertFormat()`.
`historical-unchecked` mode registers a no-op `date-time` checker, because Draft 7 asserts formats by default.
Only string instances are checked. Pattern assertions apply in both modes.

A panic in the library becomes `setup-failed` with a fixed message.

## Known engine differences

These differences from the Python adapter are recorded and accepted.

- Draft 7 metaschema reference.
  The Python adapter refuses `{"$ref": "http://json-schema.org/draft-07/schema#"}`, because the metaschema is not a bundle resource.
  The Go library resolves that reference from its built-in metaschema copy instead.
  Setup still fails in Go, but for another reason: the audit sees the metaschema's other `format` values.
- `$defs` walking.
  Draft 7 does not define `$defs`. The Python adapter audits a `$defs` member only when a `$ref` reaches it.
  The Go static walk audits every `$defs` member, so an unreferenced `$defs` member with an unlisted pattern or another format fails setup in Go only.
- No nesting threshold is approved yet. Neither engine enforces a declared nesting limit.
  Both stop at library or interpreter limits instead, and those limits differ.
  The depths below are approximate. They depend on the Python interpreter recursion limit (default 1,000) and on the decoder limits.
  Ordinary corpus inputs are far below all of them.
- Well-formed input nested between about 1,000 and 10,000 levels.
  Python fails setup: its post-parse scan reaches the interpreter recursion limit.
  Go completes, because its decoder accepts depth up to 10,000.
  Above 10,000 levels, both engines report `setup-failed`.
- Malformed input nested about 10,000 levels or more.
  Python's JSON decoder gives up at about that depth before it finds the syntax error, so Python reports `setup-failed`.
  Go scans input iteratively, finds the syntax error first, and reports `input-invalid`.
  For this case, Python does not meet the contract rule that malformed input is reported first.
  Below about 10,000 levels, both engines report malformed input as `input-invalid`.
- Well-formed input with derivative files nested about 165 levels or more (`files[].derivatives`).
  Python fails setup: structural validation reaches the interpreter recursion limit, and the limitation names that limit.
  Go completes and reports the structural outcome.
  No nesting threshold is approved, so neither result is a conformance claim about such input.
