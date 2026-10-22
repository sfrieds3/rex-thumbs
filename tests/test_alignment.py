import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rex_thumbs as thumbs

SCROLLBACK = ["older output", "$ seq 1 60"] + [str(number) for number in range(1, 38)]


class ScreenLinesTests(unittest.TestCase):
    """Hints are drawn on the rows Rex shows (#6). Fixtures follow Rex's real text format."""

    def test_short_output_starts_at_the_top(self):
        self.assertEqual(thumbs.screen_lines("one\n\nthree\n$ ", 24, (4, 3)), ["one", "", "three", "$ "])

    def test_full_screen(self):
        content = "\n".join(str(number) for number in range(1, 31)) + "\n$ "
        self.assertEqual(thumbs.screen_lines(content, 24, (24, 3)), [str(n) for n in range(8, 31)] + ["$ "])

    def test_after_ctrl_l_keeps_scrollback(self):
        content = "\n".join(SCROLLBACK + ["top-line", "/tmp/second", "sh-3.2$ "])
        self.assertEqual(thumbs.screen_lines(content, 24, (3, 9)), ["top-line", "/tmp/second", "sh-3.2$ "])

    def test_after_ctrl_l_with_short_scrollback(self):
        content = "\n".join(["older", "1", "2", "3", "4", "$ ls", "/tmp/a", "$ "])
        self.assertEqual(thumbs.screen_lines(content, 24, (3, 3)), ["$ ls", "/tmp/a", "$ "])

    def test_lines_below_the_cursor_on_a_full_screen(self):
        # A TUI in the primary screen: input box on row 22, status lines below it.
        content = "\n".join([f"history {n}" for n in range(40)] + ["> type here", "-" * 30, "status: ok"])
        lines = thumbs.screen_lines(content, 24, (22, 3))
        self.assertEqual(lines[-3:], ["> type here", "-" * 30, "status: ok"])
        self.assertEqual(len(lines), 24)

    def test_alternate_screen_trailing_newline(self):
        content = "\n".join([""] * 18 + ["1", "2", "3", "4", "5", "(END)"]) + "\n"
        lines = thumbs.screen_lines(content, 24, (24, 6))
        self.assertEqual(len(lines), 24)
        self.assertEqual(lines[-1], "(END)")

    def test_without_cursor(self):
        self.assertEqual(thumbs.screen_lines("a\nb\nc\n", 2), ["b", "c"])


class CaptureTests(unittest.TestCase):
    def test_reads_cursor_from_vt(self):
        content = "\n".join(SCROLLBACK + ["/tmp/x", "$ "])
        responses = {
            "size": {"rows": 24, "columns": 80},
            "text": {"content": content},
            "vt": {"content": "...\r\n$ \x1b[2;3H"},
        }

        def block_call(session, block, method, params=None):
            return responses[(params or {}).get("format", method)]

        with mock.patch.object(thumbs, "block_call", side_effect=block_call):
            self.assertEqual(thumbs.capture("session:a", "block:b"), (["/tmp/x", "$ "], 24, 80))


class WidthTests(unittest.TestCase):
    """Widths as Rex draws them, measured from the cursor column after printing each string."""

    def test_rex_widths(self):
        for text, width in [
            ("❤️", 1),
            ("\U0001f468‍\U0001f469‍\U0001f467", 6),
            ("\U0001f44d\U0001f3fd", 4),
            ("\U0001f1fa\U0001f1f8", 4),
            ("日本", 4),
            ("→…│✓", 4),
            ("⚡", 2),
            ("ｱ", 1),
        ]:
            self.assertEqual(thumbs.cell_width(text), width, ascii(text))


if __name__ == "__main__":
    unittest.main()
