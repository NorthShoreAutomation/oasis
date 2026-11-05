"""The record-stream engine of the semantic stage.

One engine runs the semantic checks for both package forms. A package
document gives its records in array order. A multi-file package gives them
one line at a time. Records arrive in ``REGISTRIES`` order: all storage
locations, then all metadata definitions, then all collections, then all
assets. A record out of that order raises ``ValueError``.

Storage locations, metadata definitions, and collections stay in memory,
first record per id, and ``ID-1`` reports each later record with that id at
once. Each record list has its own ids (``ID-2``). These lists are complete before the first asset, so a reference to
them resolves at once. Collections are held until their list is complete
(the first asset, or ``finish``), because a collection can name a later
collection: then each collection check, the ``member_of`` references of the
collections, and ``COL-4`` run.

The checks that need every asset keep their inputs in a SQLite store, so
memory does not grow with the number of assets: one row per asset (id,
location, and ``AssetSummary``), each deferred asset reference, each
deferred relationship, and each ``member_of`` entry with a position.
``finish`` runs these checks after the last asset: ``ID-1`` for assets,
asset references (``PKG-6``), relationship targets (``REL-4``, ``REL-6``,
and the target timeline), and ``COL-7`` positions.

"First" is add order. For a package document that is array order. A
record finding carries the ``member`` and ``line`` of its record.
"""

import sqlite3
from dataclasses import dataclass, field, replace

from tests.conformance import exact_json, semantic
from tests.conformance.semantic import REGISTRIES, AssetSummary, diagnostic, pointer, summarize_asset
from tests.conformance.types import Diagnostic

__all__ = ["Context", "PackageChecker", "Where"]

_STAGE = {registry: index for index, registry in enumerate(REGISTRIES)}
_ASSET_STAGE = _STAGE["assets"]

_PRAGMAS = (
    "PRAGMA journal_mode=OFF",
    "PRAGMA synchronous=OFF",
    "PRAGMA temp_store=FILE",
    "PRAGMA cache_size=-262144",
)

# ``ord`` counts records in add order; the first asset per id is the lowest
# ``ord``. ``target`` and ``id`` are NULL when the JSON value is not a
# string, so such a reference never resolves.
_TABLES = (
    "CREATE TABLE assets (ord INTEGER NOT NULL, id TEXT, member INTEGER, line INTEGER,"
    " base TEXT NOT NULL, summary TEXT NOT NULL)",
    "CREATE TABLE refs (member INTEGER, line INTEGER, path TEXT NOT NULL, target TEXT)",
    "CREATE TABLE relationships (member INTEGER, line INTEGER, rel_path TEXT NOT NULL,"
    " target TEXT, relationship TEXT NOT NULL, holder_timing TEXT)",
    "CREATE TABLE positions (collection TEXT, position INTEGER NOT NULL, member INTEGER, line INTEGER,"
    " path TEXT NOT NULL)",
)

# Made after the inserts, in ``finish``.
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS assets_by_id ON assets (id, ord)",
    "CREATE INDEX IF NOT EXISTS positions_by_key ON positions (collection, position)",
)

_LATER_ASSETS = (
    "SELECT a.member, a.line, a.base FROM assets AS a"
    " WHERE EXISTS (SELECT 1 FROM assets AS b WHERE b.id = a.id AND b.ord < a.ord)"
)
_UNRESOLVED_REFERENCES = (
    "SELECT r.member, r.line, r.path FROM refs AS r"
    " WHERE NOT EXISTS (SELECT 1 FROM assets AS a WHERE a.id = r.target)"
)
_RELATIONSHIP_TARGETS = (
    "SELECT r.member, r.line, r.rel_path, r.relationship, r.holder_timing,"
    " (SELECT a.summary FROM assets AS a WHERE a.id = r.target ORDER BY a.ord LIMIT 1)"
    " FROM relationships AS r"
)
_SHARED_POSITIONS = (
    "SELECT p.member, p.line, p.path FROM positions AS p"
    " WHERE EXISTS (SELECT 1 FROM positions AS q WHERE q.collection = p.collection"
    " AND q.position = p.position AND q.rowid <> p.rowid)"
)


