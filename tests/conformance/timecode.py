"""Exact frame arithmetic and timecode label derivation (TIME-7, TIME-8).

Pure standard library arithmetic with ``Fraction`` and ``Decimal``. No
``float`` value is ever created and no I/O is done.

Seconds agreement (TIME-7): ``x = seconds * numerator / denominator`` as an
exact fraction, ``n = floor(x)``, ``r = x - n``. The nearest frame is
``n + 1`` when ``r > 1/2`` and ``n`` otherwise, so a tie at exactly one half
rounds toward zero (seconds are never negative).

Labels (TIME-8): ``fps`` is the integer frames per label second from
``LABEL_RATES``. ``skip`` is the count of labels skipped at the start of each
minute that is not a multiple of 10: 2 at 30000/1001 and 4 at 60000/1001 when
drop frame applies, otherwise 0. With ``M = hh*60 + mm``:

- non-drop index: ``(M*60 + ss)*fps + ff``
- drop index: the non-drop index ``- skip * (M - M // 10)``
- day length in labels: ``24*3600*fps - skip*(1440 - 144)``

A label is derived as ``index_to_label((label_to_index(anchor) + offset) %
day_length)``.
"""

import math
import re
from decimal import Decimal
from fractions import Fraction

__all__ = ["DROP_SKIP", "LABEL_RATES", "derive_label", "index_to_label", "label_to_index", "nearest_frame"]

LABEL_RATES = {  # (numerator, denominator): frames per label second
    (24, 1): 24, (24000, 1001): 24, (25, 1): 25, (30, 1): 30, (30000, 1001): 30,
    (48, 1): 48, (50, 1): 50, (60, 1): 60, (60000, 1001): 60,
}
DROP_SKIP = {(30000, 1001): 2, (60000, 1001): 4}

_LABEL = re.compile(r"([0-9]{2}):([0-9]{2}):([0-9]{2})([:;])([0-9]{2})", re.ASCII)


def _exact(seconds):
    """Return ``seconds`` (``int`` or finite ``Decimal``) as an exact ``Fraction``."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, Decimal)):
        raise TypeError("seconds must be an int or a Decimal")
    if isinstance(seconds, Decimal):
        if not seconds.is_finite():
            raise ValueError("seconds must be finite")
        num, den = seconds.as_integer_ratio()
        return Fraction(num, den)
    return Fraction(seconds, 1)


def nearest_frame(seconds, numerator, denominator):
    """Return the frame nearest to ``seconds * numerator / denominator``.

    ``x`` is exact; ``n = floor(x)``, ``r = x - n``; the result is ``n + 1``
    when ``r > 1/2``, else ``n``. A tie at exactly one half rounds toward zero.
    """
    x = _exact(seconds) * numerator / denominator
    n = math.floor(x)
    return n + 1 if x - n > Fraction(1, 2) else n


def _day_length(fps, skip):
    return 24 * 3600 * fps - skip * (1440 - 144)


def label_to_index(label, fps, skip):
    """Return the label index counted from ``00:00:00:00``.

    Non-drop: ``((hh*60 + mm)*60 + ss)*fps + ff``. Drop (``skip > 0``): with
    ``M = hh*60 + mm``, the non-drop value ``- skip * (M - M // 10)``. The
    separator before the frames must be ``;`` for drop and ``:`` for non-drop.
    Raises ``ValueError`` for bad syntax, out-of-range fields, or a label that
    names a skipped drop-frame label.
    """
    match = _LABEL.fullmatch(label) if isinstance(label, str) else None
    if match is None:
        raise ValueError(f"not a timecode label: {label!r}")
    hh, mm, ss, sep, ff = match.groups()
    hh, mm, ss, ff = int(hh), int(mm), int(ss), int(ff)
    if sep != (";" if skip else ":"):
        raise ValueError(f"separator does not match the drop-frame mode: {label!r}")
    if hh > 23 or mm > 59 or ss > 59 or ff >= fps:
        raise ValueError(f"timecode field out of range: {label!r}")
    minutes = hh * 60 + mm
    if skip and ss == 0 and ff < skip and mm % 10 != 0:
        raise ValueError(f"label names a skipped drop-frame label: {label!r}")
    return (minutes * 60 + ss) * fps + ff - skip * (minutes - minutes // 10)


def index_to_label(index, fps, skip):
    """Return the label for ``index`` taken modulo the day length.

    Inverse of ``label_to_index``. For drop frame, each 10-minute block holds
    ``600*fps - 9*skip`` labels: its first minute holds ``60*fps`` labels and
    each of the other nine holds ``60*fps - skip`` labels that start at frame
    label ``skip``.
    """
    index %= _day_length(fps, skip)
    minute_labels = 60 * fps
    if skip:
        block_labels = 10 * minute_labels - 9 * skip
        block, rest = divmod(index, block_labels)
        if rest < minute_labels:
            minute_in_block, within = 0, rest
        else:
            extra, within = divmod(rest - minute_labels, minute_labels - skip)
            minute_in_block, within = 1 + extra, within + skip
        minutes = block * 10 + minute_in_block
    else:
        minutes, within = divmod(index, minute_labels)
    ss, ff = divmod(within, fps)
    hh, mm = divmod(minutes, 60)
    sep = ";" if skip else ":"
    return f"{hh:02d}:{mm:02d}:{ss:02d}{sep}{ff:02d}"


def derive_label(anchor, offset_frames, numerator, denominator, drop_frame):
    """Return the label ``offset_frames`` labels after ``anchor``, modulo 24 hours.

    ``fps = LABEL_RATES[(numerator, denominator)]``; ``skip`` is
    ``DROP_SKIP[(numerator, denominator)]`` when ``drop_frame`` else 0. The
    result is ``index_to_label((label_to_index(anchor) + offset_frames) %
    day_length)``, with ``;`` before the frames for drop and ``:`` otherwise.
    Raises ``ValueError`` for a rate outside ``LABEL_RATES``, for drop frame at
    a rate that does not allow it, and for an invalid or skipped anchor.
    """
    rate = (numerator, denominator)
    if rate not in LABEL_RATES:
        raise ValueError(f"labels are not defined at rate {numerator}/{denominator}")
    fps = LABEL_RATES[rate]
    if drop_frame:
        if rate not in DROP_SKIP:
            raise ValueError(f"drop frame is not allowed at rate {numerator}/{denominator}")
        skip = DROP_SKIP[rate]
    else:
        skip = 0
    index = (label_to_index(anchor, fps, skip) + offset_frames) % _day_length(fps, skip)
    return index_to_label(index, fps, skip)
