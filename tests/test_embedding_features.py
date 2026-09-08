from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor

from pr_suggestion_metrics.embedding_features import (
    SQLiteEmbeddingCache,
    FeatureSubsetRegressor,
    chunk_text,
    embedding_feature_row,
    prepare_embedding_example,
    safe_feature_prefix,
)


class FakeTokenizer:
    def num_special_tokens_to_add(self, pair: bool = False) -> int:
        return 2

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return [ord(character) for character in text]

    def __call__(self, text: str, **_: object) -> dict[str, list[int]]:
        return {"input_ids": self.encode(text)}

    def decode(self, token_ids: list[int], **_: object) -> str:
        return "".join(chr(token_id) for token_id in token_ids)


class EmbeddingFeatureTest(unittest.TestCase):
    def test_chunk_text_respects_overlap(self) -> None:
        chunks = chunk_text(FakeTokenizer(), "abcdefghij", max_length=6, overlap=1)

        self.assertEqual(chunks, ["abcd", "defg", "ghij"])

    def test_prepare_embedding_example_prefers_same_file_candidate(self) -> None:
        row = {
            "dataset_source": "internal",
            "example_id": "example-1",
            "suggested_diff": "--- a/app.py\n+++ b/app.py\n@@\n+return result",
            "landed_diff": (
                "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n+return value\n"
                "diff --git a/other.py b/other.py\n--- a/other.py\n+++ b/other.py\n@@ -1 +1 @@\n+print(value)"
            ),
        }

        prepared = prepare_embedding_example(row, FakeTokenizer(), 64, max_candidates=1, chunk_overlap=4)

        self.assertEqual(prepared.example_id, "example-1")
        self.assertEqual(len(prepared.candidates), 1)
        self.assertEqual(prepared.candidates[0].path, "app.py")

    def test_prepare_embedding_example_caps_large_candidate(self) -> None:
        row = {
            "dataset_source": "internal",
            "example_id": "example-large",
            "suggested_diff": "--- a/app.py\n+++ b/app.py\n@@\n+return result",
            "landed_diff": "--- a/app.py\n+++ b/app.py\n@@\n+" + ("long_line\n+" * 200),
        }

        prepared = prepare_embedding_example(
            row,
            FakeTokenizer(),
            32,
            max_candidates=1,
            chunk_overlap=4,
            max_chunks_per_candidate=3,
        )

        self.assertEqual(len(prepared.candidates), 3)

    def test_cache_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache = SQLiteEmbeddingCache(Path(temporary_directory) / "embeddings.sqlite3")
            vector = np.array([0.25, 0.75], dtype=np.float32)
            cache.put_many("model", "revision", 32, {"code": (vector, 2.5)})

            loaded = cache.get_many("model", "revision", 32, ["code"])
            cache.close()

        np.testing.assert_array_equal(loaded["code"][0], vector)
        self.assertEqual(loaded["code"][1], 2.5)

    def test_scalar_features_capture_best_similarity(self) -> None:
        row = {
            "dataset_source": "internal",
            "example_id": "example-2",
            "suggested_diff": "--- a/app.py\n+++ b/app.py\n@@\n+return result",
            "landed_diff": "--- a/app.py\n+++ b/app.py\n@@\n+return result",
        }
        example = prepare_embedding_example(row, FakeTokenizer(), 64, max_candidates=2, chunk_overlap=4)
        all_texts = [*example.suggestion_chunks, *(candidate.text for candidate in example.candidates)]
        embeddings = {text: (np.array([1.0, 0.0], dtype=np.float32), 1.0) for text in all_texts}

        features = embedding_feature_row(example, embeddings, safe_feature_prefix("test-model"))

        self.assertEqual(features["emb_test_model_best_cosine"], 1.0)
        self.assertEqual(features["emb_test_model_same_file_best_cosine"], 1.0)

    def test_feature_subset_regressor_ignores_unneeded_columns(self) -> None:
        features = pd.DataFrame({"needed": [1.0, 2.0], "extra": [100.0, 200.0]})
        model = DummyRegressor(strategy="mean").fit(features[["needed"]], [20.0, 40.0])
        wrapped = FeatureSubsetRegressor(model, ("needed",))

        np.testing.assert_array_equal(wrapped.predict(features), np.array([30.0, 30.0]))


if __name__ == "__main__":
    unittest.main()
