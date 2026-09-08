#!/usr/bin/env python3
"""Find PR inspections whose handlers produced code change diffs."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel, Field
from pydantic import SecretStr
from pydantic_settings import BaseSettings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fl_shared import SharedSettings  # noqa: E402
from fl_shared.hdlf_client.client import HdlfClient, HdlfConnectionParams  # noqa: E402

OutputFormat = Literal["table", "json", "csv", "jsonl"]

_DEFAULT_STATUSES = ("success",)
_PR_PATTERNS = (
    re.compile(r"(?:^|[/_-])pr[-_/]?(\d+)(?:$|[/_-])", re.IGNORECASE),
    re.compile(r"(?:^|/)pull/(\d+)(?:$|/)", re.IGNORECASE),
    re.compile(r"(?:^|/)pullrequest/(\d+)(?:$|/)", re.IGNORECASE),
    re.compile(r"refs/pull/(\d+)", re.IGNORECASE),
    re.compile(r"pullrequestid=(\d+)", re.IGNORECASE),
)
_FL_COMMENT_MARKERS = (
    "# Fault Localization",
    "Fault Analyzer",
    "<!--inspection_id_",
    "<!--feedback_block-->",
)
_CODE_SUGGESTION_FENCE_RE = re.compile(r"`{3,}(diff|patch|suggestion)\s*\n(.*?)\n`{3,}", re.IGNORECASE | re.DOTALL)
_FAULT_HANDLER_IDS_RE = re.compile(r"<!--fault_handler_ids_([^>]*)-->")


class CandidateRow(BaseModel):
    """One DB row that might represent a PR handler execution."""

    inspection_id: str
    created_at: str | None = None
    github_repo_url: str | None = None
    repo_name: str | None = None
    commit_id: str | None = None
    pipeline_url: str | None = None
    inspection_hdlf_path: str | None = None
    execution_id: str
    fault_id: str
    handler_status: str
    handler_hdlf_path: str | None = None
    pr_number: str | None = None


class CodeChangeHit(BaseModel):
    """One handler execution with an existing HDLF code_changes.diff."""

    inspection_id: str
    execution_id: str
    fault_id: str
    handler_status: str
    created_at: str | None
    github_repo_url: str | None
    repo_name: str | None
    commit_id: str | None
    pipeline_url: str | None
    pr_number: str | None
    diff_path: str
    diff_bytes: int | None = None
    diff_preview: str | None = None


class SuggestionDiff(BaseModel):
    """One FL suggestion diff loaded from HDLF with its DB context."""

    candidate: CandidateRow
    diff_path: str
    diff_text: str
    diff_bytes: int


class CodeChangeMiss(BaseModel):
    """One candidate checked in HDLF that had no readable diff."""

    inspection_id: str
    execution_id: str
    fault_id: str
    diff_path: str
    reason: str


class ApiMissDiagnostic(BaseModel):
    """Observed API files for one inspection whose expected diff was missing."""

    inspection_id: str
    candidate_fault_ids: list[str]
    handler_results_entries: list[str] = Field(default_factory=list)
    discovered_diff_files: list[str] = Field(default_factory=list)
    reason: str | None = None


class ScanResult(BaseModel):
    """Complete scan output."""

    candidates: int
    checked: int
    hits: list[CodeChangeHit]
    misses: list[CodeChangeMiss] = Field(default_factory=list)


class DatasetSettings(BaseSettings):
    """Settings needed only for dataset collection scripts."""

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


class RepoSlug(BaseModel):
    """GitHub repository without a PR number."""

    hostname: str
    owner: str
    repo: str


class OldPrRef(BaseModel):
    """PR locator parsed from an old Photon Lithium export row."""

    mission_id: str
    fix_proposal_id: str
    failed_stage_id: str
    jenkins_url: str
    repo_name: str
    pr_number: int
    updated_at: str | None = None


class PairedExample(BaseModel):
    """Dataset row pairing one FL suggestion with the final merged PR diff."""

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
    human_label: Literal["0%", "partial", "mostly", "100%"] | None = None
    reviewer_edited_version: str | None = None
    renamed_files: bool | None = None
    config_files_touched: bool | None = None


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="SQLAlchemy async DB URL. Defaults to DATABASE_URL/.env settings.")
    parser.add_argument(
        "--old-results-csv",
        type=Path,
        help="Read PR candidates from an old Photon Lithium old_results_export.csv instead of the new DB.",
    )
    parser.add_argument(
        "--github-pr-url",
        action="append",
        default=[],
        help="Directly collect from this GitHub PR URL. Repeatable. Skips DB/CSV candidate loading.",
    )
    parser.add_argument(
        "--github-closed-prs-repo",
        help=(
            "Load closed PRs from this GitHub repository. Accepts "
            "host/owner/repo, owner/repo, or https://host/owner/repo."
        ),
    )
    parser.add_argument(
        "--github-host-for-jenkins",
        default="github.wdf.sap.corp",
        help="GitHub host used when resolving Jenkins PR URLs from --old-results-csv.",
    )
    parser.add_argument(
        "--repo-owner-preference",
        action="append",
        default=["DBaaS"],
        help="Preferred GitHub owner when a Jenkins job name matches multiple repositories. Repeatable.",
    )
    parser.add_argument(
        "--assume-repo-owner",
        help="Build GitHub repo refs as <owner>/<jenkins-job-repo> without using GitHub repository search.",
    )
    parser.add_argument("--status", action="append", default=[], help="Handler status to include. Repeatable.")
    parser.add_argument("--limit", type=int, help="Maximum DB candidates to check after sorting newest first.")
    parser.add_argument(
        "--include-github-without-pr-marker",
        action="store_true",
        help="Also include GitHub-backed inspections whose pipeline URL does not expose a PR marker.",
    )
    parser.add_argument("--skip-hdlf", action="store_true", help="Only print DB candidates; do not check HDLF.")
    parser.add_argument("--hdlf-rest-api-host", help="Override HDLF_REST_API_HOST/HDLF_FILES.")
    parser.add_argument("--hdlf-container-id", help="Override HDLF_CONTAINER_ID.")
    parser.add_argument("--hdlf-cert-dir", help="Override HDLF_CERT_DIR.")
    parser.add_argument(
        "--hdlf-via-api",
        action="store_true",
        help="Read FL suggestion diffs through the deployed control-plane API instead of direct HDLF WebHDFS.",
    )
    parser.add_argument(
        "--diagnose-misses",
        type=int,
        default=0,
        help="With --hdlf-via-api, inspect handler_results/ for this many missing inspections.",
    )
    parser.add_argument(
        "--base-url",
        default="https://pipeline-fl-control-plane-test-depl-name.fl-dev.pipelinefl.shoot.canary.k8s-hana.ondemand.com",
        help="Control-plane base URL used with --hdlf-via-api.",
    )
    parser.add_argument(
        "--ias-binding",
        type=Path,
        default=Path("ias-binding.json"),
        help="IAS binding JSON used to get a bearer token for --hdlf-via-api.",
    )
    parser.add_argument(
        "--diff-preview-chars",
        type=int,
        default=0,
        help="Include the first N diff characters in output. Default: 0.",
    )
    parser.add_argument("--save-diffs-dir", type=Path, help="Write each found diff to this local directory.")
    parser.add_argument(
        "--collect-pairs",
        action="store_true",
        help="Fetch merged GitHub PR diffs and output paired examples for labeling.",
    )
    parser.add_argument(
        "--suggestions-from-pr-comments",
        action="store_true",
        help="Load FL suggestion diffs from GitHub PR comments instead of HDLF/inspection API.",
    )
    parser.add_argument(
        "--comment-source",
        choices=("fl", "hyperspace", "all"),
        default="fl",
        help="Which PR comments/review comments to treat as suggestion sources.",
    )
    parser.add_argument(
        "--comment-author-contains",
        action="append",
        default=[],
        help="Only use comments whose GitHub author login contains this text. Repeatable.",
    )
    parser.add_argument(
        "--review-comments-only",
        action="store_true",
        help="Only scan inline PR review comments; skips top-level PR issue comments.",
    )
    parser.add_argument(
        "--github-concurrency",
        type=int,
        default=8,
        help="Maximum concurrent GitHub PRs to scan/fetch. Default: 8.",
    )
    parser.add_argument("--output", type=Path, help="Write paired examples to this file. Defaults to stdout.")
    parser.add_argument("--github-token", help="Use one explicit GitHub token for every host.")
    parser.add_argument(
        "--include-unmerged-prs",
        action="store_true",
        help="Include PRs that are not merged yet. Default skips them because there is no landed diff.",
    )
    parser.add_argument(
        "--show-misses",
        action="store_true",
        help="Include checked candidates without diffs in JSON output.",
    )
    parser.add_argument("--format", choices=("table", "json", "csv", "jsonl"), default="table")
    return parser.parse_args()


def _extract_pr_number(*values: str | None) -> str | None:
    """Return the first PR number found in URL-like values."""
    for value in values:
        if not value:
            continue
        for pattern in _PR_PATTERNS:
            match = pattern.search(value)
            if match:
                return match.group(1)
    return None


def _looks_like_pr(row: CandidateRow) -> bool:
    """Return whether the DB row has a recognizable PR signal."""
    return row.pr_number is not None


def _api_base(hostname: str) -> str:
    """Return the REST API base URL for GitHub.com or GitHub Enterprise."""
    if hostname == "github.com":
        return "https://api.github.com"
    return urljoin(f"https://{hostname}/", "api/v3").rstrip("/")


def _parse_github_repo(candidate: CandidateRow) -> RepoRef | None:
    """Parse repo host, owner, name, and PR number from DB fields."""
    pr_number_raw = candidate.pr_number
    for value in (candidate.github_repo_url, candidate.pipeline_url):
        if not value:
            continue
        parsed = urlparse(value)
        if not parsed.hostname:
            continue
        if "github" not in parsed.hostname:
            continue
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) < 2:
            continue
        repo = path_parts[1]
        if repo.endswith(".git"):
            repo = repo.removesuffix(".git")
        pr_number = pr_number_raw
        if pr_number is None and "pull" in path_parts:
            pull_index = path_parts.index("pull")
            if len(path_parts) > pull_index + 1:
                pr_number = path_parts[pull_index + 1]
        if pr_number is None:
            continue
        try:
            return RepoRef(
                hostname=parsed.hostname,
                owner=path_parts[0],
                repo=repo,
                pr_number=int(pr_number),
            )
        except ValueError:
            continue
    return None


def _candidate_from_github_pr_url(url: str) -> CandidateRow:
    """Build a candidate row from a direct GitHub PR URL."""
    parsed = urlparse(url)
    if not parsed.hostname:
        raise ValueError(f"GitHub PR URL has no host: {url!r}")
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 4 or path_parts[2] != "pull":
        raise ValueError(f"GitHub PR URL must look like /owner/repo/pull/number: {url!r}")
    owner, repo_name, _, pr_number = path_parts[:4]
    int(pr_number)
    return CandidateRow(
        inspection_id=f"github-pr-{parsed.hostname}-{owner}-{repo_name}-{pr_number}",
        github_repo_url=f"https://{parsed.hostname}/{owner}/{repo_name}",
        repo_name=f"{owner}/{repo_name}",
        commit_id=None,
        pipeline_url=url,
        inspection_hdlf_path=None,
        execution_id=f"github-pr-{pr_number}",
        fault_id=f"github-pr-{pr_number}",
        handler_status="success",
        handler_hdlf_path=None,
        pr_number=pr_number,
    )


def _parse_repo_slug(value: str, *, default_host: str) -> RepoSlug:
    """Parse host/owner/repo, owner/repo, or a GitHub repository URL."""
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError(f"GitHub repository URL has no host: {value!r}")
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) < 2:
            raise ValueError(f"GitHub repository URL must look like /owner/repo: {value!r}")
        return RepoSlug(hostname=parsed.hostname, owner=path_parts[0], repo=path_parts[1].removesuffix(".git"))

    parts = [part for part in value.split("/") if part]
    if len(parts) == 2:
        return RepoSlug(hostname=default_host, owner=parts[0], repo=parts[1].removesuffix(".git"))
    if len(parts) == 3:
        return RepoSlug(hostname=parts[0], owner=parts[1], repo=parts[2].removesuffix(".git"))
    raise ValueError(f"GitHub repository must be owner/repo, host/owner/repo, or URL: {value!r}")


async def _fetch_closed_pr_jsons(
    client: httpx.AsyncClient,
    *,
    repo: RepoSlug,
    token: str | None,
    limit: int | None,
) -> list[dict[str, object]]:
    """Fetch closed pull requests for one repository, newest first."""
    rows: list[dict[str, object]] = []
    page = 1
    while limit is None or len(rows) < limit:
        url = f"{_api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/pulls"
        response = await client.get(
            url,
            headers=_github_headers(token),
            params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": 100, "page": page},
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError(f"GitHub closed PR response for {url} was not a list")
        if not data:
            break
        rows.extend(entry for entry in data if isinstance(entry, dict))
        if len(data) < 100:
            break
        page += 1
    return rows[:limit]


async def _load_closed_pr_candidates(
    repo_value: str,
    *,
    default_host: str,
    github_token: str | None,
    limit: int | None,
) -> list[CandidateRow]:
    """Load direct PR candidates from all closed PRs in one GitHub repository."""
    repo = _parse_repo_slug(repo_value, default_host=default_host)
    settings = DatasetSettings()
    token = _token_for_host(repo.hostname, explicit_token=github_token, settings=settings)
    async with httpx.AsyncClient(verify=_github_verify_value(settings), timeout=30.0) as client:
        pr_rows = await _fetch_closed_pr_jsons(client, repo=repo, token=token, limit=limit)

    candidates: list[CandidateRow] = []
    for pr_row in pr_rows:
        number = pr_row.get("number")
        if not isinstance(number, int):
            continue
        html_url = pr_row.get("html_url")
        pr_url = html_url if isinstance(html_url, str) else f"https://{repo.hostname}/{repo.owner}/{repo.repo}/pull/{number}"
        merge_commit_sha = pr_row.get("merge_commit_sha")
        candidates.append(
            CandidateRow(
                inspection_id=f"github-pr-{repo.hostname}-{repo.owner}-{repo.repo}-{number}",
                created_at=pr_row.get("updated_at") if isinstance(pr_row.get("updated_at"), str) else None,
                github_repo_url=f"https://{repo.hostname}/{repo.owner}/{repo.repo}",
                repo_name=f"{repo.owner}/{repo.repo}",
                commit_id=merge_commit_sha if isinstance(merge_commit_sha, str) else None,
                pipeline_url=pr_url,
                inspection_hdlf_path=None,
                execution_id=f"github-pr-{number}",
                fault_id=f"github-pr-{number}",
                handler_status="success",
                handler_hdlf_path=None,
                pr_number=str(number),
            )
        )
    return candidates


def _parse_old_jenkins_pr(row: dict[str, str]) -> OldPrRef | None:
    """Parse repository name and PR number from an old Jenkins URL export row."""
    jenkins_url = (row.get("JENKINS_URL") or row.get("OLD_JENKINS_URL") or "").strip()
    parsed = urlparse(jenkins_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    pr_index = next((index for index, part in enumerate(path_parts) if re.fullmatch(r"PR-\d+", part)), None)
    if pr_index is None or pr_index < 2:
        return None
    repo_name = path_parts[pr_index - 2] if path_parts[pr_index - 1] == "job" else path_parts[pr_index - 1]
    pr_number = int(path_parts[pr_index].removeprefix("PR-"))
    mission_id = row.get("MISSION_ID", "").strip()
    fix_proposal_id = row.get("FIX_PROPOSAL_ID", "").strip()
    failed_stage_id = row.get("FAILED_STAGE_ID", "").strip()
    if not mission_id or not fix_proposal_id:
        return None
    return OldPrRef(
        mission_id=mission_id,
        fix_proposal_id=fix_proposal_id,
        failed_stage_id=failed_stage_id,
        jenkins_url=jenkins_url,
        repo_name=repo_name,
        pr_number=pr_number,
        updated_at=row.get("FIX_PROPOSAL_UPDATED_AT") or None,
    )


def _read_old_pr_refs(path: Path, limit: int | None) -> list[OldPrRef]:
    """Read old Photon Lithium CSV rows as PR references."""
    text_content = path.read_text(encoding="utf-8", errors="replace")
    first_line = text_content.splitlines()[0] if text_content.splitlines() else ""
    delimiter = "\t" if "\t" in first_line else ","
    refs: list[OldPrRef] = []
    for raw_row in csv.DictReader(text_content.splitlines(), delimiter=delimiter):
        row = {str(key).upper(): value for key, value in raw_row.items() if key is not None}
        ref = _parse_old_jenkins_pr(row)
        if ref is None:
            continue
        refs.append(ref)
        if limit is not None and len(refs) >= limit:
            break
    return refs


def _github_headers(token: str | None, accept: str = "application/vnd.github+json") -> dict[str, str]:
    """Build GitHub API headers."""
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _search_repo_ref(
    client: httpx.AsyncClient,
    *,
    hostname: str,
    repo_name: str,
    pr_number: int,
    token: str | None,
    owner_preferences: list[str],
) -> RepoRef | None:
    """Resolve a Jenkins job repository name to a GitHub repository with that PR."""
    url = f"{_api_base(hostname)}/search/repositories"
    response = await client.get(
        url,
        headers=_github_headers(token),
        params={"q": f"{repo_name} in:name", "per_page": 20},
    )
    response.raise_for_status()
    data = response.json()
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None

    exact_matches: list[RepoRef] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        owner = item.get("owner")
        if not isinstance(name, str) or not isinstance(owner, dict):
            continue
        owner_login = owner.get("login")
        if name.lower() != repo_name.lower() or not isinstance(owner_login, str):
            continue
        exact_matches.append(RepoRef(hostname=hostname, owner=owner_login, repo=name, pr_number=pr_number))

    if not exact_matches:
        return None
    preference_lookup = {owner.lower(): index for index, owner in enumerate(owner_preferences)}
    return min(exact_matches, key=lambda repo: preference_lookup.get(repo.owner.lower(), len(preference_lookup)))


async def _load_old_csv_candidates(
    path: Path,
    *,
    limit: int | None,
    github_host: str,
    github_token: str | None,
    owner_preferences: list[str],
    assume_repo_owner: str | None,
) -> list[CandidateRow]:
    """Load PR candidates from old Photon Lithium CSV and resolve GitHub repos."""
    old_refs = _read_old_pr_refs(path, limit)
    settings = DatasetSettings()
    token = _token_for_host(github_host, explicit_token=github_token, settings=settings)
    candidates: list[CandidateRow] = []
    repo_cache: dict[tuple[str, int], RepoRef | None] = {}

    async with httpx.AsyncClient(verify=_github_verify_value(settings), timeout=30.0) as client:
        for index, old_ref in enumerate(old_refs, start=1):
            if index == 1 or index % 10 == 0 or index == len(old_refs):
                _progress(f"GitHub: resolving old Jenkins PR {index}/{len(old_refs)}")
            if assume_repo_owner:
                repo = RepoRef(
                    hostname=github_host,
                    owner=assume_repo_owner,
                    repo=old_ref.repo_name,
                    pr_number=old_ref.pr_number,
                )
            else:
                key = (old_ref.repo_name, old_ref.pr_number)
                if key not in repo_cache:
                    try:
                        repo_cache[key] = await _search_repo_ref(
                            client,
                            hostname=github_host,
                            repo_name=old_ref.repo_name,
                            pr_number=old_ref.pr_number,
                            token=token,
                            owner_preferences=owner_preferences,
                        )
                    except httpx.HTTPStatusError as exc:
                        _progress(f"GitHub: repo search failed for {old_ref.repo_name}: {exc.response.status_code}")
                        repo_cache[key] = None
                repo = repo_cache[key]
            if repo is None:
                continue
            candidates.append(
                CandidateRow(
                    inspection_id=old_ref.mission_id,
                    created_at=old_ref.updated_at,
                    github_repo_url=f"https://{repo.hostname}/{repo.owner}/{repo.repo}",
                    repo_name=f"{repo.owner}/{repo.repo}",
                    commit_id=None,
                    pipeline_url=old_ref.jenkins_url,
                    inspection_hdlf_path=None,
                    execution_id=old_ref.fix_proposal_id,
                    fault_id=old_ref.failed_stage_id or old_ref.fix_proposal_id,
                    handler_status="success",
                    handler_hdlf_path=None,
                    pr_number=str(old_ref.pr_number),
                )
            )

    return candidates


def _database_url(explicit_url: str | None) -> str:
    """Resolve the database URL from CLI or shared settings."""
    if explicit_url:
        return explicit_url
    return SharedSettings().database_url


def _statuses(values: list[str]) -> tuple[str, ...]:
    """Return requested statuses or the default successful status."""
    statuses = tuple(value.strip() for value in values if value.strip())
    return statuses or _DEFAULT_STATUSES


def _progress(message: str) -> None:
    """Print a progress message immediately to stderr."""
    print(message, file=sys.stderr, flush=True)


async def _load_candidates(
    engine: AsyncEngine,
    *,
    statuses: tuple[str, ...],
    limit: int | None,
    include_github_without_pr_marker: bool,
) -> list[CandidateRow]:
    """Load candidate handler executions from the DB."""
    status_params = {f"status_{index}": status for index, status in enumerate(statuses)}
    status_placeholders = ", ".join(f":{name}" for name in status_params)
    query = text(
        f"""
        SELECT
            i.id AS inspection_id,
            CAST(i.created_at AS VARCHAR) AS created_at,
            i.github_repo_url AS github_repo_url,
            i.repo_name AS repo_name,
            i.commit_id AS commit_id,
            i.pipeline_url AS pipeline_url,
            i.path_to_hdlf AS inspection_hdlf_path,
            h.id AS execution_id,
            h.fault_id AS fault_id,
            h.status AS handler_status,
            h.path_to_hdlf AS handler_hdlf_path
        FROM inspection i
        JOIN handler_executions h ON h.inspection_id = i.id
        WHERE h.status IN ({status_placeholders})
        ORDER BY i.created_at DESC
        """
    )

    async with engine.connect() as connection:
        result = await connection.execute(query, status_params)
        rows = result.mappings().all()

    candidates: list[CandidateRow] = []
    for row in rows:
        candidate = CandidateRow(
            **dict(row),
            pr_number=_extract_pr_number(
                str(row.get("pipeline_url") or ""),
                str(row.get("github_repo_url") or ""),
                str(row.get("repo_name") or ""),
            ),
        )
        if _looks_like_pr(candidate) or (include_github_without_pr_marker and candidate.github_repo_url):
            candidates.append(candidate)
        if limit is not None and len(candidates) >= limit:
            break

    return candidates


def _load_hdlf_params(args: argparse.Namespace) -> HdlfConnectionParams:
    """Resolve HDLF connection settings from CLI overrides or environment."""
    if args.hdlf_rest_api_host or args.hdlf_container_id or args.hdlf_cert_dir:
        if not args.hdlf_rest_api_host or not args.hdlf_container_id or not args.hdlf_cert_dir:
            raise ValueError(
                "When using HDLF CLI overrides, set --hdlf-rest-api-host, --hdlf-container-id, and --hdlf-cert-dir."
            )
        return HdlfConnectionParams(
            rest_api_host=args.hdlf_rest_api_host,
            container_id=args.hdlf_container_id,
            cert_dir=args.hdlf_cert_dir,
        )

    from fl_shared.hdlf_client.config import Settings as HdlfSettings  # pylint: disable=import-outside-toplevel

    settings = HdlfSettings()
    return HdlfConnectionParams(
        rest_api_host=settings.hdlf_rest_api_host or "",
        container_id=settings.hdlf_container_id or "",
        cert_dir=settings.hdlf_cert_dir,
        client_certificate=settings.hdlf_client_certificate,
        client_key=settings.hdlf_client_key,
    )


async def _check_hdlf(
    candidates: list[CandidateRow],
    *,
    params: HdlfConnectionParams,
    diff_preview_chars: int,
    save_diffs_dir: Path | None,
) -> ScanResult:
    """Check HDLF for code_changes.diff for each candidate."""
    hits: list[CodeChangeHit] = []
    misses: list[CodeChangeMiss] = []

    if save_diffs_dir is not None:
        save_diffs_dir.mkdir(parents=True, exist_ok=True)

    async with HdlfClient(
        rest_api_host=params.rest_api_host,
        container_id=params.container_id,
        cert_dir=params.cert_dir,
        client_certificate=params.client_certificate,
        client_key=params.client_key,
    ) as client:
        for index, candidate in enumerate(candidates, start=1):
            if index == 1 or index % 10 == 0 or index == len(candidates):
                _progress(f"HDLF: checking suggestion diff {index}/{len(candidates)}")
            diff_path = f"{candidate.inspection_id}/handler_results/{candidate.fault_id}/code_changes.diff"
            try:
                diff_bytes = await client.get_object(diff_path)
            except FileNotFoundError:
                misses.append(
                    CodeChangeMiss(
                        inspection_id=candidate.inspection_id,
                        execution_id=candidate.execution_id,
                        fault_id=candidate.fault_id,
                        diff_path=diff_path,
                        reason="not_found",
                    )
                )
                continue
            except OSError as exc:
                misses.append(
                    CodeChangeMiss(
                        inspection_id=candidate.inspection_id,
                        execution_id=candidate.execution_id,
                        fault_id=candidate.fault_id,
                        diff_path=diff_path,
                        reason=f"hdlf_error: {exc}",
                    )
                )
                continue

            diff_text = diff_bytes.decode("utf-8", errors="replace")
            if save_diffs_dir is not None:
                output_path = save_diffs_dir / f"{candidate.inspection_id}_{candidate.fault_id}.diff"
                output_path.write_text(diff_text, encoding="utf-8")

            hits.append(
                CodeChangeHit(
                    inspection_id=candidate.inspection_id,
                    execution_id=candidate.execution_id,
                    fault_id=candidate.fault_id,
                    handler_status=candidate.handler_status,
                    created_at=candidate.created_at,
                    github_repo_url=candidate.github_repo_url,
                    repo_name=candidate.repo_name,
                    commit_id=candidate.commit_id,
                    pipeline_url=candidate.pipeline_url,
                    pr_number=candidate.pr_number,
                    diff_path=diff_path,
                    diff_bytes=len(diff_bytes),
                    diff_preview=diff_text[:diff_preview_chars] if diff_preview_chars > 0 else None,
                )
            )

    return ScanResult(candidates=len(candidates), checked=len(candidates), hits=hits, misses=misses)


async def _load_suggestion_diffs(
    candidates: list[CandidateRow],
    *,
    params: HdlfConnectionParams,
) -> tuple[list[SuggestionDiff], list[CodeChangeMiss]]:
    """Load full FL suggestion diffs from HDLF for paired dataset collection."""
    suggestions: list[SuggestionDiff] = []
    misses: list[CodeChangeMiss] = []

    async with HdlfClient(
        rest_api_host=params.rest_api_host,
        container_id=params.container_id,
        cert_dir=params.cert_dir,
        client_certificate=params.client_certificate,
        client_key=params.client_key,
    ) as client:
        for candidate in candidates:
            diff_path = f"{candidate.inspection_id}/handler_results/{candidate.fault_id}/code_changes.diff"
            try:
                diff_bytes = await client.get_object(diff_path)
            except FileNotFoundError:
                misses.append(
                    CodeChangeMiss(
                        inspection_id=candidate.inspection_id,
                        execution_id=candidate.execution_id,
                        fault_id=candidate.fault_id,
                        diff_path=diff_path,
                        reason="not_found",
                    )
                )
                continue
            except OSError as exc:
                misses.append(
                    CodeChangeMiss(
                        inspection_id=candidate.inspection_id,
                        execution_id=candidate.execution_id,
                        fault_id=candidate.fault_id,
                        diff_path=diff_path,
                        reason=f"hdlf_error: {exc}",
                    )
                )
                continue

            suggestions.append(
                SuggestionDiff(
                    candidate=candidate,
                    diff_path=diff_path,
                    diff_text=diff_bytes.decode("utf-8", errors="replace"),
                    diff_bytes=len(diff_bytes),
                )
            )

    return suggestions, misses


def _write_ias_cert_files(binding: dict[str, str]) -> tuple[str, str]:
    """Write IAS client certificate material to temp files for token retrieval."""
    cert_path = os.path.join(tempfile.gettempdir(), "fl-pr-pairs-ias-client.crt")
    key_path = os.path.join(tempfile.gettempdir(), "fl-pr-pairs-ias-client.key")
    Path(cert_path).write_text(binding["certificate"], encoding="utf-8")
    Path(key_path).write_text(binding["key"], encoding="utf-8")
    os.chmod(key_path, 0o600)
    return cert_path, key_path


async def _get_ias_token(binding_path: Path) -> str:
    """Fetch an IAS client-credentials token using the local binding file."""
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    cert_path, key_path = _write_ias_cert_files(binding)
    token_endpoint = f"{binding.get('url', 'https://hanaqainfrastructure.accounts400.ondemand.com')}/oauth2/token"
    async with httpx.AsyncClient(cert=(cert_path, key_path), timeout=30.0) as client:
        response = await client.post(
            token_endpoint,
            data={"grant_type": "client_credentials", "client_id": binding["clientid"]},
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("IAS token response did not contain access_token")
        return token


async def _load_suggestion_diffs_via_api(
    candidates: list[CandidateRow],
    *,
    base_url: str,
    ias_binding: Path,
) -> tuple[list[SuggestionDiff], list[CodeChangeMiss]]:
    """Load full FL suggestion diffs via the deployed control-plane API."""
    suggestions: list[SuggestionDiff] = []
    misses: list[CodeChangeMiss] = []

    _progress("API: requesting IAS bearer token")
    token = await _get_ias_token(ias_binding)
    _progress("API: bearer token acquired")
    headers = {"Authorization": f"Bearer {token}"}
    root = base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=30.0) as client:
        for index, candidate in enumerate(candidates, start=1):
            if index == 1 or index % 10 == 0 or index == len(candidates):
                _progress(f"API: fetching suggestion diff {index}/{len(candidates)}")
            relative_path = f"handler_results/{candidate.fault_id}/code_changes.diff"
            diff_path = f"{candidate.inspection_id}/{relative_path}"
            url = f"{root}/api/v1/inspection/{candidate.inspection_id}/raw"
            try:
                response = await client.get(url, headers=headers, params={"path": relative_path})
                if response.status_code == 404:
                    misses.append(
                        CodeChangeMiss(
                            inspection_id=candidate.inspection_id,
                            execution_id=candidate.execution_id,
                            fault_id=candidate.fault_id,
                            diff_path=diff_path,
                            reason="not_found",
                        )
                    )
                    continue
                response.raise_for_status()
            except httpx.HTTPError as exc:
                misses.append(
                    CodeChangeMiss(
                        inspection_id=candidate.inspection_id,
                        execution_id=candidate.execution_id,
                        fault_id=candidate.fault_id,
                        diff_path=diff_path,
                        reason=f"api_error: {exc}",
                    )
                )
                continue

            suggestions.append(
                SuggestionDiff(
                    candidate=candidate,
                    diff_path=diff_path,
                    diff_text=response.text,
                    diff_bytes=len(response.content),
                )
            )

    return suggestions, misses


async def _api_list_files(
    client: httpx.AsyncClient,
    *,
    root: str,
    headers: dict[str, str],
    inspection_id: str,
    subpath: str,
) -> list[dict[str, object]]:
    """List files for one inspection subpath through the deployed API."""
    url = f"{root}/api/v1/inspection/{inspection_id}/files"
    response = await client.get(url, headers=headers, params={"subpath": subpath})
    if response.status_code == 404:
        return []
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError(f"File listing for {inspection_id}/{subpath} did not return a list")
    return [entry for entry in data if isinstance(entry, dict)]


async def _diagnose_api_misses(
    misses: list[CodeChangeMiss],
    *,
    base_url: str,
    ias_binding: Path,
    limit: int,
) -> list[ApiMissDiagnostic]:
    """Inspect handler_results folders for missed API diff lookups."""
    if limit <= 0 or not misses:
        return []

    by_inspection: dict[str, list[CodeChangeMiss]] = {}
    for miss in misses:
        by_inspection.setdefault(miss.inspection_id, []).append(miss)
        if len(by_inspection) >= limit:
            break

    _progress(f"API: diagnosing handler_results folders for {len(by_inspection)} missed inspection(s)")
    token = await _get_ias_token(ias_binding)
    headers = {"Authorization": f"Bearer {token}"}
    root = base_url.rstrip("/")

    diagnostics: list[ApiMissDiagnostic] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for inspection_id, inspection_misses in by_inspection.items():
            candidate_fault_ids = sorted({miss.fault_id for miss in inspection_misses})
            try:
                root_entries = await _api_list_files(
                    client,
                    root=root,
                    headers=headers,
                    inspection_id=inspection_id,
                    subpath="handler_results",
                )
                handler_entries = [str(entry.get("path", "")) for entry in root_entries if entry.get("path")]
                discovered_diff_files: list[str] = []
                for entry in root_entries:
                    path = entry.get("path")
                    if not isinstance(path, str):
                        continue
                    if path.endswith(".diff"):
                        discovered_diff_files.append(path)
                    if entry.get("is_directory") is not True:
                        continue
                    child_entries = await _api_list_files(
                        client,
                        root=root,
                        headers=headers,
                        inspection_id=inspection_id,
                        subpath=path,
                    )
                    for child_entry in child_entries:
                        child_path = child_entry.get("path")
                        if isinstance(child_path, str) and child_path.endswith(".diff"):
                            discovered_diff_files.append(child_path)
                diagnostics.append(
                    ApiMissDiagnostic(
                        inspection_id=inspection_id,
                        candidate_fault_ids=candidate_fault_ids,
                        handler_results_entries=sorted(handler_entries),
                        discovered_diff_files=sorted(set(discovered_diff_files)),
                    )
                )
            except (httpx.HTTPError, ValueError) as exc:
                diagnostics.append(
                    ApiMissDiagnostic(
                        inspection_id=inspection_id,
                        candidate_fault_ids=candidate_fault_ids,
                        reason=str(exc),
                    )
                )

    return diagnostics


def _print_api_miss_diagnostics(diagnostics: list[ApiMissDiagnostic]) -> None:
    """Print concise miss diagnostics to stderr."""
    for diagnostic in diagnostics:
        _progress(f"diagnostic: inspection={diagnostic.inspection_id}")
        _progress(f"  candidate_fault_ids={', '.join(diagnostic.candidate_fault_ids) or '-'}")
        if diagnostic.reason:
            _progress(f"  error={diagnostic.reason}")
            continue
        entries = ", ".join(diagnostic.handler_results_entries[:20])
        if len(diagnostic.handler_results_entries) > 20:
            entries += f", ... (+{len(diagnostic.handler_results_entries) - 20} more)"
        _progress(f"  handler_results_entries={entries or '-'}")
        _progress(f"  discovered_diff_files={', '.join(diagnostic.discovered_diff_files) or '-'}")


def _github_verify_value(settings: DatasetSettings) -> str | bool:
    """Return an httpx verify value that works on local machines and SAP hosts."""
    if settings.ssl_ca_bundle and Path(settings.ssl_ca_bundle).exists():
        return settings.ssl_ca_bundle
    return True


def _token_for_host(hostname: str, *, explicit_token: str | None, settings: DatasetSettings) -> str | None:
    """Resolve a GitHub token for one host."""
    if explicit_token:
        return explicit_token
    if "wdf" in hostname and settings.github_wdf_token:
        return settings.github_wdf_token.get_secret_value()
    if settings.github_tool_token:
        return settings.github_tool_token.get_secret_value()
    return None


async def _fetch_pr_json(
    client: httpx.AsyncClient,
    *,
    repo: RepoRef,
    token: str | None,
) -> dict[str, object]:
    """Fetch GitHub pull request metadata as JSON."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{_api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/pulls/{repo.pr_number}"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"GitHub PR response for {url} was not an object")
    return data


