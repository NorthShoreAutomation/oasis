"""Load and validate the offline 2.0 schema bundle manifest."""

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from tests.conformance.types import SetupFailed

MANIFEST_NAME = "bundle-manifest.json"
MANIFEST_VERSION = "2.0.0"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
_REVISION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TOP_KEYS = {
    "manifest_version",
    "bundle_revision",
    "spec_version",
    "json_schema_dialect",
    "id_base",
    "id_base_note",
    "document_roots",
    "schemas",
    "namespace_declaration",
}
_ENTRY_KEYS = {"name", "path", "$id", "sha256"}
_TOKEN = re.compile(r"[a-z][a-z0-9_-]*")


@dataclass(frozen=True)
class SchemaEntry:
    name: str
    path: str
    id: str
    sha256: str


@dataclass(frozen=True)
class BundleManifest:
    bundle_revision: str
    spec_version: str
    id_base: str
    document_roots: tuple[str, ...]
    schemas: tuple[SchemaEntry, ...]
    reserved_tokens: tuple[str, ...]


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
    if "/" in value:
        _fail("manifest path must be a plain file name")
    parts = PurePosixPath(value).parts
    if value != "/".join(parts) or any(p in ("", ".", "..") for p in parts):
        _fail("manifest path must stay inside the bundle")
    target = (root / value).resolve()
    if target.parent != root.resolve():
        _fail("manifest path leaves the bundle")
    if not target.is_file():
        _fail("schema file cannot be read")
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


def _text(data, key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value:
        _fail(f"{key} must be a nonempty string")
    return value


def parse_bundle_manifest(raw: bytes, root: Path) -> BundleManifest:
    """Verify manifest bytes for root, or raise SetupFailed."""
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
    spec_version = data["spec_version"]
    if not isinstance(spec_version, str) or not _REVISION.fullmatch(spec_version):
        _fail("spec_version is invalid")
    if data["json_schema_dialect"] != DIALECT:
        _fail("unsupported json_schema_dialect")
    id_base = data["id_base"]
    if not _is_absolute_uri(id_base) or not id_base.endswith("/"):
        _fail("id_base must be an absolute URI ending in a slash")
    if not isinstance(data["id_base_note"], str):
        _fail("id_base_note must be a string")

    schemas = data["schemas"]
    if not isinstance(schemas, list) or not schemas:
        _fail("schemas must be a nonempty array")
    entries = []
    names, paths, ids = set(), set(), set()
    for raw_entry in schemas:
        if not isinstance(raw_entry, dict) or set(raw_entry) != _ENTRY_KEYS:
            _fail("schema entry has the wrong shape")
        name = _text(raw_entry, "name")
        path = raw_entry["path"]
        _check_path(path, root)
        schema_id = raw_entry["$id"]
        if not _is_absolute_uri(schema_id) or schema_id != id_base + path:
            _fail("schema $id must equal id_base plus path")
        digest = raw_entry["sha256"]
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            _fail("sha256 must be 64 lowercase hexadecimal characters")
        if name in names or path in paths or schema_id in ids:
            _fail("duplicate schema name, path, or id")
        names.add(name)
        paths.add(path)
        ids.add(schema_id)
        entries.append(SchemaEntry(name, path, schema_id, digest))

    roots = data["document_roots"]
    if not isinstance(roots, list) or not roots or not all(isinstance(r, str) for r in roots):
        _fail("document_roots must be a nonempty array of names")
    if len(set(roots)) != len(roots) or not set(roots) <= names:
        _fail("document_roots must name distinct schema entries")

    declaration = data["namespace_declaration"]
    if not isinstance(declaration, dict):
        _fail("namespace_declaration must be an object")
    tokens = declaration.get("reserved_tokens")
    if not isinstance(tokens, list) or not all(isinstance(t, str) and _TOKEN.fullmatch(t) for t in tokens):
        _fail("reserved_tokens must be an array of tokens")
    if len(set(tokens)) != len(tokens):
        _fail("reserved_tokens must not repeat")
    return BundleManifest(revision, spec_version, id_base, tuple(roots), tuple(entries), tuple(tokens))