@dataclass(frozen=True)
class Where:
    """The location of one record.

    ``member`` is the manifest index of its member file and ``line`` the
    1-based line, or both are ``None`` for a package document. ``base`` is
    the pointer of the record: inside a package document, ``/<list>/<i>``;
    on a line of a member file, the empty pointer.
    """

    member: int | None
    line: int | None
    base: str


@dataclass(eq=False)
class Context:
    """What the record checks resolve against (``PKG-6``), and where they defer the rest.

    ``storage_locations``, ``metadata_definitions``, and ``collections`` map
    an id to the first record with that id. ``namespaces`` holds the
    declared extension tokens (``EXT-2``). There is no list of assets: a
    reference to an asset, and the target checks of a relationship, wait in
    the store of the engine until every asset is known.
    """

    storage_locations: dict = field(default_factory=dict)
    metadata_definitions: dict = field(default_factory=dict)
    collections: dict = field(default_factory=dict)
    namespaces: frozenset = frozenset()
    _checker: "PackageChecker" = field(default=None, init=False, repr=False)

    def require(self, registry: str, target, path: str) -> None:
        """Defer the reference ``target`` at ``path`` to an asset; ``finish`` resolves it."""
        if registry != "assets":
            raise ValueError("only a reference to an asset is deferred")
        self._checker._defer_reference(target, path)

    def defer_relationship(self, relationship: dict, rel_path: str, holder_timing) -> None:
        """Defer the target checks of one relationship until every asset is known.

        ``holder_timing`` is the ``timing`` value that defines the holder
        timeline, or ``None``.
        """
        self._checker._defer_relationship(relationship, rel_path, holder_timing)


def _located(found, member, line):
    """Return the diagnostics ``found`` with ``member`` and ``line`` attached."""
    if member is None and line is None:
        return list(found)
    return [replace(d, member=member, line=line) for d in found]


def _order(d: Diagnostic):
    return (d.member is not None, d.member or 0, d.line or 0, d.path, d.code)


