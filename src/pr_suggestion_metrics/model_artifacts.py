"""Create and verify integrity manifests for trusted local model artifacts."""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any


MANIFEST_FILENAME = "artifact_manifest.json"
MANIFEST_VERSION = 1
_RUNTIME_PACKAGES = (
    "catboost",
    "joblib",
    "lightgbm",
    "numpy",
    "pandas",
    "scikit-learn",
    "xgboost",
)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one artifact file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for package in _RUNTIME_PACKAGES:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            continue
    return versions


def write_model_manifest(model_dir: Path) -> Path:
    """Write hashes and runtime provenance for a model/schema pair."""
    model_path = model_dir / "model.joblib"
    schema_path = model_dir / "feature_schema.json"
    if not model_path.is_file() or not schema_path.is_file():
        raise FileNotFoundError(f"Model directory must contain model.joblib and feature_schema.json: {model_dir}")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "trusted_pickle_only": True,
        "model_file": model_path.name,
        "model_sha256": sha256_file(model_path),
        "schema_file": schema_path.name,
        "schema_sha256": sha256_file(schema_path),
        "model_name": schema.get("model_name"),
        "prediction_type": schema.get("prediction_type"),
        "runtime_versions": _runtime_versions(),
    }
    manifest_path = model_dir / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def verify_model_manifest(model_dir: Path) -> dict[str, Any]:
    """Verify model/schema hashes before loading a trusted local pickle artifact."""
    manifest_path = model_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing model artifact manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError(f"Unsupported model manifest version in {manifest_path}")
    if manifest.get("trusted_pickle_only") is not True:
        raise ValueError(f"Model manifest must declare trusted_pickle_only=true: {manifest_path}")

    for file_key, hash_key in (("model_file", "model_sha256"), ("schema_file", "schema_sha256")):
        file_name = manifest.get(file_key)
        expected_hash = manifest.get(hash_key)
        if not isinstance(file_name, str) or Path(file_name).name != file_name:
            raise ValueError(f"Invalid {file_key} in {manifest_path}")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise ValueError(f"Invalid {hash_key} in {manifest_path}")
        artifact_path = model_dir / file_name
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Missing model artifact: {artifact_path}")
        actual_hash = sha256_file(artifact_path)
        if actual_hash != expected_hash:
            raise ValueError(f"Artifact hash mismatch for {artifact_path}")
    return manifest
