from __future__ import annotations

import unittest

from tools.evaluate_holdout_transfer import knowledge_source_solutions, target_knowledge_mentions


class HoldoutTransferTests(unittest.TestCase):
    def test_target_mentions_are_detected_anywhere_in_knowledge(self) -> None:
        knowledge = {
            "fragments": [{"sourceSolutions": ["donors/P015/a.solution"]}],
            "transitions": [{"provenance": {"source": "heldout/P016/secret.solution"}}],
            "convergenceMotifs": [],
        }

        mentions = target_knowledge_mentions(knowledge, "P016")

        self.assertEqual(mentions, ["heldout/P016/secret.solution"])

    def test_unrelated_knowledge_passes_target_exclusion(self) -> None:
        knowledge = {
            "fragments": [{"sourceSolutions": ["donors/P014/a.solution"]}],
            "transitions": [{"sourceSolutions": ["donors/P015/b.solution"]}],
            "convergenceMotifs": [],
        }

        self.assertEqual(target_knowledge_mentions(knowledge, "P016"), [])

    def test_source_solution_inventory_is_unique_and_sorted(self) -> None:
        knowledge = {
            "fragments": [{"sourceSolutions": ["b.solution", "a.solution"]}],
            "transitions": [{"sourceSolutions": ["a.solution"]}],
            "convergenceMotifs": [{"sourceSolutions": ["c.solution"]}],
        }

        self.assertEqual(
            knowledge_source_solutions(knowledge),
            ["a.solution", "b.solution", "c.solution"],
        )


if __name__ == "__main__":
    unittest.main()
