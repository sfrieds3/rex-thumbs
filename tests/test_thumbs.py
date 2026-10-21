import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rex_thumbs as thumbs  # noqa: E402


def texts(lines, **kwargs):
    return [(match.text, match.hint) for match in thumbs.find_matches(lines, alphabet="abcd", **kwargs)]


class HintTests(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(thumbs.hints_for("abcd", 3), ["a", "b", "c"])

    def test_composed(self):
        self.assertEqual(thumbs.hints_for("abcd", 6), ["a", "b", "c", "da", "db", "dc"])

    def test_composed_multiple(self):
        self.assertEqual(thumbs.hints_for("abcd", 8), ["a", "b", "ca", "cb", "da", "db", "dc", "dd"])

    def test_composed_max(self):
        self.assertEqual(thumbs.hints_for("ab", 8), ["aa", "ab", "ba", "bb"])


class MatchTests(unittest.TestCase):
    line = "lorem 127.0.0.1 lorem 255.255.255.255 lorem 127.0.0.1 lorem"

    def test_order(self):
        self.assertEqual(texts([self.line]), [("127.0.0.1", "a"), ("255.255.255.255", "b"), ("127.0.0.1", "c")])

    def test_reverse(self):
        self.assertEqual(
            texts([self.line], reverse=True), [("127.0.0.1", "c"), ("255.255.255.255", "b"), ("127.0.0.1", "a")]
        )

    def test_unique(self):
        self.assertEqual([hint for _, hint in texts([self.line], unique=True)], ["a", "b", "a"])

    def test_docker(self):
        sha = "30557a29d5abc51e5f1d5b472e79b7e296f595abcf19fe6b9199dbbc809c6ff4"
        self.assertEqual(texts([f"latest sha256:{sha} 20 hours ago"]), [(sha, "a")])

    def test_bash_colors_are_skipped(self):
        lines = [
            "path: \x1b[32m/var/log/nginx.log\x1b[m",
            "path: \x1b[32mtest/log/nginx-2.log:32\x1b[mfolder/.nginx@4df2.log",
        ]
        self.assertEqual(
            [text for text, _ in texts(lines)], ["/var/log/nginx.log", "test/log/nginx-2.log", "folder/.nginx@4df2.log"]
        )

    def test_kinds(self):
        line = "see https://example.com/a?b=1 and src/app.py, #a1b2c3 0xdeadbeef 12345 deadbee"
        self.assertEqual(
            [(m.pattern, m.text) for m in thumbs.find_matches([line])],
            [
                ("url", "https://example.com/a?b=1"),
                ("path", "src/app.py"),
                ("color", "#a1b2c3"),
                ("address", "0xdeadbeef"),
                ("number", "12345"),
                ("sha", "deadbee"),
            ],
        )

    def test_markdown_url(self):
        self.assertEqual(texts(["[docs](https://example.com/docs)"]), [("https://example.com/docs", "a")])

    def test_diff(self):
        self.assertEqual(texts(["--- a/src/one.py", "+++ b/src/two.py"]), [("src/one.py", "a"), ("src/two.py", "b")])

    def test_custom_regexp_wins(self):
        self.assertEqual(texts(["ticket ABC-123 /tmp/x"], custom=[r"[A-Z]+-\d+"]), [("ABC-123", "a"), ("/tmp/x", "b")])

    def test_positions(self):
        matches = thumbs.find_matches(["", "  go to /tmp/file now"])
        self.assertEqual([(m.x, m.y) for m in matches], [(8, 1)])


class WidthTests(unittest.TestCase):
    def test_wide_characters(self):
        self.assertEqual(thumbs.cell_width("ab"), 2)
        self.assertEqual(thumbs.cell_width("日本"), 4)
        self.assertEqual(thumbs.cell_width("🐾 x"), 4)


class ColorTests(unittest.TestCase):
    def test_colors(self):
        self.assertEqual(thumbs.sgr_color("red"), "31")
        self.assertEqual(thumbs.sgr_color("red", True), "41")
        self.assertEqual(thumbs.sgr_color("brightblue"), "94")
        self.assertEqual(thumbs.sgr_color("default", True), "49")
        self.assertEqual(thumbs.sgr_color("#ff0080"), "38;2;255;0;128")


LINES = ["open https://example.com/a and /tmp/one.txt", "ip 10.0.0.1"]


def view(*argv, lines=LINES):
    options = thumbs.parse_args([*argv, "session:a", "block:b"])
    matches = thumbs.find_matches(lines, alphabet=options.alphabet)
    return thumbs.View(lines, matches, options)


def run_keys(target, keys):
    keys = list(keys)
    with mock.patch.object(thumbs, "read_key", lambda fd: keys.pop(0)):
        return target.run(0, io.StringIO())


class ViewTests(unittest.TestCase):
    def test_hints(self):
        self.assertEqual([m.hint for m in view().matches], ["a", "s", "d"])

    def test_hint_copies(self):
        self.assertEqual(run_keys(view(), ["s"]), [("/tmp/one.txt", False)])

    def test_upcase_hint(self):
        self.assertEqual(run_keys(view(), ["D"]), [("10.0.0.1", True)])

    def test_escape_cancels(self):
        self.assertEqual(run_keys(view(), ["esc"]), [])

    def test_unknown_hint_cancels(self):
        self.assertEqual(run_keys(view(), ["z"]), [])

    def test_arrows_and_enter(self):
        self.assertEqual(run_keys(view(), ["down", "down", "down", "up", "enter"]), [("/tmp/one.txt", False)])

    def test_multi_selection(self):
        self.assertEqual(
            run_keys(view(), ["space", "a", "z", "d", "space"]), [("https://example.com/a", False), ("10.0.0.1", False)]
        )

    def test_multi_option(self):
        self.assertEqual(run_keys(view("--multi"), ["s", "space"]), [("/tmp/one.txt", False)])

    def test_no_matches(self):
        self.assertEqual(run_keys(view(lines=["nothing here"]), []), [])

    def test_render_places_hints(self):
        out = io.StringIO()
        view("--hint-fg-color", "red").render("", out)
        screen = out.getvalue()
        # The arrow-key selection starts on the first match.
        self.assertIn("\x1b[1;6H\x1b[0;34;49mhttps://example.com/a", screen)
        self.assertIn("\x1b[1;32H\x1b[0;32;49m/tmp/one.txt", screen)
        self.assertIn("\x1b[1;6H\x1b[0;31;49ma", screen)
        self.assertIn("\x1b[2;4H", screen)

    def test_render_after_wide_characters(self):
        out = io.StringIO()
        view(lines=["日本 /tmp/x"]).render("", out)
        self.assertIn("\x1b[1;6H", out.getvalue())

    def test_render_contrast(self):
        out = io.StringIO()
        view("--contrast").render("", out)
        self.assertIn("[https://example.com/a]", out.getvalue())
        self.assertIn("[a]", out.getvalue())


class CommandTests(unittest.TestCase):
    def test_shell_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out")
            thumbs.run_command(f"printf '%s|' {{}} \"$THUMB\" > {path}; cat >> {path}", "a b'c", "session:a", "block:b")
            with open(path) as handle:
                self.assertEqual(handle.read(), "a b'c|a b'c|a b'c")

    def test_builtins(self):
        with mock.patch.object(thumbs, "copy_text") as copy, mock.patch.object(thumbs, "api") as api:
            thumbs.run_command("copy", "x", "session:a", "block:b")
            copy.assert_called_once_with("x")
            api.assert_not_called()
            thumbs.run_command("copy-paste", "y", "session:a", "block:b")
            api.assert_called_once_with(
                "block.event",
                session_id="session:a",
                block_id="block:b",
                event={"type": "paste", "payload": {"text": "y"}},
            )
            self.assertEqual(copy.call_count, 2)


class MainTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        patches = [
            mock.patch.dict(os.environ, {"REX_BLOCK": "block:me"}),
            mock.patch.object(thumbs, "capture", return_value=(LINES, 2, 40)),
            mock.patch.object(thumbs, "api", side_effect=lambda method, **params: self.calls.append((method, params))),
            mock.patch.object(thumbs, "run_command", side_effect=lambda *args: self.calls.append(("run",) + args)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def methods(self):
        return [call[0] for call in self.calls]

    def test_swaps_in_and_back(self):
        with mock.patch.object(thumbs, "present", return_value=[("/tmp/one.txt", True)]):
            thumbs.main(["--upcase-command", "open", "session:a", "block:b"])
        self.assertEqual(
            self.methods(),
            ["session.swap_blocks", "session.focus_block", "session.swap_blocks", "session.focus_block", "run"],
        )
        self.assertEqual(self.calls[1][1]["block_id"], "block:me")
        self.assertEqual(self.calls[3][1]["block_id"], "block:b")
        self.assertEqual(self.calls[-1], ("run", "open", "/tmp/one.txt", "session:a", "block:b"))

    def test_multi_joins_texts(self):
        with mock.patch.object(thumbs, "present", return_value=[("one", False), ("two", False)]):
            thumbs.main(["session:a", "block:b"])
        self.assertEqual(self.calls[-1], ("run", "copy", "one two", "session:a", "block:b"))

    def test_swaps_back_after_errors(self):
        with mock.patch.object(thumbs, "present", side_effect=OSError("tty")), self.assertRaises(OSError):
            thumbs.main(["session:a", "block:b"])
        self.assertEqual(
            self.methods(), ["session.swap_blocks", "session.focus_block", "session.swap_blocks", "session.focus_block"]
        )

    def test_nothing_to_hint(self):
        with mock.patch.object(thumbs, "capture", return_value=(["nothing"], 1, 40)):
            thumbs.main(["session:a", "block:b"])
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
