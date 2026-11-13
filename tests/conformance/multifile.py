"""The check of a multi-file package: member rules, folder scan, member reader, and the whole run.

``evaluate_folder`` checks one package folder from its manifest file and
returns one result record (``form`` is ``multi-file``). It uses the parts
below. Its stage order is on the function.

Two functions check the manifest file against itself and against the folder.
Neither reads the contents of a member file.

``check_member_list`` works on the parsed manifest root alone: duplicate
and case-colliding paths, a ``record_type`` that does not match the path,
declared counts that do not add up, empty members, and many small members.

``scan_folder`` compares the member list with the package folder. It uses
only ``os.lstat`` and ``os.scandir``. It never follows a symbolic link and
never opens a file (``SAFE-1``). A link, or anything that is not a regular
file or a regular folder, is reported where it stands and is not entered.

Where a finding is located:

- A finding about one member entry has ``member`` set to the manifest index
  and no ``line``. Its ``path`` is the full JSON Pointer into the manifest
  file, for example ``/manifest/members/3/path``. Without a ``line``, a
  ``path`` always points into the manifest file; with a ``line`` it points
  into the record on that line.
- A finding about a whole list has no ``member``: ``COUNT_MISMATCH`` is at
  ``/manifest/counts/<list>`` and ``MEMBERS_SMALL`` is at ``/manifest/members``.
- A finding about a file that the manifest does not list has ``unlisted_path``
  (relative to the package folder, with ``/``) and the empty ``path``.
- A finding about the contents of one member file as a whole
  (``MEMBER_LINE_INVALID``) has ``member`` set, no ``line``, and the empty
  ``path``.
- A finding on a line of a member file has ``member`` and ``line`` set, and
  its ``path`` points into the record on that line.

Messages are the fixed catalog text. A member path is never put in a message.

``MemberReader`` reads one member file once. It yields the lines, hashes the
stored bytes, and notes line framing and compression problems on the way.
Its rules are on the class.
"""

import contextlib
import errno
import hashlib
import os
import shutil
import signal
import sqlite3
import stat
import tempfile
import threading
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from tests.conformance.number_limits import check_number_limits
from tests.conformance.package_check import PackageChecker, Where
from tests.conformance.semantic import REGISTRIES, as_int, diagnostic, pointer
from tests.conformance.strict_json import parse_input
from tests.conformance.types import Diagnostic, InputInvalid, SetupFailed

__all__ = [
    "FINDINGS_NAME",
    "FINDINGS_PER_MEMBER",
    "MANIFEST_NAME",
    "RECORD_FOLDERS",
    "STORE_NAME",
    "LimitExceeded",
    "MemberNotRegular",
    "MemberReader",
    "ReadLimits",
    "check_member_list",
    "evaluate_folder",
    "has_members",
    "scan_folder",
]

MANIFEST_NAME = "oasis-package.json"
RECORD_FOLDERS = REGISTRIES

# The working files of ``evaluate_folder`` in the work folder: the store of
# the semantic stage, and the findings of the other read stages.
STORE_NAME = "store.sqlite"
FINDINGS_NAME = "findings.sqlite"

# A list with several member files and fewer records than this in each, on average, gets a warning.
_SMALL_AVERAGE = 1000

# Folder states for the ancestors of a member path.
_FOLDER, _ABSENT, _OTHER = "folder", "absent", "other"


def _member_field(index: int, field: str) -> str:
    """The pointer to a field of member entry ``index`` in the manifest file."""
    return pointer("", "manifest", "members", index, field)


def _located(code: str, index: int, field: str) -> Diagnostic:
    """The catalog diagnostic for ``code`` at a field of member entry ``index``, with ``member`` set."""
    return replace(diagnostic(code, _member_field(index, field)), member=index)


def check_member_list(root: dict) -> list[Diagnostic]:
    """Check the member list of a manifest root, without touching the disk.

    ``root`` is a parsed manifest file that passed the package schema, so
    every member entry has all five fields. The findings come in this order:
    path duplicates, case collisions, and type mismatches, by entry; then
    unexpected empty members, by entry; then ``COUNT_MISMATCH`` and
    ``MEMBERS_SMALL`` for each list in record list order. A repeat of an
    exact path is a duplicate only, not also a case collision.
    """
    manifest = root["manifest"]
    members = manifest["members"]
    found = []

    first_exact = set()
    first_folded = set()
    for index, member in enumerate(members):
        path = member["path"]
        folded = path.casefold()
        if path in first_exact:
            found.append(_located("MEMBER_PATH_DUPLICATE", index, "path"))
        elif folded in first_folded:
            found.append(_located("MEMBER_PATH_CASE_COLLISION", index, "path"))
        first_exact.add(path)
        first_folded.add(folded)
        if member["record_type"] != path.split("/", 1)[0]:
            found.append(_located("MEMBER_TYPE_MISMATCH", index, "record_type"))

    totals = dict.fromkeys(REGISTRIES, 0)
    sizes = dict.fromkeys(REGISTRIES, 0)
    for member in members:
        totals[member["record_type"]] += as_int(member["count"])
        sizes[member["record_type"]] += 1

    for index, member in enumerate(members):
        if as_int(member["count"]) == 0 and totals[member["record_type"]] > 0:
            found.append(_located("MEMBER_EMPTY_UNEXPECTED", index, "count"))

    counts = manifest["counts"]
    for registry in REGISTRIES:
        if registry in counts and as_int(counts[registry]) != totals[registry]:
            found.append(diagnostic("COUNT_MISMATCH", pointer("", "manifest", "counts", registry)))
        if sizes[registry] >= 2 and totals[registry] < _SMALL_AVERAGE * sizes[registry]:
            found.append(diagnostic("MEMBERS_SMALL", pointer("", "manifest", "members")))
    return found


