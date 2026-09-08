"""Generate cached frozen-transformer similarity features from suggestion and landed diffs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from pr_suggestion_metrics.embedding_features import (
    SQLiteEmbeddingCache,
    TransformerCodeEncoder,
    embed_texts_with_cache,
    embedding_feature_row,
    prepare_embedding_example,
    safe_feature_prefix,
)


def parse_dataset(value: str) -> tuple[str, Path]:
    source, separator, raw_path = value.partition("=")
    if not separator or not source or not raw_path:
        raise argparse.ArgumentTypeError("datasets must use SOURCE=PATH")
    return source, Path(raw_path)


def read_jsonl(path: Path, source: str) -> list[dict[str, object]]:
    rows = []
    with path.open() as source_file:
        for line in source_file:
            if not line.strip():
                continue
            row = json.loads(line)
            row["dataset_source"] = source
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", action="append", type=parse_dataset, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--alias", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--max-suggestion-chunks", type=int, default=8)
    parser.add_argument("--max-chunks-per-candidate", type=int, default=4)
    parser.add_argument("--chunk-overlap", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--attention-implementation")
    parser.add_argument("--input-prefix", default="")
    args = parser.parse_args()

    encoder = TransformerCodeEncoder(
        model_id=args.model_id,
        revision=args.revision,
        max_length=args.max_length,
        device=args.device,
        trust_remote_code=args.trust_remote_code,
        attention_implementation=args.attention_implementation,
        input_prefix=args.input_prefix,
    )
    rows = [row for source, path in args.dataset for row in read_jsonl(path, source)]
    prepared = [
        prepare_embedding_example(
            row,
            tokenizer=encoder.tokenizer,
            max_length=args.max_length,
            max_candidates=args.max_candidates,
            chunk_overlap=args.chunk_overlap,
            max_suggestion_chunks=args.max_suggestion_chunks,
            max_chunks_per_candidate=args.max_chunks_per_candidate,
        )
        for row in rows
    ]
    texts = [
        text
        for example in prepared
        for text in (
            *example.suggestion_chunks,
            *(candidate.text for candidate in example.candidates),
        )
    ]
    cache = SQLiteEmbeddingCache(args.cache)
    try:
        embeddings = embed_texts_with_cache(encoder, cache, texts, batch_size=args.batch_size)
    finally:
        cache.close()
    prefix = safe_feature_prefix(args.alias)
    feature_rows = [embedding_feature_row(example, embeddings, prefix) for example in prepared]
    output = pd.DataFrame(feature_rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    metadata = {
        "model_id": args.model_id,
        "revision": args.revision,
        "alias": args.alias,
        "feature_prefix": prefix,
        "max_length": args.max_length,
        "max_candidates": args.max_candidates,
        "max_suggestion_chunks": args.max_suggestion_chunks,
        "max_chunks_per_candidate": args.max_chunks_per_candidate,
        "chunk_overlap": args.chunk_overlap,
        "trust_remote_code": args.trust_remote_code,
        "attention_implementation": args.attention_implementation,
        "input_prefix": args.input_prefix,
        "rows": len(output),
        "unique_text_chunks": len(set(texts)),
        "feature_columns": [column for column in output if column not in {"dataset_source", "example_id"}],
    }
    args.output.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
