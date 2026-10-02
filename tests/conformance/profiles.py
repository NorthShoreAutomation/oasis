"""The exchange-1x profile: entry point routing, version routing, and outcomes.

``validate_profile`` applies the outcome table in CONTRACT.md "Input,
formats, and outcome order" to one strict-parsed input. It reads only the
parsed document tree and the caller reference context. It never opens files
or network resources and never mutates the document.

Semantic rules live in ``RULES``. Each rule is called as
``rule(name, value, reference_context)`` and returns an iterable of
``Diagnostic``. Rules run only for selected, structurally valid input.
"""

from decimal import Decimal

from tests.conformance.corpus import DIAGNOSTIC_SEVERITY
from tests.conformance.types import Diagnostic, ProfileOutcome, SetupFailed

LEGACY_PROFILE = "legacy-1x"
EXCHANGE_PROFILE = "exchange-1x"

INTERCHANGE_ENTRY_POINTS = frozenset({
    "asset.schema.json",
    "asset_batch_import.schema.json",
    "collection.schema.json",
    "collection_batch_import.schema.json",
    "metadata_set.schema.json",
    "storage_location.schema.json",
    "temporal_annotation.schema.json",
})
EXCLUDED_ENTRY_POINTS = frozenset({"migration-report-output.schema.json"})

ACCEPTED_VERSIONS = frozenset({"1.0.0", "1.1.0", "1.1.1", "1.2.0-draft.1"})

# Entry points whose root object declares a schema_version selector.
_ROOT_SELECTOR_ENTRY_POINTS = INTERCHANGE_ENTRY_POINTS - {"temporal_annotation.schema.json"}
# Batch entry points: the array whose standalone records declare selectors.
_BATCH_ARRAYS = {
    "asset_batch_import.schema.json": "assets",
    "collection_batch_import.schema.json": "collections",
}

# Contract whitespace for blank-identity checks: ASCII only.
WHITESPACE = " \t\r\n\f\v"

_MESSAGES = {
    "PROFILE_UNSUPPORTED": "The selected profile does not include this entry point.",
    "VERSION_UNSUPPORTED": "The declared interchange version cannot route under this profile.",
    "IDENTITY_UNUSABLE": "An explicit identity is empty or only whitespace.",
    "IDENTITY_DUPLICATE": "A top-level batch repeats its primary ID.",
    "REFERENCE_UNRESOLVED": "A collection reference cannot resolve within explicit context.",
    "MEMBERSHIP_UNINTERPRETED": "Embedded membership has no selected portable interpretation.",
    "COLLECTION_CYCLE": "A collection parent edge belongs to a known batch cycle or self-loop.",
    "SIZE_UNUSABLE": "A declared file size is negative.",
    "INTEGRITY_UNVERIFIED": "No usable expected file checksum is present.",
    "CHECKSUM_UNINTERPRETED": "A checksum string lacks defined verification context.",
    "COMPLETENESS_UNVERIFIED": "Source export completeness has not been established.",
    "VALUE_SEMANTICS_UNSPECIFIED": "A recorded metadata value lacks the selected representation contract.",
    "CONNECTION_DATA_UNREVIEWED": "Nonempty connection data needs an approved policy.",
    "RIGHTS_UNSUPPORTED": "Nonempty declared restrictions cannot be mapped by this profile.",
    "RATE_UNUSABLE": "A supplied annotation frame rate is zero.",
    "RANGE_REVERSED": "A complete numeric timing pair ends before it starts.",
    "TIMING_UNINTERPRETED": "Annotation timing meaning or conversion remains unsupported.",
}


def diagnostic(code: str, path: str, message: str) -> Diagnostic:
    """Build a diagnostic whose severity comes from the catalog."""
    return Diagnostic(code, path, DIAGNOSTIC_SEVERITY[code], message)


def check_reference_context(context) -> None:
    """Raise SetupFailed unless context has exactly asset_ids and collection_ids as nonblank string lists."""
    if not isinstance(context, dict) or set(context) != {"asset_ids", "collection_ids"}:
        raise SetupFailed("reference context must have exactly asset_ids and collection_ids")
    for key in ("asset_ids", "collection_ids"):
        ids = context[key]
        if not isinstance(ids, list) or not all(isinstance(i, str) and i.strip(WHITESPACE) for i in ids):
            raise SetupFailed(f"reference context {key} must be a list of nonblank strings")