def _safe_segments(segments: list) -> bool:
    """True when every segment stays inside the package folder when joined to it.

    The schema already limits the characters of a path. This check keeps the
    scan inside the folder even for a root that did not pass the schema.
    """
    return all(s not in ("", ".", "..") and "\\" not in s and "\0" not in s for s in segments)


def _folder_state(package_dir: str, relative: str, cache: dict) -> str:
    """Classify the entry at ``relative`` with ``os.lstat``: a real folder, absent, or something else.

    A link counts as something else, whatever it points at.
    """
    state = cache.get(relative)
    if state is None:
        try:
            mode = os.lstat(os.path.join(package_dir, *relative.split("/"))).st_mode
        except (FileNotFoundError, NotADirectoryError):
            state = _ABSENT
        else:
            state = _FOLDER if stat.S_ISDIR(mode) else _OTHER
        cache[relative] = state
    return state


def _check_member(package_dir: str, index: int, member: dict, cache: dict) -> list[Diagnostic]:
    """Check one member entry against the disk. No link is followed."""
    segments = member["path"].split("/")
    if not _safe_segments(segments):
        return [_located("MEMBER_NOT_REGULAR", index, "path")]
    for depth in range(1, len(segments)):
        state = _folder_state(package_dir, "/".join(segments[:depth]), cache)
        if state != _FOLDER:
            return [_located("MEMBER_MISSING" if state == _ABSENT else "MEMBER_NOT_REGULAR", index, "path")]
    try:
        info = os.lstat(os.path.join(package_dir, *segments))
    except (FileNotFoundError, NotADirectoryError):
        return [_located("MEMBER_MISSING", index, "path")]
    if not stat.S_ISREG(info.st_mode):
        return [_located("MEMBER_NOT_REGULAR", index, "path")]
    if info.st_size != as_int(member["size_bytes"]):
        return [_located("MEMBER_SIZE_MISMATCH", index, "size_bytes")]
    return []


def _known_paths(members: list) -> set:
    """Every listed member path and every folder above one."""
    known = set()
    for member in members:
        segments = member["path"].split("/")
        for depth in range(1, len(segments) + 1):
            known.add("/".join(segments[:depth]))
    return known


def _display_name(relative: str) -> str:
    """Return ``relative`` as valid Unicode: a byte that is not UTF-8 shows as ``\\xNN``."""
    return os.fsencode(relative).decode("utf-8", "backslashreplace")


def _unlisted(package_dir: str, known: set) -> list[Diagnostic]:
    """Walk the package folder and report every entry that is not a folder and not known.

    A real folder is entered. A link is never entered, whatever it points at:
    it is reported as one entry. An entry that is listed, or that sits above a
    listed member, is skipped, because the member check reports it. The
    manifest file in the package folder is skipped.
    """
    found = []
    stack = [("", package_dir, False)]
    while stack:
        relative, folder, in_record = stack.pop()
        with os.scandir(folder) as entries:
            children = sorted(entries, key=lambda e: e.name)
        for child in children:
            child_relative = f"{relative}/{child.name}" if relative else child.name
            child_in_record = in_record or (not relative and child.name in RECORD_FOLDERS)
            if child.is_dir(follow_symlinks=False):
                stack.append((child_relative, child.path, child_in_record))
            elif child_relative in known or (not relative and child.name == MANIFEST_NAME):
                continue
            else:
                code = "MEMBER_UNLISTED" if in_record else "FILE_UNLISTED"
                found.append(replace(diagnostic(code, ""), unlisted_path=_display_name(child_relative)))
    return sorted(found, key=lambda d: d.unlisted_path)


