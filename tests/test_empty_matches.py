import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rex_thumbs as thumbs


def texts(line, *custom):
    return [(match.pattern, match.text) for match in thumbs.find_matches([line], custom=custom)]


class EmptyMatchTests(unittest.TestCase):
    """Patterns that can match the empty string still find text later in the line (#7)."""

    def test_pattern_matching_empty_first(self):
        self.assertEqual(texts("abc 12", r"\d*"), [("custom", "12")])

    def test_optional_pattern(self):
        self.assertEqual(texts("id: xyz-42 done", r"(xyz-\d+)?"), [("custom", "xyz-42")])

    def test_empty_groups_are_skipped(self):
        self.assertEqual(texts("key=value", r"(\w*)=(\d*)"), [("custom", "key")])

    def test_builtins_unchanged(self):
        self.assertEqual(texts("see /tmp/a and 12345"), [("path", "/tmp/a"), ("number", "12345")])


if __name__ == "__main__":
    unittest.main()
