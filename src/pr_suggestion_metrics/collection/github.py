"""GitHub HTTP gateway and host-specific authentication."""

from __future__ import annotations

import base64
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import quote, urljoin

import httpx

from pr_suggestion_metrics.collection.contracts import DatasetSettings, RepoRef
from pr_suggestion_metrics.scientific_contracts import FileSnapshot


def api_base(hostname: str) -> str:
    """Return the REST API base URL for GitHub.com or GitHub Enterprise."""
    if hostname == "github.com":
        return "https://api.github.com"
    return urljoin(f"https://{hostname}/", "api/v3").rstrip("/")


def github_headers(token: str | None, accept: str = "application/vnd.github+json") -> dict[str, str]:
    """Build GitHub API headers."""
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_verify_value(settings: DatasetSettings) -> str | bool:
    """Return an httpx verify value that works on local machines and SAP hosts."""
    if settings.ssl_ca_bundle and Path(settings.ssl_ca_bundle).exists():
        return settings.ssl_ca_bundle
    return True


def token_for_host(hostname: str, *, explicit_token: str | None, settings: DatasetSettings) -> str | None:
    """Resolve a GitHub token for one host."""
    if explicit_token:
        return explicit_token
    if "wdf" in hostname and settings.github_wdf_token:
        return settings.github_wdf_token.get_secret_value()
    if settings.github_tool_token:
        return settings.github_tool_token.get_secret_value()
    return None


async def fetch_pr_json(
    client: httpx.AsyncClient,
    *,
    repo: RepoRef,
    token: str | None,
) -> dict[str, object]:
    """Fetch GitHub pull request metadata as JSON."""
    url = f"{api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/pulls/{repo.pr_number}"
    response = await client.get(url, headers=github_headers(token))
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"GitHub PR response for {url} was not an object")
    return data


async def fetch_pr_diff(client: httpx.AsyncClient, *, repo: RepoRef, token: str | None) -> str:
    """Fetch the full pull request diff from GitHub."""
    url = f"{api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/pulls/{repo.pr_number}"
    response = await client.get(url, headers=github_headers(token, "application/vnd.github.v3.diff"))
    response.raise_for_status()
    return response.text


async def fetch_pr_comments(
    client: httpx.AsyncClient,
    *,
    repo: RepoRef,
    token: str | None,
) -> list[dict[str, object]]:
    """Fetch all issue comments on one pull request."""
    comments: list[dict[str, object]] = []
    page = 1
    while True:
        url = f"{api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/issues/{repo.pr_number}/comments"
        response = await client.get(
            url,
            headers=github_headers(token),
            params={"per_page": 100, "page": page},
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError(f"GitHub comments response for {url} was not a list")
        comments.extend(entry for entry in data if isinstance(entry, dict))
        if len(data) < 100:
            return comments
        page += 1


async def fetch_pr_review_comments(
    client: httpx.AsyncClient,
    *,
    repo: RepoRef,
    token: str | None,
) -> list[dict[str, object]]:
    """Fetch all pull request review comments for one PR."""
    comments: list[dict[str, object]] = []
    page = 1
    while True:
        url = f"{api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/pulls/{repo.pr_number}/comments"
        response = await client.get(
            url,
            headers=github_headers(token),
            params={"per_page": 100, "page": page},
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError(f"GitHub review comments response for {url} was not a list")
        comments.extend(entry for entry in data if isinstance(entry, dict))
        if len(data) < 100:
            return comments
        page += 1


async def fetch_file_snapshot(
    client: httpx.AsyncClient,
    *,
    repo: RepoRef,
    token: str | None,
    path: str,
    revision_sha: str,
) -> FileSnapshot:
    """Fetch one UTF-8 repository file at an immutable Git revision."""
    encoded_path = quote(path, safe="/")
    url = f"{api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/contents/{encoded_path}"
    response = await client.get(url, headers=github_headers(token), params={"ref": revision_sha})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("type") != "file":
        raise ValueError(f"GitHub content response for {path}@{revision_sha} was not a file")
    content = payload.get("content")
    if not isinstance(content, str) or payload.get("encoding") != "base64":
        raise ValueError(f"GitHub content response for {path}@{revision_sha} was not base64 text")
    decoded = base64.b64decode(content, validate=False).decode("utf-8", errors="replace")
    return FileSnapshot(
        revision_sha=revision_sha,
        path=path,
        content=decoded,
        content_sha256=hashlib.sha256(decoded.encode("utf-8")).hexdigest(),
        source="github_contents_api",
    )


class GitHubHttpGateway:
    """GitHub operations backed by one configured HTTP client."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        explicit_token: str | None,
        settings: DatasetSettings,
    ) -> None:
        self._client = client
        self._explicit_token = explicit_token
        self._settings = settings

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        *,
        explicit_token: str | None,
        settings: DatasetSettings,
    ) -> AsyncIterator[GitHubHttpGateway]:
        async with httpx.AsyncClient(verify=github_verify_value(settings), timeout=30.0) as client:
            yield cls(client, explicit_token=explicit_token, settings=settings)

    def _token(self, hostname: str) -> str | None:
        return token_for_host(hostname, explicit_token=self._explicit_token, settings=self._settings)

    async def fetch_pr_json(self, repo: RepoRef) -> dict[str, object]:
        return await fetch_pr_json(self._client, repo=repo, token=self._token(repo.hostname))

    async def fetch_pr_diff(self, repo: RepoRef) -> str:
        return await fetch_pr_diff(self._client, repo=repo, token=self._token(repo.hostname))

    async def fetch_pr_comments(self, repo: RepoRef) -> list[dict[str, object]]:
        return await fetch_pr_comments(self._client, repo=repo, token=self._token(repo.hostname))

    async def fetch_pr_review_comments(self, repo: RepoRef) -> list[dict[str, object]]:
        return await fetch_pr_review_comments(self._client, repo=repo, token=self._token(repo.hostname))

    async def fetch_file_snapshot(self, repo: RepoRef, *, path: str, revision_sha: str) -> FileSnapshot:
        return await fetch_file_snapshot(
            self._client,
            repo=repo,
            token=self._token(repo.hostname),
            path=path,
            revision_sha=revision_sha,
        )


_api_base = api_base
_github_headers = github_headers
_github_verify_value = github_verify_value
_token_for_host = token_for_host
_fetch_pr_json = fetch_pr_json
_fetch_pr_diff = fetch_pr_diff
_fetch_pr_comments = fetch_pr_comments
_fetch_pr_review_comments = fetch_pr_review_comments
_fetch_file_snapshot = fetch_file_snapshot
