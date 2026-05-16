from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path

from . import __version__
from .ask import build_source_grounded_answer
from .checks import run_project_checks
from .config import init_config, load_config, set_config_value
from .embedding_store import build_embedding_index, current_embedding_status, test_embedding_backend
from .embeddings import EmbeddingUnavailable
from .eval import load_eval_suite, resolve_eval_cases_path, run_eval
from .hybrid_search import search_hybrid_index
from .index_store import build_index, load_index_stats
from .packer import write_repository_pack
from .scanner import scan_repository
from .search import search_index, search_repository
from .semantic_search import search_semantic_index


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="projectlens",
        description="Local-first codebase understanding tool.",
    )
    parser.add_argument("--version", action="version", version=f"projectlens {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan a repository and print a local summary.")
    scan_parser.add_argument("path", nargs="?", default=".", help="Repository path to scan.")
    scan_parser.add_argument("--json", action="store_true", help="Print the full scan report as JSON.")
    scan_parser.set_defaults(handler=handle_scan)

    pack_parser = subparsers.add_parser("pack", help="Export an AI-friendly repository digest.")
    pack_parser.add_argument("path", nargs="?", default=".", help="Repository path to pack.")
    pack_parser.add_argument(
        "-o",
        "--output",
        default="projectlens-output.md",
        help="Markdown output file path.",
    )
    pack_parser.add_argument(
        "--no-contents",
        action="store_true",
        help="Write only repository metadata, tree, and symbols; omit file contents.",
    )
    pack_parser.add_argument(
        "--max-file-chars",
        type=int,
        default=12_000,
        help="Maximum characters to include from each file.",
    )
    pack_parser.set_defaults(handler=handle_pack)

    index_parser = subparsers.add_parser("index", help="Build a local SQLite index for a repository.")
    index_parser.add_argument("path", nargs="?", default=".", help="Repository path to index.")
    index_parser.add_argument("--db", help="Optional custom SQLite index path.")
    index_parser.set_defaults(handler=handle_index)

    status_parser = subparsers.add_parser("status", help="Show repository index status.")
    status_parser.add_argument("path", nargs="?", default=".", help="Repository path to inspect.")
    status_parser.add_argument("--db", help="Optional custom SQLite index path.")
    status_parser.set_defaults(handler=handle_status)
    capabilities_parser = subparsers.add_parser("capabilities", help="Show language parser coverage and fallback status.")
    capabilities_parser.add_argument("path", nargs="?", default=".", help="Repository path to inspect.")
    capabilities_parser.add_argument("--json", action="store_true", help="Print capability report as JSON.")
    capabilities_parser.set_defaults(handler=handle_capabilities)

    search_parser = subparsers.add_parser("search", help="Find repository files or chunks related to a query.")
    search_parser.add_argument("query", help="Natural-language search query.")
    search_parser.add_argument("path", nargs="?", default=".", help="Repository path to search.")
    search_parser.add_argument("--limit", type=int, default=10, help="Maximum number of results to print.")
    search_parser.add_argument("--indexed", action="store_true", help="Use the saved SQLite index instead of live scanning.")
    search_parser.add_argument("--semantic", action="store_true", help="Use stored embedding vectors for semantic search.")
    search_parser.add_argument("--hybrid", action="store_true", help="Combine keyword/symbol/path search with semantic embedding results.")
    search_parser.set_defaults(handler=handle_search)

    ask_parser = subparsers.add_parser("ask", help="Show source-grounded evidence for a repository question.")
    ask_parser.add_argument("query", help="Natural-language repository question.")
    ask_parser.add_argument("path", nargs="?", default=".", help="Repository path to inspect.")
    ask_parser.add_argument("--limit", type=int, default=3, help="Maximum number of evidence snippets to print.")
    ask_parser.add_argument("--context-lines", type=int, default=3, help="Lines of context around each selected chunk.")
    ask_parser.set_defaults(handler=handle_ask)

    embed_parser = subparsers.add_parser("embed", help="Manage embedding availability and semantic index data.")
    embed_subparsers = embed_parser.add_subparsers(dest="embed_command", required=True)

    embed_status_parser = embed_subparsers.add_parser("status", help="Show embedding backend status.")
    embed_status_parser.add_argument("path", nargs="?", default=".", help="Repository path.")
    embed_status_parser.set_defaults(handler=handle_embed_status)

    embed_test_parser = embed_subparsers.add_parser("test", help="Load the embedding backend and embed one small probe text.")
    embed_test_parser.add_argument("path", nargs="?", default=".", help="Repository path.")
    embed_test_parser.add_argument(
        "--download-model",
        action="store_true",
        help="Allow the local embedding backend to download the configured model if it is not cached yet.",
    )
    embed_test_parser.set_defaults(handler=handle_embed_test)

    embed_build_parser = embed_subparsers.add_parser("build", help="Build embeddings for indexed code chunks.")
    embed_build_parser.add_argument("path", nargs="?", default=".", help="Repository path.")
    embed_build_parser.add_argument("--batch-size", type=int, default=16, help="Embedding batch size.")
    embed_build_parser.add_argument("--limit", type=int, help="Embed only the first N chunks; useful for smoke tests.")
    embed_build_parser.add_argument(
        "--download-model",
        action="store_true",
        help="Allow the local embedding backend to download the configured model if it is not cached yet.",
    )
    embed_build_parser.set_defaults(handler=handle_embed_build)

    config_parser = subparsers.add_parser("config", help="Manage ProjectLens configuration.")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)

    config_init_parser = config_subparsers.add_parser("init", help="Create .projectlens/config.toml with defaults.")
    config_init_parser.add_argument("path", nargs="?", default=".", help="Repository path.")
    config_init_parser.add_argument("--force", action="store_true", help="Overwrite existing config file.")
    config_init_parser.set_defaults(handler=handle_config_init)

    config_show_parser = config_subparsers.add_parser("show", help="Show effective ProjectLens config.")
    config_show_parser.add_argument("path", nargs="?", default=".", help="Repository path.")
    config_show_parser.set_defaults(handler=handle_config_show)

    config_set_parser = config_subparsers.add_parser("set", help="Set one config value.")
    config_set_parser.add_argument("key", help="Config key, for example embedding.backend.")
    config_set_parser.add_argument("value", help="Config value.")
    config_set_parser.add_argument("path", nargs="?", default=".", help="Repository path.")
    config_set_parser.set_defaults(handler=handle_config_set)

    checks_parser = subparsers.add_parser("checks", help="Run local project quality and GitHub readiness checks.")
    checks_parser.add_argument("path", nargs="?", default=".", help="Repository path to check.")
    checks_parser.add_argument("--json", action="store_true", help="Print check results as JSON.")
    checks_parser.set_defaults(handler=handle_checks)
    eval_parser = subparsers.add_parser("eval", help="Run retrieval quality eval cases for a repository.")
    eval_parser.add_argument("path", nargs="?", default=".", help="Repository path to evaluate.")
    eval_parser.add_argument("--cases", help="Eval cases JSON file. Defaults to docs/eval/projectlens-self.json under the repo.")
    eval_parser.add_argument("--limit", type=int, default=5, help="Default top-k search limit for cases without top_k.")
    eval_parser.add_argument("--no-ask", action="store_true", help="Evaluate search ranking only; skip ask source checks.")
    eval_parser.add_argument("--fail-under", type=float, default=1.0, help="Exit with failure if score is below this value.")
    eval_parser.add_argument("--json", action="store_true", help="Print eval report as JSON.")
    eval_parser.set_defaults(handler=handle_eval)

    prompts_parser = subparsers.add_parser("prompts", help="Show good questions to ask about a repository.")
    prompts_parser.add_argument("--type", choices=["generic", "python", "fastapi", "react"], default="generic")
    prompts_parser.set_defaults(handler=handle_prompts)

    doctor_parser = subparsers.add_parser("doctor", help="Show ProjectLens capability status.")
    doctor_parser.add_argument("path", nargs="?", default=".", help="Repository path to inspect.")
    doctor_parser.set_defaults(handler=handle_doctor)

    return parser


