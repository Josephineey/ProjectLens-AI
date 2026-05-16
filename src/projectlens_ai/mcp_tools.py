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
