from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .ask import build_source_grounded_answer
from .checks import run_project_checks
from .eval import load_eval_suite, resolve_eval_cases_path, run_eval
from .hybrid_search import search_hybrid_index
from .index_store import build_index, load_index_stats
from .scanner import scan_repository


def resolve_tool_root(default_root: str | Path, path: str | None = None) -> Path:
    selected = path if path else default_root
    return Path(selected).expanduser().resolve()


def mcp_scan_repository(default_root: str | Path, path: str | None = None) -> dict[str, Any]:
    root = resolve_tool_root(default_root, path)
    report = scan_repository(root)
    return {
        "ok": True,
        "root": report.root,
        "files": report.file_count,
        "symbols": report.symbol_count,
        "technologies": report.technologies,
        "entrypoints": report.entrypoints,
        "warnings": report.warnings,
        "language_capabilities": [asdict(capability) for capability in report.language_capabilities],
        "sample_files": [file.path for file in report.files[:10]],
        "sample_symbols": [
            {"name": symbol.name, "kind": symbol.kind, "path": symbol.path, "line": symbol.line}
            for symbol in report.symbols[:10]
        ],
    }


def mcp_language_capabilities(default_root: str | Path, path: str | None = None) -> dict[str, Any]:
    root = resolve_tool_root(default_root, path)
    report = scan_repository(root)
    return {
        "ok": True,
        "root": report.root,
        "technologies": report.technologies,
        "entrypoints": report.entrypoints,
        "language_capabilities": [asdict(capability) for capability in report.language_capabilities],
        "warnings": report.warnings,
    }


def mcp_repository_overview(
    default_root: str | Path,
    path: str | None = None,
    build_index_if_missing: bool = True,
    include_checks: bool = True,
) -> dict[str, Any]:
    root = resolve_tool_root(default_root, path)
    report = scan_repository(root)
    stats_before = load_index_stats(root)
    index_built = False
    stats = stats_before
    if build_index_if_missing and stats is None:
        stats = build_index(root)
        index_built = True

    checks_payload: dict[str, Any] | None = None
    if include_checks:
        checks = run_project_checks(root)
        checks_payload = {
            "ok": checks.is_passing,
            "summary": {
                "pass": checks.pass_count,
                "warn": checks.warn_count,
                "fail": checks.fail_count,
                "info": checks.info_count,
            },
            "findings": [
                {
                    "code": result.code,
                    "status": result.status,
                    "title": result.title,
                    "message": result.message,
                    "paths": list(result.paths),
                }
                for result in checks.results
                if result.status in {"fail", "warn"}
            ][:8],
        }

    return {
        "ok": True,
        "root": report.root,
        "answer_policy": "No LLM was called. This is a compact repository overview for an MCP client.",
        "summary": {
            "files": report.file_count,
            "symbols": report.symbol_count,
            "imports": len(report.imports),
            "technologies": report.technologies,
            "entrypoints": report.entrypoints,
            "warnings": report.warnings,
        },
        "index": _overview_index_payload(stats, stats_before is not None, index_built),
        "checks": checks_payload,
        "language_capabilities": [asdict(capability) for capability in report.language_capabilities],
        "important_files": _overview_important_files(report),
        "suggested_follow_up_queries": _overview_follow_up_queries(report),
        "usage_hint": (
            "Use this overview first, then call projectlens_search_code or projectlens_ask_codebase "
            "with focused technical English queries when the user asks deeper questions."
        ),
    }


def mcp_index_repository(default_root: str | Path, path: str | None = None) -> dict[str, Any]:
    root = resolve_tool_root(default_root, path)
    stats = build_index(root)
    return {
        "ok": True,
        "root": stats.root,
        "index_path": stats.index_path,
        "files": stats.file_count,
        "symbols": stats.symbol_count,
        "imports": stats.import_count,
        "chunks": stats.chunk_count,
        "embeddings": stats.embedding_count,
        "technologies": list(stats.technologies),
        "warnings": list(stats.warnings),
    }


def mcp_status(default_root: str | Path, path: str | None = None) -> dict[str, Any]:
    root = resolve_tool_root(default_root, path)
    stats = load_index_stats(root)
    if stats is None:
        return {"ok": True, "indexed": False, "root": str(root), "message": "Run projectlens_index_repository first."}
    return {
        "ok": True,
        "indexed": True,
        "root": stats.root,
        "index_path": stats.index_path,
        "schema_version": stats.schema_version,
        "files": stats.file_count,
        "symbols": stats.symbol_count,
        "imports": stats.import_count,
        "chunks": stats.chunk_count,
        "embeddings": stats.embedding_count,
        "technologies": list(stats.technologies),
    }


def mcp_search_code(default_root: str | Path, query: str, path: str | None = None, limit: int = 5) -> dict[str, Any]:
    root = resolve_tool_root(default_root, path)
    try:
        response = search_hybrid_index(root, query, limit=limit)
    except FileNotFoundError as error:
        return {"ok": False, "error": str(error), "hint": "Run projectlens_index_repository first."}
    return {
        "ok": True,
        "query": query,
        "root": str(root),
        "semantic_used": response.semantic_used,
        "semantic_error": response.semantic_error,
        "results": [
            {
                "path": result.path,
                "role": result.role,
                "score": result.score,
                "lexical_score": result.lexical_score,
                "semantic_score": result.semantic_score,
                "semantic_location": result.semantic_location,
                "semantic_label": result.semantic_label,
                "reasons": list(result.reasons),
            }
            for result in response.results
        ],
    }


