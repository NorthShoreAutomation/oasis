# Proposed synthetic corpus

This directory contains proposed test data and expected outcomes.
The conformance harness in `tests/conformance/` runs it.
The records and manifest are licensed under the Apache License, Version 2.0, with the rest of the project.
No executed semantic conformance or interoperability result is claimed.

All inputs are newly authored synthetic records or deliberately invalid JSON parser examples.
The `.invalid` host and `/synthetic/` paths are illustrative and must never be accessed during validation.
No fixture contains a customer sample, real connection credential, or adopter attribution.

## Layout and expectations

- `manifest.json` records stable case IDs, selected profiles, contexts, provenance, and expected results.
- `records/*.json` contains input records and explicitly labelled `raw-json` rejection samples. Several cases reuse an input to compare different profiles.
- `legacy-1x` cases describe frozen structural acceptance and have no semantic diagnostics.
- `exchange-1x` cases describe proposed semantic outcomes while retaining legacy structural outcomes separately.
- Required-format and historical-unchecked expectations are recorded separately for both proposed validators.
- `exchange-1x` execution requires format checking; historical-unchecked entries are structural comparison evidence only.
- `expected_routing` and `expected_execution_status` follow the proposed outcome table.
- `preservation_comparisons` declares synthetic equal/changed tree examples, including blocked rights retention. These are not implementation results.

The selected profile is never inferred from the context label.
An unsupported version can remain structurally valid while routing returns unsupported.
Format-enforced expectations are proposals until approved dependencies and the portability matrix run.
The ordinary future runner must fail setup when the required date-time checker is missing.
The proposed Python and Go engines have matching expectations, including decimal seconds, common frame rates, and large integers.
No ordinary numeric case has a proposed precision exclusion. These expectations are not executed second-engine coverage.
One 5,000-digit numeric token case proposes a resource setup refusal in both engines, while retaining normative structural acceptance.
Timecode and report-pattern boundary cases use the proposed common ECMA-262 behavior; native historical Python differs for these inputs.
Declared resource refusals fail setup before routing and never turn valid OASIS data into a structural rejection.
Per-engine `adapter_status` and `limitation` retain that distinction. Future coverage exclusions require explicit approval.

The report examples retain the published application-report shape without endorsing its use as the generic interchange core.
Every annotation enum and absence is covered in standalone, asset-embedded, and batch-contained records.
The file-group and multiple-location examples record representational intent in accepted custom technical metadata.
Those custom values do not establish new standard grouping or locator fields.

## Preservation boundary

Inputs retain missing fields, unknown custom values, literal annotation tokens, and array order.
Validation must not insert defaults or rewrite records.
Later producer/consumer tests will compare decoded JSON trees under the approved contract.
These records alone do not prove export/import preservation or correct media-byte handling.

## Public dependency boundary

The future runner must need only the published bundle and approved public dependencies.
It must resolve schema references locally with network retrieval denied.
No private package, adopter repository, account, or customer data may be required.
Do not copy private planning paths or review evidence into a public fixture manifest.
