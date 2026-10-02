# Contributing to OASIS

Thank you for helping improve OASIS.
This page explains how to propose a change and what each change must include.
How changes are reviewed and decided is described in [docs/GOVERNANCE.md](docs/GOVERNANCE.md).

## License of contributions

OASIS is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
Section 5 of that license applies: a contribution you submit is under the same license, unless you state otherwise in writing.

## Developer Certificate of Origin

Every commit must carry a Developer Certificate of Origin (DCO) sign-off.
The sign-off states that you have the right to submit the work under the project license.
Read the full text at <https://developercertificate.org/>.

Add the sign-off with the `-s` option:

```sh
git commit -s -m "docs: clarify annotation timing example"
```

This adds a line like this to the commit message:

```text
Signed-off-by: Your Name <you@example.com>
```

Use your real name and an email address you can be reached at.
A pull request with an unsigned commit cannot be merged.
To sign the last commit after the fact, run `git commit --amend -s --no-edit`, then push again.
To sign several commits, run `git rebase --signoff <base>`, then push again.

## Kinds of change

- **Editorial change.** Typos, clearer wording that keeps the meaning, and new or corrected examples. Open a pull request.
- **Normative change.** Anything that changes what a validator accepts, a field, a rule, or a diagnostic. Open an issue with a change proposal first, and wait for the review described in the governance page.

If you are not sure which kind your change is, open an issue and ask.

## What a pull request must include

- A short description of the problem and the change.
- Updated or new synthetic examples or conformance fixtures when behavior changes. Use invented values only. Never include real customer data, credentials, or personal information.
- A passing conformance run. From the repository root:

```sh
python3 -W error -m unittest discover -s tests/conformance -t . -p 'test_*.py'
```

- For a change to the Go adapter, a passing `go vet ./...` and `go test ./...` in `tests/conformance/go-validator`. See that directory's README for setup.
- A changelog entry for any change that belongs in the release notes.

Within the 1.x series, a change must not make a previously valid record invalid, remove a field, make a field required, or change a published meaning.

## Reporting problems

Open an issue for bugs, questions, and proposals.
Do not post secrets, credentials, or private records in an issue.
