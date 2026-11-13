"""The manifest member-list rules and the package folder scan.

``check_member_list`` works on the parsed manifest root alone. ``scan_folder``
compares the root with the folder on disk. It uses only ``os.lstat`` and
``os.scandir``: it never follows a link and never opens a file.
"""

import copy
import gzip
import json
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from tests.conformance import multifile
from tests.conformance.multifile_testing import build_root, member_entry, write_package
from tests.conformance.semantic import CATALOG, REGISTRIES

DATA = b'{"id":"a"}\n' * 3


def _root(*members, **overrides):
    """A manifest root from ``(path, count)`` pairs. No file exists for it."""
    entries = [member_entry(path, b"x\n" * count) for path, count in members]
    return build_root(entries, overrides or None)


def _codes(found):
    return [d.code for d in found]


def _load(manifest: Path) -> dict:
    return json.loads(manifest.read_text(encoding="utf-8"))


class CheckMemberListTest(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(multifile.MANIFEST_NAME, "oasis-package.json")
        self.assertEqual(multifile.RECORD_FOLDERS, REGISTRIES)

    def test_clean_member_list_has_no_finding(self):
        root = _root(
            ("assets/part-00001.jsonl", 2000),
            ("assets/part-00002.jsonl.gz", 1500),
            ("collections/c.jsonl", 3),
        )
        self.assertEqual(multifile.check_member_list(root), [])

    def test_single_small_member_is_not_small(self):
        self.assertEqual(multifile.check_member_list(_root(("assets/a.jsonl", 3))), [])

    def test_empty_member_list_has_no_finding(self):
        self.assertEqual(multifile.check_member_list(_root()), [])

    def test_does_not_change_the_root(self):
        root = _root(("assets/a.jsonl", 5), ("assets/A.jsonl", 0), ("collections/b.jsonl", 1))
        before = copy.deepcopy(root)
        multifile.check_member_list(root)
        self.assertEqual(root, before)

    def test_duplicate_path_is_reported_at_each_later_entry(self):
        root = _root(("assets/a.jsonl", 2000), ("assets/a.jsonl", 2000), ("assets/a.jsonl", 2000))
        found = [d for d in multifile.check_member_list(root) if d.code == "MEMBER_PATH_DUPLICATE"]
        self.assertEqual([d.path for d in found], ["/manifest/members/1/path", "/manifest/members/2/path"])
        self.assertEqual([d.member for d in found], [1, 2])
        self.assertEqual({d.rule for d in found}, {"MFP-2"})
        self.assertEqual({d.severity for d in found}, {"error"})

    def test_exact_duplicate_is_not_also_a_case_collision(self):
        root = _root(("assets/a.jsonl", 2000), ("assets/a.jsonl", 2000))
        self.assertEqual(_codes(multifile.check_member_list(root)), ["MEMBER_PATH_DUPLICATE"])

    def test_paths_that_differ_only_in_case_collide(self):
        root = _root(("assets/A.jsonl", 2000), ("assets/a.jsonl", 2000), ("assets/b.jsonl", 2000))
        found = multifile.check_member_list(root)
        self.assertEqual(_codes(found), ["MEMBER_PATH_CASE_COLLISION"])
        self.assertEqual(found[0].path, "/manifest/members/1/path")
        self.assertEqual(found[0].member, 1)

    def test_case_collision_covers_every_later_entry(self):
        root = _root(("assets/Ab.jsonl", 2000), ("assets/aB.jsonl", 2000), ("assets/AB.jsonl", 2000))
        found = multifile.check_member_list(root)
        self.assertEqual(_codes(found), ["MEMBER_PATH_CASE_COLLISION"] * 2)
        self.assertEqual([d.member for d in found], [1, 2])

    def test_case_collision_uses_casefold_across_folders(self):
        root = _root(("assets/x/Part.jsonl", 2000), ("assets/X/part.jsonl", 2000))
        self.assertEqual(_codes(multifile.check_member_list(root)), ["MEMBER_PATH_CASE_COLLISION"])

    def test_different_names_do_not_collide(self):
        root = _root(("assets/a.jsonl", 2000), ("assets/a.jsonl.gz", 2000), ("collections/a.jsonl", 2000))
        self.assertEqual(multifile.check_member_list(root), [])

    def test_record_type_must_match_the_first_segment(self):
        root = _root(("assets/a.jsonl", 5))
        root["manifest"]["members"][0]["record_type"] = "collections"
        root["manifest"]["counts"] = {"storage_locations": 0, "metadata_definitions": 0, "collections": 5, "assets": 0}
        found = multifile.check_member_list(root)
        self.assertEqual(_codes(found), ["MEMBER_TYPE_MISMATCH"])
        self.assertEqual(found[0].path, "/manifest/members/0/record_type")
        self.assertEqual(found[0].member, 0)
        self.assertEqual(found[0].rule, "MFP-2")

    def test_count_mismatch_reports_the_list(self):
        root = _root(("assets/a.jsonl", 2000), ("assets/b.jsonl", 2000))
        root["manifest"]["counts"]["assets"] = 3999
        found = multifile.check_member_list(root)
        self.assertEqual(_codes(found), ["COUNT_MISMATCH"])
        self.assertEqual(found[0].path, "/manifest/counts/assets")
        self.assertIsNone(found[0].member)
        self.assertEqual(found[0].rule, "PKG-3")

    def test_count_mismatch_is_per_list(self):
        root = _root(("assets/a.jsonl", 1), ("collections/c.jsonl", 2))
        root["manifest"]["counts"]["collections"] = 1
        root["manifest"]["counts"]["storage_locations"] = 4
        found = multifile.check_member_list(root)
        self.assertEqual(
            [(d.code, d.path) for d in found],
            [
                ("COUNT_MISMATCH", "/manifest/counts/storage_locations"),
                ("COUNT_MISMATCH", "/manifest/counts/collections"),
            ],
        )

    def test_a_list_without_members_counts_zero(self):
        root = _root(("assets/a.jsonl", 1))
        self.assertEqual(multifile.check_member_list(root), [])
        root["manifest"]["counts"]["collections"] = 1
        self.assertEqual(_codes(multifile.check_member_list(root)), ["COUNT_MISMATCH"])

    def test_an_absent_count_is_not_checked(self):
        root = _root(("assets/a.jsonl", 1))
        del root["manifest"]["counts"]["assets"]
        self.assertEqual(multifile.check_member_list(root), [])

    def test_counts_may_be_integral_decimals(self):
        root = _root(("assets/a.jsonl", 2000), ("assets/b.jsonl", 2000))
        root["manifest"]["members"][0]["count"] = Decimal("2000")
        root["manifest"]["counts"]["assets"] = Decimal("4000.0")
        self.assertEqual(multifile.check_member_list(root), [])
        root["manifest"]["counts"]["assets"] = Decimal("3999")
        self.assertEqual(_codes(multifile.check_member_list(root)), ["COUNT_MISMATCH"])

    def test_empty_member_beside_a_full_member_is_unexpected(self):
        root = _root(("assets/a.jsonl", 5), ("assets/b.jsonl", 0), ("assets/c.jsonl", 0))
        found = [d for d in multifile.check_member_list(root) if d.code == "MEMBER_EMPTY_UNEXPECTED"]
        self.assertEqual([d.path for d in found], ["/manifest/members/1/count", "/manifest/members/2/count"])
        self.assertEqual([d.member for d in found], [1, 2])
        self.assertEqual({d.rule for d in found}, {"MFP-6"})

    def test_empty_member_in_an_empty_list_is_allowed(self):
        root = _root(("collections/a.jsonl", 0))
        self.assertEqual(multifile.check_member_list(root), [])

    def test_empty_member_is_judged_per_list(self):
        root = _root(("collections/a.jsonl", 0), ("assets/a.jsonl", 2000))
        self.assertEqual(multifile.check_member_list(root), [])

    def test_small_members_warn_once_per_list(self):
        root = _root(("assets/a.jsonl", 10), ("assets/b.jsonl", 10), ("assets/c.jsonl", 10))
        found = multifile.check_member_list(root)
        self.assertEqual(_codes(found), ["MEMBERS_SMALL"])
        self.assertEqual(found[0].path, "/manifest/members")
        self.assertEqual(found[0].severity, "warning")
        self.assertEqual(found[0].rule, "MFP-3")
        self.assertIsNone(found[0].member)

    def test_small_members_are_judged_per_list(self):
        root = _root(
            ("assets/a.jsonl", 10),
            ("assets/b.jsonl", 10),
            ("collections/a.jsonl", 10),
            ("collections/b.jsonl", 10),
        )
        self.assertEqual(_codes(multifile.check_member_list(root)), ["MEMBERS_SMALL"] * 2)

    def test_average_of_1000_is_not_small(self):
        at_limit = _root(("assets/a.jsonl", 1500), ("assets/b.jsonl", 500))
        self.assertEqual(multifile.check_member_list(at_limit), [])
        below = _root(("assets/a.jsonl", 1500), ("assets/b.jsonl", 499))
        self.assertEqual(_codes(multifile.check_member_list(below)), ["MEMBERS_SMALL"])

    def test_every_code_is_in_the_catalog_with_its_severity(self):
        root = _root(("assets/a.jsonl", 5), ("assets/a.jsonl", 0), ("assets/b.jsonl", 1))
        root["manifest"]["counts"]["assets"] = 99
        for d in multifile.check_member_list(root):
            self.assertEqual((d.rule, d.severity, d.message), CATALOG[d.code])


class _FolderCase(unittest.TestCase):
    """A package folder in a temporary directory, and a scan that must not open a file."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name) / "package"
        self.dir.mkdir()
        self.other = Path(temp.name) / "elsewhere"
        self.other.mkdir()

    def package(self, members=None, **kwargs):
        members = {"assets/part-00001.jsonl": DATA} if members is None else members
        manifest = write_package(self.dir, members, **kwargs)
        return _load(manifest)

    def scan(self, root):
        refused = AssertionError("scan_folder opened a file")
        with (
            mock.patch("builtins.open", side_effect=refused),
            mock.patch("io.open", side_effect=refused),
            mock.patch("os.open", side_effect=refused),
        ):
            return multifile.scan_folder(self.dir, root)

    def symlink(self, target, link, directory=False):
        try:
            os.symlink(target, link, target_is_directory=directory)
        except (OSError, NotImplementedError, AttributeError) as error:
            self.skipTest(f"symbolic links are not available: {error}")


class ExactSpellingTest(_FolderCase):
    """`MFP-3`. A member path must match the name stored on disk, code point for code point.

    ``os.lstat`` resolves a name through the file system's folding, so on macOS
    and Windows a path that differs only in letter case still opens. Without this
    check the same package folder passes there and fails on Linux. Letter case is
    the only such difference a schema-valid path can hold, because `MFP-2` limits
    a segment to ASCII; the comparison is by code point all the same, so a path
    that reaches the check another way is treated the same way.
    """

    def test_exact_spelling_is_accepted(self):
        self.package({"assets/part-00001.jsonl": DATA})
        self.assertTrue(multifile._spelled_exactly(str(self.dir), ["assets", "part-00001.jsonl"], {}))

    def test_folder_differing_in_case_is_not_exact(self):
        self.package({"assets/part-00001.jsonl": DATA})
        self.assertFalse(multifile._spelled_exactly(str(self.dir), ["Assets", "part-00001.jsonl"], {}))

    def test_file_differing_in_case_is_not_exact(self):
        self.package({"assets/part-00001.jsonl": DATA})
        self.assertFalse(multifile._spelled_exactly(str(self.dir), ["assets", "Part-00001.jsonl"], {}))

    def test_other_unicode_form_is_not_exact(self):
        """The comparison is by code point, not by Unicode form.

        `MFP-2` keeps such a path out of a schema-valid manifest, so this is the
        property of the comparison, not a package state a checker meets.
        """
        self.package({"assets/café.jsonl": DATA})
        self.assertFalse(multifile._spelled_exactly(str(self.dir), ["assets", "café.jsonl"], {}))

    def test_case_folding_file_system_reports_not_exact(self):
        """A folded ``os.lstat``, as on macOS, must not turn a mismatch into a pass."""
        root = self.package({"assets/part-00001.jsonl": DATA})
        root["manifest"]["members"][0]["path"] = "Assets/part-00001.jsonl"
        real = os.lstat

        def folded(path, *args, **kwargs):
            try:
                return real(path, *args, **kwargs)
            except FileNotFoundError:
                return real(os.fspath(path).replace("Assets", "assets"))

        with mock.patch("os.lstat", side_effect=folded):
            found = multifile._check_member(str(self.dir), 0, root["manifest"]["members"][0], {})
        self.assertEqual(_codes(found), ["MEMBER_PATH_NOT_EXACT"])
        self.assertEqual(found[0].rule, "MFP-3")
        self.assertEqual(found[0].path, "/manifest/members/0/path")

    def test_catalog_entry_matches(self):
        self.assertEqual(CATALOG["MEMBER_PATH_NOT_EXACT"][0], "MFP-3")
        self.assertEqual(CATALOG["MEMBER_PATH_NOT_EXACT"][1], "error")


class ScanFolderTest(_FolderCase):
    def test_clean_package_has_no_finding(self):
        root = self.package(
            {
                "assets/part-00001.jsonl": DATA,
                "assets/source=dalet/part-00002.jsonl.gz": gzip.compress(DATA),
                "collections/part-00001.jsonl": DATA,
                "storage_locations/empty.jsonl": b"",
            }
        )
        self.assertEqual(self.scan(root), [])

    def test_missing_member_file(self):
        root = self.package({"assets/a.jsonl": DATA, "assets/b.jsonl": DATA}, skip=["assets/b.jsonl"])
        found = self.scan(root)
        self.assertEqual(_codes(found), ["MEMBER_MISSING"])
        self.assertEqual(found[0].path, "/manifest/members/1/path")
        self.assertEqual(found[0].member, 1)
        self.assertEqual(found[0].rule, "MFP-3")

    def test_missing_record_folder(self):
        names = ["assets/a.jsonl", "assets/deep/b.jsonl"]
        root = self.package(dict.fromkeys(names, DATA), skip=names)
        self.assertEqual(_codes(self.scan(root)), ["MEMBER_MISSING", "MEMBER_MISSING"])

    def test_size_one_byte_too_small_or_large(self):
        for delta in (-1, 1):
            with self.subTest(delta=delta):
                wrong = {"assets/a.jsonl": {"size_bytes": len(DATA) + delta}}
                root = self.package({"assets/a.jsonl": DATA}, entry_overrides=wrong)
                found = self.scan(root)
                self.assertEqual(_codes(found), ["MEMBER_SIZE_MISMATCH"])
                self.assertEqual(found[0].path, "/manifest/members/0/size_bytes")
                self.assertEqual(found[0].member, 0)

    def test_size_may_be_an_integral_decimal(self):
        root = self.package({"assets/a.jsonl": DATA})
        root["manifest"]["members"][0]["size_bytes"] = Decimal(len(DATA))
        self.assertEqual(self.scan(root), [])

    def test_findings_follow_manifest_order(self):
        root = self.package(
            {"assets/a.jsonl": DATA, "assets/b.jsonl": DATA, "assets/c.jsonl": DATA},
            entry_overrides={"assets/a.jsonl": {"size_bytes": 1}, "assets/c.jsonl": {"size_bytes": 1}},
            skip=["assets/b.jsonl"],
        )
        found = self.scan(root)
        self.assertEqual(
            [(d.code, d.member) for d in found],
            [("MEMBER_SIZE_MISMATCH", 0), ("MEMBER_MISSING", 1), ("MEMBER_SIZE_MISMATCH", 2)],
        )

    def test_folder_at_a_member_path_is_not_regular(self):
        root = self.package({"assets/a.jsonl": DATA}, skip=["assets/a.jsonl"])
        (self.dir / "assets" / "a.jsonl").mkdir(parents=True)
        found = self.scan(root)
        self.assertEqual(_codes(found), ["MEMBER_NOT_REGULAR"])
        self.assertEqual(found[0].path, "/manifest/members/0/path")

    def test_regular_file_in_place_of_a_folder_is_not_regular(self):
        root = self.package({"assets/a.jsonl": DATA}, skip=["assets/a.jsonl"])
        (self.dir / "assets").write_bytes(b"not a folder")
        self.assertEqual(_codes(self.scan(root)), ["MEMBER_NOT_REGULAR"])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "named pipes are not available")
    def test_named_pipe_is_not_regular(self):
        root = self.package({"assets/a.jsonl": DATA}, skip=["assets/a.jsonl"])
        (self.dir / "assets").mkdir()
        os.mkfifo(self.dir / "assets" / "a.jsonl")
        self.assertEqual(_codes(self.scan(root)), ["MEMBER_NOT_REGULAR"])

    def test_member_that_is_a_link_is_not_regular(self):
        root = self.package({"assets/a.jsonl": DATA}, skip=["assets/a.jsonl"])
        real = self.other / "real.jsonl"
        real.write_bytes(DATA)
        (self.dir / "assets").mkdir()
        self.symlink(real, self.dir / "assets" / "a.jsonl")
        found = self.scan(root)
        self.assertEqual(_codes(found), ["MEMBER_NOT_REGULAR"])
        self.assertEqual(found[0].member, 0)

    def test_member_that_is_a_dangling_link_is_not_regular(self):
        root = self.package({"assets/a.jsonl": DATA}, skip=["assets/a.jsonl"])
        (self.dir / "assets").mkdir()
        self.symlink(self.other / "gone.jsonl", self.dir / "assets" / "a.jsonl")
        self.assertEqual(_codes(self.scan(root)), ["MEMBER_NOT_REGULAR"])

    def test_linked_subfolder_is_not_regular(self):
        root = self.package({"assets/sub/a.jsonl": DATA}, skip=["assets/sub/a.jsonl"])
        (self.other / "a.jsonl").write_bytes(DATA)
        (self.dir / "assets").mkdir()
        self.symlink(self.other, self.dir / "assets" / "sub", directory=True)
        self.assertEqual(_codes(self.scan(root)), ["MEMBER_NOT_REGULAR"])

    def test_linked_record_folder_is_not_followed_or_read(self):
        # Review Focus 1: a linked `assets` folder that holds a valid copy.
        root = self.package({"assets/part-00001.jsonl": DATA}, skip=["assets/part-00001.jsonl"])
        (self.other / "part-00001.jsonl").write_bytes(DATA)
        (self.other / "extra.jsonl").write_bytes(DATA)
        link = self.dir / "assets"
        self.symlink(self.other, link, directory=True)
        calls = []

        def watch(name, real):
            def wrapper(path, *args, **kwargs):
                calls.append((name, os.fspath(path)))
                return real(path, *args, **kwargs)

            return wrapper

        with (
            mock.patch("os.lstat", watch("lstat", os.lstat)),
            mock.patch("os.stat", watch("stat", os.stat)),
            mock.patch("os.scandir", watch("scandir", os.scandir)),
        ):
            found = self.scan(root)

        self.assertEqual(_codes(found), ["MEMBER_NOT_REGULAR"])
        self.assertEqual(found[0].path, "/manifest/members/0/path")
        self.assertEqual(found[0].member, 0)
        link_text = os.fspath(link)
        for name, path in calls:
            beneath = path.startswith(link_text + os.sep) or path.startswith(os.fspath(self.other))
            self.assertFalse(beneath, f"{name} reached through the link: {path}")
            self.assertFalse(name == "scandir" and path == link_text, "the linked folder was listed")
        self.assertIn(("lstat", link_text), calls)

    def test_unsafe_member_path_is_not_regular_and_leaves_the_folder_alone(self):
        root = self.package({"assets/a.jsonl": DATA})
        (self.other / "x.jsonl").write_bytes(DATA)
        inside = os.fspath(self.dir)
        unsafe = (
            "../elsewhere/x.jsonl",
            "assets/../../elsewhere/x.jsonl",
            "/etc/hosts",
            "assets//a.jsonl",
            "assets\\a.jsonl",
            "./assets/a.jsonl",
        )
        for path in unsafe:
            with self.subTest(path=path):
                bad = copy.deepcopy(root)
                bad["manifest"]["members"][0]["path"] = path
                seen = []
                real = os.lstat

                def watch(target, *args, _seen=seen, _real=real, **kwargs):
                    _seen.append(os.fspath(target))
                    return _real(target, *args, **kwargs)

                with mock.patch("os.lstat", watch):
                    found = self.scan(bad)
                self.assertEqual((found[0].code, found[0].member), ("MEMBER_NOT_REGULAR", 0))
                for target in seen:
                    self.assertTrue(target == inside or target.startswith(inside + os.sep), target)

    def test_unlisted_file_in_a_record_folder_is_an_error(self):
        root = self.package({"assets/part-00001.jsonl": DATA})
        (self.dir / "assets" / "._part-00001.jsonl").write_bytes(b"\x00\x05\x16\x07")
        found = self.scan(root)
        self.assertEqual(_codes(found), ["MEMBER_UNLISTED"])
        self.assertEqual(found[0].unlisted_path, "assets/._part-00001.jsonl")
        self.assertEqual(found[0].path, "")
        self.assertIsNone(found[0].member)
        self.assertIsNone(found[0].line)
        self.assertEqual((found[0].rule, found[0].severity), ("MFP-3", "error"))

    def test_unlisted_file_in_a_subfolder_of_a_record_folder(self):
        root = self.package({"assets/part-00001.jsonl": DATA})
        (self.dir / "assets" / "source=dalet" / "deep").mkdir(parents=True)
        (self.dir / "assets" / "source=dalet" / "deep" / "stray.jsonl.gz").write_bytes(b"")
        found = self.scan(root)
        self.assertEqual(
            [(d.code, d.unlisted_path) for d in found],
            [("MEMBER_UNLISTED", "assets/source=dalet/deep/stray.jsonl.gz")],
        )

    def test_unlisted_file_outside_the_record_folders_is_a_warning(self):
        root = self.package({"assets/part-00001.jsonl": DATA})
        (self.dir / "README.txt").write_bytes(b"read me")
        found = self.scan(root)
        self.assertEqual(_codes(found), ["FILE_UNLISTED"])
        self.assertEqual(found[0].unlisted_path, "README.txt")
        self.assertEqual(found[0].path, "")
        self.assertEqual(found[0].severity, "warning")

    def test_unlisted_file_in_another_folder_is_a_warning(self):
        root = self.package({"assets/part-00001.jsonl": DATA})
        (self.dir / "notes" / "old").mkdir(parents=True)
        (self.dir / "notes" / "old" / "a.txt").write_bytes(b"x")
        (self.dir / "assets_backup").mkdir()
        (self.dir / "assets_backup" / "part-00001.jsonl").write_bytes(DATA)
        found = self.scan(root)
        self.assertEqual(
            [(d.code, d.unlisted_path) for d in found],
            [("FILE_UNLISTED", "assets_backup/part-00001.jsonl"), ("FILE_UNLISTED", "notes/old/a.txt")],
        )

    def test_manifest_file_is_not_unlisted(self):
        root = self.package({"assets/part-00001.jsonl": DATA})
        self.assertTrue((self.dir / multifile.MANIFEST_NAME).is_file())
        self.assertEqual(self.scan(root), [])

    def test_manifest_name_inside_a_record_folder_is_unlisted(self):
        root = self.package({"assets/part-00001.jsonl": DATA})
        (self.dir / "assets" / multifile.MANIFEST_NAME).write_bytes(b"{}")
        self.assertEqual(_codes(self.scan(root)), ["MEMBER_UNLISTED"])

    def test_empty_folders_are_not_reported(self):
        root = self.package({"assets/part-00001.jsonl": DATA})
        (self.dir / "assets" / "empty").mkdir()
        (self.dir / "collections").mkdir()
        (self.dir / "extras").mkdir()
        self.assertEqual(self.scan(root), [])

    def test_unlisted_files_are_sorted_by_path_after_member_findings(self):
        root = self.package({"assets/a.jsonl": DATA}, entry_overrides={"assets/a.jsonl": {"size_bytes": 1}})
        (self.dir / "assets" / "z.jsonl").write_bytes(b"")
        (self.dir / "assets" / "b.jsonl").write_bytes(b"")
        (self.dir / "top.txt").write_bytes(b"")
        found = self.scan(root)
        self.assertEqual(
            [(d.code, d.unlisted_path) for d in found],
            [
                ("MEMBER_SIZE_MISMATCH", None),
                ("MEMBER_UNLISTED", "assets/b.jsonl"),
                ("MEMBER_UNLISTED", "assets/z.jsonl"),
                ("FILE_UNLISTED", "top.txt"),
            ],
        )

    def test_unlisted_link_in_a_record_folder_is_reported_and_not_followed(self):
        root = self.package({"assets/part-00001.jsonl": DATA})
        (self.other / "secret.jsonl").write_bytes(DATA)
        self.symlink(self.other, self.dir / "assets" / "more", directory=True)
        self.symlink(self.other / "secret.jsonl", self.dir / "assets" / "file.jsonl")
        found = self.scan(root)
        self.assertEqual(
            [(d.code, d.unlisted_path) for d in found],
            [("MEMBER_UNLISTED", "assets/file.jsonl"), ("MEMBER_UNLISTED", "assets/more")],
        )

    def test_linked_folder_outside_the_record_folders_is_one_warning(self):
        root = self.package({"assets/part-00001.jsonl": DATA})
        (self.other / "secret.txt").write_bytes(b"x")
        self.symlink(self.other, self.dir / "extras", directory=True)
        found = self.scan(root)
        self.assertEqual([(d.code, d.unlisted_path) for d in found], [("FILE_UNLISTED", "extras")])

    def test_linked_record_folder_without_members_is_one_warning(self):
        root = self.package({"assets/part-00001.jsonl": DATA})
        (self.other / "c.jsonl").write_bytes(DATA)
        self.symlink(self.other, self.dir / "collections", directory=True)
        found = self.scan(root)
        self.assertEqual([(d.code, d.unlisted_path) for d in found], [("FILE_UNLISTED", "collections")])

    def test_does_not_change_the_root(self):
        root = self.package({"assets/a.jsonl": DATA})
        before = copy.deepcopy(root)
        self.scan(root)
        self.assertEqual(root, before)


class WritePackageTest(unittest.TestCase):
    def test_writes_members_and_manifest_with_computed_values(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = write_package(temp, {"assets/a.jsonl": DATA, "collections/c.jsonl": b""})
            root = _load(manifest)
        self.assertEqual(manifest.name, multifile.MANIFEST_NAME)
        entry = root["manifest"]["members"][0]
        self.assertEqual(
            (entry["path"], entry["record_type"], entry["count"], entry["size_bytes"]),
            ("assets/a.jsonl", "assets", 3, len(DATA)),
        )
        self.assertEqual(len(entry["sha256"]), 64)
        self.assertEqual(
            root["manifest"]["counts"],
            {"storage_locations": 0, "metadata_definitions": 0, "collections": 0, "assets": 3},
        )

    def test_manifest_is_written_last(self):
        order = []
        real = Path.write_bytes
        real_text = Path.write_text

        def note_bytes(self, data):
            order.append(self.name)
            return real(self, data)

        def note_text(self, data, *args, **kwargs):
            order.append(self.name)
            return real_text(self, data, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(Path, "write_bytes", note_bytes), mock.patch.object(Path, "write_text", note_text):
                write_package(temp, {"assets/a.jsonl": DATA, "assets/b.jsonl": DATA})
        self.assertEqual(order, ["a.jsonl", "b.jsonl", multifile.MANIFEST_NAME])

    def test_overrides_and_skip(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = write_package(
                temp,
                {"assets/a.jsonl": DATA, "assets/b.jsonl": DATA},
                {"manifest": {"counts": {"assets": 99}, "producer": {"version": "9"}}},
                entry_overrides={"assets/b.jsonl": {"count": 7}},
                skip=["assets/a.jsonl"],
            )
            root = _load(manifest)
            self.assertFalse((Path(temp) / "assets" / "a.jsonl").exists())
            self.assertTrue((Path(temp) / "assets" / "b.jsonl").exists())
        self.assertEqual(root["manifest"]["counts"]["assets"], 99)
        self.assertEqual(root["manifest"]["producer"], {"name": "test-exporter", "version": "9"})
        self.assertEqual([e["count"] for e in root["manifest"]["members"]], [3, 7])

    def test_gzip_count_is_the_decompressed_line_count(self):
        entry = member_entry("assets/a.jsonl.gz", gzip.compress(DATA))
        self.assertEqual(entry["count"], 3)

    def test_bytes_that_are_not_gzip_under_a_gz_name_are_counted_as_stored(self):
        entry = member_entry("assets/a.jsonl.gz", DATA)
        self.assertEqual((entry["count"], entry["size_bytes"]), (3, len(DATA)))


if __name__ == "__main__":
    unittest.main()