def scan_folder(package_dir: Path, root: dict) -> list[Diagnostic]:
    """Compare the member list of ``root`` with the folder ``package_dir``, without reading contents.

    Each member is checked with ``os.lstat``, one folder at a time from the
    top: a link, a folder that is not a real folder, or a member that is not
    a regular file gives ``MEMBER_NOT_REGULAR``; absence gives
    ``MEMBER_MISSING``; a size different from ``size_bytes`` gives
    ``MEMBER_SIZE_MISMATCH``. A check stops at the first link or odd entry, so
    nothing behind a link is touched. The findings come in manifest order.

    Then a walk with ``os.scandir`` finds entries that the manifest does not
    list: ``MEMBER_UNLISTED`` inside a record folder, ``FILE_UNLISTED``
    elsewhere. The walk enters real folders only. A link in the walk is
    reported as one unlisted entry, not entered. The unlisted findings come
    last, sorted by path. An unreadable folder or file raises ``OSError``.
    """
    base = os.fspath(package_dir)
    members = root["manifest"]["members"]
    found = []
    cache = {}
    for index, member in enumerate(members):
        found.extend(_check_member(base, index, member, cache))
    found.extend(_unlisted(base, _known_paths(members)))
    return found


# The size of one read of stored bytes, and the most that one step of decompression returns.
READ_BLOCK = 1024 * 1024

# Decompressed bytes allowed beyond ``max_gzip_ratio`` times the stored bytes.
_RATIO_ALLOWANCE = 1024 * 1024

_GZIP_MAGIC = b"\x1f\x8b"
_BOM = b"\xef\xbb\xbf"

# The framing problems, in the fixed order of ``MemberReader.framing``.
_FRAMING_ORDER = ("compression", "cr", "blank", "bom", "whitespace", "no_final_lf", "gzip_stream")

# A line may not start or end with one of these bytes: space (0x20) and tab (0x09).
_SPACE_OR_TAB = (0x20, 0x09)

# Fixed texts: a limit failure never repeats the limit, the path, or any content.
_LINE_LIMIT_MESSAGE = "a member file line is longer than the line length limit"
_RATIO_LIMIT_MESSAGE = "a member file expands beyond the decompression ratio limit"


class LimitExceeded(SetupFailed):
    """A member file passed a reader limit. This is a checker setting, not a conformance finding."""


class MemberNotRegular(OSError):
    """At open time, a member path is a link or names something that is not a regular file."""


# Open flags of a member file: never follow a link at the last step, and never wait on a pipe.
_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)

# Open flags of a folder above a member file: a real folder only, never a link.
_FOLDER_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


@dataclass(frozen=True)
class ReadLimits:
    """The two limits of ``MemberReader``.

    ``max_line_bytes`` is the longest line that is accepted, not counting the
    LF. ``max_gzip_ratio`` sets how far a gzip stream may expand: decompressed
    bytes may not pass ``max_gzip_ratio`` times the stored bytes read so far,
    plus 1 MiB.
    """

    max_line_bytes: int = 67_108_864
    max_gzip_ratio: int = 1000


