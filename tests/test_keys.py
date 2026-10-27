import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rex_thumbs as thumbs


class ParseKeysTests(unittest.TestCase):
    """Every key in a read is kept (#5)."""

    def test_fast_typing_keeps_every_key(self):
        self.assertEqual(thumbs.parse_keys("as"), ["a", "s"])
        self.assertEqual(thumbs.parse_keys("aS "), ["a", "S", "space"])

    def test_named_keys(self):
        self.assertEqual(thumbs.parse_keys("\r\x7f\x03\x1b"), ["enter", "backspace", "esc", "esc"])

    def test_arrows(self):
        self.assertEqual(thumbs.parse_keys("\x1b[A\x1bOB\x1b[1;2C\x1b[D"), ["up", "down", "right", "left"])

    def test_escape_then_key(self):
        self.assertEqual(thumbs.parse_keys("\x1ba"), ["esc", "a"])

    def test_unknown_sequences_are_ignored(self):
        self.assertEqual(thumbs.parse_keys("\x1b[3~a\x1b[200~"), ["a"])

    def test_kitty_keys(self):
        self.assertEqual(thumbs.parse_keys("\x1b[97u\x1b[97;2u"), ["a", "A"])
        self.assertEqual(thumbs.parse_keys("\x1b[27u\x1b[13u\x1b[99;5u\x1b[32u"), ["esc", "enter", "esc", "space"])
        self.assertEqual(thumbs.parse_keys("\x1b[97:65;2u"), ["A"])


class KeyReaderTests(unittest.TestCase):
    def read_all(self, chunks, count):
        reader = thumbs.KeyReader()
        chunks = list(chunks)
        with mock.patch.object(thumbs.os, "read", side_effect=lambda fd, size: chunks.pop(0)):
            return [reader(0) for _ in range(count)]

    def test_one_read_many_keys(self):
        self.assertEqual(self.read_all([b"asd"], 3), ["a", "s", "d"])

    def test_utf8_split_across_reads(self):
        self.assertEqual(self.read_all([b"\xc3", b"\xa9x"], 2), ["é", "x"])

    def test_two_letter_hint_typed_in_one_read(self):
        lines = [" ".join(f"/tmp/f{index}" for index in range(30))]
        options = thumbs.parse_args(["session:a", "block:b"])
        view = thumbs.View(lines, thumbs.find_matches(lines), options)
        target = next(match for match in view.matches if len(match.hint) == 2)
        chunks = [target.hint.encode()]
        reader = thumbs.KeyReader()
        with (
            mock.patch.object(thumbs.os, "read", side_effect=lambda fd, size: chunks.pop(0)),
            mock.patch.object(thumbs.select, "select", side_effect=lambda r, w, x, timeout: (r, w, x)),
            mock.patch.object(thumbs, "read_key", reader),
        ):
            self.assertEqual(view.run(0, io.StringIO()), [(target.text, False)])


class ResizeTests(unittest.TestCase):
    """Rex can size the layer's terminal after the first draw, which wipes it; a resize draws again."""

    def setUp(self):
        self.read_fd, self.write_fd = os.pipe()
        self.addCleanup(os.close, self.read_fd)
        self.addCleanup(os.close, self.write_fd)

    def test_reader_idles_until_a_key_arrives(self):
        reader, idles = thumbs.KeyReader(), []

        def idle():
            idles.append(True)
            if len(idles) == 2:
                os.write(self.write_fd, b"a")

        self.assertEqual(reader(self.read_fd, idle), "a")
        self.assertEqual(len(idles), 2)

    def test_resize_redraws(self):
        lines = ["see /tmp/one.txt"]
        options = thumbs.parse_args(["session:a", "block:b"])
        view = thumbs.View(lines, thumbs.find_matches(lines), options)
        draws = []
        render = view.render

        def counting_render(typed, out):
            draws.append(typed)
            render(typed, out)
            if len(draws) == 1:
                view.resized = True  # as the SIGWINCH handler does
            else:
                os.write(self.write_fd, b"\x1b")

        with (
            mock.patch.object(view, "render", counting_render),
            mock.patch.object(thumbs, "read_key", thumbs.KeyReader()),
        ):
            self.assertEqual(view.run(self.read_fd, io.StringIO()), [])
        self.assertEqual(len(draws), 2)
        self.assertFalse(view.resized)


if __name__ == "__main__":
    unittest.main()
