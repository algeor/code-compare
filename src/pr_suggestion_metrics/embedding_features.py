"""Frozen code-embedding features for semantic suggestion coverage."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin

from pr_suggestion_metrics.evaluate_metrics import (
    _added_hunks_by_file_from_diff,
    _added_lines_by_file_from_diff,
    _cross_path_anchor_recall,
    _multiset_recall,
    _normalize_identifier_and_literal_tokens,
    _prepare_hunks_by_file,
    _prepare_lines_by_file,
    _tokenize_for_path,
)


PREPROCESSING_VERSION = "embedding-diff-v1"
SIMILARITY_THRESHOLDS = (0.60, 0.70, 0.80)


@dataclass(frozen=True)
class CandidateText:
    path: str
    text: str
    same_file: bool
    retrieval_score: float


@dataclass(frozen=True)
class PreparedEmbeddingExample:
    dataset_source: str
    example_id: str
    suggestion_chunks: tuple[str, ...]
    candidates: tuple[CandidateText, ...]


class FeatureSubsetRegressor(RegressorMixin, BaseEstimator):
    """Route a shared feature frame to an estimator's required columns."""

    def __init__(self, model: Any, feature_columns: Sequence[str]) -> None:
        self.model = model
        self.feature_columns = feature_columns

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.model.predict(features.loc[:, self.feature_columns]), dtype=float)


def safe_feature_prefix(alias: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", alias.lower()).strip("_")
    if not cleaned:
        raise ValueError("embedding alias must contain at least one letter or number")
    return f"emb_{cleaned}"


def candidate_retrieval_score(
    suggestion_path: str,
    suggestion_text: str,
    candidate_path: str,
    candidate_text: str,
) -> float:
    suggestion_tokens = _normalize_identifier_and_literal_tokens(
        _tokenize_for_path(suggestion_path, suggestion_text).tokens
    )
    candidate_tokens = _normalize_identifier_and_literal_tokens(
        _tokenize_for_path(candidate_path, candidate_text).tokens
    )
    token_recall = _multiset_recall(suggestion_tokens, candidate_tokens)
    anchor_recall = _cross_path_anchor_recall(
        suggestion_path,
        suggestion_text,
        candidate_path,
        candidate_text,
    )
    same_file_bonus = 0.20 if candidate_path == suggestion_path else 0.0
    same_extension_bonus = (
        0.05
        if Path(suggestion_path).suffix.lower()
        and Path(suggestion_path).suffix.lower() == Path(candidate_path).suffix.lower()
        else 0.0
    )
    return max(token_recall, anchor_recall) + same_file_bonus + same_extension_bonus


def _candidate_texts(
    suggestion_path: str,
    suggestion_text: str,
    landed_hunks_by_file: dict[str, list[list[str]]],
    max_candidates: int,
) -> list[CandidateText]:
    candidates: list[CandidateText] = []
    seen: set[tuple[str, str]] = set()
    for candidate_path, hunks in landed_hunks_by_file.items():
        for lines in hunks:
            text = "\n".join(lines).strip()
            key = (candidate_path, text)
            if not text or key in seen:
                continue
            seen.add(key)
            candidates.append(
                CandidateText(
                    path=candidate_path,
                    text=text,
                    same_file=candidate_path == suggestion_path,
                    retrieval_score=candidate_retrieval_score(
                        suggestion_path,
                        suggestion_text,
                        candidate_path,
                        text,
                    ),
                )
            )
    return sorted(
        candidates,
        key=lambda candidate: (candidate.retrieval_score, candidate.same_file, len(candidate.text)),
        reverse=True,
    )[:max_candidates]


def prepare_embedding_example(
    row: dict[str, Any],
    tokenizer: Any,
    max_length: int,
    max_candidates: int,
    chunk_overlap: int,
    max_suggestion_chunks: int = 8,
    max_chunks_per_candidate: int = 4,
) -> PreparedEmbeddingExample:
    suggestion_by_file = _prepare_lines_by_file(_added_lines_by_file_from_diff(str(row["suggested_diff"])))
    landed_hunks_by_file = _prepare_hunks_by_file(_added_hunks_by_file_from_diff(str(row["landed_diff"])))
    suggestion_chunks: list[str] = []
    candidates: list[CandidateText] = []
    seen_candidates: set[tuple[str, str]] = set()

    for suggestion_path, lines in suggestion_by_file.items():
        suggestion_text = "\n".join(lines).strip()
        if not suggestion_text:
            continue
        suggestion_chunks.extend(
            chunk_text(tokenizer, suggestion_text, max_length, chunk_overlap)[:max_suggestion_chunks]
        )
        for candidate in _candidate_texts(
            suggestion_path,
            suggestion_text,
            landed_hunks_by_file,
            max_candidates,
        ):
            key = (candidate.path, candidate.text)
            if key in seen_candidates:
                continue
            seen_candidates.add(key)
            candidates.append(candidate)

    if not suggestion_chunks:
        fallback = str(row["suggested_diff"]).strip() or "<empty suggestion>"
        suggestion_chunks.extend(chunk_text(tokenizer, fallback, max_length, chunk_overlap))

    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: (candidate.retrieval_score, candidate.same_file),
        reverse=True,
    )[:max_candidates]
    chunked_candidates: list[CandidateText] = []
    for candidate in ranked_candidates:
        for chunk in chunk_text(tokenizer, candidate.text, max_length, chunk_overlap)[:max_chunks_per_candidate]:
            chunked_candidates.append(
                CandidateText(
                    path=candidate.path,
                    text=chunk,
                    same_file=candidate.same_file,
                    retrieval_score=candidate.retrieval_score,
                )
            )

    return PreparedEmbeddingExample(
        dataset_source=str(row["dataset_source"]),
        example_id=str(row["example_id"]),
        suggestion_chunks=tuple(suggestion_chunks),
        candidates=tuple(chunked_candidates),
    )