class MemberReader:
    """Read one member file once: its lines, its SHA-256, its framing problems.

    ``lines()`` yields ``(number, line)`` for each line, with 1-based numbers
    and the line as bytes without its LF. It reads the file in blocks of
    ``READ_BLOCK`` bytes, so memory stays near ``max_line_bytes`` plus one
    block, whatever the size of the file. The caller must exhaust the
    iterator. Then these attributes are final:

    - ``sha256``: lowercase hex digest of the stored bytes (the gzip bytes of
      a ``.jsonl.gz`` file), taken as they are read.
    - ``stored_bytes``: the number of stored bytes read.
    - ``line_count``: the number of lines yielded.
    - ``framing``: the problems found, each once, in this fixed order:
      ``"compression"``, ``"cr"``, ``"blank"``, ``"bom"``, ``"whitespace"``,
      ``"no_final_lf"``, ``"gzip_stream"``. An empty list means the file is sound.

    After an exception these attributes are not meaningful. A file that
    cannot be opened or read raises ``OSError``. The file is opened with
    ``O_NOFOLLOW`` where the platform has it, and with ``O_NONBLOCK``, so a
    pipe never blocks the read. A link at the member path, or anything that
    is not a regular file, raises ``MemberNotRegular`` (an ``OSError``).

    ``hash_only()`` reads the file once for ``sha256`` and ``stored_bytes``
    only. It yields no line and checks no framing, so ``line_count`` stays 0
    and ``framing`` stays empty.

    Compression comes from the stored bytes: they are gzip when they start
    with ``1F 8B``. ``gzip_expected`` says what the file name claims. When
    the two differ, ``framing`` is ``["compression"]``, no line is yielded,
    and the rest of the file is only hashed (a 0-byte file is not gzip). A
    gzip stream is decoded with ``zlib.decompressobj(wbits=31)``; several
    members joined in one file read as one stream. A stream that is bad,
    cut off, or followed by any other byte gives ``"gzip_stream"``. The
    reader then yields no more lines, drops the unfinished last line, and
    hashes the rest of the file. Which lines come out before the error
    depends on the block size; they are always a start of the true lines.

    Line rules apply to the decompressed bytes. Lines are yielded as they are,
    with any CR or BOM still in them:

    - ``"cr"``: a CR byte anywhere, also before the LF.
    - ``"blank"``: a line with no bytes.
    - ``"bom"``: the content starts with ``EF BB BF``. Only the start counts.
    - ``"whitespace"``: the first or last byte of a line is a space or a
      tab, so there is whitespace before or after the JSON value. A CR is
      ``"cr"`` only.
    - ``"no_final_lf"``: the content is not empty and its last byte is not
      LF. The unfinished last line is yielded and counted as a line.

    A 0-byte plain file, and a gzip stream with no content, give no lines
    and no problem.

    Two limits raise ``LimitExceeded`` and stop the read: a line longer than
    ``max_line_bytes``, and decompressed bytes above ``max_gzip_ratio`` times
    the stored bytes read so far plus 1 MiB. The reader never decompresses
    more than one byte past that allowance.
    """

    def __init__(self, path: Path, gzip_expected: bool, limits: ReadLimits, base: Path | None = None):
        self.path = path
        self.base = base
        self.gzip_expected = gzip_expected
        self.limits = limits
        self._reset()

    def _reset(self) -> None:
        self.sha256 = ""
        self.stored_bytes = 0
        self.line_count = 0
        self.framing: list[str] = []
        self._found: set[str] = set()
        self._tail = bytearray()  # the start of a line whose LF has not come yet
        self._head = b""  # the first (up to) three content bytes, for the BOM check
        self._inflater = None  # the gzip member being read, or None between members
        self._produced = 0  # decompressed bytes so far

    @property
    def line_rules_failed(self) -> bool:
        """True once the lines read so far break a line rule. The member then fails its integrity check."""
        return not self._found.isdisjoint(_LINE_PROBLEMS)

    def _open(self):
        if self.base is None:
            return _open_regular(self.path)
        return _open_beneath(self.base, Path(self.path).relative_to(self.base).parts)

    def hash_only(self) -> None:
        """Read the file once for ``sha256`` and ``stored_bytes`` only. See the class text."""
        self._reset()
        digest = hashlib.sha256()
        with self._open() as source:
            while block := source.read(READ_BLOCK):
                self.stored_bytes += len(block)
                digest.update(block)
        self.sha256 = digest.hexdigest()

    def lines(self) -> Iterator[tuple[int, bytes]]:
        """Read the file once and yield ``(number, line)``. See the class text for the rules."""
        self._reset()
        digest = hashlib.sha256()
        with self._open() as source:
            block = source.read(READ_BLOCK)
            while len(block) < len(_GZIP_MAGIC):
                more = source.read(READ_BLOCK)
                if not more:
                    break
                block += more
            is_gzip = block.startswith(_GZIP_MAGIC)
            live = is_gzip == self.gzip_expected
            if not live:
                self._found.add("compression")
            while block:
                self.stored_bytes += len(block)
                digest.update(block)
                if live:
                    try:
                        for piece in self._inflate(block) if is_gzip else (block,):
                            yield from self._split(piece)
                    except zlib.error:
                        self._found.add("gzip_stream")
                        self._tail.clear()
                        live = False
                block = source.read(READ_BLOCK)
        if live and is_gzip and self._inflater is not None:
            self._found.add("gzip_stream")  # the stream ends inside a member
            self._tail.clear()
        last = bytes(self._tail)
        if last:
            self._found.add("no_final_lf")
            self._check_ends(last)
            self.line_count += 1
        self.sha256 = digest.hexdigest()
        self.framing = [kind for kind in _FRAMING_ORDER if kind in self._found]
        if last:
            yield self.line_count, last

    def _inflate(self, block: bytes) -> Iterator[bytes]:
        """Decompress one stored block. Raise ``zlib.error`` for a bad stream, ``LimitExceeded`` for a bomb."""
        ratio = self.limits.max_gzip_ratio
        pending = block
        while pending:
            if self._inflater is None:
                self._inflater = zlib.decompressobj(wbits=31)
            inflater = self._inflater
            while True:
                # Ask for one byte more than the allowance, so that a bomb is seen and not unpacked.
                allowance = ratio * self.stored_bytes + _RATIO_ALLOWANCE - self._produced
                want = min(READ_BLOCK, allowance + 1)
                piece = inflater.decompress(pending, want)
                self._produced += len(piece)
                if len(piece) > allowance:
                    raise LimitExceeded(_RATIO_LIMIT_MESSAGE)
                if piece:
                    yield piece
                if inflater.eof:
                    break
                pending = inflater.unconsumed_tail
                if len(piece) < want:
                    pending = b""  # all input used and no output waiting
                    break
            if not inflater.eof:
                return
            pending = inflater.unused_data
            self._inflater = None

    def _split(self, piece: bytes) -> Iterator[tuple[int, bytes]]:
        """Check the framing of ``piece`` and yield the lines that it completes."""
        if len(self._head) < len(_BOM):
            self._head += piece[: len(_BOM) - len(self._head)]
            if self._head == _BOM:
                self._found.add("bom")
        if b"\r" in piece:
            self._found.add("cr")
        limit = self.limits.max_line_bytes
        parts = piece.split(b"\n")
        rest = parts.pop()  # the bytes after the last LF
        if not parts:
            if len(self._tail) + len(rest) > limit:
                raise LimitExceeded(_LINE_LIMIT_MESSAGE)
            self._tail += rest
            return
        if self._tail:
            parts[0] = bytes(self._tail) + parts[0]
            self._tail.clear()
        for line in parts:
            if len(line) > limit:
                raise LimitExceeded(_LINE_LIMIT_MESSAGE)
            if not line:
                self._found.add("blank")
            else:
                self._check_ends(line)
            self.line_count += 1
            yield self.line_count, line
        if len(rest) > limit:
            raise LimitExceeded(_LINE_LIMIT_MESSAGE)
        self._tail += rest

    def _check_ends(self, line: bytes) -> None:
        """Note ``"whitespace"`` when a line that is not empty starts or ends with a space or a tab."""
        if line[0] in _SPACE_OR_TAB or line[-1] in _SPACE_OR_TAB:
            self._found.add("whitespace")


