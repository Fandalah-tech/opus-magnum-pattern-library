from __future__ import annotations

import unittest

from tools.import_critelli_event import find_puzzle_download, parse_submission_page


HTML = """
<html><body><table>
<tr><th>submitter</th><th>pronouns</th><th>solution name</th><th>CGA</th><th>BCA</th><th>submission time (UTC)</th><th>showcase?</th><th>download</th><th>notes</th></tr>
<tr>
<td>Z. Puzzelli</td><td></td><td>GOOD PUZZ</td><td>15/240/56</td><td>6/15/56</td><td>august 14, 2026 at 14:47</td><td></td>
<td><a href="/download/event123?submission=abc123">solution file</a></td>
<td><a href="/notes/abc123">show (53 words)</a></td>
</tr>
<tr>
<td>Team THE</td><td>-y/-m</td><td>SHOWCASE</td><td></td><td></td><td>august 14, 2026 at 10:35</td><td>yes</td>
<td><a href="/download/event123?submission=def456">solution file</a></td><td></td>
</tr>
</table></body></html>
"""

EVENT_HTML = """
<html><body>
<a href="/puzzles/token123" download="weeklies2026_aqueous-dagger.puzzle">weeklies2026_aqueous-dagger.puzzle</a>
</body></html>
"""


class CritelliImportTests(unittest.TestCase):
    def test_parses_scoring_and_showcase_rows(self) -> None:
        records = parse_submission_page(HTML, page_url="https://events.critelli.technology/submissions/event123")
        self.assertEqual(len(records), 2)

        scoring = records[0]
        self.assertEqual(scoring["submitter"], "Z. Puzzelli")
        self.assertEqual(scoring["solutionName"], "GOOD PUZZ")
        self.assertEqual(scoring["submissionId"], "abc123")
        self.assertEqual(scoring["cga"], {"cycles": 15, "cost": 240, "area": 56})
        self.assertEqual(scoring["bca"], {"boundingHexagon": 6, "cycles": 15, "area": 56})
        self.assertFalse(scoring["showcase"])
        self.assertEqual(scoring["notesUrls"], ["https://events.critelli.technology/notes/abc123"])

        showcase = records[1]
        self.assertEqual(showcase["submissionId"], "def456")
        self.assertIsNone(showcase["cga"])
        self.assertIsNone(showcase["bca"])
        self.assertTrue(showcase["showcase"])

    def test_finds_download_attribute_puzzle_link(self) -> None:
        result = find_puzzle_download(
            EVENT_HTML,
            page_url="https://events.critelli.technology/OM2026Weeklies6_AqueousDagger",
        )
        self.assertEqual(
            result,
            (
                "https://events.critelli.technology/puzzles/token123",
                "weeklies2026_aqueous-dagger.puzzle",
            ),
        )


if __name__ == "__main__":
    unittest.main()