def handle_scan(args: argparse.Namespace) -> int:
    report = scan_repository(Path(args.path))
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        return 0

    print(f"ProjectLens scan: {report.root}")
    print()
    print(f"Files indexed: {report.file_count}")
    print(f"Total size: {_format_bytes(report.total_size_bytes)}")
    print(f"Symbols found: {report.symbol_count}")
    print(f"Technologies: {', '.join(report.technologies) if report.technologies else 'unknown'}")
    print(f"Entrypoints: {', '.join(report.entrypoints) if report.entrypoints else 'not detected'}")
    print()

    _print_language_capabilities(report)
    _print_top_files(report)
    _print_top_symbols(report)

    if report.warnings:
        print("Warnings:")
        for warning in report.warnings:
            print(f"  - {warning}")
        print()

    print("Next steps:")
    print('  projectlens search "database connection" .')
    print("  projectlens capabilities .")
    print("  projectlens eval .")
    print("  projectlens prompts")
    print("  projectlens doctor .")
    return 0


def handle_pack(args: argparse.Namespace) -> int:
    output = write_repository_pack(
        Path(args.path),
        Path(args.output),
        max_file_chars=args.max_file_chars,
        include_contents=not args.no_contents,
    )
    print(f"Repository pack written: {output}")
    print()
    print("Use this file when you want to give another AI assistant structured repository context.")
    return 0


