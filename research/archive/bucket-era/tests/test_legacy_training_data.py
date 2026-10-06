from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pr_suggestion_metrics.train_percentage_regressor import (
    BOOLEAN_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    prepare_features,
    read_source,
    validate_disjoint_sources,
)


def feature_row(target: object) -> dict[str, object]:
    return {
        **{feature: 0.0 for feature in NUMERIC_FEATURES},
        **{feature: False for feature in BOOLEAN_FEATURES},
        **{feature: "none" for feature in CATEGORICAL_FEATURES},
        "expected_landed_percentage": target,
    }


class LegacyTrainingDataTest(unittest.TestCase):
    def test_out_of_range_target_is_rejected_instead_of_clipped(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite and in \\[0, 100\\]"):
            prepare_features(pd.DataFrame([feature_row(101)]))

    def test_mismatched_score_and_label_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scores_path = root / "scores.csv"
            labels_path = root / "labels.csv"
            pd.DataFrame([{"example_id": "score-only"}]).to_csv(scores_path, index=False)
            pd.DataFrame(
                [
                    {
                        "example_id": "label-only",
                        "expected_landed_percentage": 50,
                        "pr_url": "https://example.invalid/pull/1",
                        "repo": "owner/repo",
                    }
                ]
            ).to_csv(labels_path, index=False)

            with self.assertRaisesRegex(ValueError, "example_id sets differ"):
                read_source("test", scores_path, labels_path)

    def test_cross_source_example_identity_overlap_is_rejected(self) -> None:
        internal = pd.DataFrame([{"example_id": " ABC123 ", "pr_url": pd.NA}])
        external = pd.DataFrame([{"example_id": "abc123", "pr_url": None}])

        with self.assertRaisesRegex(ValueError, "overlapping example_id identities"):
            validate_disjoint_sources(internal, external)

    def test_cross_source_pr_identity_overlap_is_normalized_and_rejected(self) -> None:
        internal = pd.DataFrame(
            [
                {
                    "example_id": "internal-example",
                    "pr_url": "HTTPS://GitHub.COM/Owner/Repo/pull/001/commits",
                }
            ]
        )
        external = pd.DataFrame(
            [
                {
                    "example_id": "external-example",
                    "pr_url": "https://github.com/owner/repo.git/pull/1?view=files#discussion",
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "github.com/owner/repo/pull/1"):
            validate_disjoint_sources(internal, external)

    def test_missing_or_unparseable_pr_identities_do_not_overlap(self) -> None:
        internal = pd.DataFrame(
            [
                {"example_id": "internal-one", "pr_url": pd.NA},
                {"example_id": "internal-two", "pr_url": "not-a-pr-url"},
            ]
        )
        external = pd.DataFrame(
            [
                {"example_id": "external-one", "pr_url": None},
                {"example_id": "external-two", "pr_url": ""},
            ]
        )

        validate_disjoint_sources(internal, external)


if __name__ == "__main__":
    unittest.main()
