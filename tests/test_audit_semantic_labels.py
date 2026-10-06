from __future__ import annotations

import unittest

from pr_suggestion_metrics.audit_semantic_labels import audit_status


class SemanticLabelAuditTest(unittest.TestCase):
    def test_empty_semantic_units_are_not_classified_as_fuzzy_only(self) -> None:
        status, weight = audit_status(
            {
                "confidence": "low",
                "ambiguity_flags": [],
                "semantic_units": [],
            }
        )

        self.assertEqual(status, "uncertain_metric_disagreement")
        self.assertEqual(weight, 0.12)


if __name__ == "__main__":
    unittest.main()