def handle_index(args: argparse.Namespace) -> int:
    stats = build_index(Path(args.path), index_path=Path(args.db) if args.db else None)
    print(f"ProjectLens index written: {stats.index_path}")
    print()
    print(f"Root: {stats.root}")
    print(f"Files indexed: {stats.file_count}")
    print(f"Symbols indexed: {stats.symbol_count}")
    print(f"Imports indexed: {stats.import_count}")
    print(f"Chunks indexed: {stats.chunk_count}")
    print(f"Embeddings indexed: {stats.embedding_count}")
    print(f"Technologies: {', '.join(stats.technologies) if stats.technologies else 'unknown'}")
    print(f"Created at UTC: {stats.created_at_utc}")
    if stats.warnings:
        print()
        print("Warnings:")
        for warning in stats.warnings:
            print(f"  - {warning}")
    return 0


def handle_status(args: argparse.Namespace) -> int:
    stats = load_index_stats(Path(args.path), index_path=Path(args.db) if args.db else None)
    if stats is None:
        print("ProjectLens index: not found")
        print()
        print("Run this command first:")
        print("  projectlens index .")
        return 0

    print("ProjectLens index: OK")
    print()
    print(f"Index path: {stats.index_path}")
    print(f"Root: {stats.root}")
    print(f"Schema version: {stats.schema_version}")
    print(f"Created at UTC: {stats.created_at_utc}")
    print(f"Files indexed: {stats.file_count}")
    print(f"Symbols indexed: {stats.symbol_count}")
    print(f"Imports indexed: {stats.import_count}")
    print(f"Chunks indexed: {stats.chunk_count}")
    print(f"Embeddings indexed: {stats.embedding_count}")
    print(f"Technologies: {', '.join(stats.technologies) if stats.technologies else 'unknown'}")
    return 0


