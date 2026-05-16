from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .ask import build_source_grounded_answer
from .config import load_config
from .embeddings import EmbeddingBackend, EmbeddingUnavailable, create_embedding_backend
from .hybrid_search import search_hybrid_index
from .index_store import build_index, load_index_stats
from .language_support import language_for_path
from .scanner import scan_repository


@dataclass(frozen=True)
class EvalCase:
    id: str
    query: str
    expected_paths: tuple[str, ...]
    top_k: int = 5
    require_ask_source: bool = True


@dataclass(frozen=True)
class EvalSuite:
    name: str
    cases: tuple[EvalCase, ...]


@dataclass(frozen=True)
class EvalCaseResult:
    id: str
    query: str
    expected_paths: tuple[str, ...]
    top_k: int
    passed: bool
    confidence: str
    search_rank: int | None
    ask_source_found: bool | None
    result_paths: tuple[str, ...]
    source_paths: tuple[str, ...]
    support_levels: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class EvalReport:
    root: str
    suite_name: str
    total: int
    passed: int
    failed: int
    score: float
    index_created: bool
    semantic_used_count: int
    results: tuple[EvalCaseResult, ...]

    @property
    def is_passing(self) -> bool:
        return self.failed == 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_eval_cases_path(root: str | Path) -> Path:
    return Path(root).expanduser().resolve() / "docs" / "eval" / "projectlens-self.json"


def load_eval_suite(path: str | Path) -> EvalSuite:
    suite_path = Path(path).expanduser().resolve()
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    name = str(data.get("name") or suite_path.stem)
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Eval suite must contain a non-empty 'cases' list.")

    cases: list[EvalCase] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("Each eval case must be an object.")
        case_id = str(raw_case.get("id") or "").strip()
        query = str(raw_case.get("query") or "").strip()
        expected_paths = raw_case.get("expected_paths")
        if not case_id:
            raise ValueError("Eval case is missing 'id'.")
        if not query:
            raise ValueError(f"Eval case '{case_id}' is missing 'query'.")
        if not isinstance(expected_paths, list) or not expected_paths:
            raise ValueError(f"Eval case '{case_id}' must define non-empty 'expected_paths'.")
        cases.append(
            EvalCase(
                id=case_id,
                query=query,
                expected_paths=tuple(str(path).replace("\\", "/") for path in expected_paths),
                top_k=int(raw_case.get("top_k") or 5),
                require_ask_source=bool(raw_case.get("require_ask_source", True)),
            )
        )
    return EvalSuite(name=name, cases=tuple(cases))


def resolve_eval_cases_path(root: str | Path, cases_path: str | Path | None) -> Path:
    root_path = Path(root).expanduser().resolve()
    if cases_path is None:
        return default_eval_cases_path(root_path)
    path = Path(cases_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    root_relative = (root_path / path).resolve()
    if root_relative.exists():
        return root_relative
    return path.resolve()


def run_eval(
    root: str | Path,
    suite: EvalSuite,
    *,
    limit: int = 5,
    run_ask: bool = True,
) -> EvalReport:
    root_path = Path(root).expanduser().resolve()
    index_created = False
    if load_index_stats(root_path) is None:
        build_index(root_path)
        index_created = True

    report = scan_repository(root_path)
    stats = load_index_stats(root_path)
    shared_backend = _create_shared_backend(root_path) if stats and stats.embedding_count else None
    capability_by_language = {capability.language: capability for capability in report.language_capabilities}

    results: list[EvalCaseResult] = []
    semantic_used_count = 0
    for case in suite.cases:
        top_k = max(1, case.top_k or limit or 5)
        response = search_hybrid_index(root_path, case.query, limit=top_k, backend=shared_backend)
        if response.semantic_used:
            semantic_used_count += 1
        result_paths = tuple(result.path for result in response.results)
        search_rank = _first_expected_rank(result_paths, case.expected_paths)

        ask_source_found: bool | None = None
        source_paths: tuple[str, ...] = ()
        if run_ask:
            ask_result = build_source_grounded_answer(root_path, case.query, limit=top_k, backend=shared_backend)
            source_paths = tuple(snippet.path for snippet in ask_result.snippets)
            ask_source_found = _contains_expected(source_paths, case.expected_paths)

        passed = search_rank is not None
        if run_ask and case.require_ask_source:
            passed = passed and bool(ask_source_found)

        support_levels = _support_levels_for_expected_paths(case.expected_paths, capability_by_language)
        notes = _case_notes(response.semantic_used, response.semantic_error, support_levels, index_created)
        results.append(
            EvalCaseResult(
                id=case.id,
                query=case.query,
                expected_paths=case.expected_paths,
                top_k=top_k,
                passed=passed,
                confidence=_confidence_label(search_rank, ask_source_found, support_levels, run_ask),
                search_rank=search_rank,
                ask_source_found=ask_source_found,
                result_paths=result_paths,
                source_paths=source_paths,
                support_levels=support_levels,
                notes=notes,
            )
        )

    passed_count = sum(1 for result in results if result.passed)
    total = len(results)
    score = round(passed_count / total, 4) if total else 0.0
    return EvalReport(
        root=str(root_path),
        suite_name=suite.name,
        total=total,
        passed=passed_count,
        failed=total - passed_count,
        score=score,
        index_created=index_created,
        semantic_used_count=semantic_used_count,
        results=tuple(results),
    )



def _create_shared_backend(root: Path) -> EmbeddingBackend | None:
    try:
        config = load_config(root)
        return create_embedding_backend(config.embedding, allow_download=False)
    except EmbeddingUnavailable:
        return None
def _first_expected_rank(result_paths: tuple[str, ...], expected_paths: tuple[str, ...]) -> int | None:
    expected = set(expected_paths)
    for index, path in enumerate(result_paths, start=1):
        if path in expected:
            return index
    return None


def _contains_expected(paths: tuple[str, ...], expected_paths: tuple[str, ...]) -> bool:
    return bool(set(paths).intersection(expected_paths))


def _support_levels_for_expected_paths(
    expected_paths: tuple[str, ...],
    capability_by_language: dict[str, Any],
) -> tuple[str, ...]:
    levels: list[str] = []
    for path in expected_paths:
        language = language_for_path(path)
        if language is None:
            levels.append("unknown")
            continue
        capability = capability_by_language.get(language)
        levels.append(capability.support_level if capability else "unknown")
    return tuple(levels)


def _confidence_label(
    search_rank: int | None,
    ask_source_found: bool | None,
    support_levels: tuple[str, ...],
    run_ask: bool,
) -> str:
    if search_rank is None:
        return "low"
    has_fallback_expected = "fallback" in support_levels or "unknown" in support_levels
    ask_ok = True if not run_ask else bool(ask_source_found)
    if search_rank == 1 and ask_ok and not has_fallback_expected:
        return "high"
    if ask_ok or search_rank <= 3:
        return "medium"
    return "low"


def _case_notes(
    semantic_used: bool,
    semantic_error: str | None,
    support_levels: tuple[str, ...],
    index_created: bool,
) -> tuple[str, ...]:
    notes: list[str] = []
    notes.append("semantic search used" if semantic_used else "semantic search not used")
    if semantic_error:
        notes.append(semantic_error)
    if index_created:
        notes.append("local index was created for this eval run")
    if "fallback" in support_levels:
        notes.append("expected file language is fallback-only; symbol-level confidence is limited")
    if "unknown" in support_levels:
        notes.append("expected file language could not be mapped to a known capability")
    return tuple(notes)