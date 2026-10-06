from __future__ import annotations

import base64
import unittest

import httpx
from pydantic import SecretStr

from pr_suggestion_metrics.collection.contracts import DatasetSettings, RepoRef
from pr_suggestion_metrics.collection.github import GitHubHttpGateway, token_for_host


class GitHubGatewayTest(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_applies_enterprise_url_and_explicit_token(self) -> None:
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"merged": True})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            gateway = GitHubHttpGateway(
                client,
                explicit_token="explicit",
                settings=DatasetSettings(ssl_ca_bundle=None),
            )
            result = await gateway.fetch_pr_json(
                RepoRef(hostname="github.example", owner="owner", repo="repo", pr_number=7)
            )

        self.assertEqual(result, {"merged": True})
        self.assertEqual(str(requests[0].url), "https://github.example/api/v3/repos/owner/repo/pulls/7")
        self.assertEqual(requests[0].headers["Authorization"], "Bearer explicit")

    async def test_gateway_decodes_file_snapshot(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.params["ref"], "a" * 40)
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "encoding": "base64",
                    "content": base64.b64encode("café".encode()).decode(),
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            gateway = GitHubHttpGateway(client, explicit_token=None, settings=DatasetSettings(ssl_ca_bundle=None))
            snapshot = await gateway.fetch_file_snapshot(
                RepoRef(hostname="github.com", owner="owner", repo="repo", pr_number=7),
                path="src/example.py",
                revision_sha="a" * 40,
            )

        self.assertEqual(snapshot.content, "café")
        self.assertEqual(snapshot.source, "github_contents_api")

    def test_token_resolution_keeps_host_priority(self) -> None:
        settings = DatasetSettings(
            github_wdf_token=SecretStr("wdf"),
            github_tool_token=SecretStr("tool"),
            ssl_ca_bundle=None,
        )

        self.assertEqual(token_for_host("github.wdf.example", explicit_token=None, settings=settings), "wdf")
        self.assertEqual(token_for_host("github.com", explicit_token=None, settings=settings), "tool")
        self.assertEqual(token_for_host("github.wdf.example", explicit_token="explicit", settings=settings), "explicit")


if __name__ == "__main__":
    unittest.main()