def handle_search(args: argparse.Namespace) -> int:
    if args.semantic and args.hybrid:
        print("Choose only one search mode: --semantic or --hybrid.")
        return 2

    if args.hybrid:
        try:
            response = search_hybrid_index(Path(args.path), args.query, limit=args.limit)
        except FileNotFoundError as error:
            print(str(error))
            print()
            print("Run this command first:")
            print("  projectlens index .")
            return 1

        print(f"ProjectLens search: {args.query}")
        print("Search mode: hybrid keyword + symbol + path + semantic")
        print("Index source: saved SQLite index")
        print(f"Semantic: {'used' if response.semantic_used else 'not used'}")
        if response.semantic_error:
            print(f"Semantic note: {response.semantic_error}")
        print()
        if not response.results:
            print("No matching files found.")
            return 0
        for index, result in enumerate(response.results, start=1):
            print(
                f"{index}. {result.path} ({result.role}) "
                f"score={result.score:.4f} lexical={result.lexical_score:.4f} semantic={result.semantic_score:.4f}"
            )
            if result.semantic_location and result.semantic_label:
                print(f"   - best semantic chunk: {result.semantic_label} at {result.semantic_location}")
            for reason in result.reasons[:4]:
                print(f"   - {reason}")
        return 0

    if args.semantic:
        try:
            semantic_results = search_semantic_index(Path(args.path), args.query, limit=args.limit)
        except (EmbeddingUnavailable, FileNotFoundError) as error:
            print(f"Semantic search is not ready: {error}")
            print()
            print("Useful commands:")
            print("  projectlens index .")
            print("  projectlens embed test .")
            print("  projectlens embed build .")
            return 1

        print(f"ProjectLens search: {args.query}")
        print("Search mode: semantic embeddings")
        print("Index source: saved SQLite index")
        print()
        if not semantic_results:
            print("No matching chunks found.")
            return 0
        for index, result in enumerate(semantic_results, start=1):
            location = f"{result.path}:{result.start_line}-{result.end_line}"
            print(f"{index}. {location} ({result.role}, {result.chunk_kind}) score={result.score:.4f}")
            print(f"   - {result.label}")
        return 0

    try:
        results = search_index(Path(args.path), args.query, limit=args.limit) if args.indexed else search_repository(Path(args.path), args.query, limit=args.limit)
    except FileNotFoundError as error:
        print(str(error))
        print()
        print("Run this command first:")
        print("  projectlens index .")
        return 1

    print(f"ProjectLens search: {args.query}")
    print("Search mode: keyword + symbol + path")
    print(f"Index source: {'saved SQLite index' if args.indexed else 'live scan'}")
    print("Embedding: not used")
    print()

    if not results:
        print("No matching files found.")
        return 0

    for index, result in enumerate(results, start=1):
        print(f"{index}. {result.path} ({result.role}) score={result.score}")
        for reason in result.reasons:
            print(f"   - {reason}")
    return 0


def handle_ask(args: argparse.Namespace) -> int:
    try:
        result = build_source_grounded_answer(
            Path(args.path),
            args.query,
            limit=args.limit,
            context_lines=args.context_lines,
        )
    except FileNotFoundError as error:
        print(str(error))
        print()
        print("Run this command first:")
        print("  projectlens index .")
        return 1

    print(f"ProjectLens ask: {result.query}")
    print("Mode: source-grounded evidence, no LLM answer generation")
    print(f"Semantic: {'used' if result.semantic_used else 'not used'}")
    if result.semantic_error:
        print(f"Semantic note: {result.semantic_error}")
    print()

    if not result.snippets:
        print("No source evidence found.")
        return 0

    print("Evidence:")
    for index, snippet in enumerate(result.snippets, start=1):
        location = f"{snippet.path}:{snippet.start_line}-{snippet.end_line}"
        print(
            f"{index}. {location} ({snippet.role}) "
            f"score={snippet.score:.4f} lexical={snippet.lexical_score:.4f} semantic={snippet.semantic_score:.4f}"
        )
        if snippet.label:
            print(f"   label: {snippet.label}")
        for line_number, line in snippet.lines:
            print(f"   {line_number:>4} | {line}")
        print()

    print("Answer policy: ProjectLens has not called an LLM here; it is showing grounded source evidence only.")
    return 0

