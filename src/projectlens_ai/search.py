from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import FileRecord, ScanReport
from .index_store import load_index_report
from .scanner import SECRET_LIKE_NAMES, scan_repository


QUERY_EXPANSIONS = {
    "veritabani": {"database", "db", "sqlite", "sqlalchemy", "session", "engine", "connection", "repository", "storage"},
    "veritabanı": {"database", "db", "sqlite", "sqlalchemy", "session", "engine", "connection", "repository", "storage"},
    "baglanti": {"connection", "connect", "client", "session", "engine"},
    "bağlantı": {"connection", "connect", "client", "session", "engine"},
    "giris": {"entrypoint", "main", "app", "server", "api", "start"},
    "giriş": {"entrypoint", "main", "app", "server", "api", "start"},
    "oturum": {"login", "auth", "authenticate", "authentication", "password", "token", "session"},
    "kimlik": {"auth", "authenticate", "authentication", "identity", "token", "user"},
    "kullanici": {"user", "account", "profile"},
    "kullanıcı": {"user", "account", "profile"},
    "test": {"test", "pytest", "unittest", "spec"},
    "ayar": {"config", "settings", "env", "environment"},
    "konfigurasyon": {"config", "settings", "env", "environment"},
    "api": {"api", "route", "router", "endpoint", "controller"},
}


@dataclass(frozen=True)
class SearchResult:
    path: str
    score: float
    role: str
    reasons: tuple[str, ...]


def search_repository(root: str | Path, query: str, *, limit: int = 10) -> list[SearchResult]:
    report = scan_repository(root)
    return search_report(report, query, limit=limit)

def search_index(root: str | Path, query: str, *, limit: int = 10) -> list[SearchResult]:
    report = load_index_report(root)
    return search_report(report, query, limit=limit)

def search_report(report: ScanReport, query: str, *, limit: int = 10) -> list[SearchResult]:
    root_path = Path(report.root)
    query_terms = _expand_terms(_tokenize(query))
    if not query_terms:
        return []

    results: list[SearchResult] = []
    for file in report.files:
        if file.role == "secret-like":
            continue

        score = 0.0
        reasons: list[str] = []
        path_score = _score_path(file, query_terms)
        if path_score:
            score += path_score
            reasons.append(f"path match +{path_score:.1f}")

        symbol_score, symbol_names = _score_symbols(report, file.path, query_terms)
        if symbol_score:
            score += symbol_score
            reasons.append(f"symbol match {', '.join(symbol_names[:3])} +{symbol_score:.1f}")

        content_score = _score_content(root_path, file, query_terms)
        if content_score:
            score += content_score
            reasons.append(f"content match +{content_score:.1f}")

        role_score = _score_role(file, query_terms)
        if role_score:
            score += role_score
            reasons.append(f"role hint {file.role} +{role_score:.1f}")

        if file.role == "test" and not _is_test_query(query_terms):
            score *= 0.5
            reasons.append("test file downrank -50%")

        if file.role == "documentation" and not _is_documentation_query(query_terms):
            score *= 0.6
            reasons.append("documentation downrank -40%")

        if score >= 1.0:
            results.append(SearchResult(path=file.path, score=round(score, 2), role=file.role, reasons=tuple(reasons)))

    results.sort(key=lambda item: (-item.score, item.path))
    return results[:limit]


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[\w]+", text, flags=re.UNICODE) if len(token) > 1}


def _expand_terms(terms: set[str]) -> set[str]:
    expanded = set(terms)
    for term in terms:
        expanded.update(QUERY_EXPANSIONS.get(term, set()))
    return expanded


def _score_path(file: FileRecord, terms: set[str]) -> float:
    path = file.path.lower()
    path_tokens = _tokenize(path.replace("/", " ").replace("_", " ").replace("-", " "))
    exact = terms.intersection(path_tokens)
    partial = {term for term in terms if term in path and term not in exact}
    return len(exact) * 5.0 + len(partial) * 2.0


def _score_symbols(report: ScanReport, path: str, terms: set[str]) -> tuple[float, list[str]]:
    matches: list[str] = []
    score = 0.0
    for symbol in report.symbols:
        if symbol.path != path:
            continue
        symbol_tokens = _tokenize(symbol.name.replace("_", " "))
        if terms.intersection(symbol_tokens) or any(term in symbol.name.lower() for term in terms):
            matches.append(symbol.name)
            score += 6.0 if symbol.kind in {"function", "async_function", "component", "hook"} else 5.0
    return min(score, 24.0), matches


def _score_content(root: Path, file: FileRecord, terms: set[str]) -> float:
    if file.role == "license" and not terms.intersection({"license", "mit", "copyright"}):
        return 0.0
    if file.path.rsplit("/", maxsplit=1)[-1] in SECRET_LIKE_NAMES:
        return 0.0
    path = root / file.path
    try:
        text = path.read_text(encoding="utf-8-sig").lower()
    except (UnicodeDecodeError, OSError):
        return 0.0

    score = 0.0
    for term in terms:
        count = text.count(term.lower())
        if count:
            score += min(count, 5) * 1.2
    score = min(score, 18.0)
    if file.role == "other":
        score *= 0.25
    return score


def _is_test_query(terms: set[str]) -> bool:
    return bool(terms.intersection({"test", "pytest", "unittest", "spec"}))

def _is_documentation_query(terms: set[str]) -> bool:
    return bool(terms.intersection({"readme", "docs", "documentation", "project", "proje", "what", "ne", "install", "kurulum"}))

def _score_role(file: FileRecord, terms: set[str]) -> float:
    role_terms = {
        "documentation": {"readme", "docs", "documentation", "kurulum", "install"},
        "test": {"test", "pytest", "unittest", "spec"},
        "dependency-or-config": {"dependency", "config", "settings", "ayar", "env", "package", "requirements"},
        "ci": {"ci", "workflow", "github", "action"},
    }
    if terms.intersection(role_terms.get(file.role, set())):
        return 3.0
    return 0.0
