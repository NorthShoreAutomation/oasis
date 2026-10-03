"""Load and validate an offline schema bundle manifest."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from tests.conformance.types import SetupFailed

MANIFEST_NAME = "bundle-manifest.json"
MANIFEST_VERSION = "1.0.0"
_REVISION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TOP_KEYS = {"manifest_version", "bundle_revision", "schemas"}
_ENTRY_KEYS = {"name", "path", "sha256", "id", "base_uri", "aliases"}


@dataclass(frozen=True)
class SchemaEntry:
    name: str
    path: str
    sha256: str
    id: "str | None"
    base_uri: str
    aliases: tuple


@dataclass(frozen=True)
class BundleManifest:
    manifest_version: str
    bundle_revision: str
    schemas: tuple


def _fail(message: str):
    raise SetupFailed(message)


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            _fail("manifest has a duplicate object key")
        out[key] = value
    return out


def _is_absolute_uri(value) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return bool(parts.scheme) and bool(parts.netloc) and not parts.fragment


def _check_path(value, root: Path) -> Path:
    if not isinstance(value, str) or not value:
        _fail("manifest path must be a nonempty string")
    if "\\" in value or "\x00" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        _fail("manifest path must be bundle-relative")
    parts = PurePosixPath(value).parts
    if value != "/".join(parts) or any(p in ("", ".", "..") for p in parts):
        _fail("manifest path must stay inside the bundle")
    target = (root / value).resolve()
    if root.resolve() not in target.parents:
        _fail("manifest path leaves the bundle")
    return target


def read_manifest_bytes(root: Path) -> bytes:
    """Read the raw bytes of root/bundle-manifest.json, or raise SetupFailed."""
    try:
        return (Path(root) / MANIFEST_NAME).read_bytes()
    except OSError:
        _fail("bundle manifest is missing or is not valid JSON")


def load_bundle_manifest(root: Path) -> BundleManifest:
    """Read root/bundle-manifest.json and verify every rule, or raise SetupFailed."""
    return parse_bundle_manifest(read_manifest_bytes(root), root)


def parse_bundle_manifest(raw: bytes, root: Path) -> BundleManifest:
    """Verify manifest bytes for root, including every schema file digest, or raise SetupFailed."""
    root = Path(root)
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except SetupFailed:
        raise
    except (UnicodeDecodeError, ValueError):
        _fail("bundle manifest is missing or is not valid JSON")
    if not isinstance(data, dict) or set(data) != _TOP_KEYS:
        _fail("bundle manifest has the wrong top-level shape")
    if data["manifest_version"] != MANIFEST_VERSION:
        _fail("unsupported manifest_version")
    revision = data["bundle_revision"]
    if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
        _fail("bundle_revision is invalid")
    schemas = data["schemas"]
    if not isinstance(schemas, list) or not schemas:
        _fail("schemas must be a nonempty array")

    entries = []
    names = set()
    identifiers = set()
    for raw_entry in schemas:
        if not isinstance(raw_entry, dict) or set(raw_entry) != _ENTRY_KEYS:
            _fail("schema entry has the wrong shape")
        name = raw_entry["name"]
        if not isinstance(name, str) or not name:
            _fail("schema name must be a nonempty string")
        if name in names:
            _fail("duplicate schema name")
        names.add(name)
        target = _check_path(raw_entry["path"], root)
        digest = raw_entry["sha256"]
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            _fail("sha256 must be 64 lowercase hexadecimal characters")
        try:
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError:
            _fail("schema file cannot be read")
        if actual != digest:
            _fail("schema digest does not match file bytes")
        schema_id = raw_entry["id"]
        base_uri = raw_entry["base_uri"]
        if not _is_absolute_uri(base_uri):
            _fail("base_uri must be an absolute URI")
        if schema_id is not None and schema_id != base_uri:
            _fail("base_uri must equal a non-null id")
        aliases = raw_entry["aliases"]
        if not isinstance(aliases, list) or not all(_is_absolute_uri(a) for a in aliases):
            _fail("aliases must be an array of absolute URIs")
        for identifier in [base_uri, *aliases]:
            if identifier in identifiers:
                _fail("identifier collision between bases and aliases")
            identifiers.add(identifier)
        entries.append(SchemaEntry(name, raw_entry["path"], digest, schema_id, base_uri, tuple(aliases)))
    return BundleManifest(data["manifest_version"], revision, tuple(entries))