def handle_embed_status(args: argparse.Namespace) -> int:
    status = current_embedding_status(Path(args.path))
    _print_embedding_status(status)
    return 0


def handle_embed_test(args: argparse.Namespace) -> int:
    try:
        result = test_embedding_backend(
            Path(args.path),
            allow_download=args.download_model,
            progress=_print_progress,
        )
    except EmbeddingUnavailable as error:
        status = current_embedding_status(Path(args.path))
        print("Embedding backend test failed.")
        print(f"Reason: {error}")
        print(f"Install hint: {status.install_hint}")
        if status.backend == "local" and not args.download_model:
            print("Download hint: projectlens embed test . --download-model")
        return 1

    print("ProjectLens embedding probe: OK")
    print()
    print(f"Backend: {result.backend}")
    print(f"Model: {result.model}")
    print(f"Vector dimensions: {result.vector_dimensions}")
    return 0


def handle_embed_build(args: argparse.Namespace) -> int:
    try:
        result = build_embedding_index(
            Path(args.path),
            batch_size=args.batch_size,
            limit=args.limit,
            allow_download=args.download_model,
            progress=_print_progress,
        )
    except (EmbeddingUnavailable, ValueError) as error:
        status = current_embedding_status(Path(args.path))
        print("Embedding backend is not ready.")
        print(f"Reason: {error}")
        print(f"Install hint: {status.install_hint}")
        if status.backend == "local" and not args.download_model:
            print("Download hint: projectlens embed test . --download-model")
        return 1

    print("ProjectLens embeddings written")
    print()
    print(f"Index path: {result.index_path}")
    print(f"Backend: {result.backend}")
    print(f"Model: {result.model}")
    print(f"Chunks: {result.chunk_count}")
    print(f"Embeddings written: {result.embedding_count}")
    return 0


def handle_config_init(args: argparse.Namespace) -> int:
    config = init_config(Path(args.path), force=args.force)
    print(f"ProjectLens config written: {config.path}")
    print()
    _print_config(config)
    return 0


def handle_config_show(args: argparse.Namespace) -> int:
    config = load_config(Path(args.path))
    if not config.exists:
        print("ProjectLens config: not found; using defaults")
        print(f"Default path: {config.path}")
        print()
    else:
        print(f"ProjectLens config: {config.path}")
        print()
    _print_config(config)
    return 0


def handle_config_set(args: argparse.Namespace) -> int:
    try:
        config = set_config_value(Path(args.path), args.key, args.value)
    except ValueError as error:
        print(f"Config error: {error}")
        return 1
    print(f"ProjectLens config updated: {config.path}")
    print()
    _print_config(config)
    return 0


def handle_checks(args: argparse.Namespace) -> int:
    report = run_project_checks(Path(args.path))
    if args.json:
        print(json.dumps({
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
        }, indent=2, ensure_ascii=False))
        return 0 if report.is_passing else 1

    print("ProjectLens checks")
    print()
    print(f"Root: {report.root}")
    print(
        f"Summary: pass={report.pass_count} "
        f"warn={report.warn_count} fail={report.fail_count} info={report.info_count}"
    )
    print()
    for result in report.results:
        status = result.status.upper()
        print(f"[{status}] {result.title}: {result.message}")
        if result.paths:
            print(f"       paths: {', '.join(result.paths)}")
    print()
    if report.fail_count:
        print("Result: checks found blocking issues.")
        return 1
    if report.warn_count:
        print("Result: checks passed with warnings.")
        return 0
    print("Result: checks passed.")
    return 0

