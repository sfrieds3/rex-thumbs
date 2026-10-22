import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rex_thumbs as thumbs


class ThumbEnvTests(unittest.TestCase):
    """Chosen text reaches shell commands as data, never as shell code (#1)."""

    def run_shell(self, command, text):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            marker = os.path.join(tmp, "pwned")
            thumbs.run_command(command.replace("OUT", out), text.replace("MARKER", marker), "session:a", "block:b")
            with open(out) as handle:
                return handle.read(), os.path.exists(marker)

    def test_quoted_placeholder(self):
        self.assertEqual(self.run_shell('printf %s "{}" > OUT', "a b'c"), ("a b'c", False))

    def test_placeholder_inside_double_quotes(self):
        output, ran = self.run_shell('printf "%s" "Copied {}" > OUT', '$(touch MARKER)"; touch MARKER; echo "')
        self.assertFalse(ran, "text must not run as shell code")
        self.assertTrue(output.startswith("Copied $(touch /"), output)
        self.assertTrue(output.endswith('"; touch ' + output.split("touch ")[1].split(")")[0] + '; echo "'), output)

    def test_backticks_and_variables_stay_literal(self):
        output, ran = self.run_shell('printf %s "{}" > OUT', "`touch MARKER` $HOME")
        self.assertFalse(ran)
        self.assertTrue(output.endswith("` $HOME"), output)

    def test_unquoted_placeholder_never_runs_text(self):
        self.assertFalse(self.run_shell("printf %s {} > OUT", "; touch MARKER")[1])

    def test_env_and_stdin(self):
        output, _ = self.run_shell('printf "%s|" "$THUMB" > OUT; cat >> OUT', "x y")
        self.assertEqual(output, "x y|x y")


if __name__ == "__main__":
    unittest.main()
