from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import LanguageCapability, ScanReport


LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".dart": "Dart",
    ".c": "C/C++",
    ".h": "C/C++",
    ".cc": "C/C++",
    ".cpp": "C/C++",
    ".cxx": "C/C++",
    ".hpp": "C/C++",
}

SOURCE_SUFFIXES = frozenset(LANGUAGE_BY_SUFFIX)
DEEP_SUPPORTED_LANGUAGES = {"Python"}
STRUCTURED_SUPPORTED_LANGUAGES = {"JavaScript", "TypeScript"}


def language_for_path(path: str | Path) -> str | None:
    suffix = Path(str(path)).suffix.lower()
    return LANGUAGE_BY_SUFFIX.get(suffix)


def is_source_suffix(suffix: str) -> bool:
    return suffix.lower() in SOURCE_SUFFIXES


def build_language_capabilities(report: ScanReport) -> list[LanguageCapability]:
    file_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    import_counts: Counter[str] = Counter()

    for file in report.files:
        language = language_for_path(file.path)
        if language is None:
            continue
        file_counts[language] += 1
        if file.role in {"source", "test"}:
            source_counts[language] += 1

    for symbol in report.symbols:
        language = language_for_path(symbol.path)
        if language:
            symbol_counts[language] += 1

    for record in report.imports:
        language = language_for_path(record.path)
        if language:
            import_counts[language] += 1

    capabilities: list[LanguageCapability] = []
    for language in sorted(file_counts):
        support_level, parser, confidence, notes = _support_details(language, symbol_counts[language])
        capabilities.append(
            LanguageCapability(
                language=language,
                file_count=file_counts[language],
                source_file_count=source_counts[language],
                symbol_count=symbol_counts[language],
                import_count=import_counts[language],
                support_level=support_level,
                parser=parser,
                confidence=confidence,
                notes=notes,
            )
        )
    return capabilities


def language_capabilities_to_dicts(capabilities: list[LanguageCapability]) -> list[dict[str, Any]]:
    return [asdict(capability) for capability in capabilities]


def fallback_languages(report: ScanReport) -> list[str]:
    return [
        capability.language
        for capability in report.language_capabilities
        if capability.support_level == "fallback"
    ]


def _support_details(language: str, symbol_count: int) -> tuple[str, str, str, tuple[str, ...]]:
    if language in DEEP_SUPPORTED_LANGUAGES:
        notes = ("AST parser extracts functions, classes, and imports.",)
        if symbol_count == 0:
            notes += ("No symbols were detected in the scanned files.",)
        return "deep", "python ast", "high", notes

    if language in STRUCTURED_SUPPORTED_LANGUAGES:
        notes = (
            "Built-in structured parser extracts common imports, functions, classes, components, hooks, types, and interfaces.",
            "Coverage is useful for codebase navigation, but not a full compiler-grade TypeScript AST.",
        )
        if symbol_count == 0:
            notes += ("No JS/TS symbols were detected; search still works through file, path, keyword, and embeddings.",)
        return "structured", "projectlens js/ts parser", "medium", notes

    return (
        "fallback",
        "file/path/keyword/embedding only",
        "low",
        (
            "Deep symbol parsing is not available for this language yet.",
            "ProjectLens can still scan, pack, search, embed, and show file-level evidence.",
        ),
    )