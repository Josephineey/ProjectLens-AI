from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .mcp_tools import (
    mcp_ask_codebase,
    mcp_index_repository,
    mcp_language_capabilities,
    mcp_run_checks,
    mcp_repository_overview,
    mcp_run_eval,
    mcp_scan_repository,
    mcp_search_code,
    mcp_status,
)


def create_mcp_server(default_root: str | Path):
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as error:
        raise RuntimeError(
            'ProjectLens MCP support requires the optional MCP dependency. '
            'Install it with: python -m pip install "projectlens-ai[mcp]"'
        ) from error

    root = Path(default_root).expanduser().resolve()
    mcp = FastMCP(
        "ProjectLens AI",
        instructions=(
            "Use ProjectLens to overview, scan, index, search, inspect, and report capability coverage for local code repositories. "
            "For broad repository-understanding requests, whether quick or deep, start with projectlens_repository_overview as the planning map. "
            "For quick summaries, overview may be enough; for deep or source-cited answers, continue with focused projectlens_search_code or projectlens_ask_codebase calls. "
            "After overview, do not immediately repeat projectlens_scan_repository, projectlens_status, or projectlens_language_capabilities unless an overview field is missing or the user explicitly asks for that raw view. "
            "For narrow requests such as only checks, status, eval, or finding one specific symbol/file, call the specific tool directly. "
            "Prefer projectlens_index_repository before search or ask when no index exists. "
            "projectlens_ask_codebase returns source-grounded evidence and does not call an LLM."
        ),
    )

    @mcp.tool()
    def projectlens_repository_overview(
        path: str | None = None,
        build_index_if_missing: bool = True,
        include_checks: bool = True,
    ) -> dict[str, Any]:
        """Return a compact first-pass repository overview for an MCP client."""
        return mcp_repository_overview(root, path, build_index_if_missing, include_checks)

    @mcp.tool()
    def projectlens_scan_repository(path: str | None = None) -> dict[str, Any]:
        """Scan a repository and return local metadata, technologies, files, and symbols."""
        return mcp_scan_repository(root, path)

    @mcp.tool()
    def projectlens_index_repository(path: str | None = None) -> dict[str, Any]:
        """Build or refresh the local SQLite index for a repository."""
        return mcp_index_repository(root, path)

    @mcp.tool()
    def projectlens_language_capabilities(path: str | None = None) -> dict[str, Any]:
        """Report language parser coverage, confidence, and fallback status for a repository."""
        return mcp_language_capabilities(root, path)

    @mcp.tool()
    def projectlens_status(path: str | None = None) -> dict[str, Any]:
        """Return ProjectLens index status for a repository."""
        return mcp_status(root, path)

    @mcp.tool()
    def projectlens_search_code(query: str, path: str | None = None, limit: int = 5) -> dict[str, Any]:
        """Search code with hybrid keyword, symbol, path, role, and semantic retrieval."""
        return mcp_search_code(root, query, path, limit)

    @mcp.tool()
    def projectlens_ask_codebase(question: str, path: str | None = None, limit: int = 3) -> dict[str, Any]:
        """Return source-grounded evidence snippets for a codebase question without calling an LLM."""
        return mcp_ask_codebase(root, question, path, limit)

    @mcp.tool()
    def projectlens_run_checks(path: str | None = None) -> dict[str, Any]:
        """Run local project readiness checks for README, tests, packaging, secrets, gitignore, and CI."""
        return mcp_run_checks(root, path)

    @mcp.tool()
    def projectlens_run_eval(path: str | None = None, cases_path: str | None = None, limit: int = 5, run_ask: bool = True) -> dict[str, Any]:
        """Run retrieval eval cases and report whether expected files were found with source evidence."""
        return mcp_run_eval(root, path, cases_path, limit, run_ask)

    return mcp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="projectlens-mcp",
        description="Run the ProjectLens AI MCP stdio server.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Default repository root used when an MCP tool call does not provide a path.",
    )
    args = parser.parse_args(argv)

    try:
        server = create_mcp_server(Path(args.root))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1

    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())