def _selector_paths(name: str, value):
    """Yield (pointer, selector value) for each declared selector present."""
    if name not in _ROOT_SELECTOR_ENTRY_POINTS or not isinstance(value, dict):
        return
    if "schema_version" in value:
        yield "/schema_version", value["schema_version"]
    array = _BATCH_ARRAYS.get(name)
    items = value.get(array) if array else None
    if isinstance(items, list):
        for index, item in enumerate(items):
            if isinstance(item, dict) and "schema_version" in item:
                yield f"/{array}/{index}/schema_version", item["schema_version"]


def _version_diagnostics(name: str, value) -> list:
    return [
        diagnostic("VERSION_UNSUPPORTED", path, _MESSAGES["VERSION_UNSUPPORTED"])
        for path, label in _selector_paths(name, value)
        if not (isinstance(label, str) and label in ACCEPTED_VERSIONS)
    ]


def _objects(parent, key):
    """Yield (index, item) for the object items of ``parent[key]`` when it is an array."""
    items = parent.get(key)
    if isinstance(items, list):
        for index, item in enumerate(items):
            if isinstance(item, dict):
                yield index, item


def _asset_locations(pointer: str, asset: dict):
    yield "A", pointer, asset
    stack = [(f"{pointer}/files/{i}", f) for i, f in reversed(list(_objects(asset, "files")))]
    while stack:
        file_pointer, file = stack.pop()
        yield "F", file_pointer, file
        storage = file.get("storage_location")
        if isinstance(storage, dict):
            yield "S", f"{file_pointer}/storage_location", storage
        stack.extend(
            (f"{file_pointer}/derivatives/{i}", d) for i, d in reversed(list(_objects(file, "derivatives")))
        )
    for i, item in _objects(asset, "metadata_sets"):
        yield "M", f"{pointer}/metadata_sets/{i}", item
    for i, item in _objects(asset, "collections"):
        yield from _collection_locations(f"{pointer}/collections/{i}", item)
    for i, item in _objects(asset, "temporal_annotations"):
        yield "T", f"{pointer}/temporal_annotations/{i}", item


def _collection_locations(pointer: str, collection: dict):
    yield "C", pointer, collection
    storage = collection.get("parent_storage")
    if isinstance(storage, dict):
        yield "S", f"{pointer}/parent_storage", storage
    for i, item in _objects(collection, "metadata_sets"):
        yield "M", f"{pointer}/metadata_sets/{i}", item


def entity_locations(name: str, value):
    """Yield (template, pointer, object) for each entity location of the entry point.

    Templates are the CONTRACT.md "Rule locations" letters ``A``, ``C``,
    ``F``, ``S``, ``M``, and ``T``. Only schema-declared relationships are
    followed, so opaque and undeclared content is never entered. Values whose
    type differs from the schema declaration are skipped.
    """
    if not isinstance(value, dict):
        return
    if name == "asset.schema.json":
        yield from _asset_locations("", value)
    elif name == "asset_batch_import.schema.json":
        for i, item in _objects(value, "assets"):
            yield from _asset_locations(f"/assets/{i}", item)
    elif name == "collection.schema.json":
        yield from _collection_locations("", value)
    elif name == "collection_batch_import.schema.json":
        for i, item in _objects(value, "collections"):
            yield from _collection_locations(f"/collections/{i}", item)
    elif name == "storage_location.schema.json":
        yield "S", "", value
    elif name == "metadata_set.schema.json":
        yield "M", "", value
    elif name == "temporal_annotation.schema.json":
        yield "T", "", value


def _usable(identity) -> bool:
    return isinstance(identity, str) and bool(identity.strip(WHITESPACE))


_IDENTITY_KEYS = {"A": "asset_id", "C": "collection_id", "S": "storage_id", "M": "set_id", "T": "source_id"}


def identity_rule(name, value, reference_context):
    """IDENTITY_UNUSABLE at each explicit identity that is empty or only whitespace."""
    for template, pointer, entity in entity_locations(name, value):
        key = _IDENTITY_KEYS.get(template)
        if key is None:
            continue
        candidates = [(f"{pointer}/{key}", entity.get(key))] if key in entity else []
        if template == "M":
            candidates += [(f"{pointer}/fields/{i}/name", field["name"])
                           for i, field in _objects(entity, "fields") if "name" in field]
        for path, identity in candidates:
            if isinstance(identity, str) and not _usable(identity):
                yield diagnostic("IDENTITY_UNUSABLE", path, _MESSAGES["IDENTITY_UNUSABLE"])


