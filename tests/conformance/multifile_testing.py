"""Test helpers that build a multi-file package on disk.

``write_package`` writes member files and then the manifest file, with the
sizes, checksums, and counts computed from the member bytes. A test
overrides any value to build a package that breaks one rule. The helpers
never read a package back: they only write.
"""

import gzip
import hashlib
import json
import zlib
from pathlib import Path

from tests.conformance.multifile import MANIFEST_NAME, RECORD_FOLDERS

__all__ = ["build_root", "member_entry", "write_package"]

SPEC_VERSION = "2.0.0-draft.4"


def member_entry(path: str, data: bytes, **overrides) -> dict:
    """Return the manifest entry for a member file with the bytes ``data``.

    ``record_type`` is the first segment of ``path``. ``count`` is the number
    of LF bytes in the content, after gzip decompression for a ``.gz`` path.
    Bytes that are not gzip under a ``.gz`` path are counted as stored, so a
    test can build a file whose compression does not match its name.
    ``size_bytes`` and ``sha256`` are those of ``data`` as stored. A keyword
    argument replaces the computed field of the same name.
    """
    text = data
    if path.endswith(".gz"):
        try:
            text = gzip.decompress(data)
        except (OSError, EOFError, zlib.error):
            pass
    entry = {
        "path": path,
        "record_type": path.split("/", 1)[0],
        "count": text.count(b"\n"),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    entry.update(overrides)
    return entry


def _merge(base: dict, override: dict) -> dict:
    """Return ``base`` with ``override`` merged in. A nested dict merges; any other value replaces."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_root(entries: list, root_overrides: dict | None = None) -> dict:
    """Return the manifest root for the member ``entries``.

    ``manifest.counts`` has all four lists. Each is the sum of the ``count``
    of the entries of that ``record_type``. ``root_overrides`` merges into the
    root: a nested dict merges key by key, and any other value replaces.
    """
    counts = {name: 0 for name in RECORD_FOLDERS}
    for entry in entries:
        counts[entry["record_type"]] += entry["count"]
    root = {
        "type": "package",
        "spec_version": SPEC_VERSION,
        "id": "pkg-multifile-test",
        "manifest": {
            "producer": {"name": "test-exporter", "version": "0.1.0"},
            "produced_at": "2026-11-02T18:00:00Z",
            "counts": counts,
            "namespaces": [],
            "members": list(entries),
        },
    }
    return _merge(root, root_overrides or {})


def write_package(
    directory,
    members: dict,
    root_overrides: dict | None = None,
    *,
    entry_overrides: dict | None = None,
    skip=(),
) -> Path:
    """Write a multi-file package into ``directory`` and return the manifest path.

    ``members`` maps a member path to its bytes. The helper writes each file,
    builds one manifest entry per file in dict order (see ``member_entry``),
    and writes ``oasis-package.json`` last.

    - ``root_overrides`` merges into the root (see ``build_root``).
    - ``entry_overrides`` maps a member path to a dict of entry fields that
      replace the computed ones, for example a wrong ``size_bytes``.
    - ``skip`` names member paths that get an entry but no file.
    """
    directory = Path(directory)
    overrides = entry_overrides or {}
    skipped = set(skip)
    entries = []
    for path, data in members.items():
        if path not in skipped:
            target = directory / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        entries.append(member_entry(path, data, **overrides.get(path, {})))
    manifest = directory / MANIFEST_NAME
    manifest.write_text(json.dumps(build_root(entries, root_overrides), indent=2) + "\n", encoding="utf-8")
    return manifest