def handle_eval(args: argparse.Namespace) -> int:
    root = Path(args.path)
    cases_path = resolve_eval_cases_path(root, args.cases)
    if not cases_path.exists():
        print(f"Eval cases file was not found: {cases_path}")
        print()
        print("Eval needs an answer key: a JSON file with query and expected_paths cases.")
        print("For this project, use: projectlens eval . --cases docs/eval/projectlens-self.json")
        return 1
    try:
        suite = load_eval_suite(cases_path)
        report = run_eval(root, suite, limit=args.limit, run_ask=not args.no_ask)
    except (ValueError, FileNotFoundError) as error:
        print(f"Eval error: {error}")
        return 1

    if args.json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    else:
        print("ProjectLens eval")
        print()
        print(f"Root: {report.root}")
        print(f"Suite: {report.suite_name}")
        print(f"Score: {report.score:.2%} ({report.passed}/{report.total})")
        print(f"Semantic used in cases: {report.semantic_used_count}/{report.total}")
        if report.index_created:
            print("Index note: local index was created for this eval run.")
        print()
        for result in report.results:
            status = "PASS" if result.passed else "FAIL"
            rank = result.search_rank if result.search_rank is not None else "not found"
            ask_state = "skipped" if result.ask_source_found is None else str(result.ask_source_found).lower()
            print(f"[{status}] {result.id}: rank={rank}, ask_source={ask_state}, confidence={result.confidence}")
            print(f"       query: {result.query}")
            print(f"       expected: {', '.join(result.expected_paths)}")
            print(f"       results: {', '.join(result.result_paths[:5]) if result.result_paths else 'none'}")
            for note in result.notes[:3]:
                print(f"       note: {note}")
        print()
        print("Result: eval passed." if report.is_passing else "Result: eval found retrieval misses.")

    return 0 if report.score >= args.fail_under else 1

def handle_capabilities(args: argparse.Namespace) -> int:
    report = scan_repository(Path(args.path))
    if args.json:
        print(json.dumps({
            "root": report.root,
            "technologies": report.technologies,
            "entrypoints": report.entrypoints,
            "language_capabilities": [asdict(capability) for capability in report.language_capabilities],
            "warnings": report.warnings,
        }, indent=2, ensure_ascii=False))
        return 0

    print("ProjectLens language capabilities")
    print()
    print(f"Root: {report.root}")
    print(f"Technologies: {', '.join(report.technologies) if report.technologies else 'unknown'}")
    print()
    _print_language_capabilities(report)
    if report.warnings:
        print("Warnings:")
        for warning in report.warnings:
            print(f"  - {warning}")
        print()
    print("Interpretation:")
    print("  deep: compiler/AST-level symbol extraction")
    print("  structured: tested navigation-grade extraction for common code patterns")
    print("  fallback: file/path/keyword/embedding search works, but symbol answers may be incomplete")
    return 0

def handle_prompts(args: argparse.Namespace) -> int:
    prompts = PROMPT_COOKBOOK[args.type]
    print(f"ProjectLens prompt cookbook: {args.type}")
    print()
    for title, questions in prompts:
        print(title)
        for question in questions:
            print(f"  - {question}")
        print()
    return 0


def handle_doctor(args: argparse.Namespace) -> int:
    root = Path(args.path)
    config = load_config(root)
    status = current_embedding_status(root)
    report = scan_repository(root)
    mcp_available = importlib.util.find_spec("mcp") is not None
    print("ProjectLens doctor")
    print()
    print(f"Root: {report.root}")
    print("Scanner: OK")
    print("Python symbol parser: OK")
    print("JavaScript/TypeScript symbol parser: OK (structured)")
    print("Repository pack export: OK")
    print("SQLite index: OK")
    print("Code chunking: OK")
    print("Keyword/symbol/path search: OK")
    print("Hybrid search: OK")
    print("Source-grounded ask: OK")
    print("Checks/report: OK")
    print("Language capability report: OK")
    print(f"Config: {'OK' if config.exists else 'defaults'}")
    availability = "package available" if status.available else "package unavailable"
    print(f"Embedding backend: {config.embedding.backend} ({availability})")
    print(f"Embedding detail: {status.reason}")
    print(f"LLM provider: {config.llm.provider}")
    if mcp_available:
        print("MCP server: OK (mcp package installed)")
    else:
        print('MCP server: optional dependency missing; install with python -m pip install "projectlens-ai[mcp]"')
    print()
    _print_language_capabilities(report)
    print("Current stage: local retrieval, quality checks, MCP integration, language capability reporting, and eval.")
    return 0

