from __future__ import annotations

import unittest

from app.post_formatting import XPostFormatter


class PostFormattingTestCase(unittest.TestCase):
    def test_layout_only_formatter_preserves_non_whitespace_characters(self) -> None:
        formatter = XPostFormatter(enable_skill=False)
        source = "\u7b2c\u4e00\u53e5\u3002\u7b2c\u4e8c\u53e5\u3002\u4f46\u662f\u7b2c\u4e09\u53e5\u3002"
        formatted = formatter.format_texts([source], request_id="req-1", route="drafts_generate")[0]

        self.assertEqual("".join(source.split()), "".join(formatted.split()))
        self.assertIn("\n\n", formatted)

    def test_formatter_returns_input_when_text_is_empty(self) -> None:
        formatter = XPostFormatter(enable_skill=False)
        source = "   "
        formatted = formatter.format_texts([source], request_id="req-2", route="drafts_generate")[0]
        self.assertEqual(formatted, "")


if __name__ == "__main__":
    unittest.main()
