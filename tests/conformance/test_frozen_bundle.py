"""The bundle in definitions/ is the 2.0.0-draft.4 schema. These digests pin its current bytes; any schema change updates them."""
import hashlib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO / "definitions"

# OASIS 2.0.0-draft.4 bundle.
FROZEN_DIGESTS = {
    "asset.schema.json": "9909296b1049bb0a6f37948a5d431dae82a4920fbfdc8c260b4289809d123ae6",
    "bundle-manifest.json": "4c7e5b3ce2f6a341c06e3c22c8a643af8e33b50e3e737242fb4569a0bcac5673",
    "collection.schema.json": "be1ad31393363fa0839fbf4ccba497579a754776b697b75b54a9c901632aaaa9",
    "common.schema.json": "18d3eb2a7053770c6a6c875f3cb395595796b576718ec87ef899a84dfefdffe8",
    "metadata_definition.schema.json": "a251901b313761a2923adfa6bb16043a6400a5a0ef78ff0b95a8c161648aee2b",
    "package.schema.json": "21a30c79c1bb4dcc86dbf7add5ba1e43d34a73521026d296a4fb9c972d80b3d8",
    "storage_location.schema.json": "42d5f6df84264ac918061613dddd075aa1b5746653d1d2612f6f8b8d9029e56e",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FrozenBundleTest(unittest.TestCase):
    def test_definitions_match_published_digests(self):
        for name, digest in FROZEN_DIGESTS.items():
            with self.subTest(name=name):
                self.assertEqual(sha256(DEFINITIONS / name), digest)

    def test_definitions_has_no_other_schema_or_manifest(self):
        names = {p.name for p in DEFINITIONS.glob("*.json")}
        self.assertEqual(names, set(FROZEN_DIGESTS))
