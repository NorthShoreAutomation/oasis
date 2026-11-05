"""The end-to-end check of a multi-file package and the validate command for it.

Each package is written into a temporary folder with ``write_package``. The
first stage that fails decides the outcome, and only its findings are
reported. The tests check the outcome of each stage, the order in which
records reach the semantic stage, the setup failures, and the work folder.
"""

import contextlib
import gzip
import hashlib
import io
import json
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from tests.conformance import exact_json, loader, multifile, validate
from tests.conformance.multifile import MANIFEST_NAME
from tests.conformance.multifile_testing import write_package
from tests.conformance.semantic import REGISTRIES
from tests.conformance.strict_json import parse_input

REPO = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO / "definitions"
EXAMPLES = DEFINITIONS / "examples"
RESULT_SCHEMA = Path(__file__).resolve().parent / "result.schema.json"

LIMITS = multifile.ReadLimits()
UNREADABLE_MEMBER = "Setup failed: a member file cannot be read."

REFERENCE_DEFINITION = {
    "id": "md-related",
    "label": "Related",
    "value_type": "asset_reference",
    "cardinality": "single",
}
STORAGE_LOCATION = {"id": "sl-1", "name": "Example Share", "system": "network_share", "root": "server_a:/export/"}


def _asset(asset_id, **fields):
    return {"id": asset_id, "title": "Example Clip", **fields}


def _collection(collection_id, **fields):
    return {"id": collection_id, "title": "Example Collection", "collection_type": "logical", **fields}


def _related(asset_id, target):
    return _asset(asset_id, metadata=[{"definition": "md-related", "value": target}])


def _lines(*records) -> bytes:
    """JSON Lines bytes: one compact record on each line, each line with its LF."""
    return b"".join(json.dumps(r, separators=(",", ":")).encode("utf-8") + b"\n" for r in records)


def _m(index: int) -> str:
    return f"/manifest/members/{index}"


def _found(record):
    """The diagnostics of a result record as ``(code, member, line, path)``."""
    return [(d["code"], d.get("member"), d.get("line"), d["path"]) for d in record["diagnostics"]]


def _outcome(record):
    return (record["execution_status"], record["structural"], record["semantic"])