_BATCH_IDENTITY_KEYS = {
    "asset_batch_import.schema.json": ("assets", "asset_id"),
    "collection_batch_import.schema.json": ("collections", "collection_id"),
}


def duplicate_rule(name, value, reference_context):
    """IDENTITY_DUPLICATE at each repeat of a top-level batch primary ID after the first."""
    if name not in _BATCH_IDENTITY_KEYS or not isinstance(value, dict):
        return
    array, key = _BATCH_IDENTITY_KEYS[name]
    seen = set()
    for i, record in _objects(value, array):
        identity = record.get(key)
        if not isinstance(identity, str):
            continue
        if identity in seen:
            yield diagnostic("IDENTITY_DUPLICATE", f"/{array}/{i}/{key}", _MESSAGES["IDENTITY_DUPLICATE"])
        seen.add(identity)


def _partition_ids(identities):
    """Split explicit string IDs of one input list into (included, excluded).

    Included IDs are usable and occur exactly once. Excluded IDs are
    unusable or repeated; caller context never restores them.
    """
    counts = {}
    for identity in identities:
        if isinstance(identity, str):
            counts[identity] = counts.get(identity, 0) + 1
    included = {i for i, n in counts.items() if n == 1 and _usable(i)}
    return included, set(counts) - included


def _known(included, excluded, context_ids):
    return (included | set(context_ids)) - excluded


class _Scope:
    """Collections resolved together, with their known IDs."""

    def __init__(self, collections, known_assets, known_collections, included, batch_graph):
        self.collections = collections  # list of (pointer, collection object)
        self.known_assets = known_assets
        self.known_collections = known_collections
        self.included = included  # usable, nonexcluded collection IDs of this input list
        self.batch_graph = batch_graph  # multi-record cycles apply


def _embedded_scope(pointer, asset, known_assets, context):
    collections = [(f"{pointer}/collections/{i}", c) for i, c in _objects(asset, "collections")]
    included, excluded = _partition_ids(c.get("collection_id") for _, c in collections)
    return _Scope(collections, known_assets, _known(included, excluded, context["collection_ids"]),
                  included, False)


def _collection_scopes(name, value, context):
    """Yield the reference scopes for the entry point, per CONTRACT.md "Identity and relationships"."""
    if not isinstance(value, dict):
        return
    if name == "asset.schema.json":
        own = value.get("asset_id")
        known_assets = set(context["asset_ids"]) | ({own} if _usable(own) else set())
        yield _embedded_scope("", value, known_assets, context)
    elif name == "asset_batch_import.schema.json":
        assets = list(_objects(value, "assets"))
        included, excluded = _partition_ids(a.get("asset_id") for _, a in assets)
        known_assets = _known(included, excluded, context["asset_ids"])
        for i, asset in assets:
            yield _embedded_scope(f"/assets/{i}", asset, known_assets, context)
    elif name == "collection.schema.json":
        own = value.get("collection_id")
        included = {own} if _usable(own) else set()
        yield _Scope([("", value)], set(context["asset_ids"]), included | set(context["collection_ids"]),
                     included, False)
    elif name == "collection_batch_import.schema.json":
        collections = [(f"/collections/{i}", c) for i, c in _objects(value, "collections")]
        included, excluded = _partition_ids(c.get("collection_id") for _, c in collections)
        yield _Scope(collections, set(context["asset_ids"]),
                     _known(included, excluded, context["collection_ids"]), included, True)


def reference_rule(name, value, reference_context):
    """REFERENCE_UNRESOLVED for unknown parents and string members; MEMBERSHIP_UNINTERPRETED otherwise."""
    for scope in _collection_scopes(name, value, reference_context):
        for pointer, collection in scope.collections:
            parent = collection.get("parent")
            if isinstance(parent, str) and parent not in scope.known_collections:
                yield diagnostic("REFERENCE_UNRESOLVED", f"{pointer}/parent", _MESSAGES["REFERENCE_UNRESOLVED"])
            members = collection.get("assets")
            if not isinstance(members, list):
                continue
            for i, member in enumerate(members):
                path = f"{pointer}/assets/{i}"
                if not isinstance(member, str):
                    yield diagnostic("MEMBERSHIP_UNINTERPRETED", path, _MESSAGES["MEMBERSHIP_UNINTERPRETED"])
                elif member not in scope.known_assets:
                    yield diagnostic("REFERENCE_UNRESOLVED", path, _MESSAGES["REFERENCE_UNRESOLVED"])


