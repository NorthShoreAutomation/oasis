"""The bundle in definitions/ is the frozen 2.0.0-draft.3 schema. Its bytes never change here."""
import hashlib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO / "definitions"

# OASIS 2.0.0-draft.3 bundle.
FROZEN_DIGESTS = {
    "asset.schema.json": "9909296b1049bb0a6f37948a5d431dae82a4920fbfdc8c260b4289809d123ae6",
    "bundle-manifest.json": "b7ff8f5f5e322b906a9d40ec2f49f892b47b72515432e68368538c2c66e420fb",
    "collection.schema.json": "0f22ddf5c8a37cd679c8d4173e8ea84cd85bbe392d45c279b5e367c653b3029e",
    "common.schema.json": "f4bf65a6c214d0782250300a53201a390832a8d0fe7f2bd97af84aafcad3defd",
    "metadata_definition.schema.json": "a251901b313761a2923adfa6bb16043a6400a5a0ef78ff0b95a8c161648aee2b",
    "package.schema.json": "3ad4d94baf5d6bb1d2d1deff729598cf63a06368a53fb485cddadd42cc16929f",
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