def _print_language_capabilities(report) -> None:
    print("Language support:")
    if not report.language_capabilities:
        print("  - no source language files detected")
        print()
        return
    for capability in report.language_capabilities:
        print(
            f"  - {capability.language}: {capability.support_level} "
            f"({capability.confidence} confidence, files={capability.file_count}, "
            f"symbols={capability.symbol_count}, imports={capability.import_count}, parser={capability.parser})"
        )
        for note in capability.notes[:2]:
            print(f"    note: {note}")
    print()

def _print_embedding_status(status) -> None:
    print("ProjectLens embedding status")
    print()
    print(f"Backend: {status.backend}")
    print(f"Model: {status.model or 'not configured'}")
    label = "Package available" if status.backend == "local" else "Available"
    print(f"{label}: {'yes' if status.available else 'no'}")
    print(f"Reason: {status.reason}")
    print(f"Cost/privacy: {status.cost_privacy}")
    if not status.available:
        print(f"Install hint: {status.install_hint}")


def _print_config(config) -> None:
    print(f"Embedding backend: {config.embedding.backend}")
    print(f"Embedding model: {config.embedding.model or 'not configured'}")
    print(f"Embedding cost/privacy: {_embedding_hint(config.embedding.backend)}")
    print(f"LLM provider: {config.llm.provider}")
    print(f"LLM model: {config.llm.model or 'not configured'}")
    print(f"Max context tokens: {config.runtime.max_context_tokens}")
    print(f"Privacy mode: {'on' if config.runtime.privacy_mode else 'off'}")


def _embedding_hint(backend: str) -> str:
    if backend == "local":
        return "free; code stays on this machine"
    if backend == "openai":
        return "low API cost; code chunks are sent to OpenAI for embeddings"
    if backend == "disabled":
        return "free; semantic search will be unavailable"
    return "unknown backend"


def _print_progress(message: str) -> None:
    print(f"[embed] {message}", flush=True)


def _print_top_files(report) -> None:
    files = sorted(report.files, key=lambda item: (item.role != "source", item.path))[:10]
    if not files:
        return
    print("Sample files:")
    for file in files:
        print(f"  - {file.path} ({file.role}, {_format_bytes(file.size_bytes)})")
    print()


def _print_top_symbols(report) -> None:
    if not report.symbols:
        return
    print("Sample code symbols:")
    for symbol in report.symbols[:10]:
        print(f"  - {symbol.kind} {symbol.name} ({symbol.path}:{symbol.line})")
    print()


def _format_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"


PROMPT_COOKBOOK = {
    "generic": [
        (
            "Understand the project",
            [
                "What does this project do?",
                "Where should I start reading this repository?",
                "What are the most important files?",
                "What technologies does this project appear to use?",
            ],
        ),
        (
            "Find implementation details",
            [
                "Where is the application entrypoint?",
                "Where is configuration handled?",
                "Where are tests located?",
                "Which files look risky or incomplete?",
            ],
        ),
    ],
    "python": [
        (
            "Python repository questions",
            [
                "Which Python file is the main entrypoint?",
                "Which functions and classes should I read first?",
                "Where are dependencies declared?",
                "How do I run the tests?",
            ],
        )
    ],
    "fastapi": [
        (
            "FastAPI repository questions",
            [
                "Where is the FastAPI app created?",
                "Where are routes or routers defined?",
                "Where is the database session configured?",
                "Where are Pydantic models defined?",
            ],
        )
    ],
    "react": [
        (
            "React repository questions",
            [
                "Where is the root component?",
                "Where is routing configured?",
                "Where are API calls made?",
                "How is state managed?",
            ],
        )
    ],
}