def _cycle_ids(parents: dict) -> set:
    """IDs on a cycle of a graph where each ID has at most one parent edge."""
    on_cycle, done = set(), set()
    for start in parents:
        path, position = [], {}
        node = start
        while node in parents and node not in done and node not in position:
            position[node] = len(path)
            path.append(node)
            node = parents[node]
        if node in position:
            on_cycle.update(path[position[node]:])
        done.update(path)
    return on_cycle


def cycle_rule(name, value, reference_context):
    """COLLECTION_CYCLE at each included parent edge on a batch cycle or self-loop."""
    for scope in _collection_scopes(name, value, reference_context):
        edges = {}
        for pointer, collection in scope.collections:
            own, parent = collection.get("collection_id"), collection.get("parent")
            if own in scope.included and parent in scope.included and (scope.batch_graph or parent == own):
                edges[own] = (pointer, parent)
        on_cycle = _cycle_ids({own: parent for own, (_, parent) in edges.items()})
        for own in on_cycle:
            yield diagnostic("COLLECTION_CYCLE", f"{edges[own][0]}/parent", _MESSAGES["COLLECTION_CYCLE"])


def file_rule(name, value, reference_context):
    """SIZE_UNUSABLE, INTEGRITY_UNVERIFIED, and CHECKSUM_UNINTERPRETED at each file."""
    for template, pointer, file in entity_locations(name, value):
        if template != "F":
            continue
        size = file.get("size")
        if isinstance(size, (int, Decimal)) and not isinstance(size, bool) and size < 0:
            yield diagnostic("SIZE_UNUSABLE", f"{pointer}/size", _MESSAGES["SIZE_UNUSABLE"])
        checksum = file.get("checksum")
        if checksum is None or checksum == "":
            yield diagnostic("INTEGRITY_UNVERIFIED", pointer, _MESSAGES["INTEGRITY_UNVERIFIED"])
        elif isinstance(checksum, str):
            yield diagnostic("CHECKSUM_UNINTERPRETED", f"{pointer}/checksum", _MESSAGES["CHECKSUM_UNINTERPRETED"])


def completeness_rule(name, value, reference_context):
    """COMPLETENESS_UNVERIFIED at the root of either batch entry point."""
    if name in _BATCH_ARRAYS:
        yield diagnostic("COMPLETENESS_UNVERIFIED", "", _MESSAGES["COMPLETENESS_UNVERIFIED"])


def metadata_value_rule(name, value, reference_context):
    """VALUE_SEMANTICS_UNSPECIFIED at each present metadata field value."""
    for template, pointer, metadata_set in entity_locations(name, value):
        if template != "M":
            continue
        for i, field in _objects(metadata_set, "fields"):
            if "value" in field:
                yield diagnostic("VALUE_SEMANTICS_UNSPECIFIED", f"{pointer}/fields/{i}/value",
                                 _MESSAGES["VALUE_SEMANTICS_UNSPECIFIED"])


def _nonempty(item) -> bool:
    return isinstance(item, (dict, list, str)) and len(item) > 0


def connection_rule(name, value, reference_context):
    """CONNECTION_DATA_UNREVIEWED at each nonempty storage connection_details object."""
    for template, pointer, storage in entity_locations(name, value):
        if template == "S" and isinstance(storage.get("connection_details"), dict) \
                and storage["connection_details"]:
            yield diagnostic("CONNECTION_DATA_UNREVIEWED", f"{pointer}/connection_details",
                             _MESSAGES["CONNECTION_DATA_UNREVIEWED"])


_RIGHTS_KEYS = {"A": "rights_information", "C": "permissions", "S": "security"}


def rights_rule(name, value, reference_context):
    """RIGHTS_UNSUPPORTED at each nonempty declared rights property."""
    for template, pointer, entity in entity_locations(name, value):
        key = _RIGHTS_KEYS.get(template)
        if key is not None and _nonempty(entity.get(key)):
            yield diagnostic("RIGHTS_UNSUPPORTED", f"{pointer}/{key}", _MESSAGES["RIGHTS_UNSUPPORTED"])


