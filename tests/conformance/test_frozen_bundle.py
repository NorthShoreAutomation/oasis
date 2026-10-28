"""The bundle in definitions/ is the frozen 2.0.0-draft.2 schema. Its bytes never change here."""
import hashlib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO / "definitions"

# OASIS 2.0.0-draft.2 bundle.
FROZEN_DIGESTS = {
    "annotation.schema.json": "fd838a855dcfa2c8101d3964f351addcf7f0a4b8a5ddf01a1f3af19949193e7a",
    "asset.schema.json": "77fa057c9de00aaf487d709e715e239c2ceedc6eaebadf317b5af68eb1a195e1",
    "bundle-manifest.json": "2f3af80fd1843180da249bb8b33b525f040328fbc57f36440d8fa1f9a36bfc30",
    "collection.schema.json": "8e29860c33e9f8fc0dc932c4634536e21c61aaf5120ba11bf85c93f3f6d8008a",
    "common.schema.json": "13ee03a268a0f68858107909e4b325201ded103c77910e6b72226cfc6f3581bd",
    "metadata_definition.schema.json": "e4c8e4961bd1069753cb7500e87b9119f38b31d6915bd9aea01cdec4e1f56094",
    "package.schema.json": "a2a7e533ccb35a526ffe4957fff00c01526e159364644165892313d0c1ea7954",
    "storage_location.schema.json": "b14937ed2e603a4369e40af6e4d1a631110c5096b2aa6151d8a160463fd6c349",
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