def chunk_text(tokenizer: Any, text: str, max_length: int, overlap: int) -> list[str]:
    special_tokens = int(tokenizer.num_special_tokens_to_add(pair=False))
    content_length = max_length - special_tokens
    if content_length <= 0:
        raise ValueError("max_length must exceed the tokenizer's special-token count")
    if overlap < 0 or overlap >= content_length:
        raise ValueError("chunk_overlap must be in [0, content_length)")
    token_ids = tokenizer(
        text,
        add_special_tokens=False,
        truncation=False,
        verbose=False,
    )["input_ids"]
    if not token_ids:
        return ["<empty>"]
    step = content_length - overlap
    chunks = []
    for start in range(0, len(token_ids), step):
        chunk_ids = token_ids[start : start + content_length]
        chunks.append(tokenizer.decode(chunk_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False))
        if start + content_length >= len(token_ids):
            break
    return chunks


class SQLiteEmbeddingCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS embeddings (
                cache_key TEXT PRIMARY KEY,
                model_id TEXT NOT NULL,
                revision TEXT NOT NULL,
                preprocessing_version TEXT NOT NULL,
                max_length INTEGER NOT NULL,
                text_sha256 TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                raw_norm REAL NOT NULL,
                vector BLOB NOT NULL
            )
            """
        )
        self.connection.commit()

    @staticmethod
    def key(model_id: str, revision: str, max_length: int, text: str) -> str:
        payload = json.dumps(
            {
                "model_id": model_id,
                "revision": revision,
                "preprocessing_version": PREPROCESSING_VERSION,
                "max_length": max_length,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get_many(
        self,
        model_id: str,
        revision: str,
        max_length: int,
        texts: Sequence[str],
    ) -> dict[str, tuple[np.ndarray, float]]:
        result: dict[str, tuple[np.ndarray, float]] = {}
        for text in texts:
            cache_key = self.key(model_id, revision, max_length, text)
            row = self.connection.execute(
                "SELECT dimension, raw_norm, vector FROM embeddings WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            if row is None:
                continue
            dimension, raw_norm, vector = row
            result[text] = (np.frombuffer(vector, dtype=np.float32, count=dimension).copy(), float(raw_norm))
        return result

    def put_many(
        self,
        model_id: str,
        revision: str,
        max_length: int,
        values: dict[str, tuple[np.ndarray, float]],
    ) -> None:
        rows = []
        for text, (vector, raw_norm) in values.items():
            normalized = np.asarray(vector, dtype=np.float32)
            rows.append(
                (
                    self.key(model_id, revision, max_length, text),
                    model_id,
                    revision,
                    PREPROCESSING_VERSION,
                    max_length,
                    hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    len(normalized),
                    float(raw_norm),
                    normalized.tobytes(),
                )
            )
        self.connection.executemany(
            """
            INSERT OR REPLACE INTO embeddings (
                cache_key, model_id, revision, preprocessing_version, max_length,
                text_sha256, dimension, raw_norm, vector
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


class TransformerCodeEncoder:
    def __init__(
        self,
        model_id: str,
        revision: str,
        max_length: int,
        device: str,
        trust_remote_code: bool,
        attention_implementation: str | None = None,
        input_prefix: str = "",
    ) -> None:
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        self.model_id = model_id
        self.revision = revision
        self.max_length = max_length
        self.input_prefix = input_prefix
        profile = {
            "input_prefix": input_prefix,
            "attention_implementation": attention_implementation,
            "pooling": "attention_mask_mean",
        }
        self.cache_identity = model_id if not input_prefix and attention_implementation is None else (
            f"{model_id}|profile={json.dumps(profile, sort_keys=True)}"
        )
        self.device = torch.device(device)
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            revision=revision,
            trust_remote_code=trust_remote_code,
        )
        model_options = {}
        if attention_implementation is not None:
            model_options["attn_implementation"] = attention_implementation
        self.model, loading_info = AutoModel.from_pretrained(
            model_id,
            revision=revision,
            trust_remote_code=trust_remote_code,
            output_loading_info=True,
            **model_options,
        )
        if loading_info["missing_keys"]:
            preview = ", ".join(loading_info["missing_keys"][:8])
            raise RuntimeError(
                f"checkpoint architecture mismatch for {model_id}; missing weights: {preview}"
            )
        self.model = self.model.to(self.device)
        self.model.eval()

    def encode(self, texts: Sequence[str], batch_size: int) -> dict[str, tuple[np.ndarray, float]]:
        encoded: dict[str, tuple[np.ndarray, float]] = {}
        with self.torch.inference_mode():
            for start in range(0, len(texts), batch_size):
                batch = list(texts[start : start + batch_size])
                model_inputs = [f"{self.input_prefix}{text}" for text in batch]
                tokens = self.tokenizer(
                    model_inputs,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                )
                tokens = {name: value.to(self.device) for name, value in tokens.items()}
                outputs = self.model(**tokens)
                hidden = outputs.last_hidden_state
                mask = tokens["attention_mask"].unsqueeze(-1).to(hidden.dtype)
                pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
                raw_norms = self.torch.linalg.vector_norm(pooled, dim=1)
                normalized = self.torch.nn.functional.normalize(pooled, p=2, dim=1)
                for text, vector, raw_norm in zip(batch, normalized.cpu().numpy(), raw_norms.cpu().numpy(), strict=True):
                    encoded[text] = (np.asarray(vector, dtype=np.float32), float(raw_norm))
        return encoded