def mcp_ask_codebase(default_root: str | Path, question: str, path: str | None = None, limit: int = 3) -> dict[str, Any]:
    root = resolve_tool_root(default_root, path)
    try:
        result = build_source_grounded_answer(root, question, limit=limit)
    except FileNotFoundError as error:
        return {"ok": False, "error": str(error), "hint": "Run projectlens_index_repository first."}
    return {
        "ok": True,
        "question": question,
        "root": result.root,
        "semantic_used": result.semantic_used,
        "semantic_error": result.semantic_error,
        "snippets": [
            {
                "path": snippet.path,
                "role": snippet.role,
                "label": snippet.label,
                "start_line": snippet.start_line,
                "end_line": snippet.end_line,
                "score": snippet.score,
                "lexical_score": snippet.lexical_score,
                "semantic_score": snippet.semantic_score,
                "lines": [{"line": line_number, "text": text} for line_number, text in snippet.lines],
            }
            for snippet in result.snippets
        ],
        "answer_policy": "No LLM was called. This is source-grounded evidence only.",
    }


def mcp_run_checks(default_root: str | Path, path: str | None = None) -> dict[str, Any]:
    root = resolve_tool_root(default_root, path)
    report = run_project_checks(root)
    return {
        "ok": report.is_passing,
        "root": report.root,
        "summary": {
            "pass": report.pass_count,
            "warn": report.warn_count,
            "fail": report.fail_count,
            "info": report.info_count,
        },
        "results": [
            {
                "code": result.code,
                "status": result.status,
                "title": result.title,
                "message": result.message,
                "paths": list(result.paths),
            }
            for result in report.results
        ],
    }

def mcp_run_eval(
    default_root: str | Path,
    path: str | None = None,
    cases_path: str | None = None,
    limit: int = 5,
    run_ask: bool = True,
) -> dict[str, Any]:
    root = resolve_tool_root(default_root, path)
    resolved_cases = resolve_eval_cases_path(root, cases_path)
    if not resolved_cases.exists():
        return {
            "ok": False,
            "root": str(root),
            "error": f"Eval cases file was not found: {resolved_cases}",
            "hint": "Eval needs a JSON answer key with query and expected_paths cases.",
        }
    try:
        suite = load_eval_suite(resolved_cases)
        report = run_eval(root, suite, limit=limit, run_ask=run_ask)
    except (ValueError, FileNotFoundError) as error:
        return {"ok": False, "root": str(root), "error": str(error)}
    payload = report.as_dict()
    payload["ok"] = report.is_passing
    payload["cases_path"] = str(resolved_cases)
    return payload

def _overview_index_payload(stats, indexed_before: bool, built_now: bool) -> dict[str, Any]:
    if stats is None:
        return {
            "indexed": False,
            "indexed_before": indexed_before,
            "built_now": built_now,
            "message": "Index was not built. Call projectlens_index_repository before search or ask.",
        }
    return {
        "indexed": True,
        "indexed_before": indexed_before,
        "built_now": built_now,
        "index_path": stats.index_path,
        "schema_version": stats.schema_version,
        "files": stats.file_count,
        "symbols": stats.symbol_count,
        "imports": stats.import_count,
        "chunks": stats.chunk_count,
        "embeddings": stats.embedding_count,
    }


def _overview_important_files(report) -> list[dict[str, Any]]:
    priority_names = {
        "readme.md",
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "dockerfile",
        "docker-compose.yml",
        "compose.yml",
        "tsconfig.json",
        "vite.config.ts",
        "next.config.js",
        "playwright.config.ts",
    }
    selected = []
    seen: set[str] = set()
    for file in report.files:
        name = Path(file.path).name.lower()
        if name in priority_names or file.path in report.entrypoints:
            selected.append(file)
            seen.add(file.path)
    for role in ("source", "test", "documentation", "config"):
        for file in report.files:
            if file.path not in seen and file.role == role:
                selected.append(file)
                seen.add(file.path)
                break
    return [
        {"path": file.path, "role": file.role, "suffix": file.suffix, "size_bytes": file.size_bytes}
        for file in selected[:12]
    ]


def _overview_follow_up_queries(report) -> list[str]:
    queries = [
        "project purpose README usage architecture",
        "CLI entrypoint main workflow command options",
        "configuration settings environment variables",
        "tests CI scripts quality checks",
    ]
    technologies = {technology.lower() for technology in report.technologies}
    if "python" in technologies:
        queries.append("Python package entrypoints pyproject src layout")
    if "javascript" in technologies or "typescript" in technologies or "node.js" in technologies:
        queries.append("package.json scripts TypeScript source entrypoint")
    if "playwright" in technologies:
        queries.append("Playwright test generation browser automation config")
    if "github actions" in technologies:
        queries.append("GitHub Actions CI workflow test command")
    return queries[:8]
