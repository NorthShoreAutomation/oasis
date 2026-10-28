"""Semantic checks of the 2.0 contract that a schema cannot express (Appendix B).

The diagnostic catalog lives here and nowhere else. Every check reads the
exact-number tree from ``strict_json`` and never changes it (``DOC-3``).
Integer-typed fields may be spelled as integral decimals (``DOC-2``), so every
check converts them with ``as_int`` before arithmetic, comparison, or use as a
key. Time arithmetic is exact (``timecode``).

Precondition: the tree passed structural validation against the bundle
entry point of its routed record type. The checks rely on the schema for field
presence and JSON types and do not repeat it.

Record checks take ``(record, path, context)``. ``path`` is the RFC 6901
pointer of the record in the document. ``context`` is ``None`` for a
standalone record: then nothing is resolved, and what needs another record is
reported with a warning (``TIMELINE_UNAVAILABLE``, ``DEFINITION_UNAVAILABLE``).
Inside a package, ``context`` is the ``PackageContext`` built by
``check_package``: references resolve under ``PKG-6`` and the warnings above
give way to the checks they stand for.

Messages are fixed catalog text and never carry an input value, and no
pointer ever carries an extension key.
"""

from dataclasses import dataclass
from decimal import Decimal
from math import gcd

from tests.conformance.formats import check_date, check_date_time
from tests.conformance.timecode import LABEL_RATES, derive_label, nearest_frame
from tests.conformance.types import Diagnostic

__all__ = [
    "CATALOG",
    "PackageContext",
    "as_int",
    "check",
    "check_annotation",
    "check_asset",
    "check_collection",
    "check_metadata_definition",
    "check_package",
    "check_storage_location",
    "check_value_shape",
    "diagnostic",
    "json_equal",
    "pointer",
    "resolve",
]

# code: (rule, severity, message). The contract catalog, row by row.
CATALOG = {
    "INPUT_INVALID": ("DOC-1", "error", "Input bytes cannot be parsed under the strict JSON policy."),
    "TYPE_UNSUPPORTED": ("UNS-1", "error", "The document root has no supported record type."),
    "VERSION_UNSUPPORTED": ("REC-4, UNS-1", "error", "The declared spec_version is not supported by this checker."),
    "COUNT_MISMATCH": ("PKG-3", "error", "A declared count does not equal the length of its array."),
    "REFERENCE_UNRESOLVED": ("PKG-6", "error", "A reference does not resolve in a complete registry."),
    "REFERENCE_UNRESOLVED_PARTIAL": ("PKG-6", "warning", "A reference does not resolve in a partial registry."),
    "ID_DUPLICATE": ("ID-1", "error", "A record id is repeated within its record type."),
    "NESTED_ID_DUPLICATE": ("ID-4", "error", "A nested id is repeated within its record."),
    "SNAPSHOT_MISMATCH": ("ID-6", "error", "A collection snapshot differs from the registry record."),
    "RATE_NOT_LOWEST_TERMS": ("TIME-2", "error", "A rate is not written in lowest terms."),
    "RANGE_NOT_INCREASING": ("TIME-4", "error", "A range does not end after it starts."),
    "TIMELINE_UNDECLARED": ("TIME-5, TIME-12", "error", "A frame field belongs to a timeline with no time base."),
    "TIMELINE_UNAVAILABLE": (
        "TIME-12, ANN-3",
        "warning",
        "The owning asset is not in the document, so timing agreement was not checked.",
    ),
    "SECONDS_DISAGREE": ("TIME-7", "error", "A derived seconds value names a different frame."),
    "TIMECODE_DISAGREE": (
        "TIME-7, TIME-8",
        "error",
        "A timecode label differs from the label derived from the frame value.",
    ),
    "FRAME_OUT_OF_BOUNDS": ("TIME-9", "error", "A frame position lies outside the asset duration."),
    "SEQUENCE_RANGE_EMPTY": ("GRP-3", "error", "An image sequence range does not end after it starts."),
    "TRACK_DUPLICATE": ("GRP-4", "error", "A file group repeats a track type and index pair."),
    "FILE_REFERENCE_UNRESOLVED": ("GRP-4", "error", "A file group member names a file that is not in the asset."),
    "SEGMENT_INDEX_MISSING": (
        "GRP-6",
        "error",
        "A file group member shares a track type and index pair with a segment but has no segment_index.",
    ),
    "SEGMENT_INDEX_DUPLICATE": (
        "GRP-6",
        "error",
        "A file group repeats a segment_index within one track type and index pair.",
    ),
    "SEGMENT_OUT_OF_ORDER": ("GRP-6", "error", "File group segments are not in ascending segment_index order."),
    "SEGMENT_GAP": (
        "GRP-6",
        "error",
        "A complete file group has a gap in the segment_index values of one track type and index pair.",
    ),
    "ORDINAL_DUPLICATE": ("VER-2", "error", "Two versions share an ordinal."),
    "VERSION_REFERENCE_UNRESOLVED": ("VER-3", "error", "A version reference names no version in the asset."),
    "VERSION_WITHOUT_VERSIONS": ("VER-3", "error", "A version reference appears on an asset with no versions."),
    "RELATIONSHIP_SELF": ("REL-3", "error", "A relationship targets its own asset."),
    "COLLECTION_CYCLE": ("COL-4", "error", "A collection is its own ancestor."),
    "MEMBERSHIP_DISAGREES": ("COL-5", "error", "An asset claims membership that a complete collection list denies."),
    "VALUE_SHAPE_MISMATCH": (
        "MD-4",
        "error",
        "A metadata value does not match the value_type and cardinality of its definition.",
    ),
    "VALUE_DATE_INVALID": ("MD-4, DT-1, DT-3", "error", "A date or date-time metadata value is not valid."),
    "VALUE_OPTION_UNKNOWN": ("MD-4", "error", "An enum value is not an option id of its definition."),
    "VALUE_OPTION_REPEATED": ("MD-4", "error", "A multiple enum value repeats an option id."),
    "DEFINITION_UNAVAILABLE": (
        "MD-4",
        "warning",
        "The metadata definition is not in the document, so the value shape was not checked.",
    ),
    "DEFINITION_REPEATED": ("MD-5", "error", "A metadata array names the same definition twice."),
    "NAMESPACE_UNDECLARED": ("EXT-2", "error", "An extension namespace is used but not declared in the manifest."),
    "NAMESPACE_DECLARED_TWICE": ("EXT-2", "error", "A namespace token is declared more than once."),
}