def run(*argv):
    """Run main with captured stdout and stderr: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = validate.main([str(arg) for arg in argv])
        except SystemExit as stop:
            code = stop.code
    return code, out.getvalue(), err.getvalue()


def _skip_as_root(test):
    """Skip a permission test when the process runs as root, which reads any file."""
    return unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads any file")(test)


def _convert_full_example() -> tuple[dict, dict]:
    """Return ``(members, root_overrides)`` for a multi-file copy of ``package-full.json``.

    Each record list becomes one plain member file. Lines keep every number
    exactly as written (``exact_json``).
    """
    data = (EXAMPLES / "package-full.json").read_bytes()
    exact = parse_input(data).value
    plain = json.loads(data)
    members = {}
    for registry in REGISTRIES:
        if registry in exact:
            text = "".join(exact_json.dumps(record) + "\n" for record in exact[registry])
            members[f"{registry}/part-00001.jsonl"] = text.encode("utf-8")
    manifest = {key: value for key, value in plain["manifest"].items() if key != "counts"}
    overrides = {key: plain[key] for key in ("id", "source", "extensions") if key in plain}
    overrides["manifest"] = manifest
    return members, overrides


class PackageTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.folder = self.base / "pkg"

    def write(self, members, root_overrides=None, **options) -> Path:
        return write_package(self.folder, members, root_overrides, **options)

    def check(self, manifest=None, limits=LIMITS, work_dir=None) -> dict:
        """Run ``evaluate_folder`` and check the result record against the result schema."""
        manifest = self.folder / MANIFEST_NAME if manifest is None else manifest
        record = multifile.evaluate_folder(manifest, DEFINITIONS, work_dir, limits)
        errors = list(Draft202012Validator(json.loads(RESULT_SCHEMA.read_text())).iter_errors(record))
        self.assertEqual(errors, [], record)
        return record

    def assertMultiFile(self, record):
        self.assertEqual(record["form"], "multi-file")


class PassingPackageTests(PackageTest):
    def test_converted_full_example_passes(self):
        members, overrides = _convert_full_example()
        self.assertEqual(len(members), 4)
        manifest = self.write(members, overrides)
        for target in (self.folder, manifest):
            with self.subTest(target=target.name):
                code, out, err = run(target, "--json")
                self.assertEqual(code, 0, out + err)
                record = json.loads(out)
                self.assertMultiFile(record)
                self.assertEqual(_outcome(record), ("complete", "valid", "run"))
                self.assertEqual(record["diagnostics"], [])
                self.assertEqual(record["input_sha256"], hashlib.sha256(manifest.read_bytes()).hexdigest())
                self.assertEqual((record["type"], record["spec_version"]), ("package", "2.0.0-draft.4"))
                self.assertEqual(record["file"], str(target))
        code, out, _ = run(self.folder)
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("PASS status=complete type=package structural=valid semantic=run\n"), out)

    def test_plain_and_gzip_members_pass_together(self):
        self.write({
            "assets/a.jsonl": _lines(_asset("a-1")),
            "assets/b.jsonl.gz": gzip.compress(_lines(_asset("a-2"), _asset("a-3"))),
        })
        record = self.check()
        self.assertEqual(_outcome(record), ("complete", "valid", "run"))
        self.assertEqual(_found(record), [("MEMBERS_SMALL", None, None, "/manifest/members")])
        self.assertEqual(validate.exit_code(record), 0)

    def test_reference_to_an_asset_in_a_later_member_resolves(self):
        def package(target):
            return {
                "assets/a.jsonl": _lines(_related("a-1", target)),
                "assets/b.jsonl": _lines(_asset("a-2")),
                "metadata_definitions/m.jsonl": _lines(REFERENCE_DEFINITION),
            }

        self.write(package("a-2"))
        record = self.check()
        self.assertEqual(_outcome(record), ("complete", "valid", "run"))
        self.assertEqual([d for d in _found(record) if d[0] != "MEMBERS_SMALL"], [])

        self.write(package("a-9"))
        self.assertEqual(
            [d for d in _found(self.check()) if d[0] != "MEMBERS_SMALL"],
            [("REFERENCE_UNRESOLVED", _m(0), 1, "/metadata/0/value")],
        )


class SemanticAcrossMembersTests(PackageTest):
    def test_first_duplicate_follows_manifest_order_not_file_name(self):
        # Manifest member 0 is part-b and member 1 is part-a: the later one in the manifest is the duplicate.
        self.write({
            "assets/part-b.jsonl": _lines(_asset("a-1")),
            "assets/part-a.jsonl": _lines(_asset("a-2"), _asset("a-1")),
        })
        record = self.check()
        self.assertEqual(_outcome(record), ("complete", "valid", "run"))
        self.assertEqual(
            [d for d in _found(record) if d[0] != "MEMBERS_SMALL"], [("ID_DUPLICATE", _m(1), 2, "/id")]
        )
        self.assertEqual(validate.exit_code(record), 1)

    def test_undeclared_extension_token_is_located_at_its_member_and_line(self):
        self.write({
            "assets/a.jsonl": _lines(_asset("a-1"), _asset("a-2", extensions={"vendor_b": {"tier": "x"}})),
        })
        self.assertEqual(_found(self.check()), [("NAMESPACE_UNDECLARED", _m(0), 2, "/extensions")])

    def test_declared_extension_token_passes(self):
        namespaces = [{"token": "vendor_b", "owner": "Vendor B"}]
        self.write(
            {"assets/a.jsonl": _lines(_asset("a-1", extensions={"vendor_b": {"tier": "x"}}))},
            {"manifest": {"namespaces": namespaces}},
        )
        self.assertEqual(_found(self.check()), [])

    def test_position_duplicate_across_two_members(self):
        member_of = [{"collection": "c-1", "position": 1}]
        self.write({
            "assets/a.jsonl": _lines(_asset("a-1", member_of=member_of)),
            "assets/b.jsonl": _lines(_asset("a-2", member_of=member_of)),
            "collections/c.jsonl": _lines(_collection("c-1")),
        })
        self.assertEqual(
            [d for d in _found(self.check()) if d[0] != "MEMBERS_SMALL"],
            [("POSITION_DUPLICATE", _m(0), 1, "/member_of/0"), ("POSITION_DUPLICATE", _m(1), 1, "/member_of/0")],
        )

    def test_manifest_root_findings_have_no_member(self):
        namespaces = [{"token": "vendor_a", "owner": "A"}, {"token": "vendor_a", "owner": "B"}]
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))}, {"manifest": {"namespaces": namespaces}})
        self.assertEqual(
            _found(self.check()), [("NAMESPACE_DECLARED_TWICE", None, None, "/manifest/namespaces/1/token")]
        )

    def test_records_arrive_by_list_then_in_manifest_order(self):
        self.write({
            "assets/b.jsonl": _lines(_asset("a-2")),
            "collections/c.jsonl": _lines(_collection("c-1")),
            "assets/a.jsonl": _lines(_asset("a-1")),
            "storage_locations/s.jsonl": _lines(STORAGE_LOCATION),
            "metadata_definitions/m.jsonl": _lines(REFERENCE_DEFINITION),
        })
        calls = []
        original = multifile.PackageChecker.add

        def spy(checker, registry, record, where):
            calls.append((registry, where.member, where.line, where.base))
            return original(checker, registry, record, where)

        with mock.patch.object(multifile.PackageChecker, "add", spy):
            record = self.check()
        self.assertEqual(_outcome(record), ("complete", "valid", "run"))
        self.assertEqual(
            calls,
            [
                ("storage_locations", 3, 1, ""),
                ("metadata_definitions", 4, 1, ""),
                ("collections", 1, 1, ""),
                ("assets", 0, 1, ""),
                ("assets", 2, 1, ""),
            ],
        )


class StageOrderTests(PackageTest):
    def test_checksum_mismatch_hides_a_structural_error_in_another_member(self):
        # The collections member (1) is read first, and its structural error is dropped.
        self.write(
            {
                "assets/a.jsonl": _lines(_asset("a-1")),
                "collections/c.jsonl": _lines({"id": "c-1", "title": "No type"}),
            },
            entry_overrides={"assets/a.jsonl": {"sha256": "0" * 64}},
        )
        record = self.check()
        self.assertEqual(_outcome(record), ("input-invalid", "not-run", "not-run"))
        self.assertEqual(_found(record), [("MEMBER_CHECKSUM_MISMATCH", _m(0), None, "/manifest/members/0/sha256")])
        self.assertEqual(record["structural_errors"], [])

    def test_every_damaged_member_is_reported_and_later_members_are_only_hashed(self):
        # Member 1 holds a line over the line limit. It is only hashed, so the limit never fires.
        long_line = _lines(_asset("a-2", title="x" * 200))
        self.write(
            {
                "assets/a.jsonl": _lines(_asset("a-1")),
                "assets/b.jsonl": long_line,
                "assets/c.jsonl": _lines(_asset("a-3")),
            },
            entry_overrides={"assets/a.jsonl": {"sha256": "0" * 64}, "assets/b.jsonl": {"sha256": "1" * 64}},
        )
        record = self.check(limits=multifile.ReadLimits(max_line_bytes=100))
        self.assertEqual(_outcome(record), ("input-invalid", "not-run", "not-run"))
        self.assertEqual(
            _found(record),
            [
                ("MEMBER_CHECKSUM_MISMATCH", _m(0), None, "/manifest/members/0/sha256"),
                ("MEMBER_CHECKSUM_MISMATCH", _m(1), None, "/manifest/members/1/sha256"),
            ],
        )

    def test_missing_member_reports_no_unresolved_reference(self):
        self.write(
            {
                "metadata_definitions/m.jsonl": _lines(REFERENCE_DEFINITION),
                "assets/a.jsonl": _lines(_related("a-1", "a-2")),
                "assets/b.jsonl": _lines(_asset("a-2")),
            },
            skip=["assets/b.jsonl"],
        )
        record = self.check()
        self.assertEqual(_outcome(record), ("input-invalid", "not-run", "not-run"))
        self.assertEqual(_found(record), [("MEMBER_MISSING", _m(2), None, "/manifest/members/2/path")])

    def test_line_parse_error_outranks_a_structural_error_in_another_member(self):
        # The collections member is read first: its structural error comes before the parse error.
        self.write({
            "assets/a.jsonl": _lines(_asset("a-1"), _asset("a-2")) + b'{"id": "a-3",\n',
            "collections/c.jsonl": _lines(_collection("c-1"), {"id": "c-2", "title": "No type"}),
        })
        record = self.check()
        self.assertEqual(_outcome(record), ("input-invalid", "not-run", "not-run"))
        self.assertEqual(_found(record), [("INPUT_INVALID", _m(0), 3, "")])
        self.assertEqual(record["structural_errors"], [])

    def test_every_line_parse_error_is_reported(self):
        self.write({
            "assets/a.jsonl": b"[1,]\n" + _lines(_asset("a-1")) + b"{}{}\n",
            "assets/b.jsonl": b'{"a":1,"a":2}\n',
        })
        self.assertEqual(
            [d for d in _found(self.check()) if d[0] != "MEMBERS_SMALL"],
            [("INPUT_INVALID", _m(0), 1, ""), ("INPUT_INVALID", _m(0), 3, ""), ("INPUT_INVALID", _m(1), 1, "")],
        )

    def test_number_limits_outrank_structure(self):
        big = {"gen": {"n": 9007199254740993}}
        self.write({
            "assets/a.jsonl": _lines(_asset("a-1"), _asset("a-2", extensions=big)),
            "collections/c.jsonl": _lines({"id": "c-2", "title": "No type"}),
        })
        record = self.check()
        self.assertEqual(_outcome(record), ("input-invalid", "not-run", "not-run"))
        self.assertEqual(_found(record), [("NUMBER_OUT_OF_RANGE", _m(0), 2, "/extensions")])

    def test_parse_error_outranks_number_limits(self):
        big = {"gen": {"n": 9007199254740993}}
        self.write({
            "assets/a.jsonl": _lines(_asset("a-1", extensions=big)),
            "assets/b.jsonl": b"not json\n",
        })
        self.assertEqual(
            [d for d in _found(self.check()) if d[0] != "MEMBERS_SMALL"], [("INPUT_INVALID", _m(1), 1, "")]
        )

    def test_structural_errors_carry_member_and_line(self):
        self.write({
            "assets/a.jsonl": _lines(_asset("a-1"), {"id": 5}),
            "assets/b.jsonl": b"[]\n",
        })
        record = self.check()
        self.assertEqual(_outcome(record), ("complete", "invalid", "not-run"))
        self.assertEqual(record["diagnostics"], [])
        self.assertEqual(
            record["structural_errors"],
            [
                {"path": "", "keyword": "required", "member": _m(0), "line": 2},
                {"path": "", "keyword": "unevaluatedProperties", "member": _m(0), "line": 2},
                {"path": "/id", "keyword": "type", "member": _m(0), "line": 2},
                {"path": "", "keyword": "type", "member": _m(1), "line": 1},
            ],
        )
        code, out, _ = run(self.folder)
        self.assertEqual(code, 1)
        self.assertIn("  member 0 line 2 /id keyword type\n", out)
        self.assertIn("  member 1 line 1 (root) keyword type\n", out)

    def stage_calls(self):
        """Run the check and count the calls of each record stage during the read."""
        calls = {"limits": 0, "structure": 0, "semantic": 0}
        limits = multifile.check_number_limits
        validate_record = loader.EntryPoint.validate
        add = multifile.PackageChecker.add

        def count_limits(*args):
            calls["limits"] += 1
            return limits(*args)

        def count_structure(entry_point, parsed):
            if entry_point.kind != "package":
                calls["structure"] += 1
            return validate_record(entry_point, parsed)

        def count_semantic(*args):
            calls["semantic"] += 1
            return add(*args)

        with (
            mock.patch.object(multifile, "check_number_limits", count_limits),
            mock.patch.object(loader.EntryPoint, "validate", count_structure),
            mock.patch.object(multifile.PackageChecker, "add", count_semantic),
        ):
            record = self.check()
        return record, calls

    def test_stages_after_the_earliest_failure_do_not_run(self):
        # The first line fails one stage; the two lines after it are valid.
        cases = {
            "parse": (b"nope\n", (0, 0, 0)),
            "number limits": (_lines(_asset("a-1", extensions={"g": {"n": 2**60}})), (3, 0, 0)),
            "structure": (_lines({"id": "a-1"}), (3, 3, 0)),
            "none": (_lines(_asset("a-1")), (3, 3, 3)),
        }
        for name, (first, expected) in cases.items():
            with self.subTest(name):
                self.write({"assets/a.jsonl": first + _lines(_asset("a-2"), _asset("a-3"))})
                _record, calls = self.stage_calls()
                self.assertEqual((calls["limits"], calls["structure"], calls["semantic"]), expected)

    def test_structural_error_stops_the_semantic_stage(self):
        self.write({
            "assets/a.jsonl": _lines(_asset("a-1"), _asset("a-1")),
            "assets/b.jsonl": _lines({"id": "a-3"}),
        })
        record = self.check()
        self.assertEqual(_outcome(record), ("complete", "invalid", "not-run"))
        self.assertEqual(record["diagnostics"], [])


class MemberRuleAndScanTests(PackageTest):
    def test_manifest_file_name(self):
        manifest = self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        renamed = manifest.with_name("manifest.json")
        manifest.rename(renamed)
        code, out, _ = run(renamed, "--json")
        self.assertEqual(code, 1, out)
        record = json.loads(out)
        self.assertMultiFile(record)
        self.assertEqual(_outcome(record), ("complete", "valid", "run"))
        self.assertEqual(_found(record), [("MANIFEST_FILE_NAME", None, None, "")])

    def test_member_rule_failure_drops_the_member_rule_warnings(self):
        self.write(
            {
                "assets/a.jsonl": _lines(_asset("a-1")),
                "assets/b.jsonl": _lines(_asset("a-2")),
                "assets/c.jsonl": _lines(_asset("a-3")),
            },
            entry_overrides={"assets/c.jsonl": {"record_type": "collections"}},
        )
        record = self.check()
        self.assertEqual(_outcome(record), ("complete", "valid", "run"))
        self.assertEqual(_found(record), [("MEMBER_TYPE_MISMATCH", _m(2), None, "/manifest/members/2/record_type")])

    def test_scan_failure_is_input_invalid_and_drops_warnings(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        (self.folder / "assets" / "stray.jsonl").write_bytes(b"")
        (self.folder / "notes.txt").write_bytes(b"x")
        record = self.check()
        self.assertEqual(_outcome(record), ("input-invalid", "not-run", "not-run"))
        self.assertEqual([d["code"] for d in record["diagnostics"]], ["MEMBER_UNLISTED"])
        self.assertEqual(record["diagnostics"][0]["unlisted_path"], "assets/stray.jsonl")

    def test_warnings_appear_only_at_the_semantic_stage(self):
        members = {"assets/a.jsonl": _lines(_asset("a-1")), "assets/b.jsonl": _lines(_asset("a-2"))}
        self.write(members)
        (self.folder / "notes.txt").write_bytes(b"x")
        record = self.check()
        self.assertEqual(_outcome(record), ("complete", "valid", "run"))
        self.assertEqual(
            _found(record), [("FILE_UNLISTED", None, None, ""), ("MEMBERS_SMALL", None, None, "/manifest/members")]
        )
        self.assertEqual(validate.exit_code(record), 0)

        members["assets/b.jsonl"] = _lines({"id": "a-2"})
        self.write(members)
        record = self.check()
        self.assertEqual(_outcome(record), ("complete", "invalid", "not-run"))
        self.assertEqual(record["diagnostics"], [])

    def test_text_output_never_names_an_unlisted_file(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        (self.folder / "zzsentinel-notes.txt").write_bytes(b"x")
        code, out, _ = run(self.folder)
        self.assertEqual(code, 0, out)
        self.assertIn("warning FILE_UNLISTED (unlisted file): ", out)
        self.assertNotIn("zzsentinel", out)
        code, out, _ = run(self.folder, "--json")
        self.assertIn("zzsentinel-notes.txt", out)

        (self.folder / "assets" / "zzsentinel.jsonl").write_bytes(b"")
        code, out, _ = run(self.folder)
        self.assertEqual(code, 1, out)
        self.assertIn("error MEMBER_UNLISTED (unlisted file): ", out)
        self.assertNotIn("zzsentinel", out)

    def test_unlisted_name_that_is_not_utf8_gives_valid_json(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        try:
            (self.folder / "assets" / os.fsdecode(b"bad-\xff.jsonl")).write_bytes(b"")
        except (OSError, UnicodeError):
            self.skipTest("the file system refuses a name that is not UTF-8")
        record = self.check()
        self.assertEqual([d.get("unlisted_path") for d in record["diagnostics"]], ["assets/bad-\\xff.jsonl"])
        json.dumps(record, ensure_ascii=False).encode("utf-8")
        code, out, _ = run(self.folder, "--json")
        self.assertEqual(code, 1, out)
        self.assertEqual(json.loads(out)["diagnostics"][0]["unlisted_path"], "assets/bad-\\xff.jsonl")


class IntegrityTests(PackageTest):
    def test_compression_mismatch(self):
        self.write({"assets/a.jsonl.gz": _lines(_asset("a-1"), _asset("a-2"))})
        record = self.check()
        self.assertEqual(_outcome(record), ("input-invalid", "not-run", "not-run"))
        self.assertEqual(_found(record), [("MEMBER_COMPRESSION_MISMATCH", _m(0), None, "/manifest/members/0/path")])

    def test_bad_gzip_stream_is_a_compression_finding_without_a_count_finding(self):
        cut = gzip.compress(_lines(*(_asset(f"a-{i}") for i in range(50))))[:-12]
        self.write({"assets/a.jsonl.gz": cut}, entry_overrides={"assets/a.jsonl.gz": {"count": 50}})
        self.assertEqual(
            _found(self.check()), [("MEMBER_COMPRESSION_MISMATCH", _m(0), None, "/manifest/members/0/path")]
        )

    def test_line_rule_failure_is_one_finding_for_the_member(self):
        cases = {
            "no final LF": _lines(_asset("a-1")).rstrip(b"\n"),
            "CR LF": _lines(_asset("a-1"), _asset("a-2")).replace(b"\n", b"\r\n"),
            "blank line": _lines(_asset("a-1")) + b"\n",
            "byte-order mark": b"\xef\xbb\xbf" + _lines(_asset("a-1")),
            "space before the object": b" " + _lines(_asset("a-1")),
            "tab after the object": _lines(_asset("a-1"), _asset("a-2")).replace(b"}\n", b"}\t\n"),
        }
        for name, data in cases.items():
            with self.subTest(name):
                lines = data.count(b"\n") + (0 if data.endswith(b"\n") else 1)
                self.write({"assets/a.jsonl": data}, entry_overrides={"assets/a.jsonl": {"count": lines}})
                record = self.check()
                self.assertEqual(_outcome(record), ("input-invalid", "not-run", "not-run"))
                self.assertEqual(_found(record), [("MEMBER_LINE_INVALID", _m(0), None, "")])
                code, out, _ = run(self.folder)
                self.assertIn("error MEMBER_LINE_INVALID member 0: ", out)

    def test_member_count_mismatch(self):
        self.write(
            {"assets/a.jsonl": _lines(_asset("a-1"), _asset("a-2"))},
            entry_overrides={"assets/a.jsonl": {"count": 3}},
        )
        self.assertEqual(_found(self.check()), [("MEMBER_COUNT_MISMATCH", _m(0), None, "/manifest/members/0/count")])

    def test_size_change_after_the_scan_is_a_size_finding(self):
        # The scan saw the listed size; the file changed before the read. A hashed-only member is checked too.
        # A changed size reports the size only, not also the checksum.
        self.write(
            {"assets/a.jsonl": _lines(_asset("a-1")), "assets/b.jsonl": _lines(_asset("a-2"))},
            entry_overrides={
                "assets/a.jsonl": {"size_bytes": 1, "sha256": "0" * 64},
                "assets/b.jsonl": {"size_bytes": 2},
            },
        )
        with mock.patch.object(multifile, "scan_folder", return_value=[]):
            record = self.check()
        self.assertEqual(
            _found(record),
            [
                ("MEMBER_SIZE_MISMATCH", _m(0), None, "/manifest/members/0/size_bytes"),
                ("MEMBER_SIZE_MISMATCH", _m(1), None, "/manifest/members/1/size_bytes"),
            ],
        )

    def test_link_at_open_time_is_not_regular(self):
        # The scan saw a regular file; the link appears before the read opens the member.
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        member = self.folder / "assets" / "a.jsonl"
        copy = self.base / "copy.jsonl"
        copy.write_bytes(member.read_bytes())
        member.unlink()
        member.symlink_to(copy)
        with mock.patch.object(multifile, "scan_folder", return_value=[]):
            record = self.check()
        self.assertEqual(_outcome(record), ("input-invalid", "not-run", "not-run"))
        self.assertEqual(_found(record), [("MEMBER_NOT_REGULAR", _m(0), None, "/manifest/members/0/path")])

    def test_linked_folder_at_open_time_is_not_followed(self):
        # The scan saw a real folder; a link to a copy outside the package replaces it before the read.
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        outside = self.base / "outside"
        (self.folder / "assets").rename(outside)
        (self.folder / "assets").symlink_to(outside, target_is_directory=True)
        with mock.patch.object(multifile, "scan_folder", return_value=[]):
            record = self.check()
        self.assertEqual(_outcome(record), ("input-invalid", "not-run", "not-run"))
        self.assertEqual(_found(record), [("MEMBER_NOT_REGULAR", _m(0), None, "/manifest/members/0/path")])

    def test_reader_with_a_base_refuses_a_linked_folder_above_the_member(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "a.jsonl").write_bytes(b"{}\n")
        self.folder.mkdir()
        (self.folder / "assets").symlink_to(outside, target_is_directory=True)
        reader = multifile.MemberReader(self.folder / "assets" / "a.jsonl", False, LIMITS, base=self.folder)
        with self.assertRaises(multifile.MemberNotRegular):
            list(reader.lines())
        with self.assertRaises(multifile.MemberNotRegular):
            reader.hash_only()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no named pipes")
    def test_special_file_at_open_time_is_not_regular(self):
        self.write({"assets/a.jsonl": b""}, entry_overrides={"assets/a.jsonl": {"count": 0}})
        member = self.folder / "assets" / "a.jsonl"
        member.unlink()
        os.mkfifo(member)
        with mock.patch.object(multifile, "scan_folder", return_value=[]):
            record = self.check()
        self.assertEqual(_found(record), [("MEMBER_NOT_REGULAR", _m(0), None, "/manifest/members/0/path")])

    def test_reader_refuses_a_link(self):
        target = self.base / "target.jsonl"
        target.write_bytes(b"{}\n")
        link = self.base / "link.jsonl"
        link.symlink_to(target)
        reader = multifile.MemberReader(link, False, LIMITS)
        with self.assertRaises(multifile.MemberNotRegular) as caught:
            list(reader.lines())
        self.assertIsInstance(caught.exception, OSError)
        with self.assertRaises(multifile.MemberNotRegular):
            reader.hash_only()

    def test_hash_only_gives_the_stored_digest_and_size(self):
        data = gzip.compress(b"{}\n" * 10)
        path = self.base / "a.jsonl.gz"
        path.write_bytes(data)
        reader = multifile.MemberReader(path, True, LIMITS)
        reader.hash_only()
        self.assertEqual((reader.sha256, reader.stored_bytes), (hashlib.sha256(data).hexdigest(), len(data)))
        self.assertEqual((reader.line_count, reader.framing), (0, []))


class SetupFailureTests(PackageTest):
    def test_evaluate_refuses_manifest_bytes_without_the_folder(self):
        # The member files are missing; evaluate gets only the bytes, so it cannot check them.
        manifest = self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        data = manifest.read_bytes()
        (self.folder / "assets" / "a.jsonl").unlink()
        record = validate.evaluate(data, DEFINITIONS)
        self.assertEqual(record["execution_status"], "setup-failed")
        self.assertEqual(validate.exit_code(record), 2)
        self.assertEqual(record["diagnostics"], [])

    @_skip_as_root
    def test_unreadable_member_is_a_setup_failure(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1")), "collections/c.jsonl": _lines(_collection("c-1"))})
        member = self.folder / "assets" / "a.jsonl"
        member.chmod(0)
        self.addCleanup(member.chmod, stat.S_IRUSR | stat.S_IWUSR)
        record = self.check()
        self.assertEqual(_outcome(record), ("setup-failed", "not-run", "not-run"))
        self.assertEqual(record["limitations"], [UNREADABLE_MEMBER])
        self.assertEqual(record["diagnostics"], [])
        code, out, _ = run(self.folder)
        self.assertEqual(code, 2)
        self.assertIn(f"note: {UNREADABLE_MEMBER}\n", out)

    @_skip_as_root
    def test_unreadable_folder_in_the_scan_is_a_setup_failure(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        closed = self.folder / "notes"
        closed.mkdir()
        closed.chmod(0)
        self.addCleanup(closed.chmod, stat.S_IRWXU)
        record = self.check()
        self.assertEqual(_outcome(record), ("setup-failed", "not-run", "not-run"))
        self.assertEqual(record["limitations"], [UNREADABLE_MEMBER])

    def test_line_limit_is_a_setup_failure_with_its_own_text(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        code, out, _ = run(self.folder, "--json", "--max-line-bytes", "10")
        self.assertEqual(code, 2, out)
        record = json.loads(out)
        self.assertEqual(_outcome(record), ("setup-failed", "not-run", "not-run"))
        self.assertEqual(
            record["limitations"], ["Setup failed: a member file line is longer than the line length limit."]
        )

    @_skip_as_root
    def test_path_in_a_closed_folder_is_an_unreadable_input(self):
        closed = self.base / "closed"
        closed.mkdir()
        closed.chmod(0)
        self.addCleanup(closed.chmod, stat.S_IRWXU)
        for target in (closed / "doc.json", closed / "pkg"):
            with self.subTest(target=target.name):
                code, out, err = run(target, "--json")
                self.assertEqual(code, 2, err)
                self.assertEqual(json.loads(out)["limitations"], ["Setup failed: input file cannot be read."])

    def assertUnreadableInput(self, record):
        self.assertMultiFile(record)
        self.assertEqual(_outcome(record), ("setup-failed", "not-run", "not-run"))
        self.assertEqual(record["limitations"], ["Setup failed: input file cannot be read."])
        self.assertIsNone(record["input_sha256"])

    def test_linked_manifest_in_the_folder_form_is_not_read(self):
        manifest = self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        outside = self.base / "outside.json"
        manifest.rename(outside)
        manifest.symlink_to(outside)
        code, out, _ = run(self.folder, "--json")
        self.assertEqual(code, 2, out)
        self.assertUnreadableInput(json.loads(out))
        self.assertUnreadableInput(
            multifile.evaluate_folder(manifest, DEFINITIONS, None, LIMITS, from_folder=True)
        )

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no named pipes")
    def test_special_file_manifest_in_the_folder_form_is_not_read(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))}).unlink()
        os.mkfifo(self.folder / MANIFEST_NAME)
        code, out, _ = run(self.folder, "--json")
        self.assertEqual(code, 2, out)
        self.assertUnreadableInput(json.loads(out))

    def test_directly_named_linked_manifest_is_the_callers_input(self):
        # The package folder is the folder of the path as given, not of the link target.
        manifest = self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        outside = self.base / "outside.json"
        manifest.rename(outside)
        manifest.symlink_to(outside)
        code, out, _ = run(manifest, "--json")
        self.assertEqual(code, 0, out)
        record = json.loads(out)
        self.assertEqual(_outcome(record), ("complete", "valid", "run"))
        self.assertEqual(record["diagnostics"], [])
        self.assertEqual(record["input_sha256"], hashlib.sha256(outside.read_bytes()).hexdigest())

    def test_missing_manifest_in_a_folder_is_a_setup_failure(self):
        self.folder.mkdir()
        code, out, _ = run(self.folder, "--json")
        self.assertEqual(code, 2)
        record = json.loads(out)
        self.assertMultiFile(record)
        self.assertEqual(record["limitations"], ["Setup failed: input file cannot be read."])
        self.assertIsNone(record["input_sha256"])


class ManifestStageTests(PackageTest):
    def test_manifest_parse_failure_is_input_invalid(self):
        self.folder.mkdir()
        (self.folder / MANIFEST_NAME).write_bytes(b'{"type": "package",')
        record = self.check()
        self.assertMultiFile(record)
        self.assertEqual(_outcome(record), ("input-invalid", "not-run", "not-run"))
        self.assertEqual(_found(record), [("INPUT_INVALID", None, None, "")])

    def test_unsupported_manifest_version(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))}, {"spec_version": "2.0.0-draft.3"})
        record = self.check()
        self.assertEqual(_outcome(record), ("unsupported", "not-run", "not-run"))
        self.assertEqual(_found(record), [("VERSION_UNSUPPORTED", None, None, "/spec_version")])

    def test_manifest_with_record_arrays_is_structurally_invalid(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))}, {"assets": [_asset("a-1")]})
        record = self.check()
        self.assertMultiFile(record)
        self.assertEqual(_outcome(record), ("complete", "invalid", "not-run"))
        self.assertTrue(record["structural_errors"])
        self.assertTrue(all("member" not in error for error in record["structural_errors"]))

    def test_manifest_number_limits(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))}, {"extensions": {"gen": {"n": 9007199254740993}}})
        record = self.check()
        self.assertEqual(_outcome(record), ("input-invalid", "not-run", "not-run"))
        self.assertEqual(_found(record), [("NUMBER_OUT_OF_RANGE", None, None, "/extensions")])


class DispatchTests(PackageTest):
    def test_folder_with_a_single_document_manifest_is_a_single_document(self):
        self.folder.mkdir()
        data = (EXAMPLES / "package-full.json").read_bytes()
        (self.folder / MANIFEST_NAME).write_bytes(data)
        code, out, _ = run(self.folder, "--json")
        self.assertEqual(code, 0, out)
        record = json.loads(out)
        expected = validate.evaluate(data, DEFINITIONS)
        expected["file"] = str(self.folder)
        self.assertEqual(record, expected)
        self.assertEqual(record["form"], "single-document")

    def test_single_document_file_is_checked_as_today(self):
        document = json.loads((EXAMPLES / "package-minimal.json").read_bytes())
        document["manifest"]["description"] = "The members of the team."
        path = self.base / "doc.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        code, out, _ = run(path, "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["form"], "single-document")

    def test_members_key_is_found_through_escapes(self):
        self.assertTrue(validate._is_multi_file(b'{"manifest": {"\\u006dembers": []}}'))
        self.assertTrue(validate._is_multi_file(b'{"manifest": {"members": []}}'))
        self.assertFalse(validate._is_multi_file(b'{"manifest": {"member_of": []}, "members": []}'))
        self.assertFalse(validate._is_multi_file(b'{"manifest": {"x": "\\u00e9"}}'))
        self.assertFalse(validate._is_multi_file(b'{"manifest": {"members": [}'))
        self.assertFalse(validate._is_multi_file(b"[]"))

    def test_options_reach_the_folder_check(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        work = self.base / "work"
        with mock.patch.object(multifile, "evaluate_folder", wraps=multifile.evaluate_folder) as evaluate:
            code, out, _ = run(self.folder, "--work-dir", work, "--max-line-bytes", "4096", "--max-gzip-ratio", "7")
        self.assertEqual(code, 0, out)
        manifest, definitions, work_dir, limits = evaluate.call_args.args
        self.assertEqual((manifest, definitions, work_dir), (self.folder / MANIFEST_NAME, validate.ROOT, work))
        self.assertEqual(limits, multifile.ReadLimits(max_line_bytes=4096, max_gzip_ratio=7))
        self.assertEqual(evaluate.call_args.kwargs, {"from_folder": True})
        with mock.patch.object(multifile, "evaluate_folder", wraps=multifile.evaluate_folder) as evaluate:
            code, out, _ = run(self.folder / MANIFEST_NAME)
        self.assertEqual(code, 0, out)
        self.assertEqual(evaluate.call_args.kwargs, {"from_folder": False})

    def test_defaults_reach_the_folder_check(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        with mock.patch.object(multifile, "evaluate_folder", wraps=multifile.evaluate_folder) as evaluate:
            run(self.folder)
        self.assertEqual(evaluate.call_args.args[2:], (None, multifile.ReadLimits()))

    def test_bad_limit_values_are_usage_errors(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        for option in ("--max-line-bytes", "--max-gzip-ratio"):
            for value in ("0", "-1", "ten"):
                with self.subTest(option=option, value=value):
                    code, out, err = run(self.folder, option, value)
                    self.assertEqual(code, 2)
                    self.assertEqual(out, "")
                    self.assertIn("usage:", err)


class WorkFolderTests(PackageTest):
    def test_work_dir_keeps_the_store_files(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        work = self.base / "work"
        for attempt in (1, 2):
            with self.subTest(attempt=attempt):
                code, out, _ = run(self.folder, "--work-dir", work)
                self.assertEqual(code, 0, out)
                for name in (multifile.STORE_NAME, multifile.FINDINGS_NAME):
                    self.assertTrue((work / name).read_bytes().startswith(b"SQLite format 3\x00"), name)

    def test_default_work_folder_is_removed(self):
        system_temp = self.base / "system-temp"
        system_temp.mkdir()
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        with mock.patch.object(tempfile, "tempdir", str(system_temp)):
            with mock.patch.object(tempfile, "mkdtemp", wraps=tempfile.mkdtemp) as made:
                code, out, _ = run(self.folder)
                self.assertEqual(code, 0, out)
                self.assertEqual(made.call_count, 1)
                self.assertEqual(list(system_temp.iterdir()), [])
                # A setup failure in the middle of the read removes the folder too.
                record = self.check(limits=multifile.ReadLimits(max_line_bytes=10))
                self.assertEqual(record["execution_status"], "setup-failed")
                self.assertEqual(made.call_count, 2)
                self.assertEqual(list(system_temp.iterdir()), [])

    def test_unusable_work_dir_is_a_setup_failure(self):
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        blocker = self.base / "file"
        blocker.write_bytes(b"")
        record = self.check(work_dir=blocker / "work")
        self.assertEqual(_outcome(record), ("setup-failed", "not-run", "not-run"))
        self.assertEqual(
            record["limitations"], ["Setup failed: the checker cannot write its working files in the work folder."]
        )

    def test_sqlite_temporary_files_go_to_the_work_folder(self):
        probe = sqlite3.connect(":memory:")
        self.addCleanup(probe.close)
        self.write({"assets/a.jsonl": _lines(_asset("a-1"))})
        work = self.base / "work"
        seen = []
        original = multifile.PackageChecker.finish

        def spy(checker):
            seen.append(probe.execute("PRAGMA temp_store_directory").fetchall())
            return original(checker)

        with mock.patch.object(multifile.PackageChecker, "finish", spy):
            record = self.check(work_dir=work)
        self.assertEqual(record["execution_status"], "complete")
        self.assertEqual(seen, [[(str(work),)]])
        self.assertEqual(probe.execute("PRAGMA temp_store_directory").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