def _number(item) -> bool:
    return isinstance(item, (int, Decimal)) and not isinstance(item, bool)


_TIMING_PAIRS = (("start_frame", "end_frame"), ("start_seconds", "end_seconds"))
_TIMECODE_KEYS = ("start_timecode", "end_timecode")


def _timing_uninterpreted(annotation: dict) -> bool:
    """True when any CONTRACT.md "Metadata and annotations" timing warning condition holds."""
    frames = "start_frame" in annotation or "end_frame" in annotation
    seconds = "start_seconds" in annotation or "end_seconds" in annotation
    if frames and seconds:
        return True
    if any(key in annotation for key in _TIMECODE_KEYS):
        return True
    if annotation.get("is_point_marker") is True:
        if not any(key in annotation for key in ("start_frame", "start_seconds", "start_timecode")):
            return True
    elif not any(_number(annotation.get(start)) and _number(annotation.get(end)) for start, end in _TIMING_PAIRS):
        return True
    rate = annotation.get("frame_rate")
    return frames and not (_number(rate) and rate > 0)


def timing_rule(name, value, reference_context):
    """RATE_UNUSABLE, RANGE_REVERSED, and at most one TIMING_UNINTERPRETED per annotation."""
    for template, pointer, annotation in entity_locations(name, value):
        if template != "T":
            continue
        rate = annotation.get("frame_rate")
        if _number(rate) and rate == 0:
            yield diagnostic("RATE_UNUSABLE", f"{pointer}/frame_rate", _MESSAGES["RATE_UNUSABLE"])
        for start, end in _TIMING_PAIRS:
            first, last = annotation.get(start), annotation.get(end)
            if _number(first) and _number(last) and last < first:
                yield diagnostic("RANGE_REVERSED", f"{pointer}/{end}", _MESSAGES["RANGE_REVERSED"])
        if _timing_uninterpreted(annotation):
            yield diagnostic("TIMING_UNINTERPRETED", pointer, _MESSAGES["TIMING_UNINTERPRETED"])


# Semantic rules, appended by later tasks.
RULES = [
    identity_rule, duplicate_rule, reference_rule, cycle_rule,
    file_rule, completeness_rule, metadata_value_rule, connection_rule, rights_rule,
    timing_rule,
]


def validate_profile(name: str, document, profile: str, *, structural: str, reference_context) -> ProfileOutcome:
    """Return the profile outcome for one strict-parsed input.

    ``name`` is the selected entry point and ``structural`` is ``valid`` or
    ``invalid``. Unknown profiles, unknown entry points, and malformed
    reference context raise ``SetupFailed``.
    """
    if profile not in (LEGACY_PROFILE, EXCHANGE_PROFILE):
        raise SetupFailed("profile is not known")
    if name not in INTERCHANGE_ENTRY_POINTS | EXCLUDED_ENTRY_POINTS:
        raise SetupFailed("entry point is not known")
    if structural not in ("valid", "invalid"):
        raise ValueError("structural must be valid or invalid")
    check_reference_context(reference_context)
    if profile == LEGACY_PROFILE:
        return ProfileOutcome("not-applied", "complete", ())
    if name in EXCLUDED_ENTRY_POINTS:
        return ProfileOutcome(
            "unsupported", "unsupported",
            (diagnostic("PROFILE_UNSUPPORTED", "", _MESSAGES["PROFILE_UNSUPPORTED"]),),
        )
    value = document.value
    unsupported = _version_diagnostics(name, value)
    if unsupported:
        return ProfileOutcome("unsupported", "unsupported", tuple(unsupported))
    if structural == "invalid":
        return ProfileOutcome("selected", "blocked", ())
    diagnostics = tuple(d for rule in RULES for d in rule(name, value, reference_context))
    blocked = any(DIAGNOSTIC_SEVERITY[d.code] == "error" for d in diagnostics)
    return ProfileOutcome("selected", "blocked" if blocked else "complete", diagnostics)


def exchange_checker(case, document, structural: str) -> ProfileOutcome:
    """Adapt ``validate_profile`` to ``results.ProfileChecker``."""
    return validate_profile(
        case.schema_name, document, case.profile,
        structural=structural, reference_context=case.reference_context,
    )
