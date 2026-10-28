"""Tests for the 2.0 bundle manifest parser."""

import copy
import dataclasses
import json
import unittest
from pathlib import Path

from tests.conformance import bundle
from tests.conformance.bundle import (
    DIALECT,
    BundleManifest,
    SchemaEntry,
    load_bundle_manifest,
    parse_bundle_manifest,
    read_manifest_bytes,
)
from tests.conformance.types import SetupFailed

ROOT = Path(__file__).resolve().parents[2] / "definitions"


def _real():
    return json.loads(read_manifest_bytes(ROOT).decode("utf-8"))


def _encode(data):
    return json.dumps(data).encode("utf-8")


class RealManifestTests(unittest.TestCase):
    def test_real_manifest_parses(self):
        manifest = load_bundle_manifest(ROOT)
        self.assertIsInstance(manifest, BundleManifest)
        self.assertEqual(len(manifest.schemas), 7)
        self.assertEqual(len(manifest.document_roots), 6)
        self.assertEqual(manifest.bundle_revision, "2.0.0-draft.2")
        self.assertEqual(manifest.spec_version, "2.0.0-draft.2")
        self.assertTrue(manifest.id_base.endswith("/"))
        self.assertEqual(manifest.reserved_tokens, ("oasis",))
        for entry in manifest.schemas:
            self.assertIsInstance(entry, SchemaEntry)
            self.assertEqual(entry.id, manifest.id_base + entry.path)

    def test_field_names(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(SchemaEntry)],
            ["name", "path", "id", "sha256"],
        )
        self.assertEqual(
            [f.name for f in dataclasses.fields(BundleManifest)],
            ["bundle_revision", "spec_version", "id_base", "document_roots", "schemas", "reserved_tokens"],
        )
        self.assertEqual(bundle.MANIFEST_VERSION, "2.0.0")
        self.assertEqual(DIALECT, "https://json-schema.org/draft/2020-12/schema")


class CorruptionTests(unittest.TestCase):
    def assert_refused(self, mutate):
        data = copy.deepcopy(_real())
        mutate(data)
        with self.assertRaises(SetupFailed):
            parse_bundle_manifest(_encode(data), ROOT)

    def test_missing_key(self):
        self.assert_refused(lambda d: d.pop("spec_version"))

    def test_extra_key(self):
        self.assert_refused(lambda d: d.update(extra=1))

    def test_wrong_version(self):
        self.assert_refused(lambda d: d.update(manifest_version="9.9.9"))

    def test_wrong_dialect(self):
        self.assert_refused(lambda d: d.update(json_schema_dialect="https://json-schema.org/draft-07/schema"))

    def test_id_not_under_base(self):
        self.assert_refused(lambda d: d["schemas"][0].update({"$id": "https://example.invalid/common.schema.json"}))

    def test_duplicate_name(self):
        self.assert_refused(lambda d: d["schemas"][1].update(name="common"))

    def test_bad_digest_length(self):
        self.assert_refused(lambda d: d["schemas"][0].update(sha256="ab" * 31))

    def test_uppercase_hex(self):
        self.assert_refused(lambda d: d["schemas"][0].update(sha256=d["schemas"][0]["sha256"].upper()))

    def test_path_with_slash(self):
        def mutate(d):
            d["schemas"][0]["path"] = "sub/common.schema.json"
            d["schemas"][0]["$id"] = d["id_base"] + "sub/common.schema.json"

        self.assert_refused(mutate)

    def test_unknown_document_root(self):
        self.assert_refused(lambda d: d["document_roots"].append("nonesuch"))

    def test_reserved_tokens_not_a_list(self):
        self.assert_refused(lambda d: d["namespace_declaration"].update(reserved_tokens="oasis"))

    def test_byte_order_mark(self):
        with self.assertRaises(SetupFailed):
            parse_bundle_manifest(b"\xef\xbb\xbf" + read_manifest_bytes(ROOT), ROOT)

    def test_missing_manifest_file(self):
        with self.assertRaises(SetupFailed):
            read_manifest_bytes(ROOT / "nonexistent")


if __name__ == "__main__":
    unittest.main()