async def _fetch_pr_diff(
    client: httpx.AsyncClient,
    *,
    repo: RepoRef,
    token: str | None,
) -> str:
    """Fetch the full pull request diff from GitHub."""
    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{_api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/pulls/{repo.pr_number}"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.text


async def _fetch_pr_comments(
    client: httpx.AsyncClient,
    *,
    repo: RepoRef,
    token: str | None,
) -> list[dict[str, object]]:
    """Fetch all issue comments on one pull request."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    comments: list[dict[str, object]] = []
    page = 1
    while True:
        url = f"{_api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/issues/{repo.pr_number}/comments"
        response = await client.get(url, headers=headers, params={"per_page": 100, "page": page})
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError(f"GitHub comments response for {url} was not a list")
        comments.extend(entry for entry in data if isinstance(entry, dict))
        if len(data) < 100:
            return comments
        page += 1


async def _fetch_pr_review_comments(
    client: httpx.AsyncClient,
    *,
    repo: RepoRef,
    token: str | None,
) -> list[dict[str, object]]:
    """Fetch all pull request review comments for one PR."""
    comments: list[dict[str, object]] = []
    page = 1
    while True:
        url = f"{_api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/pulls/{repo.pr_number}/comments"
        response = await client.get(url, headers=_github_headers(token), params={"per_page": 100, "page": page})
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError(f"GitHub review comments response for {url} was not a list")
        comments.extend(entry for entry in data if isinstance(entry, dict))
        if len(data) < 100:
            return comments
        page += 1


def _comment_author(comment: dict[str, object]) -> str:
    """Return the GitHub login for one comment, or empty string."""
    user = comment.get("user")
    if not isinstance(user, dict):
        return ""
    login = user.get("login")
    return login if isinstance(login, str) else ""


def _matches_comment_source(
    comment: dict[str, object],
    *,
    source: Literal["fl", "hyperspace", "all"],
    author_filters: list[str],
) -> bool:
    """Return whether a comment should be mined for suggestion code fences."""
    body = comment.get("body")
    if not isinstance(body, str):
        return False
    author = _comment_author(comment).lower()
    if author_filters and not any(value.lower() in author for value in author_filters):
        return False
    if source == "all":
        return True
    if source == "fl":
        return any(marker in body for marker in _FL_COMMENT_MARKERS)
    return "hyperspace" in author or "hyperspace" in body.lower()


def _comment_path(comment: dict[str, object]) -> str | None:
    """Return the file path attached to a review comment, when available."""
    path = comment.get("path")
    return path if isinstance(path, str) and path else None


def _normalize_comment_suggestion(language: str, text: str, path: str | None) -> str:
    """Represent a PR-comment suggestion as diff-like text for downstream tooling."""
    normalized = text.strip()
    if language.lower() in {"diff", "patch"}:
        if path and not normalized.startswith(("diff --git ", "--- ")):
            return f"--- a/{path}\n+++ b/{path}\n{normalized}"
        return normalized
    if path:
        added = "\n".join(f"+{line}" for line in normalized.splitlines())
        return f"--- a/{path}\n+++ b/{path}\n@@\n{added}"
    return normalized


def _extract_comment_diff_suggestions(
    candidate: CandidateRow,
    comment: dict[str, object],
    *,
    source: Literal["fl", "hyperspace", "all"],
    author_filters: list[str],
    kind: Literal["issue", "review"],
) -> list[SuggestionDiff]:
    """Extract code suggestion fences from one PR comment."""
    body = comment.get("body")
    if not isinstance(body, str) or not _matches_comment_source(comment, source=source, author_filters=author_filters):
        return []

    comment_id = str(comment.get("id") or "unknown")
    html_url = str(comment.get("html_url") or "")
    suggestions: list[SuggestionDiff] = []
    for index, match in enumerate(_CODE_SUGGESTION_FENCE_RE.finditer(body), start=1):
        diff_text = _normalize_comment_suggestion(match.group(1), match.group(2), _comment_path(comment))
        if not diff_text:
            continue
        following_text = body[match.end() :]
        handler_match = _FAULT_HANDLER_IDS_RE.search(following_text)
        fault_id = f"github-{kind}-comment-{comment_id}-{index}"
        if handler_match and handler_match.group(1).strip():
            fault_id = handler_match.group(1).split(",", maxsplit=1)[0].strip()
        comment_candidate = candidate.model_copy(
            update={
                "execution_id": f"github-{kind}-comment-{comment_id}-{index}",
                "fault_id": fault_id,
                "handler_hdlf_path": html_url or None,
            }
        )
        suggestions.append(
            SuggestionDiff(
                candidate=comment_candidate,
                diff_path=f"github_{kind}_comment:{comment_id}#suggestion:{index}",
                diff_text=diff_text,
                diff_bytes=len(diff_text.encode("utf-8")),
            )
        )
    return suggestions


async def _load_suggestion_diffs_from_pr_comments(
    candidates: list[CandidateRow],
    *,
    github_token: str | None,
    source: Literal["fl", "hyperspace", "all"],
    author_filters: list[str],
    review_comments_only: bool,
    github_concurrency: int,
) -> tuple[list[SuggestionDiff], list[CodeChangeMiss]]:
    """Load suggestion diffs from GitHub PR issue/review comments."""
    settings = DatasetSettings()
    suggestions: list[SuggestionDiff] = []
    misses: list[CodeChangeMiss] = []
    grouped_candidates: dict[tuple[str, str, str, int], CandidateRow] = {}

    for candidate in candidates:
        repo = _parse_github_repo(candidate)
        if repo is None:
            misses.append(
                CodeChangeMiss(
                    inspection_id=candidate.inspection_id,
                    execution_id=candidate.execution_id,
                    fault_id=candidate.fault_id,
                    diff_path="github_comments",
                    reason="github_repo_or_pr_not_resolved",
                )
            )
            continue
        key = (repo.hostname, repo.owner, repo.repo, repo.pr_number)
        grouped_candidates.setdefault(key, candidate)

    repos = [
        RepoRef(hostname=host, owner=owner, repo=repo_name, pr_number=pr_number)
        for host, owner, repo_name, pr_number in grouped_candidates
    ]
    concurrency = max(1, github_concurrency)
    semaphore = asyncio.Semaphore(concurrency)

    async def scan_repo(
        client: httpx.AsyncClient,
        repo: RepoRef,
        index: int,
    ) -> tuple[list[SuggestionDiff], CodeChangeMiss | None]:
        async with semaphore:
            if index == 1 or index % 10 == 0 or index == len(repos):
                _progress(f"GitHub: scanning PR comments {index}/{len(repos)}")
            candidate = grouped_candidates[(repo.hostname, repo.owner, repo.repo, repo.pr_number)]
            token = _token_for_host(repo.hostname, explicit_token=github_token, settings=settings)
            try:
                if review_comments_only:
                    issue_comments: list[dict[str, object]] = []
                    review_comments = await _fetch_pr_review_comments(client, repo=repo, token=token)
                else:
                    issue_comments, review_comments = await asyncio.gather(
                        _fetch_pr_comments(client, repo=repo, token=token),
                        _fetch_pr_review_comments(client, repo=repo, token=token),
                    )
            except (httpx.HTTPError, ValueError) as exc:
                return [], CodeChangeMiss(
                    inspection_id=candidate.inspection_id,
                    execution_id=candidate.execution_id,
                    fault_id=candidate.fault_id,
                    diff_path="github_comments",
                    reason=f"github_comments_error: {exc}",
                )

            found_for_pr: list[SuggestionDiff] = []
            for comment in issue_comments:
                found_for_pr.extend(
                    _extract_comment_diff_suggestions(
                        candidate,
                        comment,
                        source=source,
                        author_filters=author_filters,
                        kind="issue",
                    )
                )
            for comment in review_comments:
                found_for_pr.extend(
                    _extract_comment_diff_suggestions(
                        candidate,
                        comment,
                        source=source,
                        author_filters=author_filters,
                        kind="review",
                    )
                )
            if not found_for_pr:
                return [], CodeChangeMiss(
                    inspection_id=candidate.inspection_id,
                    execution_id=candidate.execution_id,
                    fault_id=candidate.fault_id,
                    diff_path="github_comments",
                    reason="no_comment_suggestion_found",
                )
            return found_for_pr, None

    async with httpx.AsyncClient(verify=_github_verify_value(settings), timeout=30.0) as client:
        outcomes = await asyncio.gather(*(scan_repo(client, repo, index) for index, repo in enumerate(repos, start=1)))

    for found_suggestions, miss in outcomes:
        suggestions.extend(found_suggestions)
        if miss is not None:
            misses.append(miss)

    return suggestions, misses


def _nested_string(data: dict[str, object], key: str, nested_key: str) -> str | None:
    """Extract a string from a one-level nested GitHub object."""
    nested = data.get(key)
    if not isinstance(nested, dict):
        return None
    value = nested.get(nested_key)
    return value if isinstance(value, str) else None


def _diff_has_renames(diff_text: str) -> bool:
    """Return True when a unified diff includes a file rename marker."""
    return "\nrename from " in diff_text or "\nrename to " in diff_text


def _diff_touches_config(diff_text: str) -> bool:
    """Return True when changed paths look like config files."""
    config_suffixes = (
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".conf",
        ".properties",
        ".xml",
    )
    config_names = {
        "dockerfile",
        "makefile",
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    }
    for line in diff_text.splitlines():
        if not line.startswith("diff --git "):
            continue
        path = line.rsplit(" b/", maxsplit=1)[-1].strip().lower()
        name = path.rsplit("/", maxsplit=1)[-1]
        if name in config_names or path.endswith(config_suffixes):
            return True
    return False


async def _collect_pairs(
    suggestions: list[SuggestionDiff],
    *,
    github_token: str | None,
    include_unmerged_prs: bool,
) -> tuple[list[PairedExample], list[CodeChangeMiss]]:
    """Fetch merged PR diffs and pair them with FL suggestion diffs."""
    settings = DatasetSettings()
    pairs: list[PairedExample] = []
    misses: list[CodeChangeMiss] = []
    pr_cache: dict[tuple[str, str, str, int], tuple[dict[str, object], str]] = {}

    async with httpx.AsyncClient(verify=_github_verify_value(settings), timeout=30.0) as client:
        for index, suggestion in enumerate(suggestions, start=1):
            if index == 1 or index % 10 == 0 or index == len(suggestions):
                _progress(f"GitHub: fetching merged PR diff {index}/{len(suggestions)}")
            candidate = suggestion.candidate
            repo = _parse_github_repo(candidate)
            if repo is None:
                misses.append(
                    CodeChangeMiss(
                        inspection_id=candidate.inspection_id,
                        execution_id=candidate.execution_id,
                        fault_id=candidate.fault_id,
                        diff_path=suggestion.diff_path,
                        reason="github_repo_or_pr_not_resolved",
                    )
                )
                continue

            token = _token_for_host(repo.hostname, explicit_token=github_token, settings=settings)
            repo_key = (repo.hostname, repo.owner, repo.repo, repo.pr_number)
            try:
                if repo_key not in pr_cache:
                    pr_cache[repo_key] = await asyncio.gather(
                        _fetch_pr_json(client, repo=repo, token=token),
                        _fetch_pr_diff(client, repo=repo, token=token),
                    )
                pr_json, pr_diff = pr_cache[repo_key]
            except httpx.HTTPError as exc:
                misses.append(
                    CodeChangeMiss(
                        inspection_id=candidate.inspection_id,
                        execution_id=candidate.execution_id,
                        fault_id=candidate.fault_id,
                        diff_path=suggestion.diff_path,
                        reason=f"github_error: {exc}",
                    )
                )
                continue

            merged = pr_json.get("merged")
            if merged is not True and not include_unmerged_prs:
                misses.append(
                    CodeChangeMiss(
                        inspection_id=candidate.inspection_id,
                        execution_id=candidate.execution_id,
                        fault_id=candidate.fault_id,
                        diff_path=suggestion.diff_path,
                        reason="pr_not_merged",
                    )
                )
                continue

            pairs.append(
                PairedExample(
                    inspection_id=candidate.inspection_id,
                    fault_id=candidate.fault_id,
                    handler_code_changes_diff=suggestion.diff_text,
                    merged_pr_diff=pr_diff,
                    repo_host=repo.hostname,
                    repo_owner=repo.owner,
                    repo_name=repo.repo,
                    pr_number=repo.pr_number,
                    pr_url=f"https://{repo.hostname}/{repo.owner}/{repo.repo}/pull/{repo.pr_number}",
                    source_branch=_nested_string(pr_json, "head", "ref"),
                    target_branch=_nested_string(pr_json, "base", "ref"),
                    base_sha=_nested_string(pr_json, "base", "sha"),
                    head_sha=_nested_string(pr_json, "head", "sha"),
                    merge_commit_sha=pr_json.get("merge_commit_sha")
                    if isinstance(pr_json.get("merge_commit_sha"), str)
                    else None,
                    inspection_commit_sha=candidate.commit_id,
                    handler_diff_path=suggestion.diff_path,
                    merged_pr_diff_source="github_pull_diff_api",
                    renamed_files=_diff_has_renames(pr_diff),
                    config_files_touched=_diff_touches_config(pr_diff),
                )
            )

    return pairs, misses


def _candidate_result(candidates: list[CandidateRow]) -> ScanResult:
    """Build a result object for DB-only mode."""
    hits = [
        CodeChangeHit(
            inspection_id=candidate.inspection_id,
            execution_id=candidate.execution_id,
            fault_id=candidate.fault_id,
            handler_status=candidate.handler_status,
            created_at=candidate.created_at,
            github_repo_url=candidate.github_repo_url,
            repo_name=candidate.repo_name,
            commit_id=candidate.commit_id,
            pipeline_url=candidate.pipeline_url,
            pr_number=candidate.pr_number,
            diff_path=f"{candidate.inspection_id}/handler_results/{candidate.fault_id}/code_changes.diff",
        )
        for candidate in candidates
    ]
    return ScanResult(candidates=len(candidates), checked=0, hits=hits)


def _print_json(result: ScanResult, *, show_misses: bool) -> None:
    """Print JSON output."""
    payload = result.model_dump()
    if not show_misses:
        payload.pop("misses", None)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _print_csv(result: ScanResult) -> None:
    """Print CSV output."""
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=[
            "inspection_id",
            "execution_id",
            "fault_id",
            "handler_status",
            "created_at",
            "repo_name",
            "github_repo_url",
            "pr_number",
            "commit_id",
            "pipeline_url",
            "diff_path",
            "diff_bytes",
        ],
    )
    writer.writeheader()
    for hit in result.hits:
        row = hit.model_dump()
        row.pop("diff_preview", None)
        writer.writerow(row)


def _write_pairs_jsonl(pairs: list[PairedExample], output: Path | None) -> None:
    """Write paired examples as JSONL to stdout or a file."""
    lines = [pair.model_dump_json(exclude_none=False) for pair in pairs]
    content = "\n".join(lines)
    if content:
        content += "\n"
    if output is None:
        print(content, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def _print_table(result: ScanResult) -> None:
    """Print compact human-readable output."""
    print(f"candidates={result.candidates} checked={result.checked} hits={len(result.hits)}")
    if not result.hits:
        return
    print()
    for hit in result.hits:
        print(f"inspection={hit.inspection_id} fault={hit.fault_id} bytes={hit.diff_bytes or '?'}")
        print(f"  repo={hit.repo_name or hit.github_repo_url or '-'} pr={hit.pr_number or '?'}")
        print(f"  pipeline={hit.pipeline_url or '-'}")
        print(f"  diff={hit.diff_path}")
        if hit.diff_preview:
            print("  preview:")
            print(_indent(hit.diff_preview.rstrip(), "    "))
        print()


def _indent(value: str, prefix: str) -> str:
    """Indent a multi-line value."""
    return "\n".join(f"{prefix}{line}" for line in value.splitlines())


def _emit(result: ScanResult, output_format: OutputFormat, *, show_misses: bool) -> None:
    """Emit the scan result in the requested format."""
    if output_format == "json":
        _print_json(result, show_misses=show_misses)
    elif output_format == "csv":
        _print_csv(result)
    elif output_format == "jsonl":
        for hit in result.hits:
            print(hit.model_dump_json(exclude_none=False))
    else:
        _print_table(result)


async def async_main() -> int:
    """Run the DB shortlist and optional HDLF scan."""
    args = parse_args()
    engine: AsyncEngine | None = None
    try:
        if args.github_pr_url:
            _progress("GitHub: loading direct PR candidates")
            candidates = [_candidate_from_github_pr_url(url) for url in args.github_pr_url]
            _progress(f"GitHub: loaded {len(candidates)} direct PR candidate(s)")
        elif args.github_closed_prs_repo:
            _progress("GitHub: loading closed PR candidates")
            candidates = await _load_closed_pr_candidates(
                args.github_closed_prs_repo,
                default_host=args.github_host_for_jenkins,
                github_token=args.github_token,
                limit=args.limit,
            )
            _progress(f"GitHub: loaded {len(candidates)} closed PR candidate(s)")
        elif args.old_results_csv is not None:
            _progress("CSV: loading old Photon Lithium PR candidates")
            candidates = await _load_old_csv_candidates(
                args.old_results_csv,
                limit=args.limit,
                github_host=args.github_host_for_jenkins,
                github_token=args.github_token,
                owner_preferences=args.repo_owner_preference,
                assume_repo_owner=args.assume_repo_owner,
            )
            _progress(f"CSV: loaded {len(candidates)} resolved PR candidate(s)")
        else:
            _progress("DB: loading candidate handler executions")
            engine = create_async_engine(_database_url(args.database_url))
            candidates = await _load_candidates(
                engine,
                statuses=_statuses(args.status),
                limit=args.limit,
                include_github_without_pr_marker=args.include_github_without_pr_marker,
            )
            _progress(f"DB: loaded {len(candidates)} candidate(s)")
        if args.collect_pairs:
            if not candidates:
                _write_pairs_jsonl([], args.output)
                print("summary: candidates=0 suggestions=0 pairs=0 misses=0", file=sys.stderr)
                return 0
            if args.suggestions_from_pr_comments:
                _progress("GitHub: loading FL suggestion diffs from PR comments")
                suggestions, hdlf_misses = await _load_suggestion_diffs_from_pr_comments(
                    candidates,
                    github_token=args.github_token,
                    source=args.comment_source,
                    author_filters=args.comment_author_contains,
                    review_comments_only=args.review_comments_only,
                    github_concurrency=args.github_concurrency,
                )
                _progress(f"GitHub: loaded {len(suggestions)} comment suggestion diff(s), misses={len(hdlf_misses)}")
            elif args.hdlf_via_api:
                _progress("API: loading FL suggestion diffs")
                suggestions, hdlf_misses = await _load_suggestion_diffs_via_api(
                    candidates,
                    base_url=args.base_url,
                    ias_binding=args.ias_binding,
                )
                _progress(f"API: loaded {len(suggestions)} suggestion diff(s), misses={len(hdlf_misses)}")
                if args.diagnose_misses:
                    diagnostics = await _diagnose_api_misses(
                        hdlf_misses,
                        base_url=args.base_url,
                        ias_binding=args.ias_binding,
                        limit=args.diagnose_misses,
                    )
                    _print_api_miss_diagnostics(diagnostics)
            else:
                _progress("HDLF: loading FL suggestion diffs")
                suggestions, hdlf_misses = await _load_suggestion_diffs(candidates, params=_load_hdlf_params(args))
                _progress(f"HDLF: loaded {len(suggestions)} suggestion diff(s), misses={len(hdlf_misses)}")
            _progress("GitHub: fetching merged PR diffs")
            pairs, github_misses = await _collect_pairs(
                suggestions,
                github_token=args.github_token,
                include_unmerged_prs=args.include_unmerged_prs,
            )
            _progress(f"GitHub: collected {len(pairs)} pair(s), misses={len(github_misses)}")
            _write_pairs_jsonl(pairs, args.output)
            print(
                "summary: "
                f"candidates={len(candidates)} suggestions={len(suggestions)} pairs={len(pairs)} "
                f"misses={len(hdlf_misses) + len(github_misses)}",
                file=sys.stderr,
            )
        elif args.skip_hdlf:
            result = _candidate_result(candidates)
            if args.output is not None:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            else:
                _emit(result, args.format, show_misses=args.show_misses)
        else:
            result = await _check_hdlf(
                candidates,
                params=_load_hdlf_params(args),
                diff_preview_chars=args.diff_preview_chars,
                save_diffs_dir=args.save_diffs_dir,
            )
            if args.output is not None:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            else:
                _emit(result, args.format, show_misses=args.show_misses)
    finally:
        if engine is not None:
            await engine.dispose()
    return 0


def main() -> int:
    """Script entry point."""
    try:
        return asyncio.run(async_main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
