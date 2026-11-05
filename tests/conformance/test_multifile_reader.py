"""The member reader: one read of a member file with checksum, framing, and limits.

``MemberReader`` yields the lines of a member file, hashes the stored bytes,
reports line framing and compression problems, and stops a file that passes a
size limit. These tests write small member files to a temporary folder.
"""

import functools
import gzip
import hashlib
import os
import tempfile
import tracemalloc
import unittest
import zlib
from pathlib import Path
from unittest import mock

from tests.conformance import multifile
from tests.conformance.multifile import LimitExceeded, MemberReader, ReadLimits
from tests.conformance.types import SetupFailed

MIB = 1024 * 1024
BOM = b"\xef\xbb\xbf"
LINES = [b'{"id":"a"}', b'{"id":"b"}', b'{"id":"c"}']
DATA = b"".join(line + b"\n" for line in LINES)

# Block sizes that split lines, BOMs, CR LF pairs, and gzip members at odd places.
SMALL_BLOCKS = (1, 2, 3, 7, 64)


def _members(*parts: bytes) -> bytes:
    """Gzip each part on its own and join the streams in one file."""
    return b"".join(gzip.compress(part) for part in parts)


@functools.cache
def _gzip_of_zeros(total: int) -> bytes:
    """A gzip stream of ``total`` zero bytes, built one block at a time (about 1 KiB per MiB)."""
    packer = zlib.compressobj(9, zlib.DEFLATED, 31)
    block = bytes(MIB)
    out = []
    for _ in range(total // MIB):
        out.append(packer.compress(block))
    out.append(packer.compress(bytes(total % MIB)))
    out.append(packer.flush())
    return b"".join(out)


class _CountingInflater:
    """A ``zlib.decompressobj`` stand-in that adds up the bytes it hands out."""

    produced = 0

    def __init__(self, inner):
        self._inner = inner

    def decompress(self, *args):
        out = self._inner.decompress(*args)
        _CountingInflater.produced += len(out)
        return out

    def __getattr__(self, name):
        return getattr(self._inner, name)


class ReaderTestCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def write(self, name: str, data: bytes) -> Path:
        path = self.folder / name
        path.write_bytes(data)
        return path

    def read(self, name: str, data: bytes, limits: ReadLimits | None = None):
        """Write ``data`` to the member ``name``, read it, and return the finished reader and its lines."""
        path = self.write(name, data)
        reader = MemberReader(path, name.endswith(".gz"), limits or ReadLimits())
        return reader, list(reader.lines())


class ReadLimitsTest(unittest.TestCase):
    def test_defaults(self):
        limits = ReadLimits()
        self.assertEqual(limits.max_line_bytes, 67_108_864)
        self.assertEqual(limits.max_gzip_ratio, 1000)

    def test_limits_are_not_changed_after_creation(self):
        with self.assertRaises(AttributeError):
            ReadLimits().max_line_bytes = 1

    def test_limit_exceeded_is_a_setup_failure(self):
        self.assertTrue(issubclass(LimitExceeded, SetupFailed))

    def test_read_block_is_one_mebibyte(self):
        self.assertEqual(multifile.READ_BLOCK, MIB)


class LinesTest(ReaderTestCase):
    def test_plain_member(self):
        reader, lines = self.read("a.jsonl", DATA)
        self.assertEqual(lines, list(enumerate(LINES, start=1)))
        self.assertEqual(reader.line_count, 3)
        self.assertEqual(reader.framing, [])

    def test_gzip_member_gives_the_same_lines_and_count(self):
        plain, plain_lines = self.read("a.jsonl", DATA)
        packed, packed_lines = self.read("a.jsonl.gz", gzip.compress(DATA))
        self.assertEqual(packed_lines, plain_lines)
        self.assertEqual(packed.line_count, plain.line_count)
        self.assertEqual(packed.framing, [])

    def test_lines_are_bytes_without_the_lf(self):
        _, lines = self.read("a.jsonl", b"{}\n[]\n")
        self.assertEqual(lines, [(1, b"{}"), (2, b"[]")])
        self.assertTrue(all(type(line) is bytes for _, line in lines))

    def test_line_numbers_start_at_one_and_run_across_blocks(self):
        with mock.patch.object(multifile, "READ_BLOCK", 4):
            _, lines = self.read("a.jsonl", DATA)
        self.assertEqual([n for n, _ in lines], [1, 2, 3])

    def test_two_gzip_members_read_as_one_stream(self):
        data = _members(b"".join(line + b"\n" for line in LINES[:2]), LINES[2] + b"\n")
        reader, lines = self.read("a.jsonl.gz", data)
        self.assertEqual(lines, list(enumerate(LINES, start=1)))
        self.assertEqual(reader.line_count, 3)
        self.assertEqual(reader.framing, [])

    def test_a_line_may_span_two_gzip_members(self):
        data = _members(b'{"id":', b'"a"}\n')
        _, lines = self.read("a.jsonl.gz", data)
        self.assertEqual(lines, [(1, b'{"id":"a"}')])

    def test_an_empty_gzip_member_inside_the_stream_is_allowed(self):
        data = _members(b"{}\n", b"", b"[]\n")
        reader, lines = self.read("a.jsonl.gz", data)
        self.assertEqual(lines, [(1, b"{}"), (2, b"[]")])
        self.assertEqual(reader.framing, [])

    def test_every_block_size_gives_the_same_lines_and_checksum(self):
        cases = {
            "a.jsonl": DATA,
            "b.jsonl.gz": gzip.compress(DATA),
            "c.jsonl.gz": _members(b'{"id":', b'"a"}\n{"id":"b"}\n', b"[]\n"),
            "d.jsonl": b"\r\n",
            "e.jsonl": BOM + b"{}\n\n{}",
        }
        for name, data in cases.items():
            expected, expected_lines = self.read(name, data)
            for size in SMALL_BLOCKS:
                with self.subTest(name=name, block=size), mock.patch.object(multifile, "READ_BLOCK", size):
                    reader, lines = self.read(name, data)
                self.assertEqual(lines, expected_lines)
                self.assertEqual(reader.sha256, expected.sha256)
                self.assertEqual(reader.framing, expected.framing)
                self.assertEqual(reader.line_count, expected.line_count)

    def test_the_file_is_opened_once(self):
        path = self.write("a.jsonl", DATA)
        with mock.patch.object(multifile, "open", create=True, side_effect=open) as opened:
            list(MemberReader(path, False, ReadLimits()).lines())
        self.assertEqual(opened.call_count, 1)

    def test_leaving_early_closes_the_file(self):
        path = self.write("a.jsonl", DATA)
        handles = []

        def spy(*args):
            handles.append(open(*args))
            return handles[-1]

        with mock.patch.object(multifile, "open", create=True, side_effect=spy):
            lines = MemberReader(path, False, ReadLimits()).lines()
            next(lines)
            self.assertFalse(handles[0].closed)
            lines.close()
        self.assertTrue(handles[0].closed)


class ChecksumTest(ReaderTestCase):
    def test_sha256_of_a_plain_file(self):
        reader, _ = self.read("a.jsonl", DATA)
        self.assertEqual(reader.sha256, hashlib.sha256(DATA).hexdigest())

    def test_sha256_of_a_gzip_file_is_of_the_stored_bytes(self):
        data = _members(b"{}\n", b"[]\n")
        reader, _ = self.read("a.jsonl.gz", data)
        self.assertEqual(reader.sha256, hashlib.sha256(data).hexdigest())

    def test_sha256_is_lowercase_hex_of_64_digits(self):
        reader, _ = self.read("a.jsonl", DATA)
        self.assertRegex(reader.sha256, r"\A[0-9a-f]{64}\Z")

    def test_stored_bytes_is_the_file_size(self):
        data = gzip.compress(DATA)
        reader, _ = self.read("a.jsonl.gz", data)
        self.assertEqual(reader.stored_bytes, len(data))


class FramingTest(ReaderTestCase):
    def test_cr_before_lf(self):
        reader, lines = self.read("a.jsonl", b"{}\r\n")
        self.assertEqual(reader.framing, ["cr"])
        self.assertEqual(lines, [(1, b"{}\r")])

    def test_cr_in_the_middle_of_a_line(self):
        reader, _ = self.read("a.jsonl", b'{"a":\r1}\n')
        self.assertEqual(reader.framing, ["cr"])

    def test_cr_in_a_gzip_member(self):
        reader, _ = self.read("a.jsonl.gz", gzip.compress(b"{}\r\n"))
        self.assertEqual(reader.framing, ["cr"])

    def test_blank_line(self):
        reader, lines = self.read("a.jsonl", b"{}\n\n{}\n")
        self.assertEqual(reader.framing, ["blank"])
        self.assertEqual(lines, [(1, b"{}"), (2, b""), (3, b"{}")])
        self.assertEqual(reader.line_count, 3)

    def test_blank_first_and_blank_last(self):
        for data in (b"\n{}\n", b"{}\n\n"):
            with self.subTest(data=data):
                reader, _ = self.read("a.jsonl", data)
                self.assertEqual(reader.framing, ["blank"])

    def test_bom_at_the_start(self):
        reader, lines = self.read("a.jsonl", BOM + b"{}\n")
        self.assertEqual(reader.framing, ["bom"])
        self.assertEqual(lines, [(1, BOM + b"{}")])

    def test_bom_at_the_start_of_gzip_content(self):
        reader, _ = self.read("a.jsonl.gz", gzip.compress(BOM + b"{}\n"))
        self.assertEqual(reader.framing, ["bom"])

    def test_bom_after_the_start_is_not_a_bom_problem(self):
        reader, _ = self.read("a.jsonl", b"{}\n" + BOM + b"{}\n")
        self.assertEqual(reader.framing, [])

    def test_bom_in_the_second_gzip_member_is_not_a_bom_problem(self):
        reader, _ = self.read("a.jsonl.gz", _members(b"{}\n", BOM + b"{}\n"))
        self.assertEqual(reader.framing, [])

    def test_bom_is_only_found_when_all_three_bytes_match(self):
        for head in (b"\xef\xbb", b"\xef\xbb\xbe"):
            with self.subTest(head=head):
                reader, _ = self.read("a.jsonl", head + b"{}\n")
                self.assertEqual(reader.framing, [])

    def test_no_final_lf(self):
        reader, _ = self.read("a.jsonl", b"{}\n{}")
        self.assertEqual(reader.framing, ["no_final_lf"])

    def test_the_last_line_without_lf_is_still_yielded_and_counted(self):
        reader, lines = self.read("a.jsonl", b"{}\n[]")
        self.assertEqual(lines, [(1, b"{}"), (2, b"[]")])
        self.assertEqual(reader.line_count, 2)

    def test_a_file_with_one_line_and_no_lf(self):
        reader, lines = self.read("a.jsonl", b"{}")
        self.assertEqual(reader.framing, ["no_final_lf"])
        self.assertEqual(lines, [(1, b"{}")])

    def test_no_final_lf_in_gzip_content(self):
        reader, lines = self.read("a.jsonl.gz", gzip.compress(b"{}\n[]"))
        self.assertEqual(reader.framing, ["no_final_lf"])
        self.assertEqual(lines, [(1, b"{}"), (2, b"[]")])

    def test_one_final_lf_is_not_a_blank_line(self):
        reader, _ = self.read("a.jsonl", b"{}\n")
        self.assertEqual(reader.framing, [])

    def test_a_lone_lf_is_one_blank_line(self):
        reader, lines = self.read("a.jsonl", b"\n")
        self.assertEqual(reader.framing, ["blank"])
        self.assertEqual(lines, [(1, b"")])

    def test_each_problem_is_listed_once_in_a_fixed_order(self):
        data = BOM + b"{}\r\n\n\r\n{}"
        reader, _ = self.read("a.jsonl", data)
        self.assertEqual(reader.framing, ["cr", "blank", "bom", "no_final_lf"])
        reader, _ = self.read("a.jsonl", data.replace(b"\n{}", b"\n {}\n{}\t"))
        self.assertEqual(reader.framing, ["cr", "blank", "bom", "whitespace", "no_final_lf"])

    def test_space_or_tab_before_or_after_the_object(self):
        for data in (b" {}\n", b"{} \n", b"\t{}\n", b"{}\t\n", b"{}\n [1]\t\n", b" \n", b"\t\n"):
            with self.subTest(data=data):
                reader, lines = self.read("a.jsonl", data)
                self.assertEqual(reader.framing, ["whitespace"])
                self.assertEqual(lines[-1][1], data.split(b"\n")[-2])

    def test_whitespace_inside_the_object_is_not_a_problem(self):
        reader, _ = self.read("a.jsonl", b'{"a": 1, "b" :\t[1, 2]}\n')
        self.assertEqual(reader.framing, [])

    def test_cr_at_the_end_of_a_line_is_cr_only(self):
        for data in (b"{}\r\n", b"{} \r\n"):
            with self.subTest(data=data):
                reader, _ = self.read("a.jsonl", data)
                self.assertEqual(reader.framing, ["cr"])

    def test_whitespace_on_the_last_line_without_lf(self):
        reader, lines = self.read("a.jsonl", b"{}\n{} ")
        self.assertEqual(reader.framing, ["whitespace", "no_final_lf"])
        self.assertEqual(lines, [(1, b"{}"), (2, b"{} ")])

    def test_whitespace_in_gzip_content(self):
        reader, _ = self.read("a.jsonl.gz", _members(b"{}\n", b" {}\n"))
        self.assertEqual(reader.framing, ["whitespace"])

    def test_whitespace_is_found_when_a_line_is_split_across_read_blocks(self):
        cases = {
            "a.jsonl": b'{"id":"a"}\n{"id":"b"} \n',
            "b.jsonl": b'{"id":"a"}\n\t{"id":"b"}\n',
            "c.jsonl.gz": gzip.compress(b'{"id":"a"}\n{"id":"b"}\t\n{"id":"c"}\n'),
        }
        for name, data in cases.items():
            _expected, expected_lines = self.read(name, data)
            for size in SMALL_BLOCKS:
                with self.subTest(name=name, block=size), mock.patch.object(multifile, "READ_BLOCK", size):
                    reader, lines = self.read(name, data)
                self.assertEqual(reader.framing, ["whitespace"])
                self.assertEqual(lines, expected_lines)

    def test_a_zero_byte_plain_file(self):
        reader, lines = self.read("a.jsonl", b"")
        self.assertEqual(lines, [])
        self.assertEqual(reader.line_count, 0)
        self.assertEqual(reader.framing, [])
        self.assertEqual(reader.sha256, hashlib.sha256(b"").hexdigest())

    def test_a_gzip_stream_of_zero_bytes(self):
        data = gzip.compress(b"")
        reader, lines = self.read("a.jsonl.gz", data)
        self.assertEqual(lines, [])
        self.assertEqual(reader.line_count, 0)
        self.assertEqual(reader.framing, [])
        self.assertEqual(reader.sha256, hashlib.sha256(data).hexdigest())


class CompressionTest(ReaderTestCase):
    def test_plain_bytes_in_a_gz_file(self):
        reader, lines = self.read("a.jsonl.gz", DATA)
        self.assertEqual(reader.framing, ["compression"])
        self.assertEqual(lines, [])
        self.assertEqual(reader.line_count, 0)

    def test_gzip_bytes_in_a_plain_file(self):
        data = gzip.compress(DATA)
        reader, lines = self.read("a.jsonl", data)
        self.assertEqual(reader.framing, ["compression"])
        self.assertEqual(lines, [])
        self.assertEqual(reader.line_count, 0)

    def test_a_mismatch_still_gives_the_checksum_and_size(self):
        for name, data in (("a.jsonl.gz", DATA * 50), ("a.jsonl", gzip.compress(DATA * 50))):
            for size in (None, 5):
                with self.subTest(name=name, block=size):
                    with mock.patch.object(multifile, "READ_BLOCK", size or MIB):
                        reader, _ = self.read(name, data)
                    self.assertEqual(reader.sha256, hashlib.sha256(data).hexdigest())
                    self.assertEqual(reader.stored_bytes, len(data))

    def test_a_mismatch_reports_no_other_framing_problem(self):
        reader, _ = self.read("a.jsonl.gz", BOM + b"{}\r\n\n{}")
        self.assertEqual(reader.framing, ["compression"])

    def test_a_mismatch_is_not_a_bomb(self):
        data = _gzip_of_zeros(4 * MIB)
        limits = ReadLimits(max_gzip_ratio=1)
        reader, lines = self.read("a.jsonl", data, limits)
        self.assertEqual((reader.framing, lines), (["compression"], []))

    def test_a_zero_byte_gz_file_is_not_a_gzip_stream(self):
        reader, lines = self.read("a.jsonl.gz", b"")
        self.assertEqual(reader.framing, ["compression"])
        self.assertEqual(lines, [])

    def test_one_byte_that_starts_the_magic_is_not_gzip(self):
        reader, _ = self.read("a.jsonl", b"\x1f")
        self.assertEqual(reader.framing, ["no_final_lf"])

    def test_the_magic_alone_in_a_plain_file_is_a_mismatch(self):
        reader, _ = self.read("a.jsonl", b"\x1f\x8b")
        self.assertEqual(reader.framing, ["compression"])


class GzipStreamTest(ReaderTestCase):
    def check_bad_stream(self, data, *, block=MIB):
        with mock.patch.object(multifile, "READ_BLOCK", block):
            reader, lines = self.read("a.jsonl.gz", data)
        self.assertIn("gzip_stream", reader.framing)
        self.assertEqual(reader.sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(reader.stored_bytes, len(data))
        self.assertEqual(reader.line_count, len(lines))
        return reader, lines

    def test_truncated_stream(self):
        data = gzip.compress(b"".join(b'{"id":"%d"}\n' % n for n in range(500)))
        for block in (MIB, 3):
            with self.subTest(block=block):
                reader, lines = self.check_bad_stream(data[: len(data) // 2], block=block)
                self.assertEqual(reader.framing, ["gzip_stream"])
                self.assertEqual(lines, [(n + 1, b'{"id":"%d"}' % n) for n in range(len(lines))])
                self.assertLess(len(lines), 500)

    def test_truncated_inside_the_header(self):
        reader, lines = self.check_bad_stream(gzip.compress(DATA)[:5])
        self.assertEqual((reader.framing, lines), (["gzip_stream"], []))

    def test_the_magic_and_nothing_else(self):
        reader, lines = self.check_bad_stream(b"\x1f\x8b")
        self.assertEqual((reader.framing, lines), (["gzip_stream"], []))

    def test_second_member_cut_off(self):
        data = _members(DATA, DATA)
        reader, lines = self.check_bad_stream(data[:-4])
        self.assertEqual(reader.framing, ["gzip_stream"])
        self.assertEqual(lines, list(enumerate(LINES * 2, start=1))[: len(lines)])
        self.assertGreaterEqual(len(lines), 3)

    def test_corrupt_deflate_data(self):
        data = bytearray(gzip.compress(b"".join(b'{"id":"%d"}\n' % n for n in range(2000))))
        for at in range(12, len(data) - 8, 7):
            data[at] ^= 0xFF
        reader, _ = self.check_bad_stream(bytes(data))
        self.assertEqual(reader.framing, ["gzip_stream"])

    def test_wrong_trailer_checksum(self):
        data = bytearray(gzip.compress(DATA))
        data[-8] ^= 0xFF
        reader, _ = self.check_bad_stream(bytes(data))
        self.assertEqual(reader.framing, ["gzip_stream"])

    def test_junk_after_a_member(self):
        reader, lines = self.check_bad_stream(gzip.compress(DATA) + b"junk")
        self.assertEqual(reader.framing, ["gzip_stream"])
        self.assertEqual(lines, list(enumerate(LINES, start=1)))

    def test_zero_padding_after_a_member_is_junk(self):
        reader, _ = self.check_bad_stream(gzip.compress(DATA) + bytes(8))
        self.assertEqual(reader.framing, ["gzip_stream"])

    def test_a_partial_last_line_is_dropped_when_the_stream_is_bad(self):
        reader, lines = self.check_bad_stream(gzip.compress(b"{}\n[]\n{")[:-8])
        self.assertEqual(lines, [(1, b"{}"), (2, b"[]")])
        self.assertEqual(reader.framing, ["gzip_stream"])

    def test_a_partial_line_is_dropped_when_junk_follows_the_member(self):
        reader, lines = self.check_bad_stream(gzip.compress(b"{}\n[]\n{") + b"junk")
        self.assertEqual(lines, [(1, b"{}"), (2, b"[]")])
        self.assertEqual(reader.framing, ["gzip_stream"])

    def test_a_decoding_error_gives_a_prefix_of_the_lines(self):
        # How many lines come out before zlib raises depends on the block size.
        member = gzip.compress(b"{}\n[]\n{")
        reader, lines = self.check_bad_stream(member[:-8] + b"\x00" * 8)
        self.assertEqual(lines, [(1, b"{}"), (2, b"[]")][: len(lines)])
        self.assertEqual(reader.framing, ["gzip_stream"])

    def test_the_rest_of_the_file_is_hashed_after_the_error(self):
        data = gzip.compress(DATA) + b"junk" * 1000
        self.check_bad_stream(data, block=64)

    def test_problems_found_before_the_error_stay_listed(self):
        data = gzip.compress(b"{}\r\n{}\r\n")[:-6]
        reader, _ = self.check_bad_stream(data)
        self.assertEqual(reader.framing, ["cr", "gzip_stream"])


class LimitTest(ReaderTestCase):
    def test_a_long_plain_line(self):
        path = self.write("a.jsonl", b"{}\n" + b"x" * 11 + b"\n{}\n")
        reader = MemberReader(path, False, ReadLimits(max_line_bytes=10))
        seen = []
        with self.assertRaises(LimitExceeded):
            for item in reader.lines():
                seen.append(item)
        self.assertEqual(seen, [(1, b"{}")])

    def test_a_line_of_exactly_the_limit_passes(self):
        data = b"x" * 10 + b"\n" + b"y" * 10 + b"\n"
        for size in (MIB, 3, 10, 11):
            with self.subTest(block=size), mock.patch.object(multifile, "READ_BLOCK", size):
                _, lines = self.read("a.jsonl", data, ReadLimits(max_line_bytes=10))
            self.assertEqual(lines, [(1, b"x" * 10), (2, b"y" * 10)])

    def test_the_lf_is_not_part_of_the_line_length(self):
        _, lines = self.read("a.jsonl", b"x" * 10 + b"\n", ReadLimits(max_line_bytes=10))
        self.assertEqual(len(lines), 1)

    def test_a_long_line_over_several_blocks(self):
        data = b"{}\n" + b"x" * 11 + b"\n"
        for size in (1, 3, 4, 100):
            with self.subTest(block=size), mock.patch.object(multifile, "READ_BLOCK", size):
                with self.assertRaises(LimitExceeded):
                    self.read("a.jsonl", data, ReadLimits(max_line_bytes=10))

    def test_a_long_last_line_without_lf(self):
        with self.assertRaises(LimitExceeded):
            self.read("a.jsonl", b"{}\n" + b"x" * 11, ReadLimits(max_line_bytes=10))

    def test_a_long_line_in_gzip_content(self):
        data = gzip.compress(b"{}\n" + b"x" * 11 + b"\n")
        for size in (MIB, 3):
            with self.subTest(block=size), mock.patch.object(multifile, "READ_BLOCK", size):
                with self.assertRaises(LimitExceeded):
                    self.read("a.jsonl.gz", data, ReadLimits(max_line_bytes=10))

    def test_a_line_longer_than_the_limit_never_fills_memory(self):
        # One line of 32 MiB with no LF, against a 1 KiB limit: it stops at once.
        data = gzip.compress(b"x" * (32 * MIB))
        tracemalloc.start()
        try:
            with self.assertRaises(LimitExceeded):
                self.read("a.jsonl.gz", data, ReadLimits(max_line_bytes=1024, max_gzip_ratio=100_000))
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 4 * MIB)

    def test_a_decompression_bomb_stops_early(self):
        data = _gzip_of_zeros(200 * MIB)
        path = self.write("a.jsonl.gz", data)
        limit = 100 * len(data) + MIB
        _CountingInflater.produced = 0
        real = zlib.decompressobj
        with mock.patch.object(multifile.zlib, "decompressobj", lambda *a, **k: _CountingInflater(real(*a, **k))):
            with self.assertRaises(LimitExceeded):
                list(MemberReader(path, True, ReadLimits(max_gzip_ratio=100)).lines())
        self.assertLessEqual(_CountingInflater.produced, limit + 1)
        self.assertLess(_CountingInflater.produced, 200 * MIB // 4)

    def test_the_bomb_stops_at_the_default_ratio_too(self):
        # Zeros have no LF, so the line limit is raised out of the way: only the ratio can stop this read.
        # The margin is small: 200 MiB of zeros packs to about 1029:1, and the default ratio is 1000.
        data = _gzip_of_zeros(200 * MIB)
        path = self.write("a.jsonl.gz", data)
        limit = ReadLimits().max_gzip_ratio * len(data) + MIB
        reader = MemberReader(path, True, ReadLimits(max_line_bytes=1 << 40))
        _CountingInflater.produced = 0
        real = zlib.decompressobj
        with mock.patch.object(multifile.zlib, "decompressobj", lambda *a, **k: _CountingInflater(real(*a, **k))):
            with self.assertRaises(LimitExceeded) as raised:
                list(reader.lines())
        self.assertEqual(str(raised.exception), multifile._RATIO_LIMIT_MESSAGE)
        self.assertEqual(_CountingInflater.produced, limit + 1)
        self.assertLess(_CountingInflater.produced, 200 * MIB)

    def test_the_allowance_is_the_ratio_times_the_stored_bytes_plus_one_mebibyte(self):
        # With ratio 0 only the 1 MiB allowance is left: 1 MiB passes, one byte more fails.
        line = b"x" * 1023 + b"\n"
        reader, lines = self.read("a.jsonl.gz", gzip.compress(line * 1024), ReadLimits(max_gzip_ratio=0))
        self.assertEqual(reader.line_count, 1024)
        with self.assertRaises(LimitExceeded):
            self.read("b.jsonl.gz", gzip.compress(line * 1024 + b"\n"), ReadLimits(max_gzip_ratio=0))

    def test_the_allowance_grows_with_each_stored_block(self):
        # The first block holds only the start of the file. Later blocks add to the allowance.
        body = os.urandom(64 * 1024).hex().encode()
        data = gzip.compress((body + b"\n") * 40)
        with mock.patch.object(multifile, "READ_BLOCK", 4096):
            reader, _ = self.read("a.jsonl.gz", data, ReadLimits(max_gzip_ratio=3))
        self.assertEqual(reader.line_count, 40)

    def test_the_ratio_is_not_checked_for_plain_files(self):
        reader, _ = self.read("a.jsonl", DATA, ReadLimits(max_gzip_ratio=0, max_line_bytes=100))
        self.assertEqual(reader.line_count, 3)

    def test_the_failure_text_is_fixed_and_repeats_no_input(self):
        path = self.write("secret-name-7731.jsonl", b"x" * 987)
        try:
            list(MemberReader(path, False, ReadLimits(max_line_bytes=10)).lines())
        except LimitExceeded as error:
            line_message = str(error)
        bomb = self.write("secret-bomb-4452.jsonl.gz", gzip.compress(bytes(3 * MIB)))
        try:
            list(MemberReader(bomb, True, ReadLimits(max_gzip_ratio=0)).lines())
        except LimitExceeded as error:
            ratio_message = str(error)
        self.assertNotEqual(line_message, ratio_message)
        for message in (line_message, ratio_message):
            for text in ("secret", "987", "10", "7731", "4452", str(self.folder)):
                self.assertNotIn(text, message)

    def test_an_unreadable_file_raises_the_system_error(self):
        with self.assertRaises(FileNotFoundError):
            list(MemberReader(self.folder / "absent.jsonl", False, ReadLimits()).lines())


class MemoryTest(ReaderTestCase):
    def peak_of_reading(self, name, data, limits):
        path = self.write(name, data)
        reader = MemberReader(path, name.endswith(".gz"), limits)
        tracemalloc.start()
        try:
            count = sum(1 for _ in reader.lines())
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(count, reader.line_count)
        return peak

    def test_memory_does_not_grow_with_the_file(self):
        line = b"x" * 1023 + b"\n"
        text = line * (32 * 1024)  # 32 MiB of text in 1 KiB lines
        limits = ReadLimits(max_gzip_ratio=100_000)
        self.assertLess(self.peak_of_reading("a.jsonl", text, limits), 16 * MIB)
        self.assertLess(self.peak_of_reading("a.jsonl.gz", gzip.compress(text, 1), limits), 16 * MIB)


if __name__ == "__main__":
    unittest.main()
