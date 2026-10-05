from __future__ import annotations

import unittest

from pydantic import ValidationError

from pr_suggestion_metrics.reviewer_evaluation import (
    ReviewAssessmentUnit,
    evaluate_ai_review,
    summarize_ai_reviewer,
)


def correct_unit(unit_id: str = "correct") -> ReviewAssessmentUnit:
    return ReviewAssessmentUnit(
        unit_id=unit_id,
        criterion="correctness",
        verdict="correct",
        weight=3,
        ai_review_part="The unchecked value can raise ValueError.",
        expected="Identify the unhandled ValueError at the parsing call.",
        explanation="The diagnosis and location match the verified defect.",
        evidence=["tests/test_parser.py::test_invalid_value"],
        evidence_source="test",
    )


class AIReviewerEvaluationTest(unittest.TestCase):
    def test_perfect_review_has_no_deductions(self) -> None:
        evaluation = evaluate_ai_review("review-1", [correct_unit()])

        self.assertEqual(evaluation.score_percentage, 100)
        self.assertEqual(evaluation.deductions, [])
        self.assertEqual(evaluation.correct_units, 1)

    def test_every_lost_point_maps_to_a_concrete_mistake(self) -> None:
        assessments = [
            correct_unit(),
            ReviewAssessmentUnit(
                unit_id="partial-fix",
                criterion="fix_safety",
                verdict="partially_correct",
                weight=2,
                ai_review_part="Catch every Exception and return None.",
                expected="Catch ValueError only and preserve unexpected failures.",
                explanation="The fix handles the reported failure but also hides unrelated defects.",
                evidence=["tests/test_parser.py::test_unexpected_error_propagates"],
                evidence_source="test",
                mistake_code="unsafe_fix",
            ),
            ReviewAssessmentUnit(
                unit_id="missed-null-case",
                criterion="completeness",
                verdict="missed",
                weight=1,
                ai_review_part="The review did not mention the null-input path.",
                expected="Report that None reaches parse_value and crashes.",
                explanation="A required edge case was absent from the review.",
                evidence=["tests/test_parser.py::test_none_value"],
                evidence_source="test",
                mistake_code="missed_issue",
            ),
        ]

        evaluation = evaluate_ai_review("review-2", assessments)

        self.assertEqual(evaluation.score_percentage, 67)
        self.assertAlmostEqual(sum(item.points_lost for item in evaluation.deductions), 100 - 400 / 6)
        self.assertEqual(
            {item.mistake_code for item in evaluation.deductions},
            {"unsafe_fix", "missed_issue"},
        )
        self.assertEqual(evaluation.partially_correct_units, 1)
        self.assertEqual(evaluation.missed_units, 1)

    def test_non_correct_unit_requires_mistake_code(self) -> None:
        with self.assertRaisesRegex(ValidationError, "require a mistake_code"):
            ReviewAssessmentUnit(
                unit_id="bad-diagnosis",
                criterion="correctness",
                verdict="incorrect",
                weight=3,
                ai_review_part="This function leaks memory.",
                expected="No leak exists under the documented ownership contract.",
                explanation="The claim conflicts with the verified ownership behavior.",
                evidence=["Memory-sanitizer run 42"],
                evidence_source="static_analysis",
            )

    def test_duplicate_units_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be unique"):
            evaluate_ai_review("review-3", [correct_unit(), correct_unit()])

    def test_summary_reports_recurring_reviewer_mistakes(self) -> None:
        perfect = evaluate_ai_review("perfect", [correct_unit("perfect-unit")])
        incorrect = evaluate_ai_review(
            "incorrect",
            [
                ReviewAssessmentUnit(
                    unit_id="wrong-location",
                    criterion="localization",
                    verdict="incorrect",
                    weight=2,
                    ai_review_part="The defect is in the API route.",
                    expected="The defect is in the database adapter.",
                    explanation="The review points to a caller instead of the failing implementation.",
                    evidence=["Stack trace frame db/adapter.py:41"],
                    evidence_source="test",
                    mistake_code="wrong_location",
                )
            ],
        )

        summary = summarize_ai_reviewer([perfect, incorrect])

        self.assertEqual(summary.total_reviews, 2)
        self.assertEqual(summary.mean_score, 50.0)
        self.assertEqual(summary.perfect_review_rate, 0.5)
        self.assertEqual(summary.incorrect_unit_rate, 0.5)
        self.assertEqual(summary.mistake_counts, {"wrong_location": 1})


if __name__ == "__main__":
    unittest.main()
