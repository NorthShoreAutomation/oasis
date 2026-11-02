"""Semantic checks of the 2.0.0-draft.3 contract that a schema cannot express (Appendix B).

The diagnostic catalog lives here and nowhere else. Every check reads the
exact-number tree from ``strict_json`` and never changes it (``DOC-3``).
Integer-typed fields may be spelled as integral decimals (``DOC-2``), so every
check converts them with ``as_int`` before arithmetic, comparison, or use as a
key. Time arithmetic is exact: seconds become ``Fraction`` values, and no
binary number is ever made here.

Precondition: the tree is a package that passed the root checks, the number
limits (``DOC-4``), and structural validation. The checks rely on the schema
for field presence and JSON types and do not repeat it.

Only a package is checked (``REC-2``). Every reference resolves inside the
package (``PKG-6``). An asset holds its information in holders: the asset
level, each version in array order, and ``unassigned``. A holder has a
timeline only when its ``timing`` defines one (``TIME-12``): the asset level
of an asset with no versions, or a version. Absent and empty ``versions``
mean the same (``VER-1``).

Messages are fixed catalog text and never carry an input value, and no
pointer ever carries an extension key.
"""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from math import gcd

from tests.conformance.formats import check_date, check_date_time
from tests.conformance.timecode import LABEL_RATES, derive_label, nearest_frame
from tests.conformance.types import Diagnostic

__all__ = [
    "CATALOG",
    "PackageContext",
    "Timeline",
    "as_int",
    "check",
    "check_package",
    "check_value_shape",
    "diagnostic",
    "json_equal",
    "pointer",
    "resolve",
    "timeline_of",
]

