import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rex_thumbs as thumbs

LINES = ["see /tmp/one.txt"]
# The script starts detached; show_error places it beside the focused pane.
VIEW = {"active_window_id": "window:w", "windows": [{"window_id": "window:w", "focused_block_id": "block:b"}]}


class StartupErrorTests(unittest.TestCase):
    """Errors are shown in view instead of vanishing with the detached block (#2)."""

    def setUp(self):
        self.calls = []
        patches = [
            mock.patch.dict(os.environ, {"REX_SESSION": "session:a", "REX_BLOCK": "block:me"}),
            mock.patch.object(thumbs, "capture", return_value=(LINES, 1, 40)),
            mock.patch.object(thumbs, "api", side_effect=self.api),
            mock.patch.object(thumbs, "present", return_value=[]),
            mock.patch.object(thumbs.select, "select"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def api(self, method, **params):
        self.calls.append((method, params))
        return VIEW if method == "session.view" else {}

    def run_thumbs(self, *argv):
        with mock.patch("sys.stderr") as stderr:
            code = thumbs.run([*argv, "session:a", "block:b"])
        return code, "".join(call.args[0] for call in stderr.write.call_args_list)

    def test_bad_regexp_is_shown(self):
        code, output = self.run_thumbs("--regexp", "(")
        self.assertEqual(code, 1)
        self.assertIn("invalid regexp '('", output)
        self.assertEqual(
            [call for call in self.calls if call[0] != "session.view"],
            [
                (
                    "session.move_block",
                    {"session_id": "session:a", "block_id": "block:me", "anchor_block_id": "block:b"},
                ),
                ("session.focus_block", {"session_id": "session:a", "block_id": "block:me"}),
            ],
        )

    def test_unknown_option_is_shown(self):
        code, output = self.run_thumbs("--hint-postion", "left")
        self.assertEqual(code, 1)
        self.assertIn("unrecognized arguments: --hint-postion", output)

    def test_rex_errors_are_shown(self):
        with mock.patch.object(thumbs, "capture", side_effect=RuntimeError("block not found")):
            code, output = self.run_thumbs()
        self.assertEqual(code, 1)
        self.assertIn("rex-thumbs: block not found", output)
        self.assertIn("Press any key", output)

    def test_success_shows_nothing(self):
        code, output = self.run_thumbs()
        self.assertEqual(code, 0)
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
