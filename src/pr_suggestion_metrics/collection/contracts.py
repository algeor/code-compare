"""Contracts and settings for GitHub suggestion collection."""

from __future__ import annotations

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings

from pr_suggestion_metrics.scientific_contracts import SuggestionProvenance


class CandidateRow(BaseModel):
    """One GitHub pull request selected for suggestion collection."""

    inspection_id: str
    created_at: str | None = None
    github_repo_url: str | None = None
    repo_name: str | None = None
    commit_id: str | None = None
    pipeline_url: str | None = None
    execution_id: str
    fault_id: str
    handler_status: str
    pr_number: str | None = None


class SuggestionDiff(BaseModel):
    """One suggestion diff extracted from a GitHub PR comment."""

    candidate: CandidateRow
    diff_path: str
    diff_text: str
    diff_bytes: int
    provenance: SuggestionProvenance | None = None


class CodeChangeMiss(BaseModel):
    """One candidate or suggestion that could not be collected."""

    inspection_id: str
    execution_id: str
    fault_id: str
    diff_path: str
    reason: str


class DatasetSettings(BaseSettings):
    """Settings used when collecting from GitHub."""

    github_wdf_token: SecretStr | None = None
    github_tool_token: SecretStr | None = None
    ssl_ca_bundle: str | None = "/etc/ssl/ca-bundle.pem"

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


class RepoRef(BaseModel):
    """Parsed GitHub repository reference."""

    hostname: str
    owner: str
    repo: str
    pr_number: int


class PairedExample(BaseModel):
    """Dataset row pairing one comment suggestion with the final merged PR diff."""

    inspection_id: str
    fault_id: str
    handler_code_changes_diff: str
    merged_pr_diff: str
    repo_host: str
    repo_owner: str
    repo_name: str
    pr_number: int
    pr_url: str
    source_branch: str | None = None
    target_branch: str | None = None
    base_sha: str | None = None
    head_sha: str | None = None
    merge_commit_sha: str | None = None
    inspection_commit_sha: str | None = None
    handler_diff_path: str
    merged_pr_diff_source: str
    expected_landed_percentage: int | None = None
    reviewer_edited_version: str | None = None
    renamed_files: bool | None = None
    config_files_touched: bool | None = None
    suggestion_provenance: SuggestionProvenance | None = None