class PackageChecker:
    """Run the semantic stage on a stream of records.

    ``root`` is the package root: a package document, or the manifest file of
    a multi-file package. ``store_path`` names the SQLite store; the caller
    owns the file. The constructor runs the root checks: ``EXT-2``
    declarations, ``EXT-2`` on the slots outside the record lists, and,
    only when ``manifest.members`` is absent, ``PKG-3`` counts.
    """

    def __init__(self, root: dict, store_path: str = ":memory:"):
        manifest = root["manifest"]
        tokens = frozenset(d.get("token") for _i, d in semantic._items(manifest, "namespaces"))
        self.context = Context(namespaces=tokens)
        self.context._checker = self
        self._found = []
        self._found.extend(semantic._check_declarations(root, ""))
        self._found.extend(semantic._check_root_namespaces(root, "", self.context))
        if "members" not in manifest:
            self._found.extend(semantic._check_counts(root, ""))
        self._stage = 0
        self._ord = 0
        self._current = None
        self._held = []
        self._collections_complete = False
        self._db = sqlite3.connect(store_path)
        for statement in _PRAGMAS + _TABLES:
            self._db.execute(statement)

    def add(self, registry: str, record: dict, where: Where) -> None:
        """Check one record of ``registry`` at ``where``."""
        stage = _STAGE.get(registry)
        if stage is None:
            raise ValueError("not a record list")
        if stage < self._stage:
            raise ValueError("records must arrive in REGISTRIES order")
        self._stage = stage
        if stage == _ASSET_STAGE:
            self._complete_collections()
        self._ord += 1
        self._current = where
        context = self.context
        base = where.base
        found = semantic._check_namespaces_used(record, base, context)
        if registry == "assets":
            self._db.execute(
                "INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?)",
                (self._ord, _text(record.get("id")), where.member, where.line, base,
                 summarize_asset(record).to_text()),
            )
            found.extend(semantic.check_asset(record, base, context))
            found.extend(semantic._check_membership_references(record, base, context))
        else:
            records = getattr(context, registry)
            record_id = record.get("id")
            if record_id in records:
                found.append(diagnostic("ID_DUPLICATE", pointer(base, "id")))
            else:
                records[record_id] = record
            if registry == "storage_locations":
                found.extend(semantic.check_storage_location(record, base, context))
            elif registry == "metadata_definitions":
                found.extend(semantic.check_metadata_definition(record, base, context))
            else:
                self._held.append((record, where))
        if registry in ("assets", "collections"):
            found.extend(semantic._check_membership_repeats(record, base))
            for collection, position, path in semantic._membership_positions(record, base):
                self._db.execute(
                    "INSERT INTO positions VALUES (?, ?, ?, ?, ?)",
                    (_text(collection), position, where.member, where.line, path),
                )
        self._current = None
        self._found.extend(_located(found, where.member, where.line))

    def finish(self) -> list[Diagnostic]:
        """Run the checks that need every record; return every diagnostic, sorted.

        The order is ``(member is not None, member, line, path, code)``, so
        root findings come first, then the findings of each member file. For
        a package document that is ``(path, code)``.
        """
        self._complete_collections()
        self._db.commit()
        for statement in _INDEXES:
            self._db.execute(statement)
        found = list(self._found)
        for member, line, base in self._db.execute(_LATER_ASSETS):
            found.extend(_located([diagnostic("ID_DUPLICATE", pointer(base, "id"))], member, line))
        for member, line, path in self._db.execute(_UNRESOLVED_REFERENCES):
            found.extend(_located([diagnostic("REFERENCE_UNRESOLVED", path)], member, line))
        for member, line, rel_path, relationship, holder_timing, summary in self._db.execute(_RELATIONSHIP_TARGETS):
            if summary is None:
                target_found = [diagnostic("REFERENCE_UNRESOLVED", pointer(rel_path, "target"))]
            else:
                target_found = semantic.check_relationship_target(
                    exact_json.loads(relationship),
                    rel_path,
                    None if holder_timing is None else exact_json.loads(holder_timing),
                    AssetSummary.from_text(summary),
                )
            found.extend(_located(target_found, member, line))
        for member, line, path in self._db.execute(_SHARED_POSITIONS):
            found.extend(_located([diagnostic("POSITION_DUPLICATE", path)], member, line))
        found.sort(key=_order)
        return found

    def close(self) -> None:
        """Close the store. The caller removes an on-disk store file."""
        self._db.close()

    def _complete_collections(self):
        """Run the checks that need the whole collection list, once."""
        if self._collections_complete:
            return
        self._collections_complete = True
        held, self._held = self._held, []
        for record, where in held:
            self._current = where
            found = semantic.check_collection(record, where.base, self.context)
            found.extend(semantic._check_membership_references(record, where.base, self.context))
            self._found.extend(_located(found, where.member, where.line))
        self._current = None
        cycles = semantic._check_collection_cycles([(record, where.base) for record, where in held])
        for k, d in cycles:
            where = held[k][1]
            self._found.extend(_located([d], where.member, where.line))

    def _defer_reference(self, target, path):
        where = self._current
        self._db.execute(
            "INSERT INTO refs VALUES (?, ?, ?, ?)",
            (where.member, where.line, path, _text(target)),
        )

    def _defer_relationship(self, relationship, rel_path, holder_timing):
        where = self._current
        # The target checks never read description or extensions (REL-5 ignores them too).
        kept = {k: v for k, v in relationship.items() if k not in semantic._RELATIONSHIP_IGNORED}
        self._db.execute(
            "INSERT INTO relationships VALUES (?, ?, ?, ?, ?, ?)",
            (
                where.member, where.line, rel_path, _text(relationship.get("target")),
                exact_json.dumps(kept), None if holder_timing is None else exact_json.dumps(holder_timing),
            ),
        )


def _text(value):
    """Return ``value`` when it is a string, else ``None``: only a string id can match (``PKG-6``)."""
    return value if isinstance(value, str) else None
