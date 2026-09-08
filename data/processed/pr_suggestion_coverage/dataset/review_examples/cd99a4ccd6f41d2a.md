# cd99a4ccd6f41d2a

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/53
Suggested label: 35%
File overlap: 1.0
Changed-line overlap: 0.0

## Suggested diff
```diff
--- a/fl_mcp_servers/github_finalizer/server.py
+++ b/fl_mcp_servers/github_finalizer/server.py
@@
+_update_check_run(app, check_run_id, request, config)
+    comment_url, comment_id, comment_skipped = _publish_comment(app, request, config, check_run_url)
```

## Landed PR diff
```diff
diff --git a/CLAUDE.md b/CLAUDE.md
index 1f6193fc..77acbbc4 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -1,4 +1,8 @@
 # Python Code Style Guide
+ 
+** READ THE ARCHITECTURE.md FIRST **
+
+@ARCHITECTURE.md
 
 ## Imports
 
diff --git a/fl_mcp_servers/Dockerfile b/fl_mcp_servers/Dockerfile
index 65b79ffe..c2b26430 100644
--- a/fl_mcp_servers/Dockerfile
+++ b/fl_mcp_servers/Dockerfile
@@ -38,7 +38,10 @@ ENV PATH=/home/app/venv/bin:$PATH
 
 ENV PYTHONDONTWRITEBYTECODE=1
 
+RUN python -c "import fl_mcp_servers.generic.inspection_results_mcp; import fl_mcp_servers.generic.pipeline_data_mcp; import fl_mcp_servers.github_finalizer.server"
+
 # Launched by the agent runtime as a stdio subprocess.  The runtime specifies
 # which server to start via the command, e.g.:
 #   python -m fl_mcp_servers.generic.pipeline_data_mcp
 #   python -m fl_mcp_servers.generic.inspection_results_mcp
+#   python -m fl_mcp_servers.github_finalizer.server
diff --git a/fl_mcp_servers/github_finalizer/__init__.py b/fl_mcp_servers/github_finalizer/__init__.py
new file mode 100644
index 00000000..3b5a6421
--- /dev/null
+++ b/fl_mcp_servers/github_finalizer/__init__.py
@@ -0,0 +1 @@
+"""FL Summary GitHub Finalizer MCP server and its rendering, config, and GitHub App helpers."""
diff --git a/fl_mcp_servers/github_finalizer/app_client.py b/fl_mcp_servers/github_finalizer/app_client.py
new file mode 100644
index 00000000..904032da
--- /dev/null
+++ b/fl_mcp_servers/github_finalizer/app_client.py
@@ -0,0 +1,188 @@
+"""GitHub App client for the FL summary finalizer.
+
+Uses PyGithub's GitHub App installation-auth path (``Auth.AppAuth`` +
+``GithubIntegration``), cached per ``(host, repo)`` via a registry, with tenacity
+retries.  Credentials come from
+:class:`fl_mcp_servers.github_finalizer.settings.GithubFinalizerSettings`
+(``MCP_GITHUB_APP_*`` env vars).
+
+Only the methods the finalizer needs are kept: check-run create/update/get/list
+and comment get/create/delete, plus ``get_commit`` / ``get_pull_request`` /
+``get_content``.
+
+Known limitation: PyGithub manages the installation access token internally, so
+mid-run token refresh past its 1-hour lifetime is not provided.  This is
+acceptable: the GitHub I/O this client does happens in seconds of wall-clock
+after the agent's reasoning, well within a fresh token's lifetime.
+"""
+
+from __future__ import annotations
+
+from typing import Any
+
+from github import Auth, GithubIntegration, UnknownObjectException
+from github.CheckRun import CheckRun
+from github.Commit import Commit
+from github.CommitComment import CommitComment
+from github.IssueComment import IssueComment
+from github.PullRequest import PullRequest
+from github.Repository import Repository
+from tenacity import retry
+from tenacity.stop import stop_after_attempt
+from tenacity.wait import wait_fixed
+
+from fl_mcp_servers.github_finalizer.settings import AppVariant, GithubFinalizerSettings, GitHubHost
+
+
+class GitHubAppError(Exception):
+    """Raised when a GitHub App operation cannot be performed."""
+
+
+class GithubApp:
+    """GitHub App connector scoped to a single ``(host, repository, variant)``.
+
+    Each instance is bound to one credential set (prod or test) at construction
+    and never switches — reads and writes both go through the same App. Instances
+    are created through :meth:`GithubAppRegistry.get` so they are reused across
+    tool calls; construct directly only in tests.
+    """
+
+    def __init__(
+        self,
+        host: GitHubHost,
+        repo_full_name: str,
+        settings: GithubFinalizerSettings,
+        variant: AppVariant = AppVariant.PROD,
+    ) -> None:
+        """Initialise the connector for ``host``, ``repo_full_name`` (``owner/name``), and App ``variant``."""
+        self.host = host
+        self.variant = variant
+        self._settings = settings
+        self._repo_owner, self._repo_name = repo_full_name.split("/", 1)
+        self._repo: Repository | None = None
+        self._github_integration: GithubIntegration | None = None
+
+    def get_repo_full_name(self) -> str:
+        """Return the repository full name, ``owner/name``."""
+        return f"{self._repo_owner}/{self._repo_name}"
+
+    def _get_github_integration(self) -> GithubIntegration:
+        if self._github_integration is None:
+            app_id, app_key = self._settings.get_app_credentials(self.host, self.variant)
+            auth = Auth.AppAuth(app_id, app_key)
+            self._github_integration = GithubIntegration(auth=auth, base_url=f"{self.host.value}/api/v3", verify=False)
+        return self._github_integration
+
+    def _get_repository(self) -> Repository:
+        if self._repo is None:
+            integration = self._get_github_integration()
+            installation = integration.get_repo_installation(self._repo_owner, self._repo_name)
+            github = installation.get_github_for_installation()
+            self._repo = github.get_repo(self.get_repo_full_name())
+        return self._repo
+
+    @retry(wait=wait_fixed(1), stop=stop_after_attempt(3), reraise=True)
+    def get_commit(self, commit_sha: str) -> Commit:
+        """Return the commit for ``commit_sha``."""
+        return self._get_repository().get_commit(commit_sha)
+
+    @retry(wait=wait_fixed(1), stop=stop_after_attempt(3), reraise=True)
+    def get_pull_request(self, pull_request_number: int) -> PullRequest:
+        """Return the pull request numbered ``pull_request_number``."""
+        return self._get_repository().get_pull(pull_request_number)
+
+    @retry(wait=wait_fixed(1), stop=stop_after_attempt(3), reraise=True)
+    def get_comments(self, origin: Commit | PullRequest) -> list[CommitComment | IssueComment]:
+        """Return comments on a commit or the issue comments on a pull request.
+
+        Args:
+            origin: The commit or pull request to read comments from.
+
+        Returns:
+            The comments on ``origin``.
+        """
+        if isinstance(origin, PullRequest):
+            return list(origin.get_issue_comments())
+        return list(origin.get_comments())
+
+    @retry(wait=wait_fixed(1), stop=stop_after_attempt(3), reraise=True)
+    def create_comment(self, origin: Commit | PullRequest, body: str) -> CommitComment | IssueComment:
+        """Create a comment on a commit or a pull request and return it.
+
+        Args:
+            origin: The commit or pull request to comment on.
+            body: The comment body.
+
+        Returns:
+            The created comment.
+        """
+        if isinstance(origin, PullRequest):
+            return origin.create_issue_comment(body)
+        return origin.create_comment(body)
+
+    @retry(wait=wait_fixed(1), stop=stop_after_attempt(3), reraise=True)
+    def delete_comment(self, comment: CommitComment | IssueComment) -> None:
+        """Delete a commit or issue comment."""
+        comment.delete()
+
+    @retry(wait=wait_fixed(1), stop=stop_after_attempt(3), reraise=True)
+    def get_check_runs(self, head_sha: str) -> list[CheckRun]:
+        """Return all check runs on the commit ``head_sha``."""
+        return list(self._get_repository().get_commit(head_sha).get_check_runs())
+
+    @retry(wait=wait_fixed(1), stop=stop_after_attempt(3), reraise=True)
+    def update_check_run(self, check_run_id: int, **kwargs: Any) -> CheckRun:
+        """Update the check run ``check_run_id`` and return it.
+
+        Args:
+            check_run_id: The check run to update.
+            **kwargs: Fields to edit (``status``, ``conclusion``, ``output``, ...).
+
+        Returns:
+            The updated check run.
+        """
+        check_run = self._get_repository().get_check_run(check_run_id)
+        check_run.edit(**kwargs)
+        return check_run
+
+    @retry(wait=wait_fixed(1), stop=stop_after_attempt(3), reraise=True)
+    def get_content(self, path: str, ref: str) -> str | None:
+        """Return the decoded text content of a file, or ``None`` if absent.
+
+        Args:
+            path: Repository-relative file path.
+            ref: The commit SHA or ref to read at.
+
+        Returns:
+            The file content, or ``None`` when the file does not exist.
+
+        Raises:
+            GitHubAppError: If ``path`` resolves to more than one file.
+        """
+        try:
+            content = self._get_repository().get_contents(path, ref)
+        except UnknownObjectException:
+            return None
+        if isinstance(content, list):
+            raise GitHubAppError(f"Multiple files found at path {path!r} in {self.get_repo_full_name()} at {ref}.")
+        return content.decoded_content.decode()
+
+
+class GithubAppRegistry:
+    """Caches one :class:`GithubApp` per ``(host, repo, variant)`` for the process.
+
+    The cache is owned by the MCP server's lifespan state and reset cleanly
+    between tests.
+    """
+
+    def __init__(self, settings: GithubFinalizerSettings) -> None:
+        """Initialise an empty per-``(host, repo, variant)`` cache using ``settings`` for auth."""
+        self._settings = settings
+        self._apps: dict[tuple[GitHubHost, str, AppVariant], GithubApp] = {}
+
+    def get(self, host: GitHubHost, repo_full_name: str, variant: AppVariant = AppVariant.PROD) -> GithubApp:
+        """Return the cached app for ``(host, repo_full_name, variant)``, creating it once."""
+        key = (host, repo_full_name, variant)
+        if key not in self._apps:
+            self._apps[key] = GithubApp(host, repo_full_name, self._settings, variant)
+        return self._apps[key]
diff --git a/fl_mcp_servers/github_finalizer/comment_format.py b/fl_mcp_servers/github_finalizer/comment_format.py
new file mode 100644
index 00000000..0f8d094f
--- /dev/null
+++ b/fl_mcp_servers/github_finalizer/comment_format.py
@@ -0,0 +1,236 @@
+"""Deterministic rendering of the FL summary comment and check-run output.
+
+The agent supplies :mod:`fl_mcp_servers.github_finalizer.models` objects; this module turns them
+into markdown.  It is database-free and pure — no GitHub, no I/O — so it is
+unit-testable in isolation and the rendered body can be inspected before it is
+posted.
+
+The rendered structure is byte-compatible with the production "Photon Service /
+Fault Analyzer" comment (see ``photon-service-test[bot]`` on DBaaS/sample PRs),
+because the feedback webhook parses the comment by locating these exact markers
+and the checkbox lines. Do not change marker spelling or whitespace without
+updating that parser.
+
+Marker contract:
+
+- Header comment, followed on the same line by the inspection marker, scopes the
+  whole comment for idempotent rerun and carries the inspection id::
+
+      <!-- DO NOT CHANGE ... --><!--inspection_id_<uuid>-->
+
+- The commit marker records the analysed commit::
+
+      <!--commit_sha_<sha>-->
+
+- One feedback block per proposal, led by the feedback marker and the
+  proposal's contributing fault-handler ids so the webhook attributes a rating
+  without a database lookup::
+
+      <!--feedback_block--><!--fault_handler_ids_<id>,<id>-->
+"""
+
+from __future__ import annotations
+
+import re
+
+from fl_mcp_servers.github_finalizer.models import (
+    FinalizeRequest,
+    Proposal,
+)
+
+# Header comment + inspection marker share one line; the webhook keys off both.
+HEADER_MARKER = (
+    "<!-- DO NOT CHANGE THE STRUCTURE OR CONTENT OF THIS COMMENT. "
+    "This comment will be analyzed automatically by clicking the checkboxes. -->"
+)
+
+INSPECTION_MARKER = "<!--inspection_id_{inspection_id}-->"
+
+COMMIT_MARKER = "<!--commit_sha_{commit_sha}-->"
+
+# Recognises any FL summary comment regardless of inspection, for finding a
+# previous summary comment to replace on rerun.
+OUTER_MARKER_RE = re.compile(r"<!--inspection_id_\S+-->")
+
+TITLE = "# Fault Localization"
+
+# GitHub's hard per-comment character limit is a fixed platform constant, not a
+# per-deployment knob. Rendering stays below it; the check run carries anything
+# the comment drops.
+GITHUB_CHARACTER_LIMIT = 60000
+
+INTRO = "The pipeline run encountered failures. We analyzed the build logs and identified the following issues:"
+
+# The leading marker line carries the contributing fault-handler ids (CSV) so
+# the feedback webhook attributes a rating without a database lookup; the
+# checkbox lines are what the webhook toggles.
+FEEDBACK_BLOCK = (
+    "<!--feedback_block--><!--fault_handler_ids_{fault_handler_ids}-->\n"
+    "*Please rate the quality of the fix proposal by selecting one of the following options:*\n"
+    "- [ ] :100: - The fix proposal solves the problem.\n"
+    "- [ ] :+1: - The fix proposal helps to solve the problem.\n"
+    "- [ ] :-1: - The fix proposal is not helpful.\n"
+    "<!--feedback_block_end-->\n"
+)
+
+CHECK_RUN_APPENDIX = (
+    "\nTo view the complete pipeline failure analysis, please lookup the [Fault Analyzer Check]({check_run_url})."
+)
+
+# The trailing "hint" paragraph, appended to the end of both the comment and the
+# check-run summary. In Photon this is the configurable ``HINT_MARKDOWN`` property;
+# here it is a constant because it is a single global message, not a per-repo knob
+# (per-repo behaviour lives in ``SummaryConfig``). This is the live production text
+# (github.wdf.sap.corp/DBaaS/Backup-Operator PR 1814), which is the deployed override
+# of Photon's shorter source default. Rendered italicised, as ``*{FOOTER}*``.
+FOOTER = (
+    "The Intelligent Pipeline Service currently supports analyzing issues related to "
+    "**Pipeline configuration**, **Unit Tests** (Go, Python or Type Script), "
+    "**Hadolint** (Dockerfile linting), **CheckMarx**, **SonarQube**, **GHAS/CodeQL**, "
+    "**Protecode** (BDBA), **Docker Build**, **Linting** and **Pullrequest check**. If "
+    "you need assistance with other pipeline checks and stages, or if you have any "
+    "feedback, feature requests, or questions, please feel free to reach out to us at "
+    "[# sap-intelligent-pipelines](https://sap.enterprise.slack.com/archives/C09CC5L87MW) "
+    "or via email to [DL HANA DCE Quality Eng BLG]"
+    "(mailto:DL_695E49E01174E612B0E31D54@global.corp.sap). We're here to help!"
+)
+
+NO_FINDINGS_BODY = "No actionable findings were produced for this pipeline failure.\n"
+
+
+def render_inspection_marker(inspection_id: str) -> str:
+    """Return the header comment plus the inspection marker (one line)."""
+    return HEADER_MARKER + INSPECTION_MARKER.format(inspection_id=inspection_id)
+
+
+def _render_commit_line(request: FinalizeRequest) -> str:
+    """Return the ``*Commit: [sha](url)*`` line and the following commit marker."""
+    commit_url = f"https://{request.host}/{request.repo}/commit/{request.commit_sha}"
+    return (
+        f"*Commit: [{request.commit_sha}]({commit_url})*\n"
+        + COMMIT_MARKER.format(commit_sha=request.commit_sha)
+        + "\n"
+    )
+
+
+def _blockquote(text: str) -> str:
+    """Prefix every line of ``text`` with ``>`` so it renders as a blockquote."""
+    return "\n".join(f">{line}" if line else ">" for line in text.splitlines())
+
+
+def _render_footer() -> str:
+    """Return the italicised trailing hint paragraph, led by two blank lines."""
+    return f"\n\n*{FOOTER}*\n"
+
+
+def render_proposal(proposal: Proposal, include_feedback: bool) -> str:
+    """Render one proposal as a ``## <category>`` finding block.
+
+    The diff is rendered verbatim as an illustrative example — a human or LLM
+    reading the comment adapts it, so minor structural imperfections do not
+    matter. An empty/whitespace diff is omitted rather than emitting a blank
+    ```diff block.
+
+    The feedback block (the rating checkboxes keyed to ``fault_handler_ids``) is
+    appended only when ``include_feedback`` is ``True``. The PR comment sets it so
+    developers can click a rating; the check-run summary clears it because a check
+    run's markdown is not interactive.
+    """
+    body = f"## {proposal.category}\n"
+    body += f"**Critical message:** {proposal.critical_message}\n"
+    body += "<details>\n<summary><i>Details</i></summary>\n\n"
+    body += _blockquote("*Fault description:*") + "\n"
+    body += _blockquote(proposal.fault_description) + "\n"
+    body += ">\n\n"
+    body += _blockquote("*Fix proposal:*") + "\n"
+    body += _blockquote(proposal.fix_proposal) + "\n\n"
+    body += "</details>\n\n"
+    if proposal.diff and proposal.diff.strip():
+        body += f"```diff\n{proposal.diff}\n```\n\n"
+    if include_feedback:
+        body += FEEDBACK_BLOCK.format(fault_handler_ids=",".join(proposal.fault_handler_ids))
+    return body
+
+
+def render_comment(
+    request: FinalizeRequest,
+    max_suggestions: int,
+    check_run_url: str,
+    include_feedback: bool = True,
+    character_limit: int = GITHUB_CHARACTER_LIMIT,
+) -> str:
+    """Render the full FL summary comment body.
+
+    Proposals are capped at ``max_suggestions``.  The comment stops growing
+    before it reaches ``character_limit``.  The body always ends with an appendix:
+    the check-run link when — and only when — proposals were dropped (truncated by
+    the cap or the budget) and ``check_run_url`` is non-empty, otherwise the
+    trailing footer. This mirrors Photon's ``get_comment_appendix``: the link
+    points at the check run that carries the dropped items; when nothing was
+    dropped there is nothing extra to link to, so the footer closes the comment.
+
+    Args:
+        request: The agent-supplied finalize request.
+        max_suggestions: Maximum number of proposals to present.
+        check_run_url: URL of the FL check run, linked in the appendix when
+            proposals were dropped. Empty for the check-run summary, which
+            carries the full analysis itself.
+        include_feedback: Append the per-proposal feedback block. ``True`` for the
+            PR comment; ``False`` for the check-run summary (non-interactive).
+        character_limit: GitHub comment character budget.
+
+    Returns:
+        The complete comment markdown, led by the header and inspection marker.
+    """
+    header = render_inspection_marker(request.inspection_id) + "\n"
+    header += f"{TITLE}\n"
+    header += _render_commit_line(request)
+
+    if not has_findings(request):
+        return header + NO_FINDINGS_BODY + _render_footer()
+
+    header += f"{INTRO}\n"
+
+    footer = _render_footer()
+    rendered = [render_proposal(p, include_feedback) for p in request.proposals]
+    capped = rendered[:max_suggestions]
+
+    # The link closes the comment only when items are dropped and there is a run
+    # to link to; otherwise the footer does. Reserve budget for the larger of the
+    # two so the stop check never lets the comment overshoot after the appendix.
+    link = CHECK_RUN_APPENDIX.format(check_run_url=check_run_url) if check_run_url else ""
+    appendix_reserve = max(link, footer, key=len) if check_run_url else footer
+
+    comment = header
+    shown = 0
+    for item in capped:
+        # Stop before exceeding the budget; the appendix already covers the rest.
+        if len(comment) + len(item) + len(appendix_reserve) >= character_limit:
+            break
+        comment += item
+        shown += 1
+
+    dropped = shown < len(rendered)
+    comment += link if (dropped and check_run_url) else footer
+    return comment
+
+
+def render_check_run_summary(request: FinalizeRequest) -> str:
+    """Render the check-run ``output.summary`` markdown.
+
+    The check run carries the full analysis — no cap on presented items and no
+    external link needed — still within GitHub's character budget. It omits the
+    per-proposal feedback block because a check run's markdown is not interactive,
+    and closes with the same trailing footer as the comment.
+    """
+    return render_comment(
+        request,
+        max_suggestions=len(request.proposals),
+        check_run_url="",
+        include_feedback=False,
+    )
+
+
+def has_findings(request: FinalizeRequest) -> bool:
+    """Return whether the request carries anything worth posting."""
+    return bool(request.proposals)
diff --git a/fl_mcp_servers/github_finalizer/env_vars.py b/fl_mcp_servers/github_finalizer/env_vars.py
new file mode 100644
index 00000000..fb5592bd
--- /dev/null
+++ b/fl_mcp_servers/github_finalizer/env_vars.py
@@ -0,0 +1,39 @@
+"""Names of environment variables consumed by the GitHub finalizer MCP server.
+
+Centralising the names keeps documentation, Pydantic Settings loading, and
+runtime ``os.environ`` lookups in sync — and prevents typos in error messages
+from masking real misconfiguration.
+
+The ``MCP_`` prefix reflects that these variables are populated by the agent
+runtime (Cline / Claude Code) when it launches an MCP server subprocess.
+
+Two Apps exist per host — a prod App (``MCP_GITHUB_APP_*``) and a test App
+(``MCP_TEST_GITHUB_APP_*``). The MCP selects between them at runtime by reading
+the creator of the target check run.
+"""
+
+from __future__ import annotations
+
+from typing import Final
+
+# GitHub App credentials — consumed by
+# fl_mcp_servers.github_finalizer.settings.GithubFinalizerSettings. Each GitHub
+# Enterprise host has its own App, and FL runs two Apps per host: a prod App and
+# a test App. The MCP is not told which one created a given check run, so it
+# discovers the creator from the check run and authenticates with the matching
+# App (see settings.AppVariant and server._discover_target). These are the only
+# env vars this MCP reads; behaviour knobs arrive per-request in
+# FinalizeRequest.config (see models.py).
+ENV_GITHUB_APP_ID_TOOLS: Final[str] = "MCP_GITHUB_APP_ID_TOOLS"
+ENV_GITHUB_APP_KEY_TOOLS: Final[str] = "MCP_GITHUB_APP_KEY_TOOLS"
+ENV_GITHUB_APP_ID_WDF: Final[str] = "MCP_GITHUB_APP_ID_WDF"
+ENV_GITHUB_APP_KEY_WDF: Final[str] = "MCP_GITHUB_APP_KEY_WDF"
+
+# Test-App credentials, one pair per host. Same shape as the prod vars above; the
+# TEST_ segment leads the name so the two Apps are visually grouped by
+# environment. Consumed via explicit validation aliases (not env_prefix), because
+# the prod fields already claim the MCP_GITHUB_APP_* namespace.
+ENV_TEST_GITHUB_APP_ID_TOOLS: Final[str] = "MCP_TEST_GITHUB_APP_ID_TOOLS"
+ENV_TEST_GITHUB_APP_KEY_TOOLS: Final[str] = "MCP_TEST_GITHUB_APP_KEY_TOOLS"
+ENV_TEST_GITHUB_APP_ID_WDF: Final[str] = "MCP_TEST_GITHUB_APP_ID_WDF"
+ENV_TEST_GITHUB_APP_KEY_WDF: Final[str] = "MCP_TEST_GITHUB_APP_KEY_WDF"
diff --git a/fl_mcp_servers/github_finalizer/models.py b/fl_mcp_servers/github_finalizer/models.py
new file mode 100644
index 00000000..f986613c
--- /dev/null
+++ b/fl_mcp_servers/github_finalizer/models.py
@@ -0,0 +1,166 @@
+"""Typed request/response models for the ``finalize_in_github`` MCP tool.
+
+The FL summary agent has already done the intelligent work — merged the fault
+handlers' proposals, resolved competing fixes into a single recommendation,
+budgeted content — before it calls this MCP.  These models are the contract for
+that hand-over: the agent supplies **data only, never formatting**.  Everything
+the MCP renders (markdown, markers, feedback blocks, length budgeting) is derived
+deterministically from these objects, so the agent cannot get the
+single-correct-answer formatting wrong.
+
+The models mirror the shapes the deleted ``db.Inspection`` / ``db.FixProposal``
+carried, but hold no database identity — the agent is stateless and the comment
+markers are the system of record.
+"""
+
+from __future__ import annotations
+
+from typing import Literal
+
+from pydantic import BaseModel, Field
+
+# The conclusion written onto the FL check run. Derived by the finalizer MCP from
+# whether the analysis produced findings (``success`` vs ``failure``) — never
+# agent-supplied. ``neutral`` is retained in the type for completeness but is not
+# currently emitted.
+Conclusion = Literal["success", "neutral", "failure"]
+
+
+class Proposal(BaseModel):
+    """A fix suggestion or advisory finding for one region of code.
+
+    Every finding is a proposal, so every finding is rated: the rendered block
+    always carries a feedback block keyed to ``fault_handler_ids``. A cluster of
+    one passes through unchanged; a merged cluster carries the combined
+    ``fault_description`` / ``fix_proposal`` and the union of its
+    ``fault_handler_ids``. When competing fixes touch the same region, the agent
+    resolves them into one proposal (choosing the safest) and notes the discarded
+    alternative in ``fix_proposal`` prose — the finalizer never surfaces a choice.
+
+    ``diff`` is optional: a proposal with a concrete patch carries one; a purely
+    advisory finding (e.g. "coverage is below threshold, add tests"; a gate that
+    failed downstream) omits it and renders as a diff-less proposal that is still
+    attributed and still rated.
+
+    Rendered as one ``## <category>`` finding block in the summary comment:
+    the ``critical_message`` on the ``**Critical message:**`` line, the
+    ``fault_description`` and ``fix_proposal`` inside a collapsible ``<details>``
+    block, the ``diff`` in a fenced ```diff block when present, and
+    ``fault_handler_ids`` in the ``<!--fault_handler_ids_<id>,<id>-->`` feedback
+    marker.
+
+    Attributes:
+        category: The check/stage the finding came from, used as the ``##``
+            heading. Examples: ``"GHAS"``, ``"Helm Unit Tests"``,
+            ``"Unit Tests"``, ``"Docker Build"``.
+        fault_handler_ids: The fault handlers that contributed to this proposal,
+            emitted in the feedback marker so the webhook attributes a rating to
+            them without a database lookup. Required and non-empty. The same
+            handler id may appear on more than one proposal.
+        diff: Optional unified diff, rendered verbatim in a ```diff block as an
+            illustrative example of the fix. ``None`` for advisory findings that
+            propose no concrete patch.
+    """
+
+    category: str = Field(..., description="Check/stage the finding came from; the '## ' heading, e.g. 'GHAS'.")
+    critical_message: str = Field(..., description="One-line finding summary on the '**Critical message:**' line.")
+    fault_description: str = Field(
+        ..., description="What went wrong and the root cause; the 'Fault description' block."
+    )
+    fix_proposal: str = Field(..., description="How to fix it; the 'Fix proposal:' block.")
+    fault_handler_ids: list[str] = Field(
+        ...,
+        min_length=1,
+        description="Ids of the fault handlers that contributed; emitted in the feedback marker.",
+    )
+    diff: str | None = Field(
+        default=None,
+        description="Optional unified diff, rendered verbatim in a ```diff block as an "
+        "illustrative example of the fix. Omitted when empty.",
+    )
+
+    model_config = {"extra": "forbid"}
+
+
+class SummaryConfig(BaseModel):
+    """Per-repository behaviour knobs the agent read from the repo's config.
+
+    The finalizer MCP runs in its own container with no access to the target
+    repository's checkout, so it cannot read the repo's
+    ``.pipeline/photon_config.json`` itself. The agent — which does have the
+    checkout at the failing commit — reads that file and passes the values here.
+    When the repo has no config file, the agent omits these and the defaults
+    apply.
+
+    Attributes:
+        max_suggestions: Cap on proposal items shown in the comment;
+            sourced from the photon config's
+            ``max_amount_of_fix_proposals_displayed_in_comments``. The check-run
+            summary is uncapped regardless.
+        disable_comments: When ``True``, the summary comment is skipped and only
+            the check run is updated.
+    """
+
+    max_suggestions: int = Field(default=2, ge=0, description="Cap on presented proposal items.")
+    disable_comments: bool = Field(default=False, description="Skip the comment; update only the check run.")
+
+    model_config = {"extra": "forbid"}
+
+
+class FinalizeRequest(BaseModel):
+    """Everything ``finalize_in_github`` needs to render and publish the summary.
+
+    ``pr_number`` is ``None`` when there is no PR — the summary is then posted as
+    a commit comment on ``commit_sha`` instead of an issue comment on the PR.
+
+    ``config`` carries the repo's behaviour knobs, which the agent read from the
+    local checkout (see :class:`SummaryConfig`); it defaults to the built-in
+    behaviour when the repo has no config file.
+    """
+
+    inspection_id: str = Field(..., description="FL inspection UUID; emitted in the comment's inspection marker.")
+    commit_sha: str = Field(..., description="Commit the analysis is about; shown in the commit line and marker.")
+
+    host: str = Field(
+        ...,
+        description="GitHub host, e.g. 'github.tools.sap' or 'github.wdf.sap.corp'.",
+    )
+    repo: str = Field(..., description="Repository full name, 'owner/name'.")
+    head_sha: str = Field(..., description="Head commit SHA carrying the FL check run to update.")
+    pr_number: int | None = Field(
+        default=None,
+        description="PR number to comment on; None to comment on the commit instead.",
+    )
+
+    proposals: list[Proposal] = Field(default_factory=list)
+
+    config: SummaryConfig = Field(
+        default_factory=SummaryConfig,
+        description="Repo behaviour knobs the agent read from .pipeline/photon_config.json.",
+    )
+
+    check_run_name: str = Field(
+        default="Fault Analyzer",
+        description="Name of the FL check run to locate on the head commit.",
+    )
+
+    model_config = {"extra": "forbid"}
+
+
+class FinalizeResult(BaseModel):
+    """Outcome of a ``finalize_in_github`` run.
+
+    ``comment_url`` / ``comment_id`` are ``None`` when the comment was skipped
+    (repository opted out via ``disable_comments``) or when there was nothing to
+    post; the check run is updated regardless.
+
+    ``conclusion`` is the value the MCP wrote onto the check run, derived from
+    whether the analysis produced findings: ``success`` with findings,
+    ``failure`` without.
+    """
+
+    comment_url: str | None = None
+    comment_id: int | None = None
+    check_run_id: int
+    conclusion: Conclusion
+    comment_skipped: bool = False
diff --git a/fl_mcp_servers/github_finalizer/server.py b/fl_mcp_servers/github_finalizer/server.py
new file mode 100644
index 00000000..b14685d9
--- /dev/null
+++ b/fl_mcp_servers/github_finalizer/server.py
@@ -0,0 +1,274 @@
+"""FL Summary GitHub Finalizer MCP — stdio MCP server for the FL finalizer agent.
+
+Launched as a stdio subprocess by the agent runtime.  Exposes a **single** tool,
+``finalize_in_github``: once the agent has produced its final merged content, it
+calls this tool once and the server performs the whole deterministic tail of the
+workflow — authenticate as the GitHub App, read repository config, render the
+comment and check-run output with the correct markers and feedback blocks, find
+and replace any previous summary comment, and update the FL check run.
+
+Keeping this deterministic work inside the MCP (rather than exposing formatting
+and posting primitives to the agent) means the agent cannot get the
+single-correct-answer steps wrong — wrong markers, a duplicated comment on
+rerun, a blown length budget — and it does not spend tokens on them.
+
+Receives GitHub App credentials via ``MCP_``-prefixed environment variables; see
+:mod:`fl_mcp_servers.github_finalizer.settings`:
+    MCP_GITHUB_APP_ID_TOOLS / MCP_GITHUB_APP_KEY_TOOLS  — github.tools.sap App
+    MCP_GITHUB_APP_ID_WDF   / MCP_GITHUB_APP_KEY_WDF    — github.wdf.sap.corp App
+
+Behaviour knobs are not env-configurable. The comment character budget is a
+constant in :mod:`fl_mcp_servers.github_finalizer.comment_format`. The suggestion
+cap and comment opt-out are supplied per-request in ``FinalizeRequest.config``:
+this MCP runs in its own container with no access to the target repo's checkout,
+so the agent reads the repo's ``.pipeline/photon_config.json`` and passes the
+values in the tool call.
+
+Run with:
+    python -m fl_mcp_servers.github_finalizer.server
+"""
+
+# pylint: disable=duplicate-code
+from __future__ import annotations
+
+from collections.abc import AsyncGenerator
+from contextlib import asynccontextmanager
+from dataclasses import dataclass
+
+import structlog
+from github.CheckRun import CheckRun
+from github.Commit import Commit
+from github.CommitComment import CommitComment
+from github.IssueComment import IssueComment
+from github.PullRequest import PullRequest
+from mcp.server.fastmcp import Context, FastMCP
+from mcp.server.fastmcp.exceptions import ToolError
+
+from fl_mcp_servers.github_finalizer import comment_format
+from fl_mcp_servers.github_finalizer.app_client import GithubApp, GithubAppRegistry
+from fl_mcp_servers.github_finalizer.models import Conclusion, FinalizeRequest, FinalizeResult
+from fl_mcp_servers.github_finalizer.settings import (
+    AppVariant,
+    GithubFinalizerSettings,
+    GitHubHost,
+    resolve_host,
+)
+
+log = structlog.get_logger(__name__)
+
+
+@dataclass
+class _ServerState:
+    settings: GithubFinalizerSettings
+    registry: GithubAppRegistry
+
+
+@asynccontextmanager
+async def _lifespan(_server: FastMCP) -> AsyncGenerator[_ServerState, None]:
+    """Build settings and the App registry once and reuse them across tool calls."""
+    settings = GithubFinalizerSettings()
+    log.info("FL Summary GitHub Finalizer MCP started")
+    yield _ServerState(settings=settings, registry=GithubAppRegistry(settings))
+
+
+mcp: FastMCP[_ServerState] = FastMCP("FL Summary GitHub Finalizer MCP", lifespan=_lifespan)
+
+
+@mcp.tool()
+async def finalize_in_github(request: FinalizeRequest, ctx: Context) -> FinalizeResult:
+    """Publish the FL summary: post/refresh the comment and update the check run.
+
+    Runs the full deterministic pipeline for a single inspection.  The agent calls
+    this once with its final merged content; the server renders and publishes it.
+
+    Behaviour:
+    - Honours the agent-supplied ``request.config``: if the repo opted out via
+      ``disable_comments``, the comment is skipped but the check run is still
+      updated.
+    - Finds any previous summary comment (by the inspection marker) and
+      edits it in place, so a rerun produces one comment, not duplicates.
+    - Locates the FL check run on ``head_sha`` by name and writes the summary and
+      conclusion into it. The conclusion is derived here, not agent-supplied:
+      ``success`` when the analysis produced findings, ``failure`` when it did not.
+
+    Comment posting and check-run update are independent failure domains: on a
+    partial failure the tool raises so FL can retry, and both operations are
+    idempotent so the retry converges.
+
+    Args:
+        request: The agent-supplied finalize request.
+        ctx: The MCP request context carrying the lifespan state.
+
+    Returns:
+        The URLs/ids of the published comment and check run.
+
+    Raises:
+        ToolError: On any unrecoverable GitHub failure, after recording which
+            side effects (if any) already succeeded.
+    """
+    state: _ServerState = ctx.request_context.lifespan_context
+    host = resolve_host(request.host)
+    configured_variants = [v for v in AppVariant if state.settings.has_credentials(host, v)]
+    if not configured_variants:
+        raise ToolError(f"No GitHub App credentials configured for host {request.host!r}.")
+
+    check_run_id, owning_variant = _discover_target(state, host, request, configured_variants)
+    check_run_url = f"{host.value}/{request.repo}/runs/{check_run_id}"
+
+    app = state.registry.get(host, request.repo, owning_variant)
+
+    conclusion: Conclusion = "success" if comment_format.has_findings(request) else "failure"
+
+    comment_url, comment_id, comment_skipped = _publish_comment(app, request, check_run_url)
+    _update_check_run(app, check_run_id, request, conclusion)
+
+    return FinalizeResult(
+        comment_url=comment_url,
+        comment_id=comment_id,
+        check_run_id=check_run_id,
+        conclusion=conclusion,
+        comment_skipped=comment_skipped,
+    )
+
+
+def _discover_target(
+    state: _ServerState,
+    host: GitHubHost,
+    request: FinalizeRequest,
+    configured_variants: list[AppVariant],
+) -> tuple[int, AppVariant]:
+    """Find the FL check run and the variant of the App that created it.
+
+    A check run can only be updated by the App that created it, and multiple Apps
+    can create check runs of the same name on one commit. So the target run is the
+    first one that both matches ``check_run_name`` and was created by an App this
+    MCP holds credentials for; its creator's variant is what the caller must
+    authenticate as to perform the update.
+
+    The listing itself needs an installation token, but reading each run's creator
+    works from any installed App — so the read is attempted with the prod App
+    first and falls back to the test App if prod is not installed on the repo.
+
+    Args:
+        state: The server state carrying settings and the App registry.
+        host: The resolved GitHub host.
+        request: The finalize request (``head_sha``, ``check_run_name``, ``repo``).
+        configured_variants: Variants with complete credentials for ``host``,
+            in ``AppVariant`` order (prod before test).
+
+    Returns:
+        The target check run id and the variant whose App created it.
+
+    Raises:
+        ToolError: If the check runs cannot be listed with any configured App, or
+            no run named ``check_run_name`` was created by one of our Apps.
+    """
+    check_runs = _list_check_runs(state, host, request, configured_variants)
+
+    app_id_to_variant = {
+        state.settings.get_configured_app_id(host, variant): variant for variant in configured_variants
+    }
+    for check_run in check_runs:
+        if check_run.name != request.check_run_name:
+            continue
+        variant = app_id_to_variant.get(str(check_run.app.id))
+        if variant is not None:
+            return check_run.id, variant
+    raise ToolError(f"No check run named {request.check_run_name!r} found on {request.head_sha}.")
+
+
+def _list_check_runs(
+    state: _ServerState,
+    host: GitHubHost,
+    request: FinalizeRequest,
+    configured_variants: list[AppVariant],
+) -> list[CheckRun]:
+    """List check runs on the head commit, trying each configured App in turn.
+
+    An App that is not installed on the repo cannot list its check runs, so the
+    read is retried with the next configured variant. Only the last failure is
+    surfaced if every configured App fails.
+
+    Raises:
+        ToolError: If no configured App can list the head commit's check runs.
+    """
+    last_error: Exception | None = None
+    for variant in configured_variants:
+        try:
+            return state.registry.get(host, request.repo, variant).get_check_runs(request.head_sha)
+        # Any App may be uninstalled or error; try the next variant, surface the last failure below.
+        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
+            last_error = exc
+    raise ToolError(f"Could not list check runs on {request.head_sha}: {last_error}") from last_error
+
+
+def _publish_comment(
+    app: GithubApp,
+    request: FinalizeRequest,
+    check_run_url: str,
+) -> tuple[str | None, int | None, bool]:
+    """Render and post/refresh the summary comment; return ``(url, id, skipped)``."""
+    if request.config.disable_comments:
+        log.info("Comments disabled for this repository; skipping comment, updating check run only.")
+        return None, None, True
+
+    body = comment_format.render_comment(
+        request,
+        max_suggestions=request.config.max_suggestions,
+        check_run_url=check_run_url,
+    )
+
+    try:
+        origin: Commit | PullRequest = (
+            app.get_pull_request(request.pr_number)
+            if request.pr_number is not None
+            else app.get_commit(request.commit_sha)
+        )
+        existing = _find_previous_summary_comment(app, origin)
+        if existing is not None:
+            app.delete_comment(existing)
+        created = app.create_comment(origin, body)
+        return created.html_url, created.id, False
+    except Exception as exc:  # noqa: BLE001 - surfaced cleanly to the agent
+        raise ToolError(f"Failed to post the summary comment: {exc}") from exc
+
+
+def _find_previous_summary_comment(app: GithubApp, origin: Commit | PullRequest) -> CommitComment | IssueComment | None:
+    """Return the prior comment carrying the ``fl_summary`` outer marker, if any."""
+    for comment in app.get_comments(origin):
+        if comment_format.OUTER_MARKER_RE.search(comment.body or ""):
+            return comment
+    return None
+
+
+def _update_check_run(
+    app: GithubApp,
+    check_run_id: int,
+    request: FinalizeRequest,
+    conclusion: Conclusion,
+) -> None:
+    """Write the FL summary and conclusion into the existing check run."""
+    summary = comment_format.render_check_run_summary(request)
+    try:
+        app.update_check_run(
+            check_run_id,
+            status="completed",
+            conclusion=conclusion,
+            output={"title": request.check_run_name, "summary": summary},
+        )
+    except Exception as exc:  # noqa: BLE001 - surfaced cleanly to the agent
+        raise ToolError(f"Failed to update check run {check_run_id}: {exc}") from exc
+
+
+def _ensure_settings() -> None:
+    GithubFinalizerSettings()
+
+
+if __name__ == "__main__":  # pylint: disable=duplicate-code
+    import sys
+
+    from fl_control_plane.log_config import configure_logging
+
+    configure_logging("INFO", stream=sys.stderr)
+    _ensure_settings()
+    mcp.run(transport="stdio")
diff --git a/fl_mcp_servers/github_finalizer/settings.py b/fl_mcp_servers/github_finalizer/settings.py
new file mode 100644
index 00000000..4972e3e3
--- /dev/null
+++ b/fl_mcp_servers/github_finalizer/settings.py
@@ -0,0 +1,177 @@
+"""GitHub finalizer MCP configuration loaded from ``MCP_``-prefixed env variables.
+
+Separate from the shared HDLF :class:`fl_mcp_servers.generic.settings.McpSettings`: the
+GitHub summary finalizer authenticates as a GitHub App and needs entirely
+different environment variables (``MCP_GITHUB_APP_*``) than the HDLF-backed
+servers.  The agent runtime (Cline / Claude Code) injects these as plain
+environment variables into the MCP server subprocess it spawns.
+
+Secrets are owned by the FL platform; this module contains no Vault SDK and no
+fallback secret source.  If a required value is missing the server fails at
+start-up with a clear error.
+"""
+
+from __future__ import annotations
+
+from enum import StrEnum, unique
+
+from pydantic import Field, SecretStr, model_validator
+from pydantic_settings import BaseSettings
+
+from fl_mcp_servers.github_finalizer.env_vars import (
+    ENV_GITHUB_APP_ID_TOOLS,
+    ENV_GITHUB_APP_KEY_TOOLS,
+    ENV_TEST_GITHUB_APP_ID_TOOLS,
+    ENV_TEST_GITHUB_APP_ID_WDF,
+    ENV_TEST_GITHUB_APP_KEY_TOOLS,
+    ENV_TEST_GITHUB_APP_KEY_WDF,
+)
+
+
+@unique
+class GitHubHost(StrEnum):
+    """The two GitHub Enterprise hosts FL serves."""
+
+    WDF = "https://github.wdf.sap.corp"
+    TOOLS = "https://github.tools.sap"
+
+
+@unique
+class AppVariant(StrEnum):
+    """Which of the two Apps configured per host to authenticate as.
+
+    FL runs a ``PROD`` App and a ``TEST`` App on each host. The MCP is not told
+    which one created a given check run, so it reads ``check_run.app.id`` and
+    picks the variant whose configured App id matches (see
+    ``server._discover_target``). ``PROD`` is the default everywhere a variant is
+    optional, preserving pre-test-App behaviour.
+    """
+
+    PROD = "prod"
+    TEST = "test"
+
+
+def resolve_host(host: str) -> GitHubHost:
+    """Resolve a free-form host string to a :class:`GitHubHost`.
+
+    Accepts an enum value (``https://github.tools.sap``), a bare hostname
+    (``github.tools.sap``), or anything containing the WDF marker.
+
+    Args:
+        host: The host string supplied by the agent in a tool call.
+
+    Returns:
+        ``WDF`` if the WDF marker is present, otherwise ``TOOLS``.
+    """
+    if "github.wdf.sap.corp" in host:
+        return GitHubHost.WDF
+    return GitHubHost.TOOLS
+
+
+class GithubFinalizerSettings(BaseSettings):
+    """GitHub-App credentials for the finalizer MCP.
+
+    Reads ``MCP_``-prefixed environment variables.  The two GitHub Enterprise
+    hosts each run two GitHub Apps — a prod App and a test App — so credentials
+    are held per ``(host, variant)``.  The prod pairs use the plain
+    ``MCP_GITHUB_APP_*`` names via ``env_prefix``; the test pairs use explicit
+    ``MCP_TEST_GITHUB_APP_*`` validation aliases, because the prod fields already
+    own the ``MCP_GITHUB_APP_*`` namespace and ``env_prefix`` alone would map the
+    test fields to ``MCP_GITHUB_APP_ID_TEST_TOOLS`` instead.
+
+    Behaviour knobs are not settings: the comment character budget is a constant
+    in :mod:`fl_mcp_servers.github_finalizer.comment_format`, and the suggestion
+    cap and comment opt-out arrive per-request in ``FinalizeRequest.config`` (the
+    agent reads the repo's ``.pipeline/photon_config.json`` and passes them).
+
+    The App private keys hold secret material, so they are typed as
+    :class:`~pydantic.SecretStr` to keep the raw PEM out of ``repr()``,
+    ``model_dump()`` and tracebacks.
+    """
+
+    github_app_id_tools: str | None = None
+    github_app_key_tools: SecretStr | None = None
+    github_app_id_wdf: str | None = None
+    github_app_key_wdf: SecretStr | None = None
+
+    github_app_id_test_tools: str | None = Field(
+        default=None, validation_alias=ENV_TEST_GITHUB_APP_ID_TOOLS
+    )
+    github_app_key_test_tools: SecretStr | None = Field(
+        default=None, validation_alias=ENV_TEST_GITHUB_APP_KEY_TOOLS
+    )
+    github_app_id_test_wdf: str | None = Field(
+        default=None, validation_alias=ENV_TEST_GITHUB_APP_ID_WDF
+    )
+    github_app_key_test_wdf: SecretStr | None = Field(
+        default=None, validation_alias=ENV_TEST_GITHUB_APP_KEY_WDF
+    )
+
+    model_config = {"env_prefix": "MCP_", "env_file": ".env", "extra": "ignore", "populate_by_name": True}
+
+    @model_validator(mode="after")
+    def _require_at_least_one_app(self) -> GithubFinalizerSettings:
+        """Fail fast unless at least one ``(host, variant)`` App is complete.
+
+        A ``(host, variant)`` is usable only when both its App id and App key are
+        present.  The server refuses to start if none of the four possible Apps
+        (prod/test × tools/wdf) is fully configured, since it could then
+        authenticate nowhere.
+
+        Raises:
+            ValueError: When no ``(host, variant)`` has both App id and App key set.
+        """
+        configured = any(
+            self.has_credentials(host, variant)
+            for host in GitHubHost
+            for variant in AppVariant
+        )
+        if not configured:
+            raise ValueError(
+                f"No GitHub App credentials configured. Set {ENV_GITHUB_APP_ID_TOOLS} "
+                f"+ {ENV_GITHUB_APP_KEY_TOOLS} and/or the _WDF pair (or the "
+                f"{ENV_TEST_GITHUB_APP_ID_TOOLS} test-App pairs)."
+            )
+        return self
+
+    def has_credentials(self, host: GitHubHost, variant: AppVariant = AppVariant.PROD) -> bool:
+        """Return whether both App id and key are set for ``(host, variant)``."""
+        app_id, app_key = self._credential_pair(host, variant)
+        return bool(app_id) and app_key is not None
+
+    def get_configured_app_id(self, host: GitHubHost, variant: AppVariant) -> str | None:
+        """Return the configured App id for ``(host, variant)``, or ``None``.
+
+        Used by check-run creator discovery to match ``check_run.app.id`` against
+        the Apps this MCP holds credentials for, without touching the secret key.
+        """
+        app_id, _ = self._credential_pair(host, variant)
+        return app_id
+
+    def get_app_credentials(self, host: GitHubHost, variant: AppVariant = AppVariant.PROD) -> tuple[str, str]:
+        """Return the ``(app_id, app_key)`` pair for ``(host, variant)``.
+
+        Args:
+            host: The GitHub host to look up credentials for.
+            variant: Which App (prod or test) to look up. Defaults to prod.
+
+        Returns:
+            The App id and the decoded App private key.
+
+        Raises:
+            ValueError: If credentials for ``(host, variant)`` are not fully configured.
+        """
+        app_id, app_key = self._credential_pair(host, variant)
+        if not app_id or app_key is None:
+            raise ValueError(f"No GitHub App credentials configured for host {host.value} ({variant.value}).")
+        # pylint infers FieldInfo (not SecretStr) for Field()-declared fields; app_key is a SecretStr here.
+        return app_id, app_key.get_secret_value()  # pylint: disable=no-member
+
+    def _credential_pair(self, host: GitHubHost, variant: AppVariant) -> tuple[str | None, SecretStr | None]:
+        if variant is AppVariant.TEST:
+            if host is GitHubHost.WDF:
+                return self.github_app_id_test_wdf, self.github_app_key_test_wdf
+            return self.github_app_id_test_tools, self.github_app_key_test_tools
+        if host is GitHubHost.WDF:
+            return self.github_app_id_wdf, self.github_app_key_wdf
+        return self.github_app_id_tools, self.github_app_key_tools
diff --git a/fl_mcp_servers/pyproject.toml b/fl_mcp_servers/pyproject.toml
index f064f7d6..a5294a1b 100644
--- a/fl_mcp_servers/pyproject.toml
+++ b/fl_mcp_servers/pyproject.toml
@@ -13,6 +13,7 @@ dependencies = [
     "fastmcp>=2.14.7",
     "pydantic>=2.13.4,<3",
     "pydantic-settings>=2.14.1",
+    "PyGithub>=2.5.0",
     "structlog>=25.0.0",
     "tenacity>=9.1.4",
 ]
diff --git a/fl_mcp_servers/uv.lock b/fl_mcp_servers/uv.lock
index 2ab36957..298c8b54 100644
--- a/fl_mcp_servers/uv.lock
+++ b/fl_mcp_servers/uv.lock
@@ -220,6 +220,68 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/d5/dd/0c7dbf815a579ff005008a2d815a55d6bb047c349eef536d9dc53d3f0a8d/cffi-2.1.0-cp314-cp314t-win_arm64.whl", hash = "sha256:510aeeeac94811b138077451da1fb18b308a5feab47dd2b603af55804155e1c8", size = 186404, upload-time = "2026-07-06T21:33:50.309Z" },
 ]
 
+[[package]]
+name = "charset-normalizer"
+version = "3.5.1"
+source = { registry = "https://pypi.org/simple" }
+sdist = { url = "https://files.pythonhosted.org/packages/e5/3f/143b048436775b0f76ac3eec145c019e8173ccc2885c8f20319b996d5e83/charset_normalizer-3.5.1.tar.gz", hash = "sha256:6117b84ea48435e5356dc737f5121485c30920ba43375fa7b434fd753df0eac3", size = 171764, upload-time = "2026-08-15T08:20:44.807Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/29/cd/2b812ce5e888f1ce69a5350281e58aab07ae64a958ecae8912f30865718e/charset_normalizer-3.5.1-cp314-cp314-android_24_arm64_v8a.whl", hash = "sha256:774d157f112367ff4abd29019f38f023c24e00e56edc7829c20e358a5a913ad8", size = 212318, upload-time = "2026-08-15T08:18:04.403Z" },
+    { url = "https://files.pythonhosted.org/packages/9e/4a/a6ee107430768a5334e6d63f31f148a04a1a491ef161a1ac9415a73f2fa8/charset_normalizer-3.5.1-cp314-cp314-android_24_x86_64.whl", hash = "sha256:26422d45fd13551cf564c58932f7d72b4f58b93b0fcf18c35ba6be12b46bb102", size = 224897, upload-time = "2026-08-15T08:18:05.997Z" },
+    { url = "https://files.pythonhosted.org/packages/c3/d9/35ae3f64f29d0179c35c3baefe575904df2913dde519129c7f75995a2b1d/charset_normalizer-3.5.1-cp314-cp314-ios_13_0_arm64_iphoneos.whl", hash = "sha256:09a7bba9f739468c8e78c36a75c33768e53cb1959fc638f510454c14683f00d5", size = 194848, upload-time = "2026-08-15T08:18:07.397Z" },
+    { url = "https://files.pythonhosted.org/packages/74/76/f2fc7380f056cc273a53af37f50d08ad54b2c59f61078f31432edcf1c2bd/charset_normalizer-3.5.1-cp314-cp314-ios_13_0_arm64_iphonesimulator.whl", hash = "sha256:4c9548dc78002099910abaebc0a72ac58b7d30931869e0351c09b507dff4ece3", size = 198163, upload-time = "2026-08-15T08:18:08.989Z" },
+    { url = "https://files.pythonhosted.org/packages/e9/40/095ce62fa078483cccc1fa2b36e6bc9580b85422a20ee9f925341c50e44f/charset_normalizer-3.5.1-cp314-cp314-macosx_10_15_universal2.whl", hash = "sha256:c428c6c31eb5f4277d7f8eccaf767fbd548ddd5ce3c8b4f4cbbfab3d96b5904c", size = 341823, upload-time = "2026-08-15T08:18:10.458Z" },
+    { url = "https://files.pythonhosted.org/packages/f1/5a/0e58b1c04a1596e0256f407274a92d5fb2ee21324409d1fab1da48a65b5b/charset_normalizer-3.5.1-cp314-cp314-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:2f06b7eae9dbe77fe1d644ca244dad508de8d302870a43f3c559b521270938a0", size = 242458, upload-time = "2026-08-15T08:18:11.989Z" },
+    { url = "https://files.pythonhosted.org/packages/22/95/b4618ce912e6db0b1aae89ba788e38e8a7eba0f3025cc66e8c0699f977b2/charset_normalizer-3.5.1-cp314-cp314-manylinux2014_armv7l.manylinux_2_17_armv7l.manylinux_2_31_armv7l.whl", hash = "sha256:6b7430cf5728e68f6c462254009a6ef4086e1bea43cf2f57aa9c55fb4f50ff96", size = 226717, upload-time = "2026-08-15T08:18:13.401Z" },
+    { url = "https://files.pythonhosted.org/packages/8a/76/c681192bbda3d55356db5dadd64381d5202b37c6b598fcda5282e88b5d3d/charset_normalizer-3.5.1-cp314-cp314-manylinux2014_ppc64le.manylinux_2_17_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:ab743e9bc90c1f73552ec33e10e3331315acd2c397b36065b591b0181de533cc", size = 266111, upload-time = "2026-08-15T08:18:14.961Z" },
+    { url = "https://files.pythonhosted.org/packages/88/be/55127bfca72c0cff6c022488d140d7c5b04c771e3b72e9bdb4836d54979d/charset_normalizer-3.5.1-cp314-cp314-manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl", hash = "sha256:f6f7deae3feb4edfa2efaf7c574fe88cbf055038a6abdb40188e4fff66d5699f", size = 263128, upload-time = "2026-08-15T08:18:16.515Z" },
+    { url = "https://files.pythonhosted.org/packages/e0/91/39c3af510b0aa32bbda03374259200f28430febfd1bf5e511fe765282ce5/charset_normalizer-3.5.1-cp314-cp314-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:15f024313246a4ed976c60f440bb8d257815513a681d212ff74fd46f7d715a90", size = 251240, upload-time = "2026-08-15T08:18:18.127Z" },
+    { url = "https://files.pythonhosted.org/packages/1c/a5/cbe418bbc6ecdfc3e05a0116002897c4b403a5e838d697e64c78e9f0190d/charset_normalizer-3.5.1-cp314-cp314-manylinux_2_31_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:823f82903d189af463d7df250ef1f7f696f3cee08cc8d91deb565e8d425f6506", size = 245282, upload-time = "2026-08-15T08:18:19.625Z" },
+    { url = "https://files.pythonhosted.org/packages/cc/a4/689bb42e8e7cd492f3cb64907c6bc00ad247ec9a3628cd3f8eed126e8ae1/charset_normalizer-3.5.1-cp314-cp314-musllinux_1_2_aarch64.whl", hash = "sha256:01e93745f7f219b703b60ba7afead36cfc4242782be5af484673fc500df12da5", size = 244597, upload-time = "2026-08-15T08:18:21.121Z" },
+    { url = "https://files.pythonhosted.org/packages/c1/ce/9962938e179cf9f699d3f1e7b3114b5d7642dee6a893745229f9dd04f274/charset_normalizer-3.5.1-cp314-cp314-musllinux_1_2_armv7l.whl", hash = "sha256:329fc3ccb63ad22d867d84c2adea759a64079a37ba4a343433b02c7a2816871e", size = 231376, upload-time = "2026-08-15T08:18:22.57Z" },
+    { url = "https://files.pythonhosted.org/packages/85/54/46000450ada53bd9eac5429a2c8c54cd2d9b39c0c255f229aea9af0948a5/charset_normalizer-3.5.1-cp314-cp314-musllinux_1_2_ppc64le.whl", hash = "sha256:bb57753e36e4855b8ca375069482250a6246372331a3e4f3407eaebb007443f5", size = 266715, upload-time = "2026-08-15T08:18:24.235Z" },
+    { url = "https://files.pythonhosted.org/packages/3d/bb/618749d70f792b44252a777bf89bfb86823b9bbc1ea13fe8ce759b07f38a/charset_normalizer-3.5.1-cp314-cp314-musllinux_1_2_riscv64.whl", hash = "sha256:fce8cbd4997efeb450bd298b54f755dcdff18d496f7a5ddbb4867c6d7c88fdc3", size = 245848, upload-time = "2026-08-15T08:18:25.726Z" },
+    { url = "https://files.pythonhosted.org/packages/7e/3f/ffb64458527c7668031d5eb095d978de561958dc9f5b53f8e488a533e603/charset_normalizer-3.5.1-cp314-cp314-musllinux_1_2_s390x.whl", hash = "sha256:6c9cdde8becb25a7fde49924511aa2644d6f8081cc8df8e9452724303348d8e3", size = 264521, upload-time = "2026-08-15T08:18:27.193Z" },
+    { url = "https://files.pythonhosted.org/packages/4f/ab/74a55fd803916a35ac461daf002708191aac19b546b80dc8cabfedc63d98/charset_normalizer-3.5.1-cp314-cp314-musllinux_1_2_x86_64.whl", hash = "sha256:9ac4444d8d4fd4c4bd08bf451ed3167aa9e7ec6cdb41b648794f1d1103652e36", size = 253054, upload-time = "2026-08-15T08:18:28.568Z" },
+    { url = "https://files.pythonhosted.org/packages/a0/2a/6a9034b7d3c60b17499afb482df5878bf9fa20b50cc3887d5ef017a833db/charset_normalizer-3.5.1-cp314-cp314-pyemscripten_2026_0_wasm32.whl", hash = "sha256:f03ac127268b43ef4fe9e6ab6794a6794b49485a0cc0c1db79876d2f33f75bc7", size = 140580, upload-time = "2026-08-15T08:18:30.214Z" },
+    { url = "https://files.pythonhosted.org/packages/f3/46/1d362e1a00d035d66b9869e1281eee115907f7e390a16a07824ab5737360/charset_normalizer-3.5.1-cp314-cp314-win32.whl", hash = "sha256:1f5883d77fd409a261abb5dc8ccbe335720d798b1de4abb3b1d47ccbbc76b53b", size = 180325, upload-time = "2026-08-15T08:18:31.877Z" },
+    { url = "https://files.pythonhosted.org/packages/7a/7c/4938c329b6a9d446f6a59aa2092ff7118f274209b5ed0e26893d1d30a63c/charset_normalizer-3.5.1-cp314-cp314-win_amd64.whl", hash = "sha256:c658c50ac0c98cd755a2dd50b7977d3bca7df401dcc47fbdfa87db53ef7d4e8b", size = 204175, upload-time = "2026-08-15T08:18:33.466Z" },
+    { url = "https://files.pythonhosted.org/packages/ac/33/eeb384dbd8dec570661354592f4f2e1b2fcc92585624d146a000caf53841/charset_normalizer-3.5.1-cp314-cp314-win_arm64.whl", hash = "sha256:4bea7f8ebe90bbd7f0e4a2de42ca6924ba23e3e76418c408ff82f1d46fabd687", size = 184123, upload-time = "2026-08-15T08:18:34.913Z" },
+    { url = "https://files.pythonhosted.org/packages/1c/6c/c73fa9d5a85f6ab05395de61c5f6984e0a9ff40bb5ff888d46dff02526c6/charset_normalizer-3.5.1-cp314-cp314t-macosx_10_15_universal2.whl", hash = "sha256:fbc597639158fd7c14d55e808718848319540f51b0e6746e3eefa59723a4a348", size = 381682, upload-time = "2026-08-15T08:18:36.349Z" },
+    { url = "https://files.pythonhosted.org/packages/30/c7/63565f860921457feba93bae6c86fb7746deb4cffeed2f375cb845318146/charset_normalizer-3.5.1-cp314-cp314t-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:e71c909f353863b2b89c83de2ebed71ea6d0df8a6ef65a128193c5e650766bef", size = 240826, upload-time = "2026-08-15T08:18:37.887Z" },
+    { url = "https://files.pythonhosted.org/packages/06/ae/7ae8807410dfa33f8e6f1715740adeaafa8a816cc4cb33508f54b1f7c896/charset_normalizer-3.5.1-cp314-cp314t-manylinux2014_armv7l.manylinux_2_17_armv7l.manylinux_2_31_armv7l.whl", hash = "sha256:7ac76cf9afd34929d76eb7fcb63be476a4853d8a96f0dcf2d0db68a0cbdf9885", size = 227861, upload-time = "2026-08-15T08:18:39.315Z" },
+    { url = "https://files.pythonhosted.org/packages/e9/a3/887c1642f0da26000b0e0652d91071113c0e72cea33952e225cf589f49a9/charset_normalizer-3.5.1-cp314-cp314t-manylinux2014_ppc64le.manylinux_2_17_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:a3a370082ce34d0612f421e15fe011c53bb1feff21a26d06ad4fb244dab5a375", size = 260758, upload-time = "2026-08-15T08:18:40.88Z" },
+    { url = "https://files.pythonhosted.org/packages/3e/11/e6f5b9a3d0e55b0ef7505cd3765cdd48f22db89994c947b316f52f801fd8/charset_normalizer-3.5.1-cp314-cp314t-manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl", hash = "sha256:256dd4d85d9e4dc595e2bc983c980e73f62ddeb3165c58b4c3dfe78c5c8548c1", size = 259950, upload-time = "2026-08-15T08:18:42.351Z" },
+    { url = "https://files.pythonhosted.org/packages/1b/ee/e4e10a94d51cd1ee638aa7e00b65399e6b2a4e8376ab6d2eac9f95586671/charset_normalizer-3.5.1-cp314-cp314t-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:58d4aa13a59c969dbfdf9e6a9560e242cbfd9e8a8f50c2747714df1a423adf65", size = 249329, upload-time = "2026-08-15T08:18:43.914Z" },
+    { url = "https://files.pythonhosted.org/packages/c4/25/d5f4198819e6059735a84e8d0bfb72dc33976da67b97adcd3fb5a5e07ec6/charset_normalizer-3.5.1-cp314-cp314t-manylinux_2_31_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:0c6dfb5ca6723eeed15aa8e564a014d69fcb8812f94eef11fe3631e0508199f5", size = 243137, upload-time = "2026-08-15T08:18:45.368Z" },
+    { url = "https://files.pythonhosted.org/packages/a5/e9/e925ca7569cf9fb9701fd82503fee73eea5268fdb856bdd64947092d3daa/charset_normalizer-3.5.1-cp314-cp314t-musllinux_1_2_aarch64.whl", hash = "sha256:c010f5581d9c612804cc59fcf7b524b707fbcb72828551237ab545bb5c7034af", size = 242820, upload-time = "2026-08-15T08:18:46.842Z" },
+    { url = "https://files.pythonhosted.org/packages/34/17/672c251a888ed2aebcdd2fe830ad0104e25ff83c43f5c4f9c15e9fc6853c/charset_normalizer-3.5.1-cp314-cp314t-musllinux_1_2_armv7l.whl", hash = "sha256:52ec005752a56ae79547a05c0139ca2501a0c866390b6115008456b9f0e7cde1", size = 230504, upload-time = "2026-08-15T08:18:48.353Z" },
+    { url = "https://files.pythonhosted.org/packages/3f/fc/f6a85abebd42ce4da2f1db0aa56cc6a0df1995e318b3875d14401b8381d1/charset_normalizer-3.5.1-cp314-cp314t-musllinux_1_2_ppc64le.whl", hash = "sha256:2bced4061f000f7187254a02ad3433ae17eaf991747ceea2f478422590a5bba9", size = 263087, upload-time = "2026-08-15T08:18:49.859Z" },
+    { url = "https://files.pythonhosted.org/packages/98/66/7c42677e739ba66746b297e2046918d793078094dc239e1e72768cffccc6/charset_normalizer-3.5.1-cp314-cp314t-musllinux_1_2_riscv64.whl", hash = "sha256:9eea3ab2597a5e65fe65296e2d6a84570845a6b55532d90333d740d48bbc850a", size = 243269, upload-time = "2026-08-15T08:18:51.601Z" },
+    { url = "https://files.pythonhosted.org/packages/de/d8/a50b79237f417af10f8c2a501ce8d1ca87829a22e69117891ca4ba20a69e/charset_normalizer-3.5.1-cp314-cp314t-musllinux_1_2_s390x.whl", hash = "sha256:496846868fea80e479324862fa877f02411f2fd0f83b79ccee2607aa68b2a032", size = 258766, upload-time = "2026-08-15T08:18:53.23Z" },
+    { url = "https://files.pythonhosted.org/packages/2e/1d/0fc91aeaeb3c83b748f532399ce67cf84604b48297405d740000f7a9e786/charset_normalizer-3.5.1-cp314-cp314t-musllinux_1_2_x86_64.whl", hash = "sha256:85d5855daafc240cc045c026d7a15fd198a09b0fc8ff6f5ecbb5297b509cb11e", size = 250814, upload-time = "2026-08-15T08:18:54.768Z" },
+    { url = "https://files.pythonhosted.org/packages/ae/10/3d8c777cf9024615295aa1b808324ad5b4a77855869c00824bad74ffaf8a/charset_normalizer-3.5.1-cp314-cp314t-win32.whl", hash = "sha256:58d3e12c88e0950bca850ae1f7c256055c097639c2edb9eb123af9807d8b15e4", size = 191074, upload-time = "2026-08-15T08:18:56.305Z" },
+    { url = "https://files.pythonhosted.org/packages/4d/81/ae557d3c44d1a1d688696d60563413a0866a91b7ebc50f20df838be3d8c8/charset_normalizer-3.5.1-cp314-cp314t-win_amd64.whl", hash = "sha256:acaf604462bf330b0d07e7a07c1d6e4adac79e5fb13e9c5140590542cafacc00", size = 216476, upload-time = "2026-08-15T08:18:57.889Z" },
+    { url = "https://files.pythonhosted.org/packages/27/e9/61c01fb8b804692569c036b3fc50495814502dcf13a60649c6055390b02c/charset_normalizer-3.5.1-cp314-cp314t-win_arm64.whl", hash = "sha256:fdb8a068947befafba9952162645dc2fecaeb400e64584829ed5e9b2fbe21a7f", size = 194115, upload-time = "2026-08-15T08:18:59.418Z" },
+    { url = "https://files.pythonhosted.org/packages/5b/97/fb4e82231aba271ffd775a1b4993b0defc4e3059f286ae41d9433409fe85/charset_normalizer-3.5.1-cp37-abi3-macosx_10_9_universal2.whl", hash = "sha256:41876ee62a3dddf48ff1121ad8f0798032aa03f2fd35f21f34a4cab14f18d8d2", size = 331467, upload-time = "2026-08-15T08:19:50.959Z" },
+    { url = "https://files.pythonhosted.org/packages/9f/2f/fe3f187327aac18e2d54e9d2b08e15d27bf9b642d9e51c219f130fc34d1a/charset_normalizer-3.5.1-cp37-abi3-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", hash = "sha256:a6dac12ff6b846103483683f60c5f8fee205121adc58ffd87e90a90a3af69e99", size = 253057, upload-time = "2026-08-15T08:19:52.654Z" },
+    { url = "https://files.pythonhosted.org/packages/d7/c7/9e48cee5c161fe24da823b61bf381921d77cb994a0a4de148e95018c1984/charset_normalizer-3.5.1-cp37-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:cee5dd7c6fb5dd52a0fe2a740f9bc6e3593f5f8b1788bde49de02086f30182b2", size = 240930, upload-time = "2026-08-15T08:19:54.163Z" },
+    { url = "https://files.pythonhosted.org/packages/49/e0/716601f3cc69be7b198951150c75ead1ece33c3c8036ff6ffa46029659a0/charset_normalizer-3.5.1-cp37-abi3-manylinux2014_armv7l.manylinux_2_17_armv7l.manylinux_2_31_armv7l.whl", hash = "sha256:343fb4f2821043bd87095f7b08a1a181febc8e36ac64212143bbfd0a0e1bc235", size = 230822, upload-time = "2026-08-15T08:19:55.807Z" },
+    { url = "https://files.pythonhosted.org/packages/d3/05/71bfc5caa0abcc45aea1f6a4d50ac68e59605ddc7666fe8494f4cd229665/charset_normalizer-3.5.1-cp37-abi3-manylinux2014_ppc64le.manylinux_2_17_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:ae4a097991662cd4fff0ddc74e0fe7874f82e00042fa0ea00855645ed0c79598", size = 260037, upload-time = "2026-08-15T08:19:57.312Z" },
+    { url = "https://files.pythonhosted.org/packages/c3/92/de7e32ed05341e7a9c4c877c318418197b7f2d66a3b68d561bf2ac57ca3e/charset_normalizer-3.5.1-cp37-abi3-manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl", hash = "sha256:4b599739b93b2cbeded49645ae3c8d1405c29ddfbceac1545c87a3f9580a9e96", size = 255097, upload-time = "2026-08-15T08:19:59.056Z" },
+    { url = "https://files.pythonhosted.org/packages/f5/7b/ade0a122600319dfa0b1000ab0f9731c94a817904cf3c5de408c73a4ede7/charset_normalizer-3.5.1-cp37-abi3-manylinux_2_31_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:b39b69b347e5e47a3b5b8cfc005c68c1ba347474e3960236c4944a8ecd174962", size = 250166, upload-time = "2026-08-15T08:20:00.612Z" },
+    { url = "https://files.pythonhosted.org/packages/75/9c/019fbb9f4834491a160951349b1a3714439376f66e5f7cf18b4f18f0c7aa/charset_normalizer-3.5.1-cp37-abi3-musllinux_1_2_aarch64.whl", hash = "sha256:a2028475ba855475b8b4d3cfeb4994269c967aea8b9892dfba907f4263a863a3", size = 241821, upload-time = "2026-08-15T08:20:02.321Z" },
+    { url = "https://files.pythonhosted.org/packages/2b/b8/11d4840bfc99330cc7fbcc2681ee5a044553a6e77655508d8f9b2bff7b34/charset_normalizer-3.5.1-cp37-abi3-musllinux_1_2_armv7l.whl", hash = "sha256:36047af20e17097c3bb9476c2b7655f2f7aa51322c0ba58c07695bedf755a950", size = 232529, upload-time = "2026-08-15T08:20:04.008Z" },
+    { url = "https://files.pythonhosted.org/packages/18/96/2b3a21492d9f65171ac75d872f5018260013d00bfa0ff70ec9f179148cbd/charset_normalizer-3.5.1-cp37-abi3-musllinux_1_2_ppc64le.whl", hash = "sha256:4c4fb141a727957c93edfe5c32a26ceb6b5f6461d67146e2d39f51e16170bea8", size = 260348, upload-time = "2026-08-15T08:20:05.877Z" },
+    { url = "https://files.pythonhosted.org/packages/d6/aa/a69a2028e8bd052476c245460ab19d7de595de084dd968f2d75cd50c3e25/charset_normalizer-3.5.1-cp37-abi3-musllinux_1_2_riscv64.whl", hash = "sha256:2f293479cce755c75f1697e87c409b7ae4c555c7dfecb6e988ad13abba943031", size = 247234, upload-time = "2026-08-15T08:20:07.487Z" },
+    { url = "https://files.pythonhosted.org/packages/35/8a/3d130aeabcaf3d2466af76b7b141c08d9e89c9016ab4b7cdd0f7dc2d1c62/charset_normalizer-3.5.1-cp37-abi3-musllinux_1_2_s390x.whl", hash = "sha256:3588e376b3ea2eea84976f67273d679f229e24c66dce7b82ae45aef04ff6e072", size = 256917, upload-time = "2026-08-15T08:20:09.142Z" },
+    { url = "https://files.pythonhosted.org/packages/80/c2/a7379b840292d0c1ab9fbd17d1f3967aa81794dc95bc74be8999d7fedcf7/charset_normalizer-3.5.1-cp37-abi3-musllinux_1_2_x86_64.whl", hash = "sha256:e199fb99720074809a7720f1c0b4d919eea8b87e88713e0f8f602f7bef543d9d", size = 254846, upload-time = "2026-08-15T08:20:10.727Z" },
+    { url = "https://files.pythonhosted.org/packages/01/65/d43b714731bb2f40d4053dfa00ecfc1c5a301f8e3316c5db3a09af59fe94/charset_normalizer-3.5.1-cp37-abi3-win32.whl", hash = "sha256:dd732602a7009217f658d5863d12d79d373a4de0eebc111094bcdd3bb8e0a6cc", size = 174216, upload-time = "2026-08-15T08:20:12.334Z" },
+    { url = "https://files.pythonhosted.org/packages/35/4f/b911ed898b26a09789eba9c9200c999aff6c61b4bafaf4838e56d1a1e1a3/charset_normalizer-3.5.1-cp37-abi3-win_amd64.whl", hash = "sha256:70055ff39b97c99e7ae40ea3e393fb62aa2e44dbd9b29f8d14f42fb0025c3959", size = 199764, upload-time = "2026-08-15T08:20:13.908Z" },
+    { url = "https://files.pythonhosted.org/packages/f0/a7/920baf467bfd9bf689f3b318340f37aee4572a71f162bd8db51da55ba4fa/charset_normalizer-3.5.1-cp37-abi3-win_arm64.whl", hash = "sha256:87e4f41d375c0b9be2fb5251aee4b8a689169e134535aed81bf085c3b647451e", size = 287318, upload-time = "2026-08-15T08:20:15.551Z" },
+    { url = "https://files.pythonhosted.org/packages/cc/61/d01fc49b8dea277640b55a9e15960dbca9fdc8c9fde18e572d39c59f4019/charset_normalizer-3.5.1-py3-none-any.whl", hash = "sha256:6df0ec430f9a831772c23ca5a224cba36517a58a84bb32c32bb59a9fa67c47f6", size = 68658, upload-time = "2026-08-15T08:20:43.306Z" },
+]
+
 [[package]]
 name = "click"
 version = "8.4.2"
@@ -419,6 +481,7 @@ dependencies = [
     { name = "fastmcp" },
     { name = "pydantic" },
     { name = "pydantic-settings" },
+    { name = "pygithub" },
     { name = "structlog" },
     { name = "tenacity" },
 ]
@@ -437,6 +500,7 @@ requires-dist = [
     { name = "fastmcp", specifier = ">=2.14.7" },
     { name = "pydantic", specifier = ">=2.13.4,<3" },
     { name = "pydantic-settings", specifier = ">=2.14.1" },
+    { name = "pygithub", specifier = ">=2.5.0" },
     { name = "pytest", marker = "extra == 'dev'", specifier = ">=9.0.3" },
     { name = "pytest-asyncio", marker = "extra == 'dev'", specifier = ">=1.4.0" },
     { name = "ruff", marker = "extra == 'dev'", specifier = ">=0.5.0" },
@@ -993,6 +1057,22 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/77/c1/6e422f34e569cf8e18df68d1939c81c099d2b61e4f7d9621c8a77560799c/pydantic_settings-2.14.2-py3-none-any.whl", hash = "sha256:a20c97b37910b6550d5ea50fbcc2d4187defe58cd57070b73863d069419c9440", size = 61715, upload-time = "2026-06-19T13:44:55.02Z" },
 ]
 
+[[package]]
+name = "pygithub"
+version = "2.9.1"
+source = { registry = "https://pypi.org/simple" }
+dependencies = [
+    { name = "pyjwt", extra = ["crypto"] },
+    { name = "pynacl" },
+    { name = "requests" },
+    { name = "typing-extensions" },
+    { name = "urllib3" },
+]
+sdist = { url = "https://files.pythonhosted.org/packages/ab/c3/8465a311197e16cf5ab68789fe689535e90f6b61ab524cc32a39e67237ae/pygithub-2.9.1.tar.gz", hash = "sha256:59771d7ff63d54d427be2e7d0dad2208dfffc2b0a045fec959263787739b611c", size = 2594989, upload-time = "2026-04-14T07:26:13.622Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/77/aa/81a5506f089a26338bff17535e4339b3b22049ebd1bcdeff756c4d7a7559/pygithub-2.9.1-py3-none-any.whl", hash = "sha256:2ec78fca30092d51a42d76f4ddb02131b6f0c666a35dfdf364cf302cdda115b9", size = 449710, upload-time = "2026-04-14T07:26:12.382Z" },
+]
+
 [[package]]
 name = "pygments"
 version = "2.20.0"
@@ -1016,6 +1096,41 @@ crypto = [
     { name = "cryptography" },
 ]
 
+[[package]]
+name = "pynacl"
+version = "1.6.2"
+source = { registry = "https://pypi.org/simple" }
+dependencies = [
+    { name = "cffi", marker = "platform_python_implementation != 'PyPy'" },
+]
+sdist = { url = "https://files.pythonhosted.org/packages/d9/9a/4019b524b03a13438637b11538c82781a5eda427394380381af8f04f467a/pynacl-1.6.2.tar.gz", hash = "sha256:018494d6d696ae03c7e656e5e74cdfd8ea1326962cc401bcf018f1ed8436811c", size = 3511692, upload-time = "2026-01-01T17:48:10.851Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/4b/79/0e3c34dc3c4671f67d251c07aa8eb100916f250ee470df230b0ab89551b4/pynacl-1.6.2-cp314-cp314t-macosx_10_10_universal2.whl", hash = "sha256:622d7b07cc5c02c666795792931b50c91f3ce3c2649762efb1ef0d5684c81594", size = 390064, upload-time = "2026-01-01T17:31:57.264Z" },
+    { url = "https://files.pythonhosted.org/packages/eb/1c/23a26e931736e13b16483795c8a6b2f641bf6a3d5238c22b070a5112722c/pynacl-1.6.2-cp314-cp314t-manylinux2014_aarch64.manylinux_2_17_aarch64.whl", hash = "sha256:d071c6a9a4c94d79eb665db4ce5cedc537faf74f2355e4d502591d850d3913c0", size = 809370, upload-time = "2026-01-01T17:31:59.198Z" },
+    { url = "https://files.pythonhosted.org/packages/87/74/8d4b718f8a22aea9e8dcc8b95deb76d4aae380e2f5b570cc70b5fd0a852d/pynacl-1.6.2-cp314-cp314t-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:fe9847ca47d287af41e82be1dd5e23023d3c31a951da134121ab02e42ac218c9", size = 1408304, upload-time = "2026-01-01T17:32:01.162Z" },
+    { url = "https://files.pythonhosted.org/packages/fd/73/be4fdd3a6a87fe8a4553380c2b47fbd1f7f58292eb820902f5c8ac7de7b0/pynacl-1.6.2-cp314-cp314t-manylinux_2_26_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:04316d1fc625d860b6c162fff704eb8426b1a8bcd3abacea11142cbd99a6b574", size = 844871, upload-time = "2026-01-01T17:32:02.824Z" },
+    { url = "https://files.pythonhosted.org/packages/55/ad/6efc57ab75ee4422e96b5f2697d51bbcf6cdcc091e66310df91fbdc144a8/pynacl-1.6.2-cp314-cp314t-manylinux_2_26_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:44081faff368d6c5553ccf55322ef2819abb40e25afaec7e740f159f74813634", size = 1446356, upload-time = "2026-01-01T17:32:04.452Z" },
+    { url = "https://files.pythonhosted.org/packages/78/b7/928ee9c4779caa0a915844311ab9fb5f99585621c5d6e4574538a17dca07/pynacl-1.6.2-cp314-cp314t-manylinux_2_34_aarch64.whl", hash = "sha256:a9f9932d8d2811ce1a8ffa79dcbdf3970e7355b5c8eb0c1a881a57e7f7d96e88", size = 826814, upload-time = "2026-01-01T17:32:06.078Z" },
+    { url = "https://files.pythonhosted.org/packages/f7/a9/1bdba746a2be20f8809fee75c10e3159d75864ef69c6b0dd168fc60e485d/pynacl-1.6.2-cp314-cp314t-manylinux_2_34_x86_64.whl", hash = "sha256:bc4a36b28dd72fb4845e5d8f9760610588a96d5a51f01d84d8c6ff9849968c14", size = 1411742, upload-time = "2026-01-01T17:32:07.651Z" },
+    { url = "https://files.pythonhosted.org/packages/f3/2f/5e7ea8d85f9f3ea5b6b87db1d8388daa3587eed181bdeb0306816fdbbe79/pynacl-1.6.2-cp314-cp314t-musllinux_1_2_aarch64.whl", hash = "sha256:3bffb6d0f6becacb6526f8f42adfb5efb26337056ee0831fb9a7044d1a964444", size = 801714, upload-time = "2026-01-01T17:32:09.558Z" },
+    { url = "https://files.pythonhosted.org/packages/06/ea/43fe2f7eab5f200e40fb10d305bf6f87ea31b3bbc83443eac37cd34a9e1e/pynacl-1.6.2-cp314-cp314t-musllinux_1_2_x86_64.whl", hash = "sha256:2fef529ef3ee487ad8113d287a593fa26f48ee3620d92ecc6f1d09ea38e0709b", size = 1372257, upload-time = "2026-01-01T17:32:11.026Z" },
+    { url = "https://files.pythonhosted.org/packages/4d/54/c9ea116412788629b1347e415f72195c25eb2f3809b2d3e7b25f5c79f13a/pynacl-1.6.2-cp314-cp314t-win32.whl", hash = "sha256:a84bf1c20339d06dc0c85d9aea9637a24f718f375d861b2668b2f9f96fa51145", size = 231319, upload-time = "2026-01-01T17:32:12.46Z" },
+    { url = "https://files.pythonhosted.org/packages/ce/04/64e9d76646abac2dccf904fccba352a86e7d172647557f35b9fe2a5ee4a1/pynacl-1.6.2-cp314-cp314t-win_amd64.whl", hash = "sha256:320ef68a41c87547c91a8b58903c9caa641ab01e8512ce291085b5fe2fcb7590", size = 244044, upload-time = "2026-01-01T17:32:13.781Z" },
+    { url = "https://files.pythonhosted.org/packages/33/33/7873dc161c6a06f43cda13dec67b6fe152cb2f982581151956fa5e5cdb47/pynacl-1.6.2-cp314-cp314t-win_arm64.whl", hash = "sha256:d29bfe37e20e015a7d8b23cfc8bd6aa7909c92a1b8f41ee416bbb3e79ef182b2", size = 188740, upload-time = "2026-01-01T17:32:15.083Z" },
+    { url = "https://files.pythonhosted.org/packages/be/7b/4845bbf88e94586ec47a432da4e9107e3fc3ce37eb412b1398630a37f7dd/pynacl-1.6.2-cp38-abi3-macosx_10_10_universal2.whl", hash = "sha256:c949ea47e4206af7c8f604b8278093b674f7c79ed0d4719cc836902bf4517465", size = 388458, upload-time = "2026-01-01T17:32:16.829Z" },
+    { url = "https://files.pythonhosted.org/packages/1e/b4/e927e0653ba63b02a4ca5b4d852a8d1d678afbf69b3dbf9c4d0785ac905c/pynacl-1.6.2-cp38-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.whl", hash = "sha256:8845c0631c0be43abdd865511c41eab235e0be69c81dc66a50911594198679b0", size = 800020, upload-time = "2026-01-01T17:32:18.34Z" },
+    { url = "https://files.pythonhosted.org/packages/7f/81/d60984052df5c97b1d24365bc1e30024379b42c4edcd79d2436b1b9806f2/pynacl-1.6.2-cp38-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:22de65bb9010a725b0dac248f353bb072969c94fa8d6b1f34b87d7953cf7bbe4", size = 1399174, upload-time = "2026-01-01T17:32:20.239Z" },
+    { url = "https://files.pythonhosted.org/packages/68/f7/322f2f9915c4ef27d140101dd0ed26b479f7e6f5f183590fd32dfc48c4d3/pynacl-1.6.2-cp38-abi3-manylinux_2_26_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:46065496ab748469cdd999246d17e301b2c24ae2fdf739132e580a0e94c94a87", size = 835085, upload-time = "2026-01-01T17:32:22.24Z" },
+    { url = "https://files.pythonhosted.org/packages/3e/d0/f301f83ac8dbe53442c5a43f6a39016f94f754d7a9815a875b65e218a307/pynacl-1.6.2-cp38-abi3-manylinux_2_26_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:8a66d6fb6ae7661c58995f9c6435bda2b1e68b54b598a6a10247bfcdadac996c", size = 1437614, upload-time = "2026-01-01T17:32:23.766Z" },
+    { url = "https://files.pythonhosted.org/packages/c4/58/fc6e649762b029315325ace1a8c6be66125e42f67416d3dbd47b69563d61/pynacl-1.6.2-cp38-abi3-manylinux_2_34_aarch64.whl", hash = "sha256:26bfcd00dcf2cf160f122186af731ae30ab120c18e8375684ec2670dccd28130", size = 818251, upload-time = "2026-01-01T17:32:25.69Z" },
+    { url = "https://files.pythonhosted.org/packages/c9/a8/b917096b1accc9acd878819a49d3d84875731a41eb665f6ebc826b1af99e/pynacl-1.6.2-cp38-abi3-manylinux_2_34_x86_64.whl", hash = "sha256:c8a231e36ec2cab018c4ad4358c386e36eede0319a0c41fed24f840b1dac59f6", size = 1402859, upload-time = "2026-01-01T17:32:27.215Z" },
+    { url = "https://files.pythonhosted.org/packages/85/42/fe60b5f4473e12c72f977548e4028156f4d340b884c635ec6b063fe7e9a5/pynacl-1.6.2-cp38-abi3-musllinux_1_2_aarch64.whl", hash = "sha256:68be3a09455743ff9505491220b64440ced8973fe930f270c8e07ccfa25b1f9e", size = 791926, upload-time = "2026-01-01T17:32:29.314Z" },
+    { url = "https://files.pythonhosted.org/packages/fa/f9/e40e318c604259301cc091a2a63f237d9e7b424c4851cafaea4ea7c4834e/pynacl-1.6.2-cp38-abi3-musllinux_1_2_x86_64.whl", hash = "sha256:8b097553b380236d51ed11356c953bf8ce36a29a3e596e934ecabe76c985a577", size = 1363101, upload-time = "2026-01-01T17:32:31.263Z" },
+    { url = "https://files.pythonhosted.org/packages/48/47/e761c254f410c023a469284a9bc210933e18588ca87706ae93002c05114c/pynacl-1.6.2-cp38-abi3-win32.whl", hash = "sha256:5811c72b473b2f38f7e2a3dc4f8642e3a3e9b5e7317266e4ced1fba85cae41aa", size = 227421, upload-time = "2026-01-01T17:32:33.076Z" },
+    { url = "https://files.pythonhosted.org/packages/41/ad/334600e8cacc7d86587fe5f565480fde569dfb487389c8e1be56ac21d8ac/pynacl-1.6.2-cp38-abi3-win_amd64.whl", hash = "sha256:62985f233210dee6548c223301b6c25440852e13d59a8b81490203c3227c5ba0", size = 239754, upload-time = "2026-01-01T17:32:34.557Z" },
+    { url = "https://files.pythonhosted.org/packages/29/7d/5945b5af29534641820d3bd7b00962abbbdfee84ec7e19f0d5b3175f9a31/pynacl-1.6.2-cp38-abi3-win_arm64.whl", hash = "sha256:834a43af110f743a754448463e8fd61259cd4ab5bbedcf70f9dabad1d28a394c", size = 184801, upload-time = "2026-01-01T17:32:36.309Z" },
+]
+
 [[package]]
 name = "pyperclip"
 version = "1.11.0"
@@ -1129,6 +1244,21 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/2c/58/ca301544e1fa93ed4f80d724bf5b194f6e4b945841c5bfd555878eea9fcb/referencing-0.37.0-py3-none-any.whl", hash = "sha256:381329a9f99628c9069361716891d34ad94af76e461dcb0335825aecc7692231", size = 26766, upload-time = "2025-10-13T15:30:47.625Z" },
 ]
 
+[[package]]
+name = "requests"
+version = "2.34.2"
+source = { registry = "https://pypi.org/simple" }
+dependencies = [
+    { name = "certifi" },
+    { name = "charset-normalizer" },
+    { name = "idna" },
+    { name = "urllib3" },
+]
+sdist = { url = "https://files.pythonhosted.org/packages/ac/c3/e2a2b89f2d3e2179abd6d00ebd70bff6273f37fb3e0cc209f48b39d00cbf/requests-2.34.2.tar.gz", hash = "sha256:f288924cae4e29463698d6d60bc6a4da69c89185ad1e0bcc4104f584e960b9ed", size = 142856, upload-time = "2026-05-14T19:25:27.735Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/a0/f4/c67b0b3f1b9245e8d266f0f112c500d50e5b4e83cb6f3b71b6528104182a/requests-2.34.2-py3-none-any.whl", hash = "sha256:2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0", size = 73075, upload-time = "2026-05-14T19:25:26.443Z" },
+]
+
 [[package]]
 name = "rich"
 version = "15.0.0"
@@ -1303,6 +1433,15 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/3b/25/2c87754f3a9e692315f7b811244090e68f362979fc8886b3fbd2985a1d8c/uncalled_for-0.3.2-py3-none-any.whl", hash = "sha256:0ff60b142c7d1f8070bde9d42afaa70aedc77dcc10998c227687e9c15713418e", size = 11444, upload-time = "2026-05-06T13:38:24.025Z" },
 ]
 
+[[package]]
+name = "urllib3"
+version = "2.7.0"
+source = { registry = "https://pypi.org/simple" }
+sdist = { url = "https://files.pythonhosted.org/packages/53/0c/06f8b233b8fd13b9e5ee11424ef85419ba0d8ba0b3138bf360be2ff56953/urllib3-2.7.0.tar.gz", hash = "sha256:231e0ec3b63ceb14667c67be60f2f2c40a518cb38b03af60abc813da26505f4c", size = 433602, upload-time = "2026-05-07T16:13:18.596Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/7f/3e/5db95bcf282c52709639744ca2a8b149baccf648e39c8cc87553df9eae0c/urllib3-2.7.0-py3-none-any.whl", hash = "sha256:9fb4c81ebbb1ce9531cce37674bbc6f1360472bc18ca9a553ede278ef7276897", size = 131087, upload-time = "2026-05-07T16:13:17.151Z" },
+]
+
 [[package]]
 name = "uvicorn"
 version = "0.51.0"
diff --git a/pyproject.toml b/pyproject.toml
index ce6816e2..dcc29324 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -15,6 +15,7 @@ dependencies = [
     "kubernetes-asyncio>=30.1.0",
     "pydantic>=2.13.4,<3",
     "pydantic-settings>=2.14.1",
+    "PyGithub>=2.5.0",
     "python-jose[cryptography]>=3.5.0",
     "requests>=2.32.0",
     "sap-ai-sdk-gen[all]>=5.11.0",
diff --git a/tests/execution_engine/test_hdlf_cert_provisioner.py b/tests/execution_engine/test_hdlf_cert_provisioner.py
index e772f60a..da25e6aa 100644
--- a/tests/execution_engine/test_hdlf_cert_provisioner.py
+++ b/tests/execution_engine/test_hdlf_cert_provisioner.py
@@ -109,6 +109,72 @@ async def test_poll_certificate_fails_on_terminal_ready_false_reason() -> None:
         )
 
 
+class _FakeCustomObjectsApi:
+    def __init__(self, certificates: list[dict[str, object]]) -> None:
+        self.get_namespaced_custom_object = AsyncMock(side_effect=certificates)
+
+
+@pytest.mark.asyncio
+async def test_poll_certificate_waits_while_secret_does_not_exist(monkeypatch: pytest.MonkeyPatch) -> None:
+    """Secret absence during issuance is treated as in-progress, not failed."""
+    monkeypatch.setattr(hdlf_cert_provisioner, "_CERT_POLL_INTERVAL_SECONDS", 0)
+    custom = _FakeCustomObjectsApi(
+        [
+            {
+                "status": {
+                    "conditions": [
+                        {
+                            "type": "Ready",
+                            "status": "False",
+                            "reason": "DoesNotExist",
+                            "message": "Issuing certificate as Secret does not exist",
+                        }
+                    ]
+                }
+            },
+            {"status": {"conditions": [{"type": "Ready", "status": "True"}]}},
+        ]
+    )
+
+    await hdlf_cert_provisioner._poll_certificate(  # type: ignore[arg-type]
+        custom,
+        "fl-job-exec-1-hdlf-cert",
+        "test-depl-name",
+        "insp-1",
+    )
+
+    assert custom.get_namespaced_custom_object.await_count == 2
+
+
+@pytest.mark.asyncio
+async def test_poll_certificate_fails_on_terminal_ready_false_reason() -> None:
+    """Explicit terminal certificate Ready=False reasons fail fast."""
+    custom = _FakeCustomObjectsApi(
+        [
+            {
+                "status": {
+                    "conditions": [
+                        {
+                            "type": "Ready",
+                            "status": "False",
+                            "reason": "Failed",
+                            "message": "private key generation failed",
+                        }
+                    ]
+                }
+            }
+        ]
+    )
+
+    with pytest.raises(IOError, match="failed: Failed"):
+        await hdlf_cert_provisioner._poll_certificate(  # type: ignore[arg-type]
+            custom,
+            "fl-job-exec-1-hdlf-cert",
+            "test-depl-name",
+            "insp-1",
+        )
+
+
 @pytest.mark.asyncio
 async def test_provision_inspection_access_grants_read_write_policy(monkeypatch: pytest.MonkeyPatch) -> None:
     """Per-inspection handler certs can read inputs and write handler results."""
diff --git a/tests/mcp_servers/github_finalizer/__init__.py b/tests/mcp_servers/github_finalizer/__init__.py
new file mode 100644
index 00000000..e69de29b
diff --git a/tests/mcp_servers/github_finalizer/test_comment_format.py b/tests/mcp_servers/github_finalizer/test_comment_format.py
new file mode 100644
index 00000000..95b49c17
--- /dev/null
+++ b/tests/mcp_servers/github_finalizer/test_comment_format.py
@@ -0,0 +1,245 @@
+"""Tests for the deterministic comment / check-run rendering.
+
+The structure asserted here is byte-compatible with the production
+"Photon Service / Fault Analyzer" comment; ``test_render_proposal_matches_photon_structure_byte_for_byte``
+pins the exact bytes against a captured reference block.
+"""
+
+from fl_mcp_servers.github_finalizer import comment_format as cf
+from fl_mcp_servers.github_finalizer.models import (
+    FinalizeRequest,
+    Proposal,
+)
+
+VALID_DIFF = "--- a/f.py\n+++ b/f.py\n@@ -1,2 +1,2 @@\n-old\n+new\n context\n"
+
+
+def _proposal(**overrides: object) -> Proposal:
+    """Build a Proposal with the new photon fields and the given overrides."""
+    base: dict[str, object] = {
+        "category": "GHAS",
+        "critical_message": "Building a command line with string concatenation",
+        "fault_description": "The code concatenates user input into a shell command.",
+        "fix_proposal": "Use ProcessBuilder with a List<String>.",
+        "fault_handler_ids": ["ghas-handler"],
+    }
+    base.update(overrides)
+    return Proposal(**base)  # type: ignore[arg-type]
+
+
+def _request(**overrides: object) -> FinalizeRequest:
+    """Build a FinalizeRequest with sensible defaults and the given overrides."""
+    base: dict[str, object] = {
+        "inspection_id": "866008e6-0704-484b-b49d-a9c297da9896",
+        "commit_sha": "c263f2f5c7d5ecc95a57cbcbbcfed2ead12ccbf3",
+        "host": "github.wdf.sap.corp",
+        "repo": "DBaaS/sample",
+        "head_sha": "c263f2f5c7d5ecc95a57cbcbbcfed2ead12ccbf3",
+        "pr_number": 657,
+    }
+    base.update(overrides)
+    return FinalizeRequest(**base)  # type: ignore[arg-type]
+
+
+def test_inspection_marker_carries_header_and_inspection_id() -> None:
+    """The inspection marker pins the DO-NOT-CHANGE header and the inspection id, and matches OUTER_MARKER_RE."""
+    marker = cf.render_inspection_marker("m-9")
+    assert marker.startswith("<!-- DO NOT CHANGE THE STRUCTURE OR CONTENT OF THIS COMMENT.")
+    assert marker.endswith("<!--inspection_id_m-9-->")
+    assert cf.OUTER_MARKER_RE.search(marker)
+
+
+def test_feedback_block_is_byte_compatible_with_historical_parser() -> None:
+    """The feedback block keeps the exact markers, handler-id list, and checkbox lines the webhook expects."""
+    block = cf.FEEDBACK_BLOCK.format(fault_handler_ids="h1,h2")
+    assert block.startswith("<!--feedback_block--><!--fault_handler_ids_h1,h2-->")
+    assert "<!--feedback_block_end-->" in block
+    assert "- [ ] :100: - The fix proposal solves the problem." in block
+    assert "- [ ] :+1: - The fix proposal helps to solve the problem." in block
+    assert "- [ ] :-1: - The fix proposal is not helpful." in block
+
+
+def test_render_proposal_matches_photon_structure_byte_for_byte() -> None:
+    """A rendered proposal reproduces the production finding block exactly."""
+    proposal = _proposal(
+        category="GHAS",
+        critical_message="Building a command line with string concatenation",
+        fault_description="The code at line 14 directly concatenates user input.",
+        fix_proposal="Replace the string concatenation with ProcessBuilder.",
+        fault_handler_ids=["ghas-handler", "sast-handler"],
+        diff="--- a/x.java\n+++ b/x.java\n@@ -1 +1 @@\n-bad\n+good",
+    )
+    expected = (
+        "## GHAS\n"
+        "**Critical message:** Building a command line with string concatenation\n"
+        "<details>\n"
+        "<summary><i>Details</i></summary>\n"
+        "\n"
+        ">*Fault description:*\n"
+        ">The code at line 14 directly concatenates user input.\n"
+        ">\n"
+        "\n"
+        ">*Fix proposal:*\n"
+        ">Replace the string concatenation with ProcessBuilder.\n"
+        "\n"
+        "</details>\n"
+        "\n"
+        "```diff\n"
+        "--- a/x.java\n+++ b/x.java\n@@ -1 +1 @@\n-bad\n+good\n"
+        "```\n"
+        "\n"
+        "<!--feedback_block--><!--fault_handler_ids_ghas-handler,sast-handler-->\n"
+        "*Please rate the quality of the fix proposal by selecting one of the following options:*\n"
+        "- [ ] :100: - The fix proposal solves the problem.\n"
+        "- [ ] :+1: - The fix proposal helps to solve the problem.\n"
+        "- [ ] :-1: - The fix proposal is not helpful.\n"
+        "<!--feedback_block_end-->\n"
+    )
+    assert cf.render_proposal(proposal, include_feedback=True) == expected
+
+
+def test_render_proposal_omits_feedback_block_when_not_included() -> None:
+    """The check-run rendering (include_feedback=False) drops the rating checkboxes entirely."""
+    out = cf.render_proposal(_proposal(), include_feedback=False)
+    assert "<!--feedback_block-->" not in out
+    assert ":100:" not in out
+    assert "**Critical message:**" in out
+
+
+def test_render_proposal_renders_imperfect_diff_verbatim() -> None:
+    """A non-empty diff renders verbatim; structural imperfections are not policed."""
+    out = cf.render_proposal(_proposal(diff="not a perfectly formed diff"), include_feedback=True)
+    assert "```diff\nnot a perfectly formed diff\n```" in out
+
+
+def test_render_proposal_omits_empty_diff() -> None:
+    """A whitespace-only diff is omitted rather than emitting a blank diff block."""
+    out = cf.render_proposal(_proposal(diff="   \n"), include_feedback=True)
+    assert "```diff" not in out
+
+
+def test_render_comment_reproduces_header_title_and_commit_line() -> None:
+    """The comment leads with the header/inspection marker, title, commit link, and commit marker."""
+    out = cf.render_comment(
+        _request(proposals=[_proposal()]),
+        max_suggestions=5,
+        character_limit=60000,
+        check_run_url="url",
+    )
+    sha = "c263f2f5c7d5ecc95a57cbcbbcfed2ead12ccbf3"
+    assert out.startswith("<!-- DO NOT CHANGE THE STRUCTURE OR CONTENT OF THIS COMMENT.")
+    assert "<!--inspection_id_866008e6-0704-484b-b49d-a9c297da9896-->\n" in out
+    assert "# Fault Localization\n" in out
+    assert f"*Commit: [{sha}](https://github.wdf.sap.corp/DBaaS/sample/commit/{sha})*\n" in out
+    assert f"<!--commit_sha_{sha}-->\n" in out
+    assert "We analyzed the build logs and identified the following issues:" in out
+
+
+def test_render_comment_no_findings() -> None:
+    """An empty request renders the no-findings body and footer under the header, with no intro line."""
+    out = cf.render_comment(_request(), max_suggestions=2, character_limit=60000, check_run_url="url")
+    assert "No actionable findings" in out
+    assert "identified the following issues" not in out
+    assert cf.OUTER_MARKER_RE.search(out)
+    assert out.rstrip().endswith("We're here to help!*")
+
+
+def test_render_comment_caps_suggestions_and_links_check_run() -> None:
+    """More proposals than the cap are truncated and the check-run link closes the comment."""
+    proposals = [_proposal(critical_message=f"P{i}", fault_handler_ids=[f"h-{i}"]) for i in range(5)]
+    out = cf.render_comment(
+        _request(proposals=proposals),
+        max_suggestions=2,
+        character_limit=60000,
+        check_run_url="THE_URL",
+    )
+    assert out.count("**Critical message:** P") == 2
+    assert out.rstrip().endswith("[Fault Analyzer Check](THE_URL).")
+
+
+def test_render_comment_ends_with_footer_when_nothing_dropped() -> None:
+    """When every proposal fits, the comment closes with the footer, not the check-run link."""
+    out = cf.render_comment(
+        _request(proposals=[_proposal()]),
+        max_suggestions=2,
+        character_limit=60000,
+        check_run_url="THE_URL",
+    )
+    assert "THE_URL" not in out
+    assert out.rstrip().endswith("We're here to help!*")
+
+
+def test_render_comment_includes_feedback_block_by_default() -> None:
+    """The PR comment (include_feedback default True) carries the rating checkboxes."""
+    out = cf.render_comment(
+        _request(proposals=[_proposal()]),
+        max_suggestions=2,
+        character_limit=60000,
+        check_run_url="",
+    )
+    assert "<!--feedback_block-->" in out
+    assert ":100:" in out
+
+
+def test_render_comment_respects_character_budget() -> None:
+    """Rendering stops before the character budget and links the check run for the dropped items."""
+    big = "x" * 500
+    proposals = [_proposal(fault_description=big, fault_handler_ids=[f"h-{i}"]) for i in range(5)]
+    out = cf.render_comment(
+        _request(proposals=proposals),
+        max_suggestions=5,
+        character_limit=800,
+        check_run_url="THE_URL",
+    )
+    assert len(out) < 800 + 300
+    assert "THE_URL" in out
+
+
+def test_render_proposal_without_diff_still_carries_feedback_block() -> None:
+    """An advisory (diff-less) proposal renders no diff block but is still rated in the comment."""
+    out = cf.render_proposal(_proposal(diff=None), include_feedback=True)
+    assert "```diff" not in out
+    assert "<!--feedback_block--><!--fault_handler_ids_ghas-handler-->" in out
+    assert "<!--feedback_block_end-->" in out
+
+
+def test_check_run_summary_shows_all_items_without_feedback_or_link() -> None:
+    """The check-run summary shows every item, drops feedback checkboxes and the external link, keeps the footer."""
+    proposals = [_proposal(critical_message=f"P{i}", fault_handler_ids=[f"h-{i}"]) for i in range(5)]
+    out = cf.render_check_run_summary(_request(proposals=proposals))
+    assert out.count("**Critical message:** P") == 5
+    assert "Fault Analyzer Check" not in out
+    assert "<!--feedback_block-->" not in out
+    assert out.rstrip().endswith("We're here to help!*")
+
+
+def test_footer_matches_production_reference_byte_for_byte() -> None:
+    """The trailing footer reproduces the live production hint text exactly (DBaaS/Backup-Operator PR 1814)."""
+    assert cf.FOOTER == (
+        "The Intelligent Pipeline Service currently supports analyzing issues related to "
+        "**Pipeline configuration**, **Unit Tests** (Go, Python or Type Script), "
+        "**Hadolint** (Dockerfile linting), **CheckMarx**, **SonarQube**, **GHAS/CodeQL**, "
+        "**Protecode** (BDBA), **Docker Build**, **Linting** and **Pullrequest check**. If "
+        "you need assistance with other pipeline checks and stages, or if you have any "
+        "feedback, feature requests, or questions, please feel free to reach out to us at "
+        "[# sap-intelligent-pipelines](https://sap.enterprise.slack.com/archives/C09CC5L87MW) "
+        "or via email to [DL HANA DCE Quality Eng BLG]"
+        "(mailto:DL_695E49E01174E612B0E31D54@global.corp.sap). We're here to help!"
+    )
+
+
+def test_comment_feedback_block_is_immediately_followed_by_footer() -> None:
+    """In the comment, the last feedback block is closed and then the italic footer follows."""
+    out = cf.render_comment(
+        _request(proposals=[_proposal()]),
+        max_suggestions=2,
+        character_limit=60000,
+        check_run_url="",
+    )
+    assert out.endswith(f"<!--feedback_block_end-->\n\n\n*{cf.FOOTER}*\n")
+
+
+def test_has_findings() -> None:
+    """has_findings is true only when the request carries proposals."""
+    assert not cf.has_findings(_request())
+    assert cf.has_findings(_request(proposals=[_proposal()]))
diff --git a/tests/mcp_servers/github_finalizer/test_github_app_client.py b/tests/mcp_servers/github_finalizer/test_github_app_client.py
new file mode 100644
index 00000000..1c659771
--- /dev/null
+++ b/tests/mcp_servers/github_finalizer/test_github_app_client.py
@@ -0,0 +1,104 @@
+"""Tests for the GitHub App client credential sourcing and host selection."""
+
+from typing import Any
+
+import pytest
+
+import fl_mcp_servers.github_finalizer.app_client as gac
+from fl_mcp_servers.github_finalizer.app_client import GithubApp, GithubAppRegistry
+from fl_mcp_servers.github_finalizer.settings import AppVariant, GithubFinalizerSettings, GitHubHost
+
+
+def _settings(monkeypatch: pytest.MonkeyPatch) -> GithubFinalizerSettings:
+    """Build finalizer settings with both hosts' prod and test App credentials configured."""
+    for name in (
+        "MCP_GITHUB_APP_ID_TOOLS",
+        "MCP_GITHUB_APP_KEY_TOOLS",
+        "MCP_GITHUB_APP_ID_WDF",
+        "MCP_GITHUB_APP_KEY_WDF",
+        "MCP_TEST_GITHUB_APP_ID_TOOLS",
+        "MCP_TEST_GITHUB_APP_KEY_TOOLS",
+        "MCP_TEST_GITHUB_APP_ID_WDF",
+        "MCP_TEST_GITHUB_APP_KEY_WDF",
+    ):
+        monkeypatch.delenv(name, raising=False)
+    monkeypatch.setenv("MCP_GITHUB_APP_ID_TOOLS", "111")
+    monkeypatch.setenv("MCP_GITHUB_APP_KEY_TOOLS", "tools-key")
+    monkeypatch.setenv("MCP_GITHUB_APP_ID_WDF", "222")
+    monkeypatch.setenv("MCP_GITHUB_APP_KEY_WDF", "wdf-key")
+    monkeypatch.setenv("MCP_TEST_GITHUB_APP_ID_TOOLS", "333")
+    monkeypatch.setenv("MCP_TEST_GITHUB_APP_KEY_TOOLS", "tools-test-key")
+    return GithubFinalizerSettings()
+
+
+def test_integration_built_with_settings_credentials_and_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
+    """The GithubIntegration is built with the host's credentials, base URL, and verify=False."""
+    settings = _settings(monkeypatch)
+    captured: dict[str, Any] = {}
+
+    def fake_app_auth(app_id: str, app_key: str) -> str:
+        captured["app_id"] = app_id
+        captured["app_key"] = app_key
+        return "auth-obj"
+
+    def fake_integration(*, auth: str, base_url: str, verify: bool) -> Any:
+        captured["auth"] = auth
+        captured["base_url"] = base_url
+        captured["verify"] = verify
+        return object()
+
+    monkeypatch.setattr(gac.Auth, "AppAuth", fake_app_auth)
+    monkeypatch.setattr(gac, "GithubIntegration", fake_integration)
+
+    app = GithubApp(GitHubHost.WDF, "org/repo", settings)
+    app._get_github_integration()  # pylint: disable=protected-access
+
+    assert captured["app_id"] == "222"
+    assert captured["app_key"] == "wdf-key"
+    assert captured["base_url"] == "https://github.wdf.sap.corp/api/v3"
+    assert captured["verify"] is False
+
+
+def test_integration_uses_test_variant_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
+    """A GithubApp built with the TEST variant authenticates with the test-App credentials."""
+    settings = _settings(monkeypatch)
+    captured: dict[str, Any] = {}
+
+    def fake_app_auth(app_id: str, app_key: str) -> str:
+        captured["app_id"] = app_id
+        captured["app_key"] = app_key
+        return "auth-obj"
+
+    monkeypatch.setattr(gac.Auth, "AppAuth", fake_app_auth)
+    monkeypatch.setattr(gac, "GithubIntegration", lambda **_kwargs: object())
+
+    app = GithubApp(GitHubHost.TOOLS, "org/repo", settings, AppVariant.TEST)
+    app._get_github_integration()  # pylint: disable=protected-access
+
+    assert captured["app_id"] == "333"
+    assert captured["app_key"] == "tools-test-key"
+
+
+def test_registry_caches_one_app_per_host_repo_variant(monkeypatch: pytest.MonkeyPatch) -> None:
+    """The registry returns the same GithubApp per (host, repo, variant) and distinct ones otherwise."""
+    settings = _settings(monkeypatch)
+    registry = GithubAppRegistry(settings)
+
+    a1 = registry.get(GitHubHost.TOOLS, "org/repo")
+    a2 = registry.get(GitHubHost.TOOLS, "org/repo")
+    a3 = registry.get(GitHubHost.TOOLS, "org/other")
+    a4 = registry.get(GitHubHost.WDF, "org/repo")
+    a5 = registry.get(GitHubHost.TOOLS, "org/repo", AppVariant.TEST)
+
+    assert a1 is a2
+    assert a1 is not a3
+    assert a1 is not a4
+    assert a1 is not a5
+    assert a5.variant is AppVariant.TEST
+
+
+def test_repo_full_name_split(monkeypatch: pytest.MonkeyPatch) -> None:
+    """get_repo_full_name round-trips the owner/name split."""
+    settings = _settings(monkeypatch)
+    app = GithubApp(GitHubHost.TOOLS, "my-org/my-repo", settings)
+    assert app.get_repo_full_name() == "my-org/my-repo"
diff --git a/tests/mcp_servers/github_finalizer/test_github_finalizer_mcp.py b/tests/mcp_servers/github_finalizer/test_github_finalizer_mcp.py
new file mode 100644
index 00000000..ffcce9ea
--- /dev/null
+++ b/tests/mcp_servers/github_finalizer/test_github_finalizer_mcp.py
@@ -0,0 +1,307 @@
+"""Tests for the finalize_in_github orchestration with GitHub calls mocked."""
+
+from types import SimpleNamespace
+from typing import Any
+
+import pytest
+from mcp.server.fastmcp.exceptions import ToolError
+
+import fl_mcp_servers.github_finalizer.server as srv
+from fl_mcp_servers.github_finalizer.app_client import GithubAppRegistry
+from fl_mcp_servers.github_finalizer.comment_format import render_inspection_marker
+from fl_mcp_servers.github_finalizer.models import FinalizeRequest, Proposal, SummaryConfig
+from fl_mcp_servers.github_finalizer.settings import AppVariant, GithubFinalizerSettings, GitHubHost
+
+# App ids matching the credentials configured by _settings below. The prod App
+# creates check runs by default; PROD_APP_ID is what discovery matches against.
+PROD_APP_ID = 1
+TEST_APP_ID = 2
+
+
+class FakeComment:
+    """Stand-in for a GitHub comment capturing delete side effects."""
+
+    def __init__(self, body: str = "", comment_id: int = 111) -> None:
+        self.body = body
+        self.id = comment_id
+        self.html_url = f"https://example/comment/{comment_id}"
+        self.deleted = False
+
+    def delete(self) -> None:
+        self.deleted = True
+
+
+class FakeCheckRun:
+    """Stand-in for a GitHub check run capturing the edit payload.
+
+    ``app_id`` mirrors ``CheckRun.app.id`` — the id of the GitHub App that created
+    the run, which discovery reads to pick the owning credential variant. Defaults
+    to the prod App.
+    """
+
+    def __init__(self, name: str, check_id: int, app_id: int = PROD_APP_ID) -> None:
+        self.name = name
+        self.id = check_id
+        self.app = SimpleNamespace(id=app_id)
+        self.edited_with: dict[str, Any] | None = None
+
+    def edit(self, **kwargs: Any) -> None:
+        self.edited_with = kwargs
+
+
+class FakeApp:
+    """Stand-in for GithubApp capturing side effects."""
+
+    def __init__(self) -> None:
+        self.comments: list[FakeComment] = []
+        self.check_runs = [FakeCheckRun("Fault Analyzer", 42), FakeCheckRun("Other", 99)]
+        self.created: list[str] = []
+        self.origin = SimpleNamespace(kind="pr")
+
+    def get_pull_request(self, _n: int) -> Any:
+        return self.origin
+
+    def get_commit(self, _sha: str) -> Any:
+        return self.origin
+
+    def get_check_runs(self, _head_sha: str) -> list[FakeCheckRun]:
+        return self.check_runs
+
+    def get_comments(self, _origin: Any) -> list[FakeComment]:
+        return self.comments
+
+    def create_comment(self, _origin: Any, body: str) -> FakeComment:
+        self.created.append(body)
+        comment = FakeComment(body=body, comment_id=222)
+        self.comments.append(comment)
+        return comment
+
+    def delete_comment(self, comment: FakeComment) -> None:
+        comment.delete()
+        self.comments = [c for c in self.comments if c is not comment]
+
+    def update_check_run(self, check_run_id: int, **kwargs: Any) -> FakeCheckRun:
+        run = next(r for r in self.check_runs if r.id == check_run_id)
+        run.edit(**kwargs)
+        return run
+
+
+def _settings(monkeypatch: pytest.MonkeyPatch) -> GithubFinalizerSettings:
+    """Build finalizer settings with both prod and test TOOLS credentials.
+
+    The prod/test App ids match PROD_APP_ID / TEST_APP_ID so check-run creator
+    discovery resolves to the right variant.
+    """
+    for name in (
+        "MCP_GITHUB_APP_ID_TOOLS",
+        "MCP_GITHUB_APP_KEY_TOOLS",
+        "MCP_GITHUB_APP_ID_WDF",
+        "MCP_GITHUB_APP_KEY_WDF",
+        "MCP_TEST_GITHUB_APP_ID_TOOLS",
+        "MCP_TEST_GITHUB_APP_KEY_TOOLS",
+        "MCP_TEST_GITHUB_APP_ID_WDF",
+        "MCP_TEST_GITHUB_APP_KEY_WDF",
+    ):
+        monkeypatch.delenv(name, raising=False)
+    monkeypatch.setenv("MCP_GITHUB_APP_ID_TOOLS", str(PROD_APP_ID))
+    monkeypatch.setenv("MCP_GITHUB_APP_KEY_TOOLS", "k")
+    monkeypatch.setenv("MCP_TEST_GITHUB_APP_ID_TOOLS", str(TEST_APP_ID))
+    monkeypatch.setenv("MCP_TEST_GITHUB_APP_KEY_TOOLS", "test-k")
+    return GithubFinalizerSettings()
+
+
+def _ctx(settings: GithubFinalizerSettings, app: FakeApp, test_app: FakeApp | None = None) -> Any:
+    """Build a fake MCP Context whose registry is preloaded with the fake app(s).
+
+    ``app`` backs the prod variant; ``test_app`` backs the test variant and
+    defaults to ``app`` so a single fake serves whichever variant discovery
+    resolves to. Pass a distinct ``test_app`` to exercise variant selection or the
+    prod-not-installed read fallback.
+    """
+    registry = GithubAppRegistry(settings)
+    registry._apps[(GitHubHost.TOOLS, "org/repo", AppVariant.PROD)] = app  # type: ignore[assignment]  # pylint: disable=protected-access
+    registry._apps[(GitHubHost.TOOLS, "org/repo", AppVariant.TEST)] = test_app or app  # type: ignore[assignment]  # pylint: disable=protected-access
+    state = srv._ServerState(settings=settings, registry=registry)  # pylint: disable=protected-access
+    request_context = SimpleNamespace(lifespan_context=state)
+    return SimpleNamespace(request_context=request_context)
+
+
+def _request(**overrides: Any) -> FinalizeRequest:
+    """Build a FinalizeRequest with sensible defaults and the given overrides."""
+    base: dict[str, Any] = {
+        "inspection_id": "m-1",
+        "commit_sha": "abc",
+        "host": "github.tools.sap",
+        "repo": "org/repo",
+        "head_sha": "head",
+        "pr_number": 7,
+        "proposals": [
+            Proposal(
+                category="Unit Tests",
+                critical_message="Fix",
+                fault_description="it broke",
+                fix_proposal="do it",
+                fault_handler_ids=["unit-test-handler"],
+            )
+        ],
+    }
+    base.update(overrides)
+    return FinalizeRequest(**base)
+
+
+async def test_finalize_posts_new_comment_and_updates_check_run(monkeypatch: pytest.MonkeyPatch) -> None:
+    """A first run posts a new comment and completes the named check run."""
+    settings = _settings(monkeypatch)
+    app = FakeApp()
+    result = await srv.finalize_in_github(_request(), _ctx(settings, app))
+
+    assert result.check_run_id == 42
+    assert result.conclusion == "success"
+    assert result.comment_skipped is False
+    assert result.comment_id == 222
+    assert len(app.created) == 1
+    run = next(r for r in app.check_runs if r.id == 42)
+    assert run.edited_with is not None
+    assert run.edited_with["status"] == "completed"
+    assert run.edited_with["conclusion"] == "success"
+    assert "summary" in run.edited_with["output"]
+
+
+async def test_finalize_sets_failure_conclusion_when_no_findings(monkeypatch: pytest.MonkeyPatch) -> None:
+    """With no proposals to report, the check run is completed with a failure conclusion."""
+    settings = _settings(monkeypatch)
+    app = FakeApp()
+    result = await srv.finalize_in_github(_request(proposals=[]), _ctx(settings, app))
+
+    assert result.conclusion == "failure"
+    assert next(r for r in app.check_runs if r.id == 42).edited_with["conclusion"] == "failure"
+
+
+async def test_finalize_replaces_existing_summary_comment(monkeypatch: pytest.MonkeyPatch) -> None:
+    """A rerun deletes the prior summary comment and posts a fresh one so the developer is re-notified."""
+    settings = _settings(monkeypatch)
+    app = FakeApp()
+    prior = FakeComment(body=render_inspection_marker("old-inspection") + "stale", comment_id=555)
+    app.comments.append(prior)
+
+    result = await srv.finalize_in_github(_request(), _ctx(settings, app))
+
+    assert prior.deleted is True
+    assert len(app.created) == 1
+    assert "<!--inspection_id_m-1-->" in app.created[0]
+    assert result.comment_id == 222
+
+
+async def test_finalize_skips_comment_when_disabled_still_updates_check_run(monkeypatch: pytest.MonkeyPatch) -> None:
+    """When the request config disables comments the comment is skipped but the check run is still updated."""
+    settings = _settings(monkeypatch)
+    app = FakeApp()
+    result = await srv.finalize_in_github(_request(config=SummaryConfig(disable_comments=True)), _ctx(settings, app))
+
+    assert result.comment_skipped is True
+    assert result.comment_url is None and result.comment_id is None
+    assert app.created == []
+    assert next(r for r in app.check_runs if r.id == 42).edited_with is not None
+
+
+async def test_finalize_raises_when_check_run_missing(monkeypatch: pytest.MonkeyPatch) -> None:
+    """A missing FL check run raises ToolError."""
+    settings = _settings(monkeypatch)
+    app = FakeApp()
+    app.check_runs = [FakeCheckRun("Other", 99)]
+    with pytest.raises(ToolError, match="No check run named"):
+        await srv.finalize_in_github(_request(), _ctx(settings, app))
+
+
+async def test_finalize_raises_without_credentials_for_host(monkeypatch: pytest.MonkeyPatch) -> None:
+    """A request for a host without configured credentials raises ToolError."""
+    settings = _settings(monkeypatch)
+    app = FakeApp()
+    with pytest.raises(ToolError, match="No GitHub App credentials"):
+        await srv.finalize_in_github(_request(host="github.wdf.sap.corp"), _ctx(settings, app))
+
+
+async def test_finalize_check_run_update_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
+    """A failure updating the check run is surfaced as ToolError."""
+    settings = _settings(monkeypatch)
+    app = FakeApp()
+
+    def boom(*_a: Any, **_k: Any) -> None:
+        raise RuntimeError("github down")
+
+    app.update_check_run = boom  # type: ignore[method-assign]
+    with pytest.raises(ToolError, match="Failed to update check run"):
+        await srv.finalize_in_github(_request(), _ctx(settings, app))
+
+
+async def test_finalize_updates_test_owned_check_run_via_test_app(monkeypatch: pytest.MonkeyPatch) -> None:
+    """A check run created by the test App is updated through the test-variant app."""
+    settings = _settings(monkeypatch)
+    prod_app = FakeApp()
+    # The only Fault Analyzer run on the commit was created by the test App.
+    prod_app.check_runs = [FakeCheckRun("Fault Analyzer", 42, app_id=TEST_APP_ID), FakeCheckRun("Other", 99)]
+    test_app = FakeApp()
+    test_app.check_runs = prod_app.check_runs
+
+    result = await srv.finalize_in_github(_request(), _ctx(settings, prod_app, test_app=test_app))
+
+    assert result.check_run_id == 42
+    # The write (comment + check-run edit) went through the test app, not prod.
+    assert len(test_app.created) == 1
+    assert prod_app.created == []
+    assert next(r for r in test_app.check_runs if r.id == 42).edited_with is not None
+
+
+async def test_finalize_first_owned_run_wins_when_both_variants_present(monkeypatch: pytest.MonkeyPatch) -> None:
+    """When both a prod-owned and test-owned run share the name, the first in order wins."""
+    settings = _settings(monkeypatch)
+    app = FakeApp()
+    app.check_runs = [
+        FakeCheckRun("Fault Analyzer", 42, app_id=PROD_APP_ID),
+        FakeCheckRun("Fault Analyzer", 43, app_id=TEST_APP_ID),
+    ]
+    result = await srv.finalize_in_github(_request(), _ctx(settings, app))
+
+    assert result.check_run_id == 42
+    assert next(r for r in app.check_runs if r.id == 42).edited_with is not None
+    assert next(r for r in app.check_runs if r.id == 43).edited_with is None
+
+
+async def test_finalize_raises_when_run_owned_by_foreign_app(monkeypatch: pytest.MonkeyPatch) -> None:
+    """A name-matching run created by neither our prod nor test App is not a target."""
+    settings = _settings(monkeypatch)
+    app = FakeApp()
+    app.check_runs = [FakeCheckRun("Fault Analyzer", 42, app_id=9999), FakeCheckRun("Other", 99)]
+    with pytest.raises(ToolError, match="No check run named"):
+        await srv.finalize_in_github(_request(), _ctx(settings, app))
+
+
+async def test_finalize_falls_back_to_test_app_when_prod_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
+    """When the prod App cannot list check runs, discovery reads with the test App."""
+    settings = _settings(monkeypatch)
+    prod_app = FakeApp()
+
+    def not_installed(_head_sha: str) -> list[FakeCheckRun]:
+        raise RuntimeError("prod app not installed on repo")
+
+    prod_app.get_check_runs = not_installed  # type: ignore[method-assign]
+    test_app = FakeApp()
+    test_app.check_runs = [FakeCheckRun("Fault Analyzer", 42, app_id=TEST_APP_ID)]
+
+    result = await srv.finalize_in_github(_request(), _ctx(settings, prod_app, test_app=test_app))
+
+    assert result.check_run_id == 42
+    assert next(r for r in test_app.check_runs if r.id == 42).edited_with is not None
+
+
+async def test_finalize_raises_when_no_app_can_list_check_runs(monkeypatch: pytest.MonkeyPatch) -> None:
+    """If every configured App fails to list check runs, the read failure is surfaced."""
+    settings = _settings(monkeypatch)
+    app = FakeApp()
+
+    def boom(_head_sha: str) -> list[FakeCheckRun]:
+        raise RuntimeError("github down")
+
+    app.get_check_runs = boom  # type: ignore[method-assign]
+    with pytest.raises(ToolError, match="Could not list check runs"):
+        await srv.finalize_in_github(_request(), _ctx(settings, app))
diff --git a/tests/mcp_servers/github_finalizer/test_github_finalizer_settings.py b/tests/mcp_servers/github_finalizer/test_github_finalizer_settings.py
new file mode 100644
index 00000000..eeb9f88a
--- /dev/null
+++ b/tests/mcp_servers/github_finalizer/test_github_finalizer_settings.py
@@ -0,0 +1,146 @@
+"""Tests for GithubFinalizerSettings and host resolution."""
+
+import pytest
+
+from fl_mcp_servers.github_finalizer.env_vars import (
+    ENV_GITHUB_APP_ID_TOOLS,
+    ENV_GITHUB_APP_ID_WDF,
+    ENV_GITHUB_APP_KEY_TOOLS,
+    ENV_GITHUB_APP_KEY_WDF,
+    ENV_TEST_GITHUB_APP_ID_TOOLS,
+    ENV_TEST_GITHUB_APP_ID_WDF,
+    ENV_TEST_GITHUB_APP_KEY_TOOLS,
+    ENV_TEST_GITHUB_APP_KEY_WDF,
+)
+from fl_mcp_servers.github_finalizer.settings import (
+    AppVariant,
+    GithubFinalizerSettings,
+    GitHubHost,
+    resolve_host,
+)
+
+_ALL_APP_ENV_VARS = (
+    ENV_GITHUB_APP_ID_TOOLS,
+    ENV_GITHUB_APP_KEY_TOOLS,
+    ENV_GITHUB_APP_ID_WDF,
+    ENV_GITHUB_APP_KEY_WDF,
+    ENV_TEST_GITHUB_APP_ID_TOOLS,
+    ENV_TEST_GITHUB_APP_KEY_TOOLS,
+    ENV_TEST_GITHUB_APP_ID_WDF,
+    ENV_TEST_GITHUB_APP_KEY_WDF,
+)
+
+
+def _env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
+    """Clear all finalizer App env vars (prod and test), then set the given ones."""
+    for name in _ALL_APP_ENV_VARS:
+        monkeypatch.delenv(name, raising=False)
+    for key, value in values.items():
+        monkeypatch.setenv(key, value)
+
+
+def test_resolve_host_defaults_to_tools() -> None:
+    """resolve_host returns TOOLS for tools hosts and anything non-WDF."""
+    assert resolve_host("github.tools.sap") is GitHubHost.TOOLS
+    assert resolve_host("https://github.tools.sap") is GitHubHost.TOOLS
+    assert resolve_host("anything-else") is GitHubHost.TOOLS
+
+
+def test_resolve_host_detects_wdf() -> None:
+    """resolve_host returns WDF whenever the WDF marker is present."""
+    assert resolve_host("github.wdf.sap.corp") is GitHubHost.WDF
+    assert resolve_host("https://github.wdf.sap.corp") is GitHubHost.WDF
+
+
+def test_settings_require_at_least_one_app(monkeypatch: pytest.MonkeyPatch) -> None:
+    """Construction fails when neither host has App credentials."""
+    _env(monkeypatch)
+    with pytest.raises(ValueError, match="No GitHub App credentials"):
+        GithubFinalizerSettings()
+
+
+def test_settings_partial_credentials_are_not_enough(monkeypatch: pytest.MonkeyPatch) -> None:
+    """An App id without its key is incomplete for that host."""
+    _env(monkeypatch, MCP_GITHUB_APP_ID_TOOLS="123")
+    with pytest.raises(ValueError, match="No GitHub App credentials"):
+        GithubFinalizerSettings()
+
+
+def test_get_app_credentials_returns_decoded_key(monkeypatch: pytest.MonkeyPatch) -> None:
+    """get_app_credentials returns the id and the decoded private key for a configured host."""
+    _env(monkeypatch, MCP_GITHUB_APP_ID_TOOLS="123", MCP_GITHUB_APP_KEY_TOOLS="private-key")
+    settings = GithubFinalizerSettings()
+    assert settings.has_credentials(GitHubHost.TOOLS)
+    assert not settings.has_credentials(GitHubHost.WDF)
+    assert settings.get_app_credentials(GitHubHost.TOOLS) == ("123", "private-key")
+
+
+def test_get_app_credentials_missing_host_raises(monkeypatch: pytest.MonkeyPatch) -> None:
+    """get_app_credentials raises for a host that is not configured."""
+    _env(monkeypatch, MCP_GITHUB_APP_ID_TOOLS="123", MCP_GITHUB_APP_KEY_TOOLS="k")
+    settings = GithubFinalizerSettings()
+    with pytest.raises(ValueError, match="host"):
+        settings.get_app_credentials(GitHubHost.WDF)
+
+
+def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
+    """Settings hold only GitHub App credentials; no behaviour knobs or checkout path."""
+    _env(monkeypatch, MCP_GITHUB_APP_ID_WDF="9", MCP_GITHUB_APP_KEY_WDF="k")
+    settings = GithubFinalizerSettings()
+    assert settings.has_credentials(GitHubHost.WDF)
+    # Behaviour knobs and the local checkout path are not settings.
+    assert not hasattr(settings, "local_repo_path")
+    assert not hasattr(settings, "github_character_limit")
+    assert not hasattr(settings, "max_suggestions")
+    assert not hasattr(settings, "disable_comments")
+
+
+def test_app_key_kept_out_of_repr(monkeypatch: pytest.MonkeyPatch) -> None:
+    """The App private key never leaks into repr() or model_dump()."""
+    _env(monkeypatch, MCP_GITHUB_APP_ID_TOOLS="1", MCP_GITHUB_APP_KEY_TOOLS="s3cr3t-pem")
+    settings = GithubFinalizerSettings()
+    assert "s3cr3t-pem" not in repr(settings)
+    assert "s3cr3t-pem" not in str(settings.model_dump())
+
+
+def test_test_app_env_vars_populate_test_variant(monkeypatch: pytest.MonkeyPatch) -> None:
+    """MCP_TEST_GITHUB_APP_* env vars load into the test variant, not the prod fields."""
+    _env(
+        monkeypatch,
+        MCP_TEST_GITHUB_APP_ID_TOOLS="t-111",
+        MCP_TEST_GITHUB_APP_KEY_TOOLS="t-key",
+    )
+    settings = GithubFinalizerSettings()
+    assert settings.has_credentials(GitHubHost.TOOLS, AppVariant.TEST)
+    assert not settings.has_credentials(GitHubHost.TOOLS, AppVariant.PROD)
+    assert settings.get_app_credentials(GitHubHost.TOOLS, AppVariant.TEST) == ("t-111", "t-key")
+
+
+def test_prod_and_test_variants_are_independent(monkeypatch: pytest.MonkeyPatch) -> None:
+    """Prod and test credentials for the same host are held and read separately."""
+    _env(
+        monkeypatch,
+        MCP_GITHUB_APP_ID_TOOLS="p-1",
+        MCP_GITHUB_APP_KEY_TOOLS="p-key",
+        MCP_TEST_GITHUB_APP_ID_TOOLS="t-1",
+        MCP_TEST_GITHUB_APP_KEY_TOOLS="t-key",
+    )
+    settings = GithubFinalizerSettings()
+    assert settings.get_configured_app_id(GitHubHost.TOOLS, AppVariant.PROD) == "p-1"
+    assert settings.get_configured_app_id(GitHubHost.TOOLS, AppVariant.TEST) == "t-1"
+    assert settings.get_app_credentials(GitHubHost.TOOLS, AppVariant.PROD) == ("p-1", "p-key")
+    assert settings.get_app_credentials(GitHubHost.TOOLS, AppVariant.TEST) == ("t-1", "t-key")
+
+
+def test_get_configured_app_id_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
+    """get_configured_app_id returns None for a variant with no configured id."""
+    _env(monkeypatch, MCP_GITHUB_APP_ID_TOOLS="p-1", MCP_GITHUB_APP_KEY_TOOLS="p-key")
+    settings = GithubFinalizerSettings()
+    assert settings.get_configured_app_id(GitHubHost.TOOLS, AppVariant.TEST) is None
+
+
+def test_only_test_credentials_are_enough_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
+    """The server starts when only a test-App pair is configured."""
+    _env(monkeypatch, MCP_TEST_GITHUB_APP_ID_WDF="9", MCP_TEST_GITHUB_APP_KEY_WDF="k")
+    settings = GithubFinalizerSettings()
+    assert settings.has_credentials(GitHubHost.WDF, AppVariant.TEST)
diff --git a/tests/mcp_servers/github_finalizer/test_models.py b/tests/mcp_servers/github_finalizer/test_models.py
new file mode 100644
index 00000000..e15a5eab
--- /dev/null
+++ b/tests/mcp_servers/github_finalizer/test_models.py
@@ -0,0 +1,98 @@
+"""Tests for FinalizeRequest input validation guards.
+
+These cover the corruption cases the field types alone cannot catch: unknown /
+typo'd keys (``extra="forbid"``) and a missing/empty ``fault_handler_ids`` list.
+Both must surface as ValidationErrors so the agent learns what to fix rather
+than getting silently-wrong behaviour.
+"""
+
+import pytest
+from pydantic import ValidationError
+
+from fl_mcp_servers.github_finalizer.models import FinalizeRequest, Proposal, SummaryConfig
+
+
+def _proposal(**overrides: object) -> Proposal:
+    """Build a minimal valid proposal with the given overrides."""
+    base: dict[str, object] = {
+        "category": "GHAS",
+        "critical_message": "msg",
+        "fault_description": "what",
+        "fix_proposal": "how",
+        "fault_handler_ids": ["h-1"],
+    }
+    base.update(overrides)
+    return Proposal(**base)  # type: ignore[arg-type]
+
+
+def _request(**overrides: object) -> dict[str, object]:
+    """Return valid FinalizeRequest kwargs with the given overrides applied."""
+    base: dict[str, object] = {
+        "inspection_id": "i-1",
+        "commit_sha": "abc",
+        "host": "github.tools.sap",
+        "repo": "org/repo",
+        "head_sha": "head",
+    }
+    base.update(overrides)
+    return base
+
+
+def test_unknown_top_level_key_is_rejected() -> None:
+    """A typo'd top-level field surfaces as a ValidationError, not a silent ignore."""
+    with pytest.raises(ValidationError, match="max_suggestion"):
+        FinalizeRequest(**_request(max_suggestion=5))  # type: ignore[arg-type]  # typo: should be nested in config
+
+
+def test_unknown_config_key_is_rejected() -> None:
+    """A typo'd config key surfaces as a ValidationError rather than defaulting silently."""
+    with pytest.raises(ValidationError, match="disable_commentss"):
+        SummaryConfig(disable_commentss=True)  # type: ignore[call-arg]
+
+
+def test_unknown_proposal_key_is_rejected() -> None:
+    """A typo'd nested proposal field is rejected too."""
+    with pytest.raises(ValidationError, match="fault_descriptionn"):
+        Proposal(
+            category="GHAS",
+            critical_message="m",
+            fault_descriptionn="oops",  # type: ignore[call-arg]
+            fix_proposal="how",
+            fault_handler_ids=["h-1"],
+        )
+
+
+def test_missing_fault_handler_ids_is_rejected() -> None:
+    """fault_handler_ids is required; omitting it is a ValidationError."""
+    with pytest.raises(ValidationError, match="fault_handler_ids"):
+        Proposal(
+            category="GHAS",
+            critical_message="m",
+            fault_description="what",
+            fix_proposal="how",
+        )  # type: ignore[call-arg]
+
+
+def test_empty_fault_handler_ids_is_rejected() -> None:
+    """An empty fault_handler_ids list violates min_length=1."""
+    with pytest.raises(ValidationError, match="fault_handler_ids"):
+        _proposal(fault_handler_ids=[])
+
+
+def test_shared_handler_id_across_proposals_is_accepted() -> None:
+    """The same handler id may contribute to more than one proposal."""
+    request = FinalizeRequest(
+        **_request(  # type: ignore[arg-type]
+            proposals=[
+                _proposal(fault_handler_ids=["ghas"]),
+                _proposal(fault_handler_ids=["ghas", "sast"]),
+            ]
+        )
+    )
+    assert len(request.proposals) == 2
+
+
+def test_negative_max_suggestions_is_rejected() -> None:
+    """A negative max_suggestions violates the ge=0 constraint."""
+    with pytest.raises(ValidationError):
+        SummaryConfig(max_suggestions=-1)
diff --git a/uv.lock b/uv.lock
index cb3be231..a3a81771 100644
--- a/uv.lock
+++ b/uv.lock
@@ -774,6 +774,7 @@ dependencies = [
     { name = "kubernetes-asyncio" },
     { name = "pydantic" },
     { name = "pydantic-settings" },
+    { name = "pygithub" },
     { name = "python-jose", extra = ["cryptography"] },
     { name = "requests" },
     { name = "sap-ai-sdk-gen", extra = ["all"] },
@@ -825,6 +826,7 @@ requires-dist = [
     { name = "pydantic", specifier = ">=2.13.4,<3" },
     { name = "pydantic-settings", specifier = ">=2.14.1" },
     { name = "pydocstyle", marker = "extra == 'dev'", specifier = ">=6.3.0" },
+    { name = "pygithub", specifier = ">=2.5.0" },
     { name = "pylint", marker = "extra == 'dev'", specifier = ">=3.3" },
     { name = "pylint-pydantic", marker = "extra == 'dev'", specifier = ">=0.3.0" },
     { name = "pytest", marker = "extra == 'dev'", specifier = ">=9.0.3" },
@@ -2265,6 +2267,22 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/36/ea/99ddefac41971acad68f14114f38261c1f27dac0b3ec529824ebc739bdaa/pydocstyle-6.3.0-py3-none-any.whl", hash = "sha256:118762d452a49d6b05e194ef344a55822987a462831ade91ec5c06fd2169d019", size = 38038, upload-time = "2023-01-17T20:29:18.094Z" },
 ]
 
+[[package]]
+name = "pygithub"
+version = "2.9.1"
+source = { registry = "https://pypi.org/simple" }
+dependencies = [
+    { name = "pyjwt", extra = ["crypto"] },
+    { name = "pynacl" },
+    { name = "requests" },
+    { name = "typing-extensions" },
+    { name = "urllib3" },
+]
+sdist = { url = "https://files.pythonhosted.org/packages/ab/c3/8465a311197e16cf5ab68789fe689535e90f6b61ab524cc32a39e67237ae/pygithub-2.9.1.tar.gz", hash = "sha256:59771d7ff63d54d427be2e7d0dad2208dfffc2b0a045fec959263787739b611c", size = 2594989, upload-time = "2026-04-14T07:26:13.622Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/77/aa/81a5506f089a26338bff17535e4339b3b22049ebd1bcdeff756c4d7a7559/pygithub-2.9.1-py3-none-any.whl", hash = "sha256:2ec78fca30092d51a42d76f4ddb02131b6f0c666a35dfdf364cf302cdda115b9", size = 449710, upload-time = "2026-04-14T07:26:12.382Z" },
+]
+
 [[package]]
 name = "pygments"
 version = "2.20.0"
@@ -2340,6 +2358,41 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/2d/ac/5de3c91c7f9354444af251f053cc9953c89cce1defa74b907f67be4f770a/pylint_pydantic-0.4.1-py3-none-any.whl", hash = "sha256:d1b937abe5c346d38de69ee1ada80c93d38ee2356addbabb687e2eb44036ac93", size = 16161, upload-time = "2025-10-27T08:03:33.641Z" },
 ]
 
+[[package]]
+name = "pynacl"
+version = "1.6.2"
+source = { registry = "https://pypi.org/simple" }
+dependencies = [
+    { name = "cffi", marker = "platform_python_implementation != 'PyPy'" },
+]
+sdist = { url = "https://files.pythonhosted.org/packages/d9/9a/4019b524b03a13438637b11538c82781a5eda427394380381af8f04f467a/pynacl-1.6.2.tar.gz", hash = "sha256:018494d6d696ae03c7e656e5e74cdfd8ea1326962cc401bcf018f1ed8436811c", size = 3511692, upload-time = "2026-01-01T17:48:10.851Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/4b/79/0e3c34dc3c4671f67d251c07aa8eb100916f250ee470df230b0ab89551b4/pynacl-1.6.2-cp314-cp314t-macosx_10_10_universal2.whl", hash = "sha256:622d7b07cc5c02c666795792931b50c91f3ce3c2649762efb1ef0d5684c81594", size = 390064, upload-time = "2026-01-01T17:31:57.264Z" },
+    { url = "https://files.pythonhosted.org/packages/eb/1c/23a26e931736e13b16483795c8a6b2f641bf6a3d5238c22b070a5112722c/pynacl-1.6.2-cp314-cp314t-manylinux2014_aarch64.manylinux_2_17_aarch64.whl", hash = "sha256:d071c6a9a4c94d79eb665db4ce5cedc537faf74f2355e4d502591d850d3913c0", size = 809370, upload-time = "2026-01-01T17:31:59.198Z" },
+    { url = "https://files.pythonhosted.org/packages/87/74/8d4b718f8a22aea9e8dcc8b95deb76d4aae380e2f5b570cc70b5fd0a852d/pynacl-1.6.2-cp314-cp314t-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:fe9847ca47d287af41e82be1dd5e23023d3c31a951da134121ab02e42ac218c9", size = 1408304, upload-time = "2026-01-01T17:32:01.162Z" },
+    { url = "https://files.pythonhosted.org/packages/fd/73/be4fdd3a6a87fe8a4553380c2b47fbd1f7f58292eb820902f5c8ac7de7b0/pynacl-1.6.2-cp314-cp314t-manylinux_2_26_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:04316d1fc625d860b6c162fff704eb8426b1a8bcd3abacea11142cbd99a6b574", size = 844871, upload-time = "2026-01-01T17:32:02.824Z" },
+    { url = "https://files.pythonhosted.org/packages/55/ad/6efc57ab75ee4422e96b5f2697d51bbcf6cdcc091e66310df91fbdc144a8/pynacl-1.6.2-cp314-cp314t-manylinux_2_26_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:44081faff368d6c5553ccf55322ef2819abb40e25afaec7e740f159f74813634", size = 1446356, upload-time = "2026-01-01T17:32:04.452Z" },
+    { url = "https://files.pythonhosted.org/packages/78/b7/928ee9c4779caa0a915844311ab9fb5f99585621c5d6e4574538a17dca07/pynacl-1.6.2-cp314-cp314t-manylinux_2_34_aarch64.whl", hash = "sha256:a9f9932d8d2811ce1a8ffa79dcbdf3970e7355b5c8eb0c1a881a57e7f7d96e88", size = 826814, upload-time = "2026-01-01T17:32:06.078Z" },
+    { url = "https://files.pythonhosted.org/packages/f7/a9/1bdba746a2be20f8809fee75c10e3159d75864ef69c6b0dd168fc60e485d/pynacl-1.6.2-cp314-cp314t-manylinux_2_34_x86_64.whl", hash = "sha256:bc4a36b28dd72fb4845e5d8f9760610588a96d5a51f01d84d8c6ff9849968c14", size = 1411742, upload-time = "2026-01-01T17:32:07.651Z" },
+    { url = "https://files.pythonhosted.org/packages/f3/2f/5e7ea8d85f9f3ea5b6b87db1d8388daa3587eed181bdeb0306816fdbbe79/pynacl-1.6.2-cp314-cp314t-musllinux_1_2_aarch64.whl", hash = "sha256:3bffb6d0f6becacb6526f8f42adfb5efb26337056ee0831fb9a7044d1a964444", size = 801714, upload-time = "2026-01-01T17:32:09.558Z" },
+    { url = "https://files.pythonhosted.org/packages/06/ea/43fe2f7eab5f200e40fb10d305bf6f87ea31b3bbc83443eac37cd34a9e1e/pynacl-1.6.2-cp314-cp314t-musllinux_1_2_x86_64.whl", hash = "sha256:2fef529ef3ee487ad8113d287a593fa26f48ee3620d92ecc6f1d09ea38e0709b", size = 1372257, upload-time = "2026-01-01T17:32:11.026Z" },
+    { url = "https://files.pythonhosted.org/packages/4d/54/c9ea116412788629b1347e415f72195c25eb2f3809b2d3e7b25f5c79f13a/pynacl-1.6.2-cp314-cp314t-win32.whl", hash = "sha256:a84bf1c20339d06dc0c85d9aea9637a24f718f375d861b2668b2f9f96fa51145", size = 231319, upload-time = "2026-01-01T17:32:12.46Z" },
+    { url = "https://files.pythonhosted.org/packages/ce/04/64e9d76646abac2dccf904fccba352a86e7d172647557f35b9fe2a5ee4a1/pynacl-1.6.2-cp314-cp314t-win_amd64.whl", hash = "sha256:320ef68a41c87547c91a8b58903c9caa641ab01e8512ce291085b5fe2fcb7590", size = 244044, upload-time = "2026-01-01T17:32:13.781Z" },
+    { url = "https://files.pythonhosted.org/packages/33/33/7873dc161c6a06f43cda13dec67b6fe152cb2f982581151956fa5e5cdb47/pynacl-1.6.2-cp314-cp314t-win_arm64.whl", hash = "sha256:d29bfe37e20e015a7d8b23cfc8bd6aa7909c92a1b8f41ee416bbb3e79ef182b2", size = 188740, upload-time = "2026-01-01T17:32:15.083Z" },
+    { url = "https://files.pythonhosted.org/packages/be/7b/4845bbf88e94586ec47a432da4e9107e3fc3ce37eb412b1398630a37f7dd/pynacl-1.6.2-cp38-abi3-macosx_10_10_universal2.whl", hash = "sha256:c949ea47e4206af7c8f604b8278093b674f7c79ed0d4719cc836902bf4517465", size = 388458, upload-time = "2026-01-01T17:32:16.829Z" },
+    { url = "https://files.pythonhosted.org/packages/1e/b4/e927e0653ba63b02a4ca5b4d852a8d1d678afbf69b3dbf9c4d0785ac905c/pynacl-1.6.2-cp38-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.whl", hash = "sha256:8845c0631c0be43abdd865511c41eab235e0be69c81dc66a50911594198679b0", size = 800020, upload-time = "2026-01-01T17:32:18.34Z" },
+    { url = "https://files.pythonhosted.org/packages/7f/81/d60984052df5c97b1d24365bc1e30024379b42c4edcd79d2436b1b9806f2/pynacl-1.6.2-cp38-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:22de65bb9010a725b0dac248f353bb072969c94fa8d6b1f34b87d7953cf7bbe4", size = 1399174, upload-time = "2026-01-01T17:32:20.239Z" },
+    { url = "https://files.pythonhosted.org/packages/68/f7/322f2f9915c4ef27d140101dd0ed26b479f7e6f5f183590fd32dfc48c4d3/pynacl-1.6.2-cp38-abi3-manylinux_2_26_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:46065496ab748469cdd999246d17e301b2c24ae2fdf739132e580a0e94c94a87", size = 835085, upload-time = "2026-01-01T17:32:22.24Z" },
+    { url = "https://files.pythonhosted.org/packages/3e/d0/f301f83ac8dbe53442c5a43f6a39016f94f754d7a9815a875b65e218a307/pynacl-1.6.2-cp38-abi3-manylinux_2_26_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:8a66d6fb6ae7661c58995f9c6435bda2b1e68b54b598a6a10247bfcdadac996c", size = 1437614, upload-time = "2026-01-01T17:32:23.766Z" },
+    { url = "https://files.pythonhosted.org/packages/c4/58/fc6e649762b029315325ace1a8c6be66125e42f67416d3dbd47b69563d61/pynacl-1.6.2-cp38-abi3-manylinux_2_34_aarch64.whl", hash = "sha256:26bfcd00dcf2cf160f122186af731ae30ab120c18e8375684ec2670dccd28130", size = 818251, upload-time = "2026-01-01T17:32:25.69Z" },
+    { url = "https://files.pythonhosted.org/packages/c9/a8/b917096b1accc9acd878819a49d3d84875731a41eb665f6ebc826b1af99e/pynacl-1.6.2-cp38-abi3-manylinux_2_34_x86_64.whl", hash = "sha256:c8a231e36ec2cab018c4ad4358c386e36eede0319a0c41fed24f840b1dac59f6", size = 1402859, upload-time = "2026-01-01T17:32:27.215Z" },
+    { url = "https://files.pythonhosted.org/packages/85/42/fe60b5f4473e12c72f977548e4028156f4d340b884c635ec6b063fe7e9a5/pynacl-1.6.2-cp38-abi3-musllinux_1_2_aarch64.whl", hash = "sha256:68be3a09455743ff9505491220b64440ced8973fe930f270c8e07ccfa25b1f9e", size = 791926, upload-time = "2026-01-01T17:32:29.314Z" },
+    { url = "https://files.pythonhosted.org/packages/fa/f9/e40e318c604259301cc091a2a63f237d9e7b424c4851cafaea4ea7c4834e/pynacl-1.6.2-cp38-abi3-musllinux_1_2_x86_64.whl", hash = "sha256:8b097553b380236d51ed11356c953bf8ce36a29a3e596e934ecabe76c985a577", size = 1363101, upload-time = "2026-01-01T17:32:31.263Z" },
+    { url = "https://files.pythonhosted.org/packages/48/47/e761c254f410c023a469284a9bc210933e18588ca87706ae93002c05114c/pynacl-1.6.2-cp38-abi3-win32.whl", hash = "sha256:5811c72b473b2f38f7e2a3dc4f8642e3a3e9b5e7317266e4ced1fba85cae41aa", size = 227421, upload-time = "2026-01-01T17:32:33.076Z" },
+    { url = "https://files.pythonhosted.org/packages/41/ad/334600e8cacc7d86587fe5f565480fde569dfb487389c8e1be56ac21d8ac/pynacl-1.6.2-cp38-abi3-win_amd64.whl", hash = "sha256:62985f233210dee6548c223301b6c25440852e13d59a8b81490203c3227c5ba0", size = 239754, upload-time = "2026-01-01T17:32:34.557Z" },
+    { url = "https://files.pythonhosted.org/packages/29/7d/5945b5af29534641820d3bd7b00962abbbdfee84ec7e19f0d5b3175f9a31/pynacl-1.6.2-cp38-abi3-win_arm64.whl", hash = "sha256:834a43af110f743a754448463e8fd61259cd4ab5bbedcf70f9dabad1d28a394c", size = 184801, upload-time = "2026-01-01T17:32:36.309Z" },
+]
+
 [[package]]
 name = "pyperclip"
 version = "1.11.0"

```
