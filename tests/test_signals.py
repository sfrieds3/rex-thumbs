import os
import signal
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rex_thumbs as thumbs


class SignalTests(unittest.TestCase):
    """SIGHUP and SIGTERM still swap the pane back (#4)."""

    def setUp(self):
        self.calls = []
        patches = [
            mock.patch.dict(os.environ, {"REX_BLOCK": "block:me"}),
            mock.patch.object(thumbs, "capture", return_value=(["see /tmp/one.txt"], 1, 40)),
            mock.patch.object(thumbs, "api", side_effect=lambda method, **params: self.calls.append(method)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def check(self, signum):
        before = signal.getsignal(signum)
        kill = mock.patch.object(thumbs, "present", side_effect=lambda *args: os.kill(os.getpid(), signum))
        with kill, self.assertRaises(SystemExit) as raised:
            thumbs.main(["session:a", "block:b"])
        self.assertEqual(raised.exception.code, 128 + signum)
        self.assertEqual(
            self.calls, ["session.swap_blocks", "session.focus_block", "session.swap_blocks", "session.focus_block"]
        )
        self.assertIs(signal.getsignal(signum), before, "main restores the previous handler")

    def test_sighup(self):
        self.check(signal.SIGHUP)

    def test_sigterm(self):
        self.check(signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
