# OASIS governance

This page explains who maintains OASIS and how changes are decided.
It describes how the project works today. It will change as the community grows.

## Steward

North Shore Automation, LLC stewards OASIS.
The steward makes the final decision when the maintainers cannot agree.
OASIS is not affiliated with, endorsed by, or published by any standards body.

## Maintainers

| Name | GitHub |
| --- | --- |
| Damien Corbell | [@nsa-damien](https://github.com/nsa-damien) |
| Brant Goddard | [@nsa-brant](https://github.com/nsa-brant) |
| Brandon Dedolph | [@nsa-brandon](https://github.com/nsa-brandon) |

Maintainers review pull requests, triage issues, run the change process below, and prepare releases.

### Becoming a maintainer

A contributor can become a maintainer after a record of useful, well-reviewed contributions.
An existing maintainer nominates the contributor in a public issue.
The maintainers decide by agreement. If they cannot agree, the steward decides.
New maintainers are added to the table above in a pull request.

## Kinds of change

- **Editorial change.** Typos, clearer wording that keeps the meaning, and new or corrected examples.
  One maintainer approval is enough. There is no minimum wait.
- **Normative change.** Anything that changes what a validator accepts, a field, a rule, or a diagnostic.
  It starts as an issue with a change proposal.

### Change proposals

A change proposal states:

- the use case and the problem;
- the exact proposed behavior;
- the effect on existing records and implementations;
- the conformance fixtures that show the behavior;
- the alternatives considered.

A normative change stays open for public comment for at least 14 days before it is merged.

## Decisions

The maintainers try to reach agreement in the issue or pull request.
If they cannot agree, the steward decides and records the reason in the issue.

## Appeals

Anyone may ask for a decision to be reconsidered within 14 days, by commenting on the issue.
A maintainer who did not make the original decision reviews the request.
The steward's answer after that review is final for that release.

## Issue triage

New issues are labelled within 7 days as a bug, question, editorial change, or change proposal.
An issue that is missing requested information is closed after 30 days without a reply.
The closing note explains how to reopen it.

## Compatibility promise for 1.x

Within the 1.x series, a release does not make a previously valid record invalid.
It does not remove a field, make a field required, or change a published meaning.
Changes of that kind wait for a new major version.

## Related pages

- [Contributing](../CONTRIBUTING.md)
- [License](../LICENSE)