def diagnostic(code: str, path: str) -> Diagnostic:
    """Return the catalog diagnostic for ``code`` at the pointer ``path``."""
    rule, severity, message = CATALOG[code]
    return Diagnostic(code, rule, severity, path, message)


def pointer(base: str, *segments) -> str:
    """Append segments to the RFC 6901 pointer ``base``.

    Each key has ``~`` escaped as ``~0`` and ``/`` as ``~1``; array indexes
    are written in decimal.
    """
    parts = [base]
    for segment in segments:
        text = str(segment) if isinstance(segment, int) else segment
        parts.append("/" + text.replace("~", "~0").replace("/", "~1"))
    return "".join(parts)


def as_int(value) -> int:
    """Return an integer-typed field as ``int``: an ``int``, or an integral ``Decimal`` (``DOC-2``)."""
    if isinstance(value, bool):
        raise TypeError("a boolean is not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        return int(value)
    raise TypeError("not an integer value")


def _items(record, key):
    """Yield ``(index, item)`` for the array ``record[key]``, or nothing when absent."""
    array = record.get(key)
    if isinstance(array, list):
        yield from enumerate(array)


def _sorted(diagnostics):
    return sorted(diagnostics, key=lambda d: (d.path, d.code))


def _is_json_number(value):
    return isinstance(value, (int, Decimal)) and not isinstance(value, bool)


def json_equal(a, b) -> bool:
    """Compare two parsed JSON values exactly (``ID-6``, ``DOC-2``).

    Both values must have the same JSON type, where a boolean is its own type.
    Numbers (``int`` or ``Decimal``) are equal when mathematically equal.
    Objects need the same key set and equal members; arrays the same length
    and equal items in order; strings compare exactly; ``null`` equals only
    ``null``.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if _is_json_number(a) or _is_json_number(b):
        return _is_json_number(a) and _is_json_number(b) and a == b
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, str) or isinstance(b, str):
        return isinstance(a, str) and isinstance(b, str) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b))
    return False


# Package context.

REGISTRIES = ("storage_locations", "metadata_definitions", "collections", "assets")


@dataclass(frozen=True)
class PackageContext:
    """What the record checks of one package resolve against.

    Each registry maps an id to the first record with that id (``ID-1``
    reports every later one). ``completeness`` maps a registry name to
    ``complete`` or ``partial`` from the manifest. ``namespaces`` holds the
    declared extension tokens (``EXT-2``).
    """

    spec_version: str
    completeness: dict
    storage_locations: dict
    metadata_definitions: dict
    collections: dict
    assets: dict
    namespaces: frozenset


def resolve(context, registry: str, target: str, path: str):
    """PKG-6 and ID-5: resolve the reference ``target`` in ``registry``.

    Returns ``(record, None)`` when found. Otherwise returns ``(None, d)``
    where ``d`` is ``REFERENCE_UNRESOLVED`` at ``path`` when the registry is
    ``complete`` and ``REFERENCE_UNRESOLVED_PARTIAL`` when it is ``partial``.
    """
    records = getattr(context, registry)
    if isinstance(target, str) and target in records:
        return records[target], None
    if context.completeness.get(registry) == "partial":
        return None, diagnostic("REFERENCE_UNRESOLVED_PARTIAL", path)
    return None, diagnostic("REFERENCE_UNRESOLVED", path)


def _resolve_into(out, context, registry, target, path):
    """Resolve and append any unresolved diagnostic to ``out``; return the record or ``None``."""
    record, problem = resolve(context, registry, target, path)
    if problem is not None:
        out.append(problem)
    return record


# Identity.

def _nested_id_duplicates(record, path, key):
    """ID-4: a nested id is unique within its record; every repeat after the first is reported."""
    seen = set()
    out = []
    for i, item in _items(record, key):
        nested_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(nested_id, str):
            continue
        if nested_id in seen:
            out.append(diagnostic("NESTED_ID_DUPLICATE", pointer(path, key, i, "id")))
        seen.add(nested_id)
    return out


# Time.

def _rate(timing):
    """Return the time base rate of ``timing`` as ``(numerator, denominator)`` integers."""
    rate = timing["time_base"]["rate"]
    return as_int(rate["numerator"]), as_int(rate["denominator"])


def _check_rate(timing, path):
    """TIME-2: a rate is written in lowest terms."""
    numerator, denominator = _rate(timing)
    if gcd(numerator, denominator) != 1:
        return [diagnostic("RATE_NOT_LOWEST_TERMS", pointer(path, "time_base", "rate"))]
    return []


def _check_range_order(span, path):
    """TIME-4: a range has ``end_frame`` greater than ``start_frame``."""
    if "start_frame" in span and "end_frame" in span:
        if as_int(span["end_frame"]) <= as_int(span["start_frame"]):
            return [diagnostic("RANGE_NOT_INCREASING", pointer(path, "end_frame"))]
    return []


def _check_derived_values(annotation, path, timing):
    """TIME-7 and TIME-8: derived seconds and labels agree with their frame values.

    Seconds agree when ``nearest_frame`` (tie toward zero) equals the frame.
    A label agrees when it equals the label derived from the asset's
    ``source_timecode`` anchor. A label without an anchor, or at a rate
    outside ``LABEL_RATES``, is rejected by the schema, so it is skipped here.
    """
    numerator, denominator = _rate(timing)
    drop_frame = timing["time_base"]["drop_frame"] is True
    anchor = timing.get("source_timecode")
    out = []
    for end in ("start", "end"):
        frame_key = end + "_frame"
        if frame_key not in annotation:
            continue
        frame = as_int(annotation[frame_key])
        seconds_key = end + "_seconds"
        if seconds_key in annotation:
            if nearest_frame(annotation[seconds_key], numerator, denominator) != frame:
                out.append(diagnostic("SECONDS_DISAGREE", pointer(path, seconds_key)))
        label_key = end + "_timecode"
        if label_key in annotation:
            if anchor is None or (numerator, denominator) not in LABEL_RATES:
                continue  # Structurally rejected (TIME-8 table and anchor rule).
            try:
                derived = derive_label(anchor, frame, numerator, denominator, drop_frame)
            except ValueError:
                continue  # An invalid anchor is structurally rejected.
            if derived != annotation[label_key]:
                out.append(diagnostic("TIMECODE_DISAGREE", pointer(path, label_key)))
    return out


def _check_bounds(span, path, timing):
    """TIME-9: positions lie inside ``duration_frames`` D when D is declared.

    A point needs ``0 <= start_frame < D``. A range needs
    ``start_frame < D`` and ``end_frame <= D``; each field out of bounds is
    reported, even when the range is also reversed (``TIME-4``). Without D no
    upper bound is checked.
    """
    if "duration_frames" not in timing or "start_frame" not in span:
        return []
    duration = as_int(timing["duration_frames"])
    out = []
    if not 0 <= as_int(span["start_frame"]) < duration:
        out.append(diagnostic("FRAME_OUT_OF_BOUNDS", pointer(path, "start_frame")))
    if "end_frame" in span and as_int(span["end_frame"]) > duration:
        out.append(diagnostic("FRAME_OUT_OF_BOUNDS", pointer(path, "end_frame")))
    return out


def _has_frame_field(record):
    return "start_frame" in record or "end_frame" in record


# Metadata.

def _is_integer(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value()


def _is_number(value):
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, Decimal) and value.is_finite())


_SCALAR_TESTS = {
    "string": lambda v: isinstance(v, str),
    "integer": _is_integer,
    "number": _is_number,
    "boolean": lambda v: isinstance(v, bool),
    "date": lambda v: isinstance(v, str),
    "datetime": lambda v: isinstance(v, str),
    "enum": lambda v: isinstance(v, str),
    "asset_reference": lambda v: isinstance(v, str),
    "collection_reference": lambda v: isinstance(v, str),
}


def _check_scalar(type_, option_ids, item, path):
    """MD-4 for one scalar: JSON type, then date validity or enum option."""
    if not _SCALAR_TESTS[type_](item):
        return [diagnostic("VALUE_SHAPE_MISMATCH", path)]
    if type_ == "date" and not check_date(item):
        return [diagnostic("VALUE_DATE_INVALID", path)]
    if type_ == "datetime" and not check_date_time(item):
        return [diagnostic("VALUE_DATE_INVALID", path)]
    if type_ == "enum" and item not in option_ids:
        return [diagnostic("VALUE_OPTION_UNKNOWN", path)]
    return []


def check_value_shape(definition, value, path: str) -> list:
    """MD-4 and DT-3: a value matches the value_type and cardinality of its definition.

    ``path`` is the pointer of the ``value`` field. A ``single`` value is one
    scalar; a ``multiple`` value is an array (possibly empty) whose items are
    checked one by one at ``path/<k>``. ``date`` values follow ``DT-3`` and
    ``datetime`` values ``DT-1``. An ``enum`` value is an option id, and a
    ``multiple`` enum value repeats no item (every repeat after the first is
    reported for known option ids only; an unknown id gets
    ``VALUE_OPTION_UNKNOWN`` on every occurrence and no repeat code).
    Reference-typed values are strings here; their resolution is ``MD-6`` in a
    package. Constraints are never executed (``MD-2``).
    """
    type_ = definition["value_type"]
    option_ids = {o.get("id") for o in definition.get("options", ()) if isinstance(o, dict)}
    if definition["cardinality"] == "single":
        if isinstance(value, list):
            return [diagnostic("VALUE_SHAPE_MISMATCH", path)]
        return _check_scalar(type_, option_ids, value, path)
    if not isinstance(value, list):
        return [diagnostic("VALUE_SHAPE_MISMATCH", path)]
    out = []
    seen = set()
    for k, item in enumerate(value):
        item_path = pointer(path, k)
        out.extend(_check_scalar(type_, option_ids, item, item_path))
        if type_ == "enum" and isinstance(item, str) and item in option_ids:
            if item in seen:
                out.append(diagnostic("VALUE_OPTION_REPEATED", item_path))
            seen.add(item)
    return out


_REFERENCE_REGISTRY = {"asset_reference": "assets", "collection_reference": "collections"}


def _check_value_references(definition, value, value_path, context):
    """MD-6: reference-typed values resolve under PKG-6, one diagnostic per unresolved item.

    A ``single`` value is reported at ``value``, a ``multiple`` item at
    ``value/<k>``. Items that are not strings already failed MD-4.
    """
    registry = _REFERENCE_REGISTRY.get(definition["value_type"])
    if registry is None:
        return []
    if definition["cardinality"] == "single":
        items = [(value_path, value)]
    elif isinstance(value, list):
        items = [(pointer(value_path, k), item) for k, item in enumerate(value)]
    else:
        items = []
    out = []
    for item_path, item in items:
        if isinstance(item, str):
            _resolve_into(out, context, registry, item, item_path)
    return out


def _check_metadata(record, path, context):
    """MD-4 to MD-6 for the ``metadata`` array of one record or annotation.

    MD-5: a definition id appears at most once; every repeat after the first
    is reported at its ``definition``. Standalone (no context), no definition
    is available, so every value gets ``DEFINITION_UNAVAILABLE`` (MD-4)
    at the value object's pointer. In a package, ``definition`` resolves under
    PKG-6 at its own pointer and the unresolved diagnostic replaces that
    warning; a resolved definition gets MD-4 shape and MD-6 references.
    """
    out = []
    seen = set()
    for j, item in _items(record, "metadata"):
        item_path = pointer(path, "metadata", j)
        definition_id = item.get("definition")
        if definition_id in seen:
            out.append(diagnostic("DEFINITION_REPEATED", pointer(item_path, "definition")))
        seen.add(definition_id)
        if context is None:
            out.append(diagnostic("DEFINITION_UNAVAILABLE", item_path))
            continue
        definition = _resolve_into(
            out, context, "metadata_definitions", definition_id, pointer(item_path, "definition")
        )
        if definition is not None:
            value_path = pointer(item_path, "value")
            out.extend(check_value_shape(definition, item["value"], value_path))
            out.extend(_check_value_references(definition, item["value"], value_path, context))
    return out


# Assets.

def _check_versions(asset, path):
    """VER-2: version ordinals are unique within the asset; every repeat after the first is reported."""
    out = []
    seen = set()
    for i, version in _items(asset, "versions"):
        ordinal = as_int(version["ordinal"])
        if ordinal in seen:
            out.append(diagnostic("ORDINAL_DUPLICATE", pointer(path, "versions", i, "ordinal")))
        seen.add(ordinal)
    return out


def _check_version_reference(asset, owner, owner_path):
    """VER-3: a file, group, or embedded annotation ``version`` names a version of the asset.

    When the asset has no ``versions`` array, any ``version`` reference is
    rejected with ``VERSION_WITHOUT_VERSIONS``.
    """
    if "version" not in owner:
        return []
    version_path = pointer(owner_path, "version")
    if "versions" not in asset:
        return [diagnostic("VERSION_WITHOUT_VERSIONS", version_path)]
    ids = {v.get("id") for _i, v in _items(asset, "versions")}
    if owner["version"] not in ids:
        return [diagnostic("VERSION_REFERENCE_UNRESOLVED", version_path)]
    return []


def _check_group(group, group_path, file_ids):
    """GRP-3, GRP-4, and GRP-6 for one file group.

    GRP-3: a member ``sequence_range`` has ``start`` less than ``end``.
    GRP-4: every member ``file`` names a file of the asset, and
    ``(track_type, track_index)`` pairs are unique in the file group except
    for the segments of one spanned recording (GRP-6). A repeated pair where
    no member carries ``segment_index`` gives ``TRACK_DUPLICATE`` at every
    repeat after the first.
    GRP-6, per pair that has at least one ``segment_index``: when the pair is
    repeated, every member of it without ``segment_index`` gives
    ``SEGMENT_INDEX_MISSING`` at the member. In member order, a repeated
    ``segment_index`` gives ``SEGMENT_INDEX_DUPLICATE`` and a value lower than
    an earlier one gives ``SEGMENT_OUT_OF_ORDER``, both at that
    ``segment_index``. In a complete file group the distinct values are 0 to
    n - 1; the lowest value that breaks this gives ``SEGMENT_GAP`` at its
    first ``segment_index``. An incomplete file group may have gaps.
    """
    out = []
    pairs = {}
    for j, member in _items(group, "members"):
        member_path = pointer(group_path, "members", j)
        span = member.get("sequence_range")
        if isinstance(span, dict) and as_int(span["start"]) >= as_int(span["end"]):
            out.append(diagnostic("SEQUENCE_RANGE_EMPTY", pointer(member_path, "sequence_range")))
        if member.get("file") not in file_ids:
            out.append(diagnostic("FILE_REFERENCE_UNRESOLVED", pointer(member_path, "file")))
        pair = (member.get("track_type"), as_int(member["track_index"]))
        pairs.setdefault(pair, []).append((member_path, member))
    for members in pairs.values():
        segments = [(p, as_int(m["segment_index"])) for p, m in members if "segment_index" in m]
        if not segments:
            out.extend(diagnostic("TRACK_DUPLICATE", p) for p, _m in members[1:])
            continue
        if len(members) > 1:
            out.extend(diagnostic("SEGMENT_INDEX_MISSING", p) for p, m in members if "segment_index" not in m)
        first_at = {}
        highest = -1
        for p, index in segments:
            index_path = pointer(p, "segment_index")
            if index in first_at:
                out.append(diagnostic("SEGMENT_INDEX_DUPLICATE", index_path))
            else:
                if index < highest:
                    out.append(diagnostic("SEGMENT_OUT_OF_ORDER", index_path))
                first_at[index] = index_path
            highest = max(highest, index)
        if group.get("complete") is True:
            for expected, index in enumerate(sorted(first_at)):
                if index != expected:
                    out.append(diagnostic("SEGMENT_GAP", first_at[index]))
                    break
    return out


def _check_relationship(asset, relationship, rel_path, context):
    """REL-3 target, TIME-4 range order, and TIME-12 and TIME-9 range timeline.

    REL-3: ``target`` must not be the asset's own id, and in a package it
    resolves under PKG-6 in ``assets``. TIME-4: a ``range`` ends after it
    starts. TIME-12: the range is on the target's timeline. Standalone, the
    target is not in the document, so ``TIMELINE_UNAVAILABLE`` is reported at
    the range. In a package, a resolved target without ``timing`` gives
    ``TIMELINE_UNDECLARED`` at the range; with ``timing``, TIME-9 bounds use the
    target's ``duration_frames``. An unresolved target checks nothing more.
    """
    out = []
    target_id = relationship.get("target")
    if target_id == asset.get("id"):
        out.append(diagnostic("RELATIONSHIP_SELF", pointer(rel_path, "target")))
    target = None
    if context is not None:
        target = _resolve_into(out, context, "assets", target_id, pointer(rel_path, "target"))
    span = relationship.get("range")
    if isinstance(span, dict):
        range_path = pointer(rel_path, "range")
        out.extend(_check_range_order(span, range_path))
        if context is None:
            out.append(diagnostic("TIMELINE_UNAVAILABLE", range_path))
        elif target is not None:
            timing = target.get("timing")
            if isinstance(timing, dict):
                out.extend(_check_bounds(span, range_path, timing))
            else:
                out.append(diagnostic("TIMELINE_UNDECLARED", range_path))
    return out


def _check_embedded_annotation(asset, annotation, ann_path, context):
    """ANN-3 and section 6 for an annotation inside its asset.

    TIME-4 order, TIME-7 and TIME-8 derived values, TIME-9 bounds against the
    asset ``timing``; VER-3 version reference; MD-4 to MD-6 metadata.
    """
    out = []
    timing = asset.get("timing")
    if _has_frame_field(annotation) and isinstance(timing, dict):
        out.extend(_check_range_order(annotation, ann_path))
        out.extend(_check_derived_values(annotation, ann_path, timing))
        out.extend(_check_bounds(annotation, ann_path, timing))
    out.extend(_check_version_reference(asset, annotation, ann_path))
    out.extend(_check_metadata(annotation, ann_path, context))
    return out


def check_asset(asset, path: str, context) -> list:
    """Record checks for one asset.

    ID-4 nested ids (files, file groups, versions, annotations); TIME-2 rate;
    VER-2 ordinals; VER-3 version references; GRP-3, GRP-4, and GRP-6 file groups;
    REL-3 and TIME-4 relationships (TIME-12 warning standalone); embedded
    annotations (TIME-4, TIME-7, TIME-8, TIME-9); MD-4 to MD-6 metadata;
    COL-4 self-parent and metadata on collection snapshots. In a package, also
    PKG-6 file ``storage_location`` and the ``collections`` entries
    (``_check_asset_collections``).
    """
    out = []
    for key in ("files", "file_groups", "versions", "annotations"):
        out.extend(_nested_id_duplicates(asset, path, key))
    timing = asset.get("timing")
    if isinstance(timing, dict):
        out.extend(_check_rate(timing, pointer(path, "timing")))
    out.extend(_check_versions(asset, path))
    file_ids = {f.get("id") for _i, f in _items(asset, "files")}
    for i, file in _items(asset, "files"):
        file_path = pointer(path, "files", i)
        out.extend(_check_version_reference(asset, file, file_path))
        if context is not None and "storage_location" in file:
            location_path = pointer(file_path, "storage_location")
            _resolve_into(out, context, "storage_locations", file["storage_location"], location_path)
    for i, group in _items(asset, "file_groups"):
        group_path = pointer(path, "file_groups", i)
        out.extend(_check_version_reference(asset, group, group_path))
        out.extend(_check_group(group, group_path, file_ids))
    for i, relationship in _items(asset, "relationships"):
        out.extend(_check_relationship(asset, relationship, pointer(path, "relationships", i), context))
    for i, annotation in _items(asset, "annotations"):
        out.extend(_check_embedded_annotation(asset, annotation, pointer(path, "annotations", i), context))
    out.extend(_check_metadata(asset, path, context))
    if context is None:
        for j, entry in _items(asset, "collections"):
            if isinstance(entry, dict):
                out.extend(check_collection(entry, pointer(path, "collections", j), None))
    else:
        out.extend(_check_asset_collections(asset, path, context))
    return out


def _check_asset_collections(asset, path, context):
    """The asset ``collections`` entries in a package: PKG-6, ID-6, COL-5.

    Each entry (an id string, or a snapshot's ``id``) resolves under PKG-6 in
    ``collections``, reported at the entry pointer. A snapshot whose registry
    record is present gets ID-6: every field other than ``members`` must be
    ``json_equal`` to the registry record's, and the key sets must agree, else
    ``SNAPSHOT_MISMATCH`` at the entry. The collection record checks then run
    on the registry record only. A snapshot whose registry record is absent
    gets the collection record checks itself. COL-5: when the resolved
    collection has ``members.complete`` true and its ``members.assets`` lacks
    this asset, ``MEMBERSHIP_DISAGREES`` at the entry.
    """
    out = []
    for j, entry in _items(asset, "collections"):
        entry_path = pointer(path, "collections", j)
        snapshot = entry if isinstance(entry, dict) else None
        collection_id = snapshot.get("id") if snapshot is not None else entry
        registry_record = _resolve_into(out, context, "collections", collection_id, entry_path)
        if registry_record is None:
            if snapshot is not None:
                out.extend(check_collection(snapshot, entry_path, context))
            continue
        if snapshot is not None and not _snapshot_agrees(snapshot, registry_record):
            out.append(diagnostic("SNAPSHOT_MISMATCH", entry_path))
        members = registry_record.get("members")
        if isinstance(members, dict) and members.get("complete") is True:
            if asset.get("id") not in members.get("assets", ()):
                out.append(diagnostic("MEMBERSHIP_DISAGREES", entry_path))
    return out


def _snapshot_agrees(snapshot, record):
    """ID-6: same key set apart from ``members``, and every shared field ``json_equal``."""
    keys = set(snapshot) - {"members"}
    if keys != set(record) - {"members"}:
        return False
    return all(json_equal(snapshot[k], record[k]) for k in keys)


# Other record types.

def check_collection(collection, path: str, context) -> list:
    """Record checks for one collection: COL-4 self-parent and MD-4 to MD-6 metadata.

    COL-4: a ``parent`` equal to the collection's own ``id`` is a cycle,
    reported at ``/parent``. Cycles through other collections are found by
    ``check_package``. In a package, PKG-6 also resolves ``parent`` (COL-4),
    ``storage.storage_location``, and each ``members.assets`` item (COL-3).
    """
    out = []
    if "parent" in collection and collection["parent"] == collection.get("id"):
        out.append(diagnostic("COLLECTION_CYCLE", pointer(path, "parent")))
    if context is not None:
        if "parent" in collection:
            _resolve_into(out, context, "collections", collection["parent"], pointer(path, "parent"))
        storage = collection.get("storage")
        if isinstance(storage, dict) and "storage_location" in storage:
            _resolve_into(
                out, context, "storage_locations", storage["storage_location"],
                pointer(path, "storage", "storage_location"),
            )
        members = collection.get("members")
        if isinstance(members, dict):
            for k, asset_id in _items(members, "assets"):
                _resolve_into(out, context, "assets", asset_id, pointer(path, "members", "assets", k))
    out.extend(_check_metadata(collection, path, context))
    return out


def check_storage_location(record, path: str, context) -> list:
    """A storage location has no record-level semantic check (STO-2 is a producer obligation)."""
    return []


def check_metadata_definition(record, path: str, context) -> list:
    """ID-4: option ids are unique within the definition."""
    return _nested_id_duplicates(record, path, "options")


def check_annotation(record, path: str, context) -> list:
    """Record checks for a standalone annotation (ANN-1, ANN-3, TIME-12).

    Its asset is never in the same document, so any frame field gets the
    ``TIMELINE_UNAVAILABLE`` warning at the record pointer. TIME-4 order is
    still checked. MD-4 to MD-6 apply to its metadata.
    """
    out = []
    if _has_frame_field(record):
        out.append(diagnostic("TIMELINE_UNAVAILABLE", path))
        out.extend(_check_range_order(record, path))
    out.extend(_check_metadata(record, path, context))
    return out


_RECORD_CHECKS = {
    "asset": check_asset,
    "collection": check_collection,
    "storage_location": check_storage_location,
    "metadata_definition": check_metadata_definition,
    "annotation": check_annotation,
}


# Packages.

_REGISTRY_CHECKS = {
    "storage_locations": check_storage_location,
    "metadata_definitions": check_metadata_definition,
    "collections": check_collection,
    "assets": check_asset,
}


def _check_counts(package, path):
    """PKG-3: each declared count equals the length of its array; an absent array counts as 0."""
    out = []
    counts = package["manifest"]["counts"]
    for registry in REGISTRIES:
        if as_int(counts[registry]) != len(package.get(registry, ())):
            out.append(diagnostic("COUNT_MISMATCH", pointer(path, "manifest", "counts", registry)))
    return out


def _check_ids(package, path):
    """ID-1 and ID-2: ids are unique within each registry; every repeat after the first is reported."""
    out = []
    for registry in REGISTRIES:
        seen = set()
        for i, record in _items(package, registry):
            record_id = record.get("id")
            if record_id in seen:
                out.append(diagnostic("ID_DUPLICATE", pointer(path, registry, i, "id")))
            seen.add(record_id)
    return out


def _build_context(package):
    """Build the PackageContext from the first record of each id per registry."""
    registries = {}
    for registry in REGISTRIES:
        records = {}
        for _i, record in _items(package, registry):
            records.setdefault(record.get("id"), record)
        registries[registry] = records
    manifest = package["manifest"]
    tokens = frozenset(d.get("token") for _i, d in _items(manifest, "namespaces"))
    return PackageContext(
        spec_version=package.get("spec_version"),
        completeness=dict(manifest["completeness"]),
        namespaces=tokens,
        **registries,
    )


def _check_declarations(package, path):
    """EXT-2: a namespace token appears in at most one declaration; every repeat after the first is reported."""
    out = []
    seen = set()
    for i, declaration in _items(package["manifest"], "namespaces"):
        token = declaration.get("token")
        if token in seen:
            out.append(diagnostic("NAMESPACE_DECLARED_TWICE", pointer(path, "manifest", "namespaces", i, "token")))
        seen.add(token)
    return out


def _slot(owner, path):
    """Yield the ``extensions`` slot of ``owner`` as ``(slot pointer, object)`` when present."""
    extensions = owner.get("extensions") if isinstance(owner, dict) else None
    if isinstance(extensions, dict):
        yield pointer(path, "extensions"), extensions


def _each_slot(record, path, key):
    for i, item in _items(record, key):
        yield from _slot(item, pointer(path, key, i))


def _collection_slots(collection, path):
    yield from _slot(collection, path)
    yield from _each_slot(collection, path, "metadata")


def _asset_slots(asset, path, context):
    """EXT-1 slots of an asset: the record, its nested entities, and unresolved snapshots.

    A snapshot whose registry record is present is compared to that record
    (ID-6) and is not walked again.
    """
    yield from _slot(asset, path)
    for key in ("files", "versions", "relationships", "metadata"):
        yield from _each_slot(asset, path, key)
    for i, group in _items(asset, "file_groups"):
        group_path = pointer(path, "file_groups", i)
        yield from _slot(group, group_path)
        yield from _each_slot(group, group_path, "members")
    for i, annotation in _items(asset, "annotations"):
        annotation_path = pointer(path, "annotations", i)
        yield from _slot(annotation, annotation_path)
        yield from _each_slot(annotation, annotation_path, "metadata")
    for j, entry in _items(asset, "collections"):
        if isinstance(entry, dict) and entry.get("id") not in context.collections:
            yield from _collection_slots(entry, pointer(path, "collections", j))


def _package_slots(package, path, context):
    """Every schema-defined ``extensions`` slot of the package (EXT-1)."""
    yield from _slot(package, path)
    for i, record in _items(package, "storage_locations"):
        yield from _slot(record, pointer(path, "storage_locations", i))
    for i, record in _items(package, "metadata_definitions"):
        record_path = pointer(path, "metadata_definitions", i)
        yield from _slot(record, record_path)
        yield from _each_slot(record, record_path, "options")
    for i, record in _items(package, "collections"):
        yield from _collection_slots(record, pointer(path, "collections", i))
    for i, record in _items(package, "assets"):
        yield from _asset_slots(record, pointer(path, "assets", i), context)


def _check_namespaces_used(package, path, context):
    """EXT-2: every namespace used in a slot is declared.

    One ``NAMESPACE_UNDECLARED`` per slot that holds any undeclared token, at
    the slot pointer. The value object of a namespace is payload and is never
    descended into. Standalone records skip this check (EXT-5).
    """
    out = []
    for slot_path, extensions in _package_slots(package, path, context):
        if any(token not in context.namespaces for token in extensions):
            out.append(diagnostic("NAMESPACE_UNDECLARED", slot_path))
    return out


def _check_collection_cycles(package, path, context):
    """COL-4: a collection is not its own ancestor.

    Walks ``parent`` from each registry collection with a visited set and
    reports ``COLLECTION_CYCLE`` at ``/collections/<i>/parent`` for every
    collection on a cycle. A self-parent is reported by ``check_collection``.
    """
    out = []
    for i, collection in _items(package, "collections"):
        own_id = collection.get("id")
        current = collection.get("parent")
        if current is None or current == own_id:
            continue
        visited = set()
        while current in context.collections and current not in visited:
            if current == own_id:
                out.append(diagnostic("COLLECTION_CYCLE", pointer(path, "collections", i, "parent")))
                break
            visited.add(current)
            current = context.collections[current].get("parent")
    return out


def check_package(package, path: str = "") -> list:
    """Run the package checks and every record check in package context.

    PKG-3 counts; ID-1 and ID-2 ids per registry; EXT-2 declarations and
    used namespaces; COL-4 cycles; then each registry record with the
    context (PKG-6, ID-5, ID-6, TIME-9, TIME-12, REL-3, COL-4, COL-5, MD-4
    to MD-6). Diagnostics are sorted by ``(path, code)``.
    """
    out = []
    out.extend(_check_counts(package, path))
    out.extend(_check_ids(package, path))
    context = _build_context(package)
    out.extend(_check_declarations(package, path))
    out.extend(_check_namespaces_used(package, path, context))
    out.extend(_check_collection_cycles(package, path, context))
    for registry, record_check in _REGISTRY_CHECKS.items():
        for i, record in _items(package, registry):
            out.extend(record_check(record, pointer(path, registry, i), context))
    return _sorted(out)


def check(value, routing) -> list:
    """Run the semantic checks for the routed root record.

    Runs nothing unless ``routing.status`` is ``selected``. Dispatches on
    ``routing.kind``: a package is checked by ``check_package``; a standalone
    record is checked with no context. Diagnostics are sorted by
    ``(path, code)``.
    """
    if routing.status != "selected":
        return []
    if routing.kind == "package":
        return check_package(value)
    if routing.kind not in _RECORD_CHECKS:
        raise ValueError("routing selected no supported record type")
    return _sorted(_RECORD_CHECKS[routing.kind](value, "", None))
