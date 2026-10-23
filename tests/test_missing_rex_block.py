import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rex_thumbs as thumbs


class MissingRexBlockTests(unittest.TestCase):
    """Without REX_BLOCK the script fails instead of waiting in the detached block (#3)."""

    def test_fails_before_capturing(self):
        env = {key: value for key, value in os.environ.items() if key != "REX_BLOCK"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(thumbs, "capture") as capture,
            self.assertRaisesRegex(RuntimeError, "REX_BLOCK is not set"),
        ):
            thumbs.main(["session:a", "block:b"])
        capture.assert_not_called()

    def test_no_swap_still_runs_by_hand(self):
        env = {key: value for key, value in os.environ.items() if key != "REX_BLOCK"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(thumbs, "capture", return_value=(["/tmp/x"], 1, 20)),
            mock.patch.object(thumbs, "terminal_size", return_value=(1, 20)),
            mock.patch.object(thumbs, "present", return_value=[]) as present,
            mock.patch.object(thumbs, "api") as api,
        ):
            self.assertEqual(thumbs.main(["--no-swap", "session:a", "block:b"]), 0)
        present.assert_called_once()
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