# code: (rule, severity, message). The contract catalog, row by row, in the
# order of the catalog in docs/ADOPTION.md.
CATALOG = {
    "INPUT_INVALID": ("DOC-1", "error", "Input bytes cannot be parsed under the strict JSON policy."),
    "NOT_EXCHANGE_DOCUMENT": ("REC-2", "error", "The document root is not a package exchange document."),
    "VERSION_UNSUPPORTED": ("UNS-1", "error", "The declared spec_version is not supported by this checker."),
    "NUMBER_OUT_OF_RANGE": ("DOC-4", "error", "A number has an absolute value greater than 2^53 - 1."),
    "NUMBER_TOO_PRECISE": ("DOC-4", "error", "A number has more precision than a binary64 number holds."),
    "COUNT_MISMATCH": ("PKG-3", "error", "A declared count does not equal the length of its array."),
    "REFERENCE_UNRESOLVED": ("PKG-6", "error", "A reference does not resolve in the package."),
    "ID_DUPLICATE": ("ID-1", "error", "A record id is repeated within its record list."),
    "NESTED_ID_DUPLICATE": ("ID-4", "error", "A nested id is repeated within its asset or definition."),
    "RATE_NOT_LOWEST_TERMS": ("TIME-2", "error", "A rate is not written in lowest terms."),
    "RANGE_NOT_INCREASING": ("TIME-4, TIME-13", "error", "A range does not end after it starts."),
    "TIMELINE_UNDECLARED": (
        "TIME-5, TIME-12",
        "error",
        "A frame field is on a timeline that is not in the frame form.",
    ),
    "SECONDS_DISAGREE": ("TIME-7", "error", "A seconds value names a different frame than its frame field."),
    "TIMECODE_DISAGREE": (
        "TIME-7, TIME-8",
        "error",
        "A timecode label differs from the label derived from its frame field.",
    ),
    "SAMPLE_DISAGREE": (
        "TIME-13",
        "error",
        "A sample value does not restate its seconds value at the sample rate.",
    ),
    "SAMPLE_RATE_UNDECLARED": (
        "TIME-13",
        "error",
        "A sample field is on a timeline that declares no sample_rate.",
    ),
    "POSITION_OUT_OF_BOUNDS": ("TIME-9", "error", "A position lies outside the timeline length."),
    "PART_START_OUT_OF_ORDER": (
        "GRP-7",
        "error",
        "Part starts of one track pair do not increase with segment_index.",
    ),
    "SUBCLIP_LENGTH_DISAGREES": (
        "REL-4",
        "error",
        "A subclip length does not agree with the length of its range on the target.",
    ),
    "LOCATION_DUPLICATE": ("FILE-6", "error", "A file lists one storage location more than once."),
    "SEQUENCE_RANGE_EMPTY": ("FILE-8", "error", "An image sequence ends before it starts."),
    "SEQUENCE_STEP_MISMATCH": (
        "FILE-8",
        "error",
        "The last frame number is not reached from the first in whole steps.",
    ),
    "SEQUENCE_PATTERN_INVALID": (
        "FILE-8",
        "error",
        "A sequence path does not hold the {frame} placeholder exactly once.",
    ),
    "SEQUENCE_FRAME_OUTSIDE": (
        "FILE-8",
        "error",
        "A listed frame number is not an expected number of the sequence.",
    ),
    "SEQUENCE_IMAGE_REPEATED": ("FILE-8", "error", "A sequence lists details for one image more than once."),
    "TRACK_DUPLICATE": ("GRP-4", "error", "A file group repeats a track type and index pair."),
    "FILE_REFERENCE_UNRESOLVED": (
        "GRP-4",
        "error",
        "A file group member names a file that is not in the same holder.",
    ),
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
    "STREAM_DUPLICATE": ("GRP-10", "error", "A file group selects one stream of a file twice."),
    "CHANNEL_LAYOUT_MISMATCH": ("GRP-11", "error", "A channel layout does not have channel_count entries."),
    "STREAM_FACTS_DISAGREE": ("GRP-11", "error", "Two members describe one stream with different values."),
    "SEQUENCE_FRAME_MISSING": (
        "GRP-12",
        "error",
        "A member shares a pair with sequence images but has no sequence_frame.",
    ),
    "SEQUENCE_FRAME_DUPLICATE": ("GRP-12", "error", "A file group repeats a sequence_frame within one pair."),
    "SEQUENCE_FRAME_OUT_OF_ORDER": (
        "GRP-12",
        "error",
        "Sequence images are not in ascending sequence_frame order.",
    ),
    "TRACK_PARTS_MIXED": ("GRP-12", "error", "One track pair mixes segments and sequence images."),
    "SEQUENCE_FRAME_ON_COMPACT": (
        "GRP-12",
        "error",
        "An explicit sequence image names a compact sequence file.",
    ),
    "ORDINAL_DUPLICATE": ("VER-2", "error", "Two versions share an ordinal."),
    "VERSION_REFERENCE_UNRESOLVED": (
        "VER-6, REL-6",
        "error",
        "A version reference names no version of its asset.",
    ),
    "TARGET_VERSION_REQUIRED": (
        "REL-6",
        "error",
        "A relationship range has no target_version, and its target has versions.",
    ),
    "DEFINITION_SHARED_AND_VERSIONED": (
        "VER-7",
        "error",
        "A metadata definition used at asset level is also used in a version or in unassigned.",
    ),
    "RELATIONSHIP_SELF": ("REL-3", "error", "A relationship targets its own asset."),
    "RELATIONSHIP_DUPLICATE": (
        "REL-5",
        "error",
        "A relationships list repeats an entry in every field except description and extensions.",
    ),
    "COLLECTION_CYCLE": ("COL-4", "error", "A member_of entry is on a cycle among collections."),
    "MEMBERSHIP_DUPLICATE": (
        "COL-7",
        "error",
        "A member_of list names one collection more than once without a position on each entry.",
    ),
    "POSITION_DUPLICATE": ("COL-7", "error", "Two entries that name one collection share a position."),
    "VALUE_SHAPE_MISMATCH": (
        "MD-4",
        "error",
        "A metadata value does not match the value_type and cardinality of its definition.",
    ),
    "VALUE_DATE_INVALID": ("MD-4, DT-1, DT-3", "error", "A date or date-time metadata value is not valid."),
    "VALUE_OPTION_UNKNOWN": (
        "MD-4, MD-7",
        "error",
        "An enum value on a fixed list is not an option id of its definition.",
    ),
    "VALUE_REPEATED": ("MD-8", "error", "A multiple value repeats an item."),
    "DEFINITION_REPEATED": ("MD-5", "error", "A metadata list names the same definition twice."),
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


def _exact(value) -> Fraction:
    """Return a JSON number (``int`` or finite ``Decimal``) as an exact ``Fraction`` (``DOC-2``)."""
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise TypeError("not a number value")
    return Fraction(value)


def _items(record, key):
    """Yield ``(index, item)`` for the array ``record[key]``, or nothing when absent."""
    array = record.get(key) if isinstance(record, dict) else None
    if isinstance(array, list):
        yield from enumerate(array)


def _sorted(diagnostics):
    return sorted(diagnostics, key=lambda d: (d.path, d.code))


def _is_json_number(value):
    return isinstance(value, (int, Decimal)) and not isinstance(value, bool)


def json_equal(a, b) -> bool:
    """Compare two parsed JSON values exactly (``DOC-2``).

    Used by ``COL-7``, ``REL-5``, ``MD-8``, and ``GRP-11``. Both values must
    have the same JSON type, where a boolean is its own type. Numbers
    (``int`` or ``Decimal``) are equal when mathematically equal. Objects need
    the same key set and equal members, so an empty object never equals an
    absent member; arrays need the same length and equal items in order;
    strings compare by exact code points, with no Unicode normalization
    (``DOC-3``); ``null`` equals only ``null``.
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


def _scalar_key(value):
    """Return a hashable key that is equal for two scalars exactly when ``json_equal`` holds."""
    if isinstance(value, bool):
        return ("boolean", value)
    if _is_json_number(value):
        return ("number", _exact(value))
    if isinstance(value, str):
        return ("string", value)
    if value is None:
        return ("null", None)
    return None


# Package context.

REGISTRIES = ("storage_locations", "metadata_definitions", "collections", "assets")


@dataclass(frozen=True)
class PackageContext:
    """What the checks of one package resolve against (``PKG-6``).

    Each registry maps an id to the first record with that id (``ID-1``
    reports every later one). ``namespaces`` holds the declared extension
    tokens (``EXT-2``).
    """

    storage_locations: dict
    metadata_definitions: dict
    collections: dict
    assets: dict
    namespaces: frozenset


def resolve(context, registry: str, target, path: str):
    """PKG-6 and ID-5: resolve the reference ``target`` in ``registry``.

    Returns ``(record, None)`` when found, else ``(None, d)`` where ``d`` is
    ``REFERENCE_UNRESOLVED`` at ``path``. Ids compare exactly.
    """
    records = getattr(context, registry)
    if isinstance(target, str) and target in records:
        return records[target], None
    return None, diagnostic("REFERENCE_UNRESOLVED", path)


def _resolve_into(out, context, registry, target, path):
    """Resolve and append any unresolved diagnostic to ``out``; return the record or ``None``."""
    record, problem = resolve(context, registry, target, path)
    if problem is not None:
        out.append(problem)
    return record


# Timelines.

@dataclass(frozen=True)
class Timeline:
    """One timeline, read from a ``timing`` object (``TIME-11``).

    ``rate`` is ``(numerator, denominator)`` in the frame form and ``None``
    in the seconds form. ``frames`` is ``duration_frames`` or ``None``.
    ``seconds`` is the exact length in seconds, or ``None`` when unknown: in
    the frame form ``duration_frames * denominator / numerator``, in the
    seconds form ``duration_seconds``. ``anchor`` is the frame-form
    ``source_timecode``. ``sample_rate`` and ``samples`` come from
    ``TIME-13``.
    """

    rate: tuple
    drop_frame: bool
    anchor: str
    frames: int
    seconds: Fraction
    sample_rate: int
    samples: int

    @property
    def frame_form(self) -> bool:
        return self.rate is not None

    def frame_duration(self) -> Fraction:
        """One frame duration in seconds, ``denominator / numerator``."""
        numerator, denominator = self.rate
        return Fraction(denominator, numerator)

    def frame_seconds(self, frame) -> Fraction:
        """The start time in seconds of ``frame``, exactly."""
        numerator, denominator = self.rate
        return Fraction(frame * denominator, numerator)


def timeline_of(timing):
    """Return the ``Timeline`` of a ``timing`` object, or ``None`` when there is no ``timing``.

    Never reads ``time_base`` unless it is present: a seconds-form timing may
    carry ``source_timecode`` with its own ``timecode_base`` (``TIME-14``).
    """
    if not isinstance(timing, dict):
        return None
    sample_rate = as_int(timing["sample_rate"]) if "sample_rate" in timing else None
    samples = as_int(timing["duration_samples"]) if "duration_samples" in timing else None
    if "time_base" in timing:
        time_base = timing["time_base"]
        rate = (as_int(time_base["rate"]["numerator"]), as_int(time_base["rate"]["denominator"]))
        frames = as_int(timing["duration_frames"]) if "duration_frames" in timing else None
        seconds = Fraction(frames * rate[1], rate[0]) if frames is not None else None
        return Timeline(
            rate=rate,
            drop_frame=time_base.get("drop_frame") is True,
            anchor=timing.get("source_timecode"),
            frames=frames,
            seconds=seconds,
            sample_rate=sample_rate,
            samples=samples,
        )
    seconds = _exact(timing["duration_seconds"]) if "duration_seconds" in timing else None
    return Timeline(
        rate=None, drop_frame=False, anchor=None, frames=None, seconds=seconds,
        sample_rate=sample_rate, samples=samples,
    )


def _check_lowest_terms(rate, path):
    """TIME-2: a rate ``{numerator, denominator}`` is written in lowest terms."""
    if gcd(as_int(rate["numerator"]), as_int(rate["denominator"])) != 1:
        return [diagnostic("RATE_NOT_LOWEST_TERMS", path)]
    return []


def _check_timing(timing, path):
    """Checks of one holder ``timing`` object, run on every holder, each version included.

    TIME-2 on ``time_base`` and ``timecode_base`` rates. TIME-7:
    ``duration_seconds`` restates ``duration_frames`` in the frame form.
    TIME-13: ``duration_samples`` restates ``duration_seconds`` at
    ``sample_rate``.
    """
    out = []
    for key in ("time_base", "timecode_base"):
        base = timing.get(key)
        if isinstance(base, dict):
            out.extend(_check_lowest_terms(base["rate"], pointer(path, key, "rate")))
    timeline = timeline_of(timing)
    if timeline.frame_form and timeline.frames is not None and "duration_seconds" in timing:
        numerator, denominator = timeline.rate
        if nearest_frame(timing["duration_seconds"], numerator, denominator) != timeline.frames:
            out.append(diagnostic("SECONDS_DISAGREE", pointer(path, "duration_seconds")))
    if timeline.samples is not None and timeline.sample_rate is not None and "duration_seconds" in timing:
        if nearest_frame(timing["duration_seconds"], timeline.sample_rate, 1) != timeline.samples:
            out.append(diagnostic("SAMPLE_DISAGREE", pointer(path, "duration_samples")))
    return out


_FRAME_FIELDS = ("start_frame", "end_frame")
_SECONDS_FIELDS = ("start_seconds", "end_seconds")
_SAMPLE_FIELDS = ("start_sample", "end_sample")


def _has_frame_field(marker):
    return any(key in marker for key in _FRAME_FIELDS)


def _check_order(marker, path):
    """TIME-4 and TIME-13: a range ends after it starts.

    The defining unit is frames when a frame field is present, else seconds.
    Sample fields are compared on their own when both are present.
    """
    out = []
    pairs = [_FRAME_FIELDS if _has_frame_field(marker) else _SECONDS_FIELDS, _SAMPLE_FIELDS]
    for start, end in pairs:
        if start in marker and end in marker and _exact(marker[end]) <= _exact(marker[start]):
            out.append(diagnostic("RANGE_NOT_INCREASING", pointer(path, end)))
    return out


def _check_frame_marker(marker, path, timeline):
    """TIME-7, TIME-8, and TIME-9 for a marker whose frames define it, on a frame-form timeline.

    Seconds agree when ``nearest_frame`` (tie toward zero) equals the frame.
    A label agrees when it equals the label derived from the ``source_timecode``
    anchor. A label without an anchor, or at a rate outside ``LABEL_RATES``,
    is rejected by the schema, so it is skipped here. Bounds: each frame field
    greater than ``duration_frames`` is reported at that field, and so is the
    ``start_frame`` of a range that equals it.
    """
    out = []
    numerator, denominator = timeline.rate
    is_range = _is_range(marker)
    for end in ("start", "end"):
        frame_key = end + "_frame"
        if frame_key not in marker:
            continue
        frame = as_int(marker[frame_key])
        seconds_key = end + "_seconds"
        if seconds_key in marker and nearest_frame(marker[seconds_key], numerator, denominator) != frame:
            out.append(diagnostic("SECONDS_DISAGREE", pointer(path, seconds_key)))
        label_key = end + "_timecode"
        if label_key in marker and timeline.anchor is not None and timeline.rate in LABEL_RATES:
            try:
                derived = derive_label(timeline.anchor, frame, numerator, denominator, timeline.drop_frame)
            except ValueError:
                derived = None  # An invalid anchor is structurally rejected.
            if derived is not None and derived != marker[label_key]:
                out.append(diagnostic("TIMECODE_DISAGREE", pointer(path, label_key)))
        if timeline.frames is not None and (
            frame > timeline.frames or (is_range and end == "start" and frame == timeline.frames)
        ):
            out.append(diagnostic("POSITION_OUT_OF_BOUNDS", pointer(path, frame_key)))
    return out


def _is_range(marker):
    """A marker with an end field is a range (``TIME-4``)."""
    return "end_frame" in marker or "end_seconds" in marker


def _check_seconds_bounds(marker, path, timeline):
    """TIME-9 for a marker with no frame field.

    Each seconds field greater than the length S is out of bounds, and so is
    the ``start_seconds`` of a range that equals S.
    """
    if timeline is None or timeline.seconds is None:
        return []
    is_range = _is_range(marker)
    out = []
    for key in _SECONDS_FIELDS:
        if key not in marker:
            continue
        seconds = _exact(marker[key])
        if seconds > timeline.seconds or (is_range and key == "start_seconds" and seconds == timeline.seconds):
            out.append(diagnostic("POSITION_OUT_OF_BOUNDS", pointer(path, key)))
    return out


def _check_samples(marker, path, timeline):
    """TIME-13 and TIME-9 for the sample fields of a marker.

    With no timeline ``sample_rate``, ``SAMPLE_RATE_UNDECLARED`` once, at the
    first sample field. Otherwise each sample field restates its seconds
    field (``SAMPLE_DISAGREE``), and each sample field greater than
    ``duration_samples`` is out of bounds. A marker with an end field is a
    range (``TIME-4``). Its ``start_sample`` is also out of bounds when it
    equals ``duration_samples``, with or without an ``end_sample``.
    """
    present = [key for key in _SAMPLE_FIELDS if key in marker]
    if not present:
        return []
    if timeline is None or timeline.sample_rate is None:
        return [diagnostic("SAMPLE_RATE_UNDECLARED", pointer(path, present[0]))]
    is_range = _is_range(marker)
    out = []
    for key in present:
        sample = as_int(marker[key])
        seconds_key = key.replace("_sample", "_seconds")
        if seconds_key in marker and nearest_frame(marker[seconds_key], timeline.sample_rate, 1) != sample:
            out.append(diagnostic("SAMPLE_DISAGREE", pointer(path, key)))
        if timeline.samples is not None and (
            sample > timeline.samples or (is_range and key == "start_sample" and sample == timeline.samples)
        ):
            out.append(diagnostic("POSITION_OUT_OF_BOUNDS", pointer(path, key)))
    return out


def _check_marker(marker, path, timeline, undeclared_path):
    """Section 6 checks of a marker against a known timeline (``None`` for no ``timing``).

    A frame field on a timeline that is not in the frame form gives
    ``TIMELINE_UNDECLARED`` at ``undeclared_path`` and no other frame check.
    Order (``TIME-4``) is not checked here.
    """
    out = []
    if _has_frame_field(marker):
        if timeline is None or not timeline.frame_form:
            out.append(diagnostic("TIMELINE_UNDECLARED", undeclared_path))
        else:
            out.extend(_check_frame_marker(marker, path, timeline))
    else:
        out.extend(_check_seconds_bounds(marker, path, timeline))
    out.extend(_check_samples(marker, path, timeline))
    return out


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


def _check_scalar(definition, option_ids, item, path):
    """MD-4 and MD-7 for one scalar: JSON type, then date validity or the fixed option list."""
    type_ = definition["value_type"]
    if not _SCALAR_TESTS[type_](item):
        return [diagnostic("VALUE_SHAPE_MISMATCH", path)]
    if type_ == "date" and not check_date(item):
        return [diagnostic("VALUE_DATE_INVALID", path)]
    if type_ == "datetime" and not check_date_time(item):
        return [diagnostic("VALUE_DATE_INVALID", path)]
    if type_ == "enum" and definition.get("list_type") == "fixed" and item not in option_ids:
        return [diagnostic("VALUE_OPTION_UNKNOWN", path)]
    return []


def check_value_shape(definition, value, path: str) -> list:
    """MD-4, MD-7, MD-8, DT-1, and DT-3: a value matches its definition.

    ``path`` is the pointer of the ``value`` field. A ``single`` value is one
    scalar; a ``multiple`` value is an array (possibly empty) whose items are
    checked one by one at ``path/<k>``. ``date`` values follow ``DT-3`` and
    ``datetime`` values ``DT-1``. An ``enum`` item on a ``fixed`` list is an
    option id, compared by exact code points; an empty ``fixed`` list accepts
    no item, and an ``open`` list accepts any string (``MD-7``). MD-8: in a
    ``multiple`` value of any type, each repeat after the first is
    ``VALUE_REPEATED``. Numbers compare by value, strings by code points, and
    a boolean never equals a number. An item can get both an option or
    resolution finding and a repeat finding. Constraints are never executed
    (``MD-2``).
    """
    option_ids = {o.get("id") for o in definition.get("options", ()) if isinstance(o, dict)}
    if definition["cardinality"] == "single":
        if isinstance(value, list):
            return [diagnostic("VALUE_SHAPE_MISMATCH", path)]
        return _check_scalar(definition, option_ids, value, path)
    if not isinstance(value, list):
        return [diagnostic("VALUE_SHAPE_MISMATCH", path)]
    out = []
    seen = set()
    for k, item in enumerate(value):
        item_path = pointer(path, k)
        out.extend(_check_scalar(definition, option_ids, item, item_path))
        key = _scalar_key(item)
        if key is None:
            continue
        if key in seen:
            out.append(diagnostic("VALUE_REPEATED", item_path))
        seen.add(key)
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


def _check_metadata(owner, path, context):
    """MD-4 to MD-8 for one ``metadata`` list, checked on its own.

    MD-5: a definition id appears at most once; every repeat after the first
    is reported at its ``definition``. ``definition`` resolves under PKG-6 at
    its own pointer; a resolved definition gets the value checks.
    """
    out = []
    seen = set()
    for j, item in _items(owner, "metadata"):
        item_path = pointer(path, "metadata", j)
        definition_id = item.get("definition")
        if definition_id in seen:
            out.append(diagnostic("DEFINITION_REPEATED", pointer(item_path, "definition")))
        seen.add(definition_id)
        definition = _resolve_into(
            out, context, "metadata_definitions", definition_id, pointer(item_path, "definition")
        )
        if definition is not None:
            value_path = pointer(item_path, "value")
            out.extend(check_value_shape(definition, item["value"], value_path))
            out.extend(_check_value_references(definition, item["value"], value_path, context))
    return out


# Files and file groups.

def _check_file(file, file_path, context):
    """PKG-6, FILE-6, and FILE-8 for one file.

    PKG-6: each ``locations/<k>/storage_location`` resolves. FILE-6: a repeated
    storage location gives ``LOCATION_DUPLICATE`` at each repeat after the
    first. FILE-8, when ``sequence`` is present: ``SEQUENCE_RANGE_EMPTY`` when
    ``last_frame < first_frame``, else ``SEQUENCE_STEP_MISMATCH`` when the last
    number is not reached in whole steps; ``SEQUENCE_PATTERN_INVALID`` at each
    path whose count of ``{frame}`` is not 1; ``SEQUENCE_FRAME_OUTSIDE`` at each
    ``images/<i>/frame`` and ``missing_frames`` item that is not an expected
    number; ``SEQUENCE_IMAGE_REPEATED`` at each repeated image frame. A number
    n is expected when ``first_frame <= n <= last_frame`` and
    ``(n - first_frame) % step == 0``. An empty range expects no number and
    reports no ``SEQUENCE_FRAME_OUTSIDE``.
    """
    out = []
    seen = set()
    for k, location in _items(file, "locations"):
        location_path = pointer(file_path, "locations", k)
        storage = location.get("storage_location")
        _resolve_into(out, context, "storage_locations", storage, pointer(location_path, "storage_location"))
        if storage in seen:
            out.append(diagnostic("LOCATION_DUPLICATE", pointer(location_path, "storage_location")))
        seen.add(storage)
    sequence = file.get("sequence")
    if not isinstance(sequence, dict):
        return out
    sequence_path = pointer(file_path, "sequence")
    first = as_int(sequence["first_frame"])
    last = as_int(sequence["last_frame"])
    step = as_int(sequence["step"])
    empty = last < first
    if empty:
        out.append(diagnostic("SEQUENCE_RANGE_EMPTY", pointer(sequence_path, "last_frame")))
    elif (last - first) % step != 0:
        out.append(diagnostic("SEQUENCE_STEP_MISMATCH", pointer(sequence_path, "step")))

    def outside(number):
        return not empty and not (first <= number <= last and (number - first) % step == 0)

    for k, location in _items(file, "locations"):
        location_path = pointer(file_path, "locations", k)
        path = location.get("path")
        if isinstance(path, str) and path.count("{frame}") != 1:
            out.append(diagnostic("SEQUENCE_PATTERN_INVALID", pointer(location_path, "path")))
        for j, number in _items(location, "missing_frames"):
            if outside(as_int(number)):
                out.append(diagnostic("SEQUENCE_FRAME_OUTSIDE", pointer(location_path, "missing_frames", j)))
    frames_seen = set()
    for i, image in _items(sequence, "images"):
        frame_path = pointer(sequence_path, "images", i, "frame")
        number = as_int(image["frame"])
        if outside(number):
            out.append(diagnostic("SEQUENCE_FRAME_OUTSIDE", frame_path))
        if number in frames_seen:
            out.append(diagnostic("SEQUENCE_IMAGE_REPEATED", frame_path))
        frames_seen.add(number)
    return out


def _check_part_kind(field, members, duplicate_code, order_code):
    """Unique values in ascending member order for ``segment_index`` or ``sequence_frame``.

    The order check starts with no highest value, so negative values work.
    """
    out = []
    seen = set()
    highest = None
    for member_path, member in members:
        if field not in member:
            continue
        value = as_int(member[field])
        value_path = pointer(member_path, field)
        if value in seen:
            out.append(diagnostic(duplicate_code, value_path))
        elif highest is not None and value < highest:
            out.append(diagnostic(order_code, value_path))
        seen.add(value)
        highest = value if highest is None else max(highest, value)
    return out


def _start_time(member, timeline):
    """The exact start time of a part (GRP-7), or ``None`` when it has no usable start."""
    if "start_frame" in member:
        if timeline is None or not timeline.frame_form:
            return None
        return timeline.frame_seconds(as_int(member["start_frame"]))
    if "start_seconds" in member:
        return _exact(member["start_seconds"])
    return None


def _check_part_start(member, member_path, timeline):
    """GRP-7 for one member start: TIME-5 frame form, TIME-7 agreement, and strict bounds.

    A start must be less than the timeline length when the length is known.
    """
    out = []
    if "start_frame" in member:
        frame_path = pointer(member_path, "start_frame")
        if timeline is None or not timeline.frame_form:
            return [diagnostic("TIMELINE_UNDECLARED", frame_path)]
        frame = as_int(member["start_frame"])
        if "start_seconds" in member:
            numerator, denominator = timeline.rate
            if nearest_frame(member["start_seconds"], numerator, denominator) != frame:
                out.append(diagnostic("SECONDS_DISAGREE", pointer(member_path, "start_seconds")))
        if timeline.frames is not None and frame >= timeline.frames:
            out.append(diagnostic("POSITION_OUT_OF_BOUNDS", frame_path))
    elif "start_seconds" in member:
        if timeline is not None and timeline.seconds is not None:
            if _exact(member["start_seconds"]) >= timeline.seconds:
                out.append(diagnostic("POSITION_OUT_OF_BOUNDS", pointer(member_path, "start_seconds")))
    return out


def _check_pair(members, timeline):
    """GRP-4, GRP-6, GRP-12, and the GRP-7 order check for one ``(track_type, track_index)`` pair.

    The first member that carries ``segment_index`` or ``sequence_frame``
    sets the kind of the pair. Each later member that carries the other field
    gives ``TRACK_PARTS_MIXED`` at that field, and a mixed pair skips the
    other checks. A repeated pair with neither field gives
    ``TRACK_DUPLICATE`` at every member after the first. A pair of segments
    follows GRP-6, and a pair of sequence images follows GRP-12. Part starts
    must increase strictly with ``segment_index``, checked only when the pair
    passes GRP-6; the finding is at the later start field.
    """
    kind = None
    mixed = []
    for member_path, member in members:
        for field in ("segment_index", "sequence_frame"):
            if field not in member:
                continue
            if kind is None:
                kind = field
            elif field != kind:
                mixed.append(diagnostic("TRACK_PARTS_MIXED", pointer(member_path, field)))
    if mixed:
        return mixed
    if kind is None:
        return [diagnostic("TRACK_DUPLICATE", member_path) for member_path, _m in members[1:]]
    out = []
    if kind == "sequence_frame":
        out.extend(diagnostic("SEQUENCE_FRAME_MISSING", p) for p, m in members if "sequence_frame" not in m)
        out.extend(_check_part_kind(
            "sequence_frame", members, "SEQUENCE_FRAME_DUPLICATE", "SEQUENCE_FRAME_OUT_OF_ORDER"
        ))
        return out
    if len(members) > 1:
        out.extend(diagnostic("SEGMENT_INDEX_MISSING", p) for p, m in members if "segment_index" not in m)
    out.extend(_check_part_kind("segment_index", members, "SEGMENT_INDEX_DUPLICATE", "SEGMENT_OUT_OF_ORDER"))
    if out:
        return out
    previous = None
    for member_path, member in members:
        start = _start_time(member, timeline)
        if start is None:
            continue
        if previous is not None and start <= previous:
            field = "start_frame" if "start_frame" in member else "start_seconds"
            out.append(diagnostic("PART_START_OUT_OF_ORDER", pointer(member_path, field)))
        previous = start
    return out


def _check_group(group, group_path, files, timeline):
    """GRP-4, GRP-6, GRP-7, GRP-10, GRP-11, GRP-12, and TIME-2 for one file group.

    ``files`` maps the file ids of the group's holder to their file objects.
    Per member: ``file`` names a file of the same holder
    (``FILE_REFERENCE_UNRESOLVED``); ``frame_rate`` and
    ``capture_frame_rate`` are in lowest terms; ``channel_layout`` has
    ``channel_count`` entries; a ``(file, stream_index)`` repeat is
    ``STREAM_DUPLICATE`` at the later ``stream_index``; ``sequence_frame`` on a
    member whose file has ``sequence`` is ``SEQUENCE_FRAME_ON_COMPACT``; and
    the part start checks. Then the pair checks (``_check_pair``).
    """
    out = []
    pairs = {}
    streams = set()
    for j, member in _items(group, "members"):
        member_path = pointer(group_path, "members", j)
        file_id = member.get("file")
        if file_id not in files:
            out.append(diagnostic("FILE_REFERENCE_UNRESOLVED", pointer(member_path, "file")))
        for key in ("frame_rate", "capture_frame_rate"):
            if isinstance(member.get(key), dict):
                out.extend(_check_lowest_terms(member[key], pointer(member_path, key)))
        if isinstance(member.get("channel_layout"), list) and "channel_count" in member:
            if len(member["channel_layout"]) != as_int(member["channel_count"]):
                out.append(diagnostic("CHANNEL_LAYOUT_MISMATCH", pointer(member_path, "channel_layout")))
        if "stream_index" in member:
            stream = (file_id, as_int(member["stream_index"]))
            if stream in streams:
                out.append(diagnostic("STREAM_DUPLICATE", pointer(member_path, "stream_index")))
            streams.add(stream)
        if "sequence_frame" in member and isinstance(files.get(file_id), dict) and "sequence" in files[file_id]:
            out.append(diagnostic("SEQUENCE_FRAME_ON_COMPACT", pointer(member_path, "sequence_frame")))
        out.extend(_check_part_start(member, member_path, timeline))
        pair = (member.get("track_type"), as_int(member["track_index"]))
        pairs.setdefault(pair, []).append((member_path, member))
    for members in pairs.values():
        out.extend(_check_pair(members, timeline))
    return out


_STREAM_FACT_FIELDS = (
    "track_type", "language", "codec", "bit_rate", "duration_seconds", "width", "height",
    "display_aspect_ratio", "bit_depth", "frame_rate", "capture_frame_rate", "frame_count",
    "scan_type", "sample_rate", "channel_count", "channel_layout",
)


def _check_stream_facts(holder, holder_path):
    """GRP-11: members of one holder that select one stream state the same facts.

    Visits the members of all file groups of the holder in array order, and
    only members with ``stream_index``. For each ``(file, stream_index,
    field)``, the first value seen is recorded; a later member whose value
    differs (``json_equal``) gives ``STREAM_FACTS_DISAGREE`` at its field.
    ``label`` is not a stream fact.
    """
    out = []
    recorded = {}
    for i, group in _items(holder, "file_groups"):
        for j, member in _items(group, "members"):
            if "stream_index" not in member:
                continue
            member_path = pointer(holder_path, "file_groups", i, "members", j)
            stream = (member.get("file"), as_int(member["stream_index"]))
            for field in _STREAM_FACT_FIELDS:
                if field not in member:
                    continue
                key = (stream, field)
                if key not in recorded:
                    recorded[key] = member[field]
                elif not json_equal(recorded[key], member[field]):
                    out.append(diagnostic("STREAM_FACTS_DISAGREE", pointer(member_path, field)))
    return out


# Relationships.

_RELATIONSHIP_IGNORED = ("description", "extensions")


def _relationship_key_fields(relationship):
    return {k: v for k, v in relationship.items() if k not in _RELATIONSHIP_IGNORED}


def _check_relationship_duplicates(holder, holder_path):
    """REL-5: within one list, an entry equal to an earlier one in every field except
    ``description`` and ``extensions`` is reported at the later entry."""
    out = []
    earlier = []
    for i, relationship in _items(holder, "relationships"):
        fields = _relationship_key_fields(relationship)
        if any(json_equal(fields, other) for other in earlier):
            out.append(diagnostic("RELATIONSHIP_DUPLICATE", pointer(holder_path, "relationships", i)))
        earlier.append(fields)
    return out


def _target_timeline(target, relationship):
    """REL-6: return ``(known, timeline)`` of the target timeline of a relationship.

    Known when ``target_version`` resolves, or when it is absent and the
    target has no versions.
    """
    versions = [v for _i, v in _items(target, "versions")]
    if "target_version" in relationship:
        for version in versions:
            if version.get("id") == relationship["target_version"]:
                return True, timeline_of(version.get("timing"))
        return False, None
    if not versions:
        return True, timeline_of(target.get("timing"))
    return False, None


def _range_length(span, target_timeline):
    """REL-4: the exact range length on the target, or ``None`` when it has no end."""
    if "start_frame" in span:
        if "end_frame" not in span:
            return None
        frames = as_int(span["end_frame"]) - as_int(span["start_frame"])
        return target_timeline.frame_seconds(frames)
    if "start_seconds" in span and "end_seconds" in span:
        return _exact(span["end_seconds"]) - _exact(span["start_seconds"])
    return None


def _check_subclip(relationship, rel_path, holder_timeline, target_timeline):
    """REL-4: a ``subclip_of`` child length agrees with its range length on the target.

    The child length is the holder timeline length; with no length the check
    does not apply. The allowance is one frame duration of the slowest
    frame-form timeline among the target and the child, or 0 when neither is
    in the frame form. The lengths agree when they differ by less than the
    allowance, or are equal when the allowance is 0. The child length must be
    greater than 0. One finding, at the relationship.
    """
    if holder_timeline is None or holder_timeline.seconds is None:
        return []
    range_length = _range_length(relationship["range"], target_timeline)
    if range_length is None:
        return []
    child = holder_timeline.seconds
    frame_durations = [
        t.frame_duration() for t in (target_timeline, holder_timeline) if t is not None and t.frame_form
    ]
    allowance = max(frame_durations) if frame_durations else Fraction(0)
    difference = abs(child - range_length)
    agrees = difference < allowance if allowance else difference == 0
    if child <= 0 or not agrees:
        return [diagnostic("SUBCLIP_LENGTH_DISAGREES", rel_path)]
    return []


def _check_relationship(asset, relationship, rel_path, holder_timeline, context):
    """REL-3, REL-4, REL-6, TIME-4, and the target-timeline checks for one relationship.

    REL-3: ``target`` is not the asset's own id and resolves under PKG-6.
    TIME-4: a ``range`` ends after it starts, always. When ``target``
    resolves: a ``target_version`` names a version of the target
    (``VERSION_REFERENCE_UNRESOLVED``), and a ``range`` with no
    ``target_version`` on a target with versions is
    ``TARGET_VERSION_REQUIRED`` at the relationship. When the target timeline
    is known (REL-6), a range with frame fields on a timeline not in the
    frame form gives ``TIMELINE_UNDECLARED`` at the range; otherwise TIME-7,
    TIME-8, and TIME-9 apply on that timeline, and a ``subclip_of`` with an
    increasing range gets REL-4.
    """
    out = []
    target_id = relationship.get("target")
    target_path = pointer(rel_path, "target")
    if target_id == asset.get("id"):
        out.append(diagnostic("RELATIONSHIP_SELF", target_path))
    target = _resolve_into(out, context, "assets", target_id, target_path)
    span = relationship.get("range")
    range_path = pointer(rel_path, "range")
    order = _check_order(span, range_path) if isinstance(span, dict) else []
    out.extend(order)
    if target is None:
        return out
    has_versions = any(True for _ in _items(target, "versions"))
    if "target_version" in relationship:
        version_ids = {v.get("id") for _i, v in _items(target, "versions")}
        if relationship["target_version"] not in version_ids:
            out.append(diagnostic("VERSION_REFERENCE_UNRESOLVED", pointer(rel_path, "target_version")))
    elif isinstance(span, dict) and has_versions:
        out.append(diagnostic("TARGET_VERSION_REQUIRED", rel_path))
    if not isinstance(span, dict):
        return out
    known, target_timeline = _target_timeline(target, relationship)
    if not known:
        return out
    timeline_findings = _check_marker(span, range_path, target_timeline, range_path)
    out.extend(timeline_findings)
    undeclared = any(d.code == "TIMELINE_UNDECLARED" for d in timeline_findings)
    if relationship.get("type") == "subclip_of" and not order and not undeclared:
        out.extend(_check_subclip(relationship, rel_path, holder_timeline, target_timeline))
    return out


# Assets.

def _holders(asset, path):
    """Yield ``(holder, holder path, timeline)`` for each holder of an asset, in holder order.

    The asset level, then each version in array order, then ``unassigned``.
    The asset level has a timeline only when the asset has no versions.
    """
    versions = [(i, v) for i, v in _items(asset, "versions")]
    asset_timeline = None if versions else timeline_of(asset.get("timing"))
    yield asset, path, asset_timeline
    for i, version in versions:
        yield version, pointer(path, "versions", i), timeline_of(version.get("timing"))
    unassigned = asset.get("unassigned")
    if isinstance(unassigned, dict):
        yield unassigned, pointer(path, "unassigned"), None


def _check_nested_ids(asset, path):
    """ID-4: version ids are unique within the asset; file, file group, and
    annotation ids are unique across every holder. Each repeat after the first
    is reported, in holder order."""
    out = []
    seen = set()
    for i, version in _items(asset, "versions"):
        version_id = version.get("id")
        if version_id in seen:
            out.append(diagnostic("NESTED_ID_DUPLICATE", pointer(path, "versions", i, "id")))
        seen.add(version_id)
    seen_by_key = {"files": set(), "file_groups": set(), "annotations": set()}
    for holder, holder_path, _timeline in _holders(asset, path):
        for key, seen_ids in seen_by_key.items():
            for i, item in _items(holder, key):
                nested_id = item.get("id")
                if not isinstance(nested_id, str):
                    continue
                if nested_id in seen_ids:
                    out.append(diagnostic("NESTED_ID_DUPLICATE", pointer(holder_path, key, i, "id")))
                seen_ids.add(nested_id)
    return out


def _check_versions(asset, path):
    """VER-2 unique ordinals, VER-6 ``current_version``, and VER-7 one level per definition."""
    out = []
    seen = set()
    version_ids = set()
    for i, version in _items(asset, "versions"):
        version_ids.add(version.get("id"))
        ordinal = as_int(version["ordinal"])
        if ordinal in seen:
            out.append(diagnostic("ORDINAL_DUPLICATE", pointer(path, "versions", i, "ordinal")))
        seen.add(ordinal)
    if "current_version" in asset and asset["current_version"] not in version_ids:
        out.append(diagnostic("VERSION_REFERENCE_UNRESOLVED", pointer(path, "current_version")))
    asset_level = {item.get("definition") for _j, item in _items(asset, "metadata")}
    if asset_level:
        for holder, holder_path, _timeline in list(_holders(asset, path))[1:]:
            for j, item in _items(holder, "metadata"):
                if item.get("definition") in asset_level:
                    out.append(diagnostic(
                        "DEFINITION_SHARED_AND_VERSIONED", pointer(holder_path, "metadata", j, "definition")
                    ))
    return out


def _check_holder(asset, holder, holder_path, timeline, context):
    """The checks of one holder: files, file groups, stream facts, metadata,
    annotations, and relationships."""
    out = []
    files = {}
    for i, file in _items(holder, "files"):
        out.extend(_check_file(file, pointer(holder_path, "files", i), context))
        files.setdefault(file.get("id"), file)
    for i, group in _items(holder, "file_groups"):
        out.extend(_check_group(group, pointer(holder_path, "file_groups", i), files, timeline))
    out.extend(_check_stream_facts(holder, holder_path))
    out.extend(_check_metadata(holder, holder_path, context))
    for i, annotation in _items(holder, "annotations"):
        annotation_path = pointer(holder_path, "annotations", i)
        out.extend(_check_order(annotation, annotation_path))
        out.extend(_check_marker(annotation, annotation_path, timeline, pointer(annotation_path, "start_frame")))
        out.extend(_check_metadata(annotation, annotation_path, context))
    for i, relationship in _items(holder, "relationships"):
        out.extend(_check_relationship(
            asset, relationship, pointer(holder_path, "relationships", i), timeline, context
        ))
    out.extend(_check_relationship_duplicates(holder, holder_path))
    return out


def check_asset(asset, path: str, context) -> list:
    """Every check of one asset in its package.

    ID-4 nested ids; VER-2, VER-6, and VER-7; section 6 checks of each
    ``timing`` (the asset with no versions, and each version); then the
    checks of each holder (``_check_holder``).
    """
    out = []
    out.extend(_check_nested_ids(asset, path))
    out.extend(_check_versions(asset, path))
    if isinstance(asset.get("timing"), dict):
        out.extend(_check_timing(asset["timing"], pointer(path, "timing")))
    for i, version in _items(asset, "versions"):
        if isinstance(version.get("timing"), dict):
            out.extend(_check_timing(version["timing"], pointer(path, "versions", i, "timing")))
    for holder, holder_path, timeline in _holders(asset, path):
        out.extend(_check_holder(asset, holder, holder_path, timeline, context))
    return out


def check_collection(collection, path: str, context) -> list:
    """PKG-6 for ``storage.storage_location``, and MD-4 to MD-8 for the collection metadata."""
    out = []
    storage = collection.get("storage")
    if isinstance(storage, dict) and "storage_location" in storage:
        _resolve_into(
            out, context, "storage_locations", storage["storage_location"],
            pointer(path, "storage", "storage_location"),
        )
    out.extend(_check_metadata(collection, path, context))
    return out


def check_metadata_definition(record, path: str, context) -> list:
    """ID-4: option ids are unique within the definition."""
    out = []
    seen = set()
    for i, option in _items(record, "options"):
        option_id = option.get("id")
        if option_id in seen:
            out.append(diagnostic("NESTED_ID_DUPLICATE", pointer(path, "options", i, "id")))
        seen.add(option_id)
    return out


def check_storage_location(record, path: str, context) -> list:
    """A storage location has no semantic check. STO-2 and the producer parts of STO-3 are not checkable."""
    return []


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
        if registry in counts and as_int(counts[registry]) != len(package.get(registry, ())):
            out.append(diagnostic("COUNT_MISMATCH", pointer(path, "manifest", "counts", registry)))
    return out


def _check_ids(package, path):
    """ID-1 and ID-2: ids are unique within each record list; every repeat after the first is reported."""
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
    """Build the PackageContext from the first record of each id per record list."""
    registries = {}
    for registry in REGISTRIES:
        records = {}
        for _i, record in _items(package, registry):
            records.setdefault(record.get("id"), record)
        registries[registry] = records
    tokens = frozenset(d.get("token") for _i, d in _items(package["manifest"], "namespaces"))
    return PackageContext(namespaces=tokens, **registries)


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


def _extension_slots(package, path):
    """Yield ``(slot pointer, extensions object)`` for every ``extensions`` slot of the package (EXT-1).

    The walk follows the package tree and never descends into an extension
    value, which is payload. The schema allows ``extensions`` only at its
    slots, so every ``extensions`` member found is a slot. Explicit stack.
    """
    stack = [(package, path)]
    while stack:
        node, node_path = stack.pop()
        if isinstance(node, dict):
            for key, item in node.items():
                if key == "extensions":
                    if isinstance(item, dict):
                        yield pointer(node_path, key), item
                    continue
                stack.append((item, pointer(node_path, key)))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                stack.append((item, pointer(node_path, index)))


def _check_namespaces_used(package, path, context):
    """EXT-2: every namespace used in a slot is declared.

    One ``NAMESPACE_UNDECLARED`` per slot that holds any undeclared token, at
    the slot pointer. The value of a namespace is payload and is never
    descended into.
    """
    out = []
    for slot_path, extensions in _extension_slots(package, path):
        if any(token not in context.namespaces for token in extensions):
            out.append(diagnostic("NAMESPACE_UNDECLARED", slot_path))
    return out


def _member_of_entries(package, path):
    """Yield ``(owner path, owner id, list key, entry index, entry)`` for every ``member_of`` entry."""
    for registry in ("assets", "collections"):
        for i, record in _items(package, registry):
            record_path = pointer(path, registry, i)
            for j, entry in _items(record, "member_of"):
                yield registry, record_path, record.get("id"), j, entry


def _check_membership_references(package, path, context):
    """PKG-6 and COL-3: each ``member_of/<j>/collection`` resolves."""
    out = []
    for _registry, record_path, _owner, j, entry in _member_of_entries(package, path):
        _resolve_into(
            out, context, "collections", entry.get("collection"),
            pointer(record_path, "member_of", j, "collection"),
        )
    return out


def _strongly_connected(graph):
    """Return a map from node to component number, for the directed ``graph`` (Tarjan, iterative)."""
    index_of = {}
    low = {}
    on_stack = set()
    stack = []
    component = {}
    counter = 0
    next_component = 0
    for root in graph:
        if root in index_of:
            continue
        work = [(root, iter(graph.get(root, ())))]
        index_of[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, successors = work[-1]
            advanced = False
            for successor in successors:
                if successor not in graph:
                    continue
                if successor not in index_of:
                    index_of[successor] = low[successor] = counter
                    counter += 1
                    stack.append(successor)
                    on_stack.add(successor)
                    work.append((successor, iter(graph.get(successor, ()))))
                    advanced = True
                    break
                if successor in on_stack:
                    low[node] = min(low[node], index_of[successor])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component[member] = next_component
                    if member == node:
                        break
                next_component += 1
    return component


def _check_collection_cycles(package, path):
    """COL-4: membership among collections forms no cycle.

    Edges run from a collection id to each collection id that its
    ``member_of`` names. Every entry whose owner and target are one id, or
    lie in one strongly connected component, is on a cycle and gives
    ``COLLECTION_CYCLE`` at the entry.
    """
    graph = {}
    entries = []
    for i, collection in _items(package, "collections"):
        owner = collection.get("id")
        targets = graph.setdefault(owner, [])
        for j, entry in _items(collection, "member_of"):
            target = entry.get("collection")
            targets.append(target)
            entries.append((owner, target, pointer(path, "collections", i, "member_of", j)))
    component = _strongly_connected(graph)
    out = []
    for owner, target, entry_path in entries:
        if owner == target or (
            target in component and component.get(owner) == component[target]
        ):
            out.append(diagnostic("COLLECTION_CYCLE", entry_path))
    return out


def _check_positions(package, path):
    """COL-7: positions and repeated entries.

    All entries that name one collection, from assets and collections
    together, share one position scope. Positions compare by value. Every
    entry that shares a position with another gives ``POSITION_DUPLICATE``.
    When one ``member_of`` names a collection more than once and any of
    those entries has no ``position``, each entry for it after the first gives
    ``MEMBERSHIP_DUPLICATE``.
    """
    out = []
    scopes = {}
    lists = {}
    for _registry, record_path, _owner, j, entry in _member_of_entries(package, path):
        collection = entry.get("collection")
        entry_path = pointer(record_path, "member_of", j)
        if "position" in entry:
            key = (collection, as_int(entry["position"]))
            scopes.setdefault(key, []).append(entry_path)
        lists.setdefault((record_path, collection), []).append((entry_path, entry))
    for entry_paths in scopes.values():
        if len(entry_paths) > 1:
            out.extend(diagnostic("POSITION_DUPLICATE", p) for p in entry_paths)
    for named in lists.values():
        if len(named) > 1 and any("position" not in e for _p, e in named):
            out.extend(diagnostic("MEMBERSHIP_DUPLICATE", p) for p, _e in named[1:])
    return out


def check_package(package, path: str = "") -> list:
    """Run every semantic check of one package.

    PKG-3 counts; ID-1 and ID-2 ids per record list; EXT-2 declarations and
    used namespaces; COL-3 and PKG-6 membership references; COL-4 cycles;
    COL-7 positions; then each record with the package context. Diagnostics
    are sorted by ``(path, code)``.
    """
    out = []
    out.extend(_check_counts(package, path))
    out.extend(_check_ids(package, path))
    context = _build_context(package)
    out.extend(_check_declarations(package, path))
    out.extend(_check_namespaces_used(package, path, context))
    out.extend(_check_membership_references(package, path, context))
    out.extend(_check_collection_cycles(package, path))
    out.extend(_check_positions(package, path))
    for registry, record_check in _REGISTRY_CHECKS.items():
        for i, record in _items(package, registry):
            out.extend(record_check(record, pointer(path, registry, i), context))
    return _sorted(out)


def check(value, routing) -> list:
    """Run the semantic checks for a routed package.

    Runs nothing unless ``routing.status`` is ``selected``. Only a package
    routes (``REC-2``). Diagnostics are sorted by ``(path, code)``.
    """
    if routing.status != "selected":
        return []
    if routing.kind != "package":
        raise ValueError("routing selected no package")
    return check_package(value)