def _open_regular(path, dir_fd=None):
    """Open ``path`` for reading with ``_OPEN_FLAGS``. Refuse a link or a file that is not regular.

    A link at the last step of the path, or anything that is not a regular
    file, raises ``MemberNotRegular``. Any other failure raises ``OSError``.
    With ``dir_fd``, ``path`` is one name inside that open folder.
    """
    try:
        fd = os.open(path, _OPEN_FLAGS, dir_fd=dir_fd)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise MemberNotRegular(errno.ELOOP, "the path is a link") from None
        raise
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise MemberNotRegular("the path is not a regular file")
    except BaseException:
        os.close(fd)
        raise
    return open(fd, "rb")


def _open_beneath(base, parts):
    """Open the member at ``parts`` inside the folder ``base``, one step at a time.

    Each folder step is opened inside the one before it, with ``O_NOFOLLOW``,
    so a link that replaces a folder after the scan is refused, not followed
    (``SAFE-1``). A step that is a link or not a folder raises
    ``MemberNotRegular``. ``base`` is the caller's own input and may be a link.
    Where the platform cannot open relative to a folder, the whole path is
    opened, and only its last step is protected.
    """
    if os.open not in os.supports_dir_fd:
        return _open_regular(Path(base, *parts))
    folder = os.open(base, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        for part in parts[:-1]:
            try:
                inner = os.open(part, _FOLDER_FLAGS, dir_fd=folder)
            except OSError as error:
                if error.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise MemberNotRegular(error.errno, "a folder of the path is a link or not a folder") from None
                raise
            os.close(folder)
            folder = inner
        return _open_regular(parts[-1], dir_fd=folder)
    finally:
        os.close(folder)


def has_members(root) -> bool:
    """True when ``root`` is an object whose ``manifest`` object has ``members``: the multi-file form."""
    manifest = root.get("manifest") if isinstance(root, dict) else None
    return isinstance(manifest, dict) and "members" in manifest


_UNREADABLE_MEMBER = "Setup failed: a member file cannot be read."
_WORK_FILES = "Setup failed: the checker cannot write its working files in the work folder."
_FINDINGS_CAPPED = (
    "Findings were capped: the result lists at most 1000 findings of each member file, and the rest are not listed."
)

# The most findings of one stage kept for one member file. Later ones are left out,
# so the findings store and the result stay bounded for a small file with many bad lines.
FINDINGS_PER_MEMBER = 1000

# The stages of the read, in outcome order. The lowest stage with a finding decides.
_INTEGRITY, _PARSE, _LIMITS, _STRUCTURE, _SEMANTIC = range(5)

_STREAM_PROBLEMS = frozenset({"compression", "gzip_stream"})
_LINE_PROBLEMS = frozenset({"cr", "blank", "bom", "whitespace", "no_final_lf"})

_FINDINGS_PRAGMAS = (
    "PRAGMA journal_mode=OFF",
    "PRAGMA synchronous=OFF",
    "PRAGMA temp_store=FILE",
    "PRAGMA cache_size=-65536",
)
# One row per finding. A structural error has ``keyword`` and no ``code``; any other finding has ``code``.
_FINDINGS_TABLE = (
    "CREATE TABLE findings (stage INTEGER NOT NULL, member INTEGER NOT NULL, line INTEGER,"
    " path TEXT NOT NULL, code TEXT, keyword TEXT)"
)
_STAGE_FINDINGS = "SELECT member, line, path, code, keyword FROM findings WHERE stage = ?"


class _Stop(Exception):
    """A setup failure during the read. ``limitation`` is the fixed text for the result record."""

    def __init__(self, limitation: str):
        super().__init__(limitation)
        self.limitation = limitation


def _errors(found: list) -> list:
    return [d for d in found if d.severity == "error"]


def evaluate_folder(
    manifest_path: Path, definitions: Path, work_dir: Path | None, limits: ReadLimits, *, from_folder: bool = False
) -> dict:
    """Check the multi-file package of ``manifest_path``; return one result record.

    ``definitions`` is the schema bundle folder, as ``root`` in
    ``validate.evaluate``. The package folder is the folder of the manifest
    file. The record has ``form`` ``multi-file`` and the ``input_sha256`` of
    the manifest file bytes; ``file`` is ``None`` (``main`` fills it).

    ``from_folder`` is true when the caller named the package folder, so
    ``manifest_path`` is ``<folder>/oasis-package.json``. The manifest file
    is then opened as a member file is: never through a link, never a pipe
    or another special file (``SAFE-1``). Such a file gives the setup failure
    ``Setup failed: input file cannot be read.`` When ``from_folder`` is
    false, the caller named the manifest file, which is the caller's own
    input and may be a link; the package folder is the parent of the path
    as given.

    The first stage that fails decides the outcome, and only its findings
    are reported:

    1. The manifest file: setup, parse, route, number limits, and structure,
       with the same outcomes as a single document. A manifest root without
       ``manifest.members`` is a single document: the result is that of
       ``validate.evaluate``.
    2. The member rules (``check_member_list``) and ``MANIFEST_FILE_NAME``:
       an error gives ``complete``, structure ``valid``, semantic ``run``.
    3. The folder scan (``scan_folder``): an error gives ``input-invalid``.
    4. The read. Members are read by record list in ``REGISTRIES`` order, and
       in manifest order inside each list, so "first" follows the manifest.
       Each member is read once. Every line runs the record stages: parse
       (``INPUT_INVALID``), number limits, structure (the record entry point),
       and semantic (``PackageChecker``, with ``Where(member, line, "")``).
       A stage after the earliest failed stage cannot change the outcome, so
       it is not run. Once a line of a member breaks a line rule, the member
       fails its integrity check, so its later lines run no record stage.
       At the end of each member its integrity is checked:
       size, checksum, compression, line rules, and line count. After the
       first integrity failure every later member is only hashed, so every
       damaged member is reported and no record stage runs.

       The earliest failed stage decides: integrity, parse, or number limits
       give ``input-invalid``; structure gives ``complete`` and structure
       ``invalid``, with ``structural_errors`` located by member and line;
       otherwise the semantic stage runs ``finish`` and gives ``complete``,
       structure ``valid``, semantic ``run``. Warnings of the member rules
       and of the scan (``MEMBERS_SMALL``, ``FILE_UNLISTED``) are reported
       only then.

    For each member file, at most ``FINDINGS_PER_MEMBER`` findings of one
    stage are kept. When the deciding stage had more, the result lists the
    first ones of each member and has the limitation ``_FINDINGS_CAPPED``.

    Setup failures outrank every finding. A member file or a folder that
    cannot be read gives the fixed limitation ``Setup failed: a member file
    cannot be read.``; a reader limit gives the text of ``LimitExceeded``.

    The findings of the read stages are kept in ``FINDINGS_NAME`` and the
    semantic store in ``STORE_NAME``, both in the work folder, so memory does
    not grow with the number of lines. SQLite temporary files go there too.
    ``work_dir`` names the work folder; it is made when absent, and the two
    files stay there after the run. When ``work_dir`` is ``None``, a new
    folder from ``tempfile.mkdtemp`` is used and removed at the end, also
    when the process gets SIGTERM during the read.
    """
    # validate imports this module, so the import waits until the first call.
    from tests.conformance import validate

    manifest_path = Path(manifest_path)
    try:
        if from_folder:
            with _open_regular(manifest_path) as source:
                data = source.read()
        else:
            data = manifest_path.read_bytes()
    except OSError:
        data = None
    record = validate._blank_record(data)
    record["form"] = validate.FORM_MULTI
    if data is None:
        return validate._setup_failed(record, validate._UNREADABLE_INPUT)
    stages = validate._document_stages(record, data, definitions)
    if stages is None:
        return record
    bundle, parsed, _routing = stages
    root = parsed.value
    if not has_members(root):
        return validate.evaluate(data, definitions)

    rules = check_member_list(root)
    if manifest_path.name != MANIFEST_NAME:
        rules.append(diagnostic("MANIFEST_FILE_NAME", ""))
    if _errors(rules):
        record["execution_status"] = "complete"
        record["structural"] = "valid"
        record["semantic"] = "run"
        validate.assign_diagnostics(record, _errors(rules))
        return record

    package_dir = manifest_path.parent
    try:
        scanned = scan_folder(package_dir, root)
    except OSError:
        return validate._setup_failed(record, _UNREADABLE_MEMBER)
    if _errors(scanned):
        record["execution_status"] = "input-invalid"
        validate.assign_diagnostics(record, _errors(scanned))
        return record

    def reduce_error(error):
        return validate.safe_pointer(error), validate.schema_keyword(error)

    try:
        stage, found, capped = _read_package(package_dir, root, bundle, work_dir, limits, reduce_error)
    except _Stop as stop:
        return validate._setup_failed(record, stop.limitation)
    except RecursionError:
        return validate._setup_failed(record, validate._SEMANTIC_NESTING)
    if stage == _SEMANTIC:
        record["execution_status"] = "complete"
        record["structural"] = "valid"
        record["semantic"] = "run"
        # Only warnings are left in the member rules and the scan here.
        validate.assign_diagnostics(record, rules + scanned + found)
    elif stage == _STRUCTURE:
        record["execution_status"] = "complete"
        record["structural"] = "invalid"
        record["structural_errors"] = validate.cap_entries(record, validate._structural_records(found))
    else:
        record["execution_status"] = "input-invalid"
        validate.assign_diagnostics(record, found)
    if capped:
        validate.add_limitation(record, _FINDINGS_CAPPED)
    return record


def _read_package(package_dir, root, bundle, work_dir, limits, reduce_error):
    """Read every member file once; return ``(stage, findings, capped)`` of the earliest failed stage.

    For ``_STRUCTURE`` the findings are ``(path, keyword, member, line)``
    items; for any other stage they are diagnostics. ``_SEMANTIC`` means no
    other stage failed. ``capped`` is true when findings of that stage were
    left out (``FINDINGS_PER_MEMBER``). A setup failure raises ``_Stop``.
    """
    try:
        with _exit_on_sigterm(), contextlib.ExitStack() as stack:
            folder = _work_folder(stack, work_dir)
            findings = _open_findings(stack, folder)
            checker = PackageChecker(root, str(folder / STORE_NAME))
            stack.callback(checker.close)
            read = _PackageRead(findings, checker, bundle, limits, reduce_error)
            read.read_members(package_dir, root["manifest"]["members"])
            return read.outcome()
    except SetupFailed as error:
        # LimitExceeded, a numeric resource or nesting limit of a line, or a schema bundle problem.
        raise _Stop(f"Setup failed: {error}.") from None
    except (sqlite3.Error, UnicodeError):
        raise _Stop(_WORK_FILES) from None


@contextlib.contextmanager
def _exit_on_sigterm():
    """Turn SIGTERM into ``SystemExit`` while the block runs, so a temporary work folder is removed.

    Python ends on SIGTERM without running cleanup, which would leave the
    folder behind. A handler can only be set in the main thread; elsewhere
    the block runs unchanged.
    """
    if not hasattr(signal, "SIGTERM") or threading.current_thread() is not threading.main_thread():
        yield
        return

    def stop(signum, _frame):
        raise SystemExit(128 + signum)

    previous = signal.signal(signal.SIGTERM, stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_DFL if previous is None else previous)


def _work_folder(stack: contextlib.ExitStack, work_dir) -> Path:
    """Return the work folder. A new temporary folder is removed when ``stack`` closes."""
    try:
        if work_dir is None:
            folder = Path(tempfile.mkdtemp(prefix="oasis-check-"))
            stack.callback(shutil.rmtree, folder, ignore_errors=True)
        else:
            folder = Path(work_dir)
            folder.mkdir(parents=True, exist_ok=True)
            for name in (STORE_NAME, FINDINGS_NAME):
                (folder / name).unlink(missing_ok=True)
    except OSError:
        raise _Stop(_WORK_FILES) from None
    return folder


def _open_findings(stack: contextlib.ExitStack, folder: Path) -> sqlite3.Connection:
    """Open the findings store, and send the SQLite temporary files of the process to ``folder``.

    The temporary folder is a process setting of SQLite. Setting the
    ``SQLITE_TMPDIR`` variable has no effect after SQLite starts, so the
    ``temp_store_directory`` pragma sets it. It is reset when ``stack`` closes.
    """
    db = sqlite3.connect(folder / FINDINGS_NAME)
    stack.callback(db.close)
    for statement in _FINDINGS_PRAGMAS:
        db.execute(statement)
    quoted = str(folder).replace("'", "''")
    db.execute(f"PRAGMA temp_store_directory = '{quoted}'")
    stack.callback(db.execute, "PRAGMA temp_store_directory = ''")
    db.execute(_FINDINGS_TABLE)
    return db


class _PackageRead:
    """One read of the member files, with the findings of each stage kept in the findings store.

    ``failed`` is the earliest stage with a finding so far, or ``_SEMANTIC``
    when there is none. A stage after ``failed`` is not run, and the
    semantic stage gets a record only while no other stage has failed.
    ``kept`` counts the findings kept for each ``(stage, member)``, and
    ``capped`` holds the stages that had findings left out.
    """

    def __init__(self, findings, checker, bundle, limits, reduce_error):
        self.findings = findings
        self.checker = checker
        self.bundle = bundle
        self.limits = limits
        self.reduce_error = reduce_error
        self.failed = _SEMANTIC
        self.kept: dict[tuple[int, int], int] = {}
        self.capped: set[int] = set()

    def read_members(self, package_dir, members) -> None:
        """Read the members by record list, in manifest order inside each list."""
        for registry in REGISTRIES:
            entry_point = self.bundle.record_entry_point(registry)
            for index, member in enumerate(members):
                if member["record_type"] == registry:
                    self._read_member(package_dir, registry, entry_point, index, member)

    def _read_member(self, package_dir, registry, entry_point, index, member) -> None:
        path = Path(package_dir, *member["path"].split("/"))
        reader = MemberReader(path, member["path"].endswith(".gz"), self.limits, base=Path(package_dir))
        whole = self.failed != _INTEGRITY
        try:
            if whole:
                for number, line in reader.lines():
                    if reader.line_rules_failed:
                        # The member fails integrity, which outranks every record stage.
                        continue
                    self._read_line(registry, entry_point, index, number, line)
            else:
                reader.hash_only()
        except MemberNotRegular:
            self._add(_INTEGRITY, index, None, _member_field(index, "path"), "MEMBER_NOT_REGULAR")
            return
        except OSError:
            raise _Stop(_UNREADABLE_MEMBER) from None
        self._check_integrity(index, member, reader, whole)

    def _read_line(self, registry, entry_point, index, number, line) -> None:
        try:
            parsed = parse_input(line)
        except InputInvalid:
            self._add(_PARSE, index, number, "", "INPUT_INVALID")
            return
        if self.failed < _LIMITS:
            return
        limits = check_number_limits(parsed.value, self.bundle.property_names)
        if limits:
            for d in limits:
                self._add(_LIMITS, index, number, d.path, d.code)
            return
        if self.failed < _STRUCTURE:
            return
        errors = entry_point.validate(parsed)
        if errors:
            for error in errors:
                path, keyword = self.reduce_error(error)
                self._add(_STRUCTURE, index, number, path, keyword=keyword)
            return
        if self.failed < _SEMANTIC:
            return
        self.checker.add(registry, parsed.value, Where(index, number, ""))

    def _check_integrity(self, index, member, reader, whole) -> None:
        """Compare one member file, as read, with its entry. A file only hashed gets size and checksum only."""
        if reader.stored_bytes != as_int(member["size_bytes"]):
            # The file changed after the scan.
            self._add(_INTEGRITY, index, None, _member_field(index, "size_bytes"), "MEMBER_SIZE_MISMATCH")
        elif reader.sha256 != member["sha256"]:
            self._add(_INTEGRITY, index, None, _member_field(index, "sha256"), "MEMBER_CHECKSUM_MISMATCH")
        if not whole:
            return
        framing = set(reader.framing)
        if framing & _STREAM_PROBLEMS:
            # The lines were not all read, so the line count means nothing.
            self._add(_INTEGRITY, index, None, _member_field(index, "path"), "MEMBER_COMPRESSION_MISMATCH")
        elif reader.line_count != as_int(member["count"]):
            self._add(_INTEGRITY, index, None, _member_field(index, "count"), "MEMBER_COUNT_MISMATCH")
        if framing & _LINE_PROBLEMS:
            self._add(_INTEGRITY, index, None, "", "MEMBER_LINE_INVALID")

    def _add(self, stage, member, line, path, code=None, keyword=None) -> None:
        self.failed = min(self.failed, stage)
        kept = self.kept.get((stage, member), 0)
        if kept >= FINDINGS_PER_MEMBER:
            self.capped.add(stage)
            return
        self.kept[(stage, member)] = kept + 1
        row = (stage, member, line, path, code, keyword)
        self.findings.execute("INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?)", row)

    def outcome(self):
        """Return ``(stage, findings, capped)`` for the earliest failed stage; see ``_read_package``."""
        self.findings.commit()
        if self.failed == _SEMANTIC:
            return _SEMANTIC, self.checker.finish(), False
        capped = self.failed in self.capped
        rows = self.findings.execute(_STAGE_FINDINGS, (self.failed,))
        if self.failed == _STRUCTURE:
            return _STRUCTURE, [(path, keyword, member, line) for member, line, path, _code, keyword in rows], capped
        return (
            self.failed,
            [replace(diagnostic(code, path), member=member, line=line) for member, line, path, code, _keyword in rows],
            capped,
        )
