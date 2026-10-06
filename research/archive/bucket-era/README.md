# Bucket-Era Research Archive

This directory preserves superseded research that categorized coverage as coarse labels or numeric ranges.

The active package uses continuous percentages from `0` through `100`. Nothing under this archive is imported by the package, exposed as a CLI entry point, or required by the supported benchmark pipeline.

## Provenance

- Archived on: 2026-10-06
- Last repository commit before archival: `caa3fd4a7ab921bbe424a839a8572f5c86641ea6`
- Historical data remains under `data/` because current reproducibility workflows reference those immutable source records.

## Contents

- `docs/`: superseded plans, prompts, worklogs, and paper materials.
- `notebooks/`: exploratory classifier, dashboard, and early regression notebooks.
- `reports/`: generated categorical and range-based evaluation outputs.
- `models/`: classifier, weighted regression, and embedding artifacts trained with superseded policies.
- `code/`: generators tied exclusively to archived reports.
- `data/`: generated labeling batches and duplicated feature/report artifacts.

### Markdown note

This archive contains many Markdown files that are intentionally retained but not part of the active documentation set.

- `docs/` contains superseded plans, prompts, and paper materials.
- `data/internal-generated/review_examples/*.md` contains generated example inspection files preserved for provenance.
- These Markdown files are useful for historical reconstruction, not for onboarding or current product claims.

These files are retained for research provenance only. Do not copy their bucket schemas back into active code or datasets.

## Integrity

`archive_manifest.json` records file counts, byte counts, and deterministic tree hashes for every archive section. It covers 586 payload files, including all 584 files removed from their active locations plus the bucket-field migration helper and its test.

Verify the archive from the repository root:

```bash
python3 research/archive/bucket-era/scripts/verify_bucket_archive.py
```

Run this verifier manually before publishing or relying on the archive as byte-preserved provenance. Normal CI does not gate on this unsupported archive.

The archived Python files and tests contain the final safety fixes made before archival, so they are not expected to be byte-identical to the pre-review commit. Four archived CSV snapshots differ from the previous commit only by line-ending normalization.
