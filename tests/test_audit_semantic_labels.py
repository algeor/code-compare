from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pr_suggestion_metrics.audit_semantic_labels import apply_manual_override, audit_status, load_manual_overrides


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

    def test_loads_versioned_manual_override_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "overrides.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "overrides": [
                            {
                                "example_id": "example-1",
                                "expected_landed_percentage": 0,
                                "reviewer": "reviewer",
                                "guide_version": "guide-v1",
                                "rationale": "No requested behavior landed.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            overrides, schema_version = load_manual_overrides(path)
            row = apply_manual_override(
                {
                    "example_id": "example-1",
                    "confidence": "low",
                    "ambiguity_flags": [],
                    "semantic_units": [{"unit": "do x", "status": "landed_partially"}],
                    "matched_parts": ["do x"],
                    "missing_or_changed_parts": [],
                },
                overrides,
            )

        self.assertEqual(schema_version, "1.0")
        self.assertEqual(row["expected_landed_percentage"], 0)
        self.assertEqual(row["confidence"], "high")
        self.assertIn("manually_verified", row["ambiguity_flags"])


if __name__ == "__main__":
    unittest.main()