def embed_texts_with_cache(
    encoder: TransformerCodeEncoder,
    cache: SQLiteEmbeddingCache,
    texts: Iterable[str],
    batch_size: int,
) -> dict[str, tuple[np.ndarray, float]]:
    unique_texts = list(dict.fromkeys(texts))
    values = cache.get_many(encoder.cache_identity, encoder.revision, encoder.max_length, unique_texts)
    missing = [text for text in unique_texts if text not in values]
    for start in range(0, len(missing), batch_size * 25):
        batch_texts = missing[start : start + batch_size * 25]
        encoded = encoder.encode(batch_texts, batch_size=batch_size)
        cache.put_many(encoder.cache_identity, encoder.revision, encoder.max_length, encoded)
        values.update(encoded)
        print(f"embedded {min(start + len(batch_texts), len(missing))}/{len(missing)} uncached chunks", flush=True)
    return values


def cosine(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.clip(np.dot(left, right), -1.0, 1.0))


def embedding_feature_row(
    example: PreparedEmbeddingExample,
    embeddings: dict[str, tuple[np.ndarray, float]],
    prefix: str,
) -> dict[str, float | int | str]:
    suggestion_vectors = [embeddings[text][0] for text in example.suggestion_chunks]
    suggestion_norms = [embeddings[text][1] for text in example.suggestion_chunks]
    candidate_vectors = [embeddings[candidate.text][0] for candidate in example.candidates]
    candidate_norms = [embeddings[candidate.text][1] for candidate in example.candidates]
    candidate_scores = []
    same_file_scores = []
    cross_file_scores = []
    for candidate, candidate_vector in zip(example.candidates, candidate_vectors, strict=True):
        score = max(cosine(suggestion_vector, candidate_vector) for suggestion_vector in suggestion_vectors)
        candidate_scores.append(score)
        (same_file_scores if candidate.same_file else cross_file_scores).append(score)

    ordered_scores = sorted(candidate_scores, reverse=True)
    best = ordered_scores[0] if ordered_scores else 0.0
    second = ordered_scores[1] if len(ordered_scores) > 1 else 0.0
    top_three = ordered_scores[:3]
    if candidate_vectors:
        landed_centroid = np.mean(candidate_vectors, axis=0)
        landed_centroid /= max(np.linalg.norm(landed_centroid), 1e-12)
        centroid_score = max(cosine(vector, landed_centroid) for vector in suggestion_vectors)
    else:
        centroid_score = 0.0

    result: dict[str, float | int | str] = {
        "dataset_source": example.dataset_source,
        "example_id": example.example_id,
        f"{prefix}_best_cosine": best,
        f"{prefix}_mean_top3_cosine": float(np.mean(top_three)) if top_three else 0.0,
        f"{prefix}_best_second_margin": best - second,
        f"{prefix}_candidate_mean_cosine": float(np.mean(candidate_scores)) if candidate_scores else 0.0,
        f"{prefix}_landed_centroid_cosine": centroid_score,
        f"{prefix}_same_file_best_cosine": max(same_file_scores, default=0.0),
        f"{prefix}_cross_file_best_cosine": max(cross_file_scores, default=0.0),
        f"{prefix}_suggestion_raw_norm": float(np.mean(suggestion_norms)),
        f"{prefix}_candidate_raw_norm": float(np.mean(candidate_norms)) if candidate_norms else 0.0,
        f"{prefix}_suggestion_chunk_count": len(suggestion_vectors),
        f"{prefix}_candidate_chunk_count": len(candidate_vectors),
    }
    for threshold in SIMILARITY_THRESHOLDS:
        suffix = str(int(threshold * 100))
        result[f"{prefix}_fraction_above_{suffix}"] = (
            float(np.mean(np.asarray(candidate_scores) >= threshold)) if candidate_scores else 0.0
        )
    return result


def add_embedding_interactions(frame: pd.DataFrame, embedding_columns: Sequence[str]) -> pd.DataFrame:
    result = frame.copy()
    best_columns = [column for column in embedding_columns if column.endswith("_best_cosine") and "same_file" not in column and "cross_file" not in column]
    for best_column in best_columns:
        result[f"{best_column}_x_token_recall"] = result[best_column] * result["best_hunk_token_recall"]
        result[f"{best_column}_x_structural_similarity"] = result[best_column] * result["structural_similarity"]
    return result
