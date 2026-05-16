from __future__ import annotations

import ast
import os
from collections import Counter
from pathlib import Path

from .js_ts_parser import JS_TS_SUFFIXES, extract_js_ts_symbols
from .language_support import build_language_capabilities, fallback_languages, is_source_suffix
from .models import FileRecord, ImportRecord, ScanReport, SymbolRecord


DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".test-tmp",
    ".projectlens",
    "node_modules",
    "dist",
    "build",
}

DEFAULT_IGNORE_FILES = {
    "projectlens-output.md",
}

SECRET_LIKE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "secrets.json",
    "credentials.json",
}

ENTRYPOINT_NAMES = {
    "main.py",
    "app.py",
    "server.py",
    "api.py",
    "index.js",
    "index.jsx",
    "index.ts",
    "index.tsx",
    "main.js",
    "main.jsx",
    "main.ts",
    "main.tsx",
    "app.js",
    "app.jsx",
    "app.ts",
    "app.tsx",
    "server.js",
    "server.ts",
}


def scan_repository(root: str | Path) -> ScanReport:
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Repository path does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root_path}")

    report = ScanReport(root=str(root_path))
    paths = _collect_files(root_path)

    for path in paths:
        relative = _relative_path(root_path, path)
        role = _classify_file(relative)
        report.files.append(
            FileRecord(
                path=relative,
                size_bytes=path.stat().st_size,
                suffix=path.suffix.lower(),
                role=role,
            )
        )

        if path.name in SECRET_LIKE_NAMES:
            report.warnings.append(f"Secret-like file detected and not read: {relative}")
            continue

        suffix = path.suffix.lower()
        if suffix == ".py":
            symbols, imports = _extract_python_symbols(root_path, path)
            report.symbols.extend(symbols)
            report.imports.extend(imports)
        elif suffix in JS_TS_SUFFIXES:
            symbols, imports = extract_js_ts_symbols(root_path, path)
            report.symbols.extend(symbols)
            report.imports.extend(imports)

    report.technologies = _detect_technologies(root_path, report.files)
    report.entrypoints = _detect_entrypoints(report.files)
    report.language_capabilities = build_language_capabilities(report)
    report.warnings.extend(_detect_repository_warnings(report))
    return report


def _collect_files(root: Path) -> list[Path]:
    collected: list[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in DEFAULT_IGNORE_DIRS)
        current_path = Path(current)
        for file_name in sorted(files):
            path = current_path / file_name
            if _should_skip_file(path):
                continue
            collected.append(path)
    return collected


def _should_skip_file(path: Path) -> bool:
    if path.name in DEFAULT_IGNORE_FILES:
        return True
    if path.name.endswith((".pyc", ".pyo")):
        return True
    if path.stat().st_size > 1_000_000:
        return True
    return False


def _classify_file(relative_path: str) -> str:
    lowered = relative_path.lower().replace("\\", "/")
    name = lowered.rsplit("/", maxsplit=1)[-1]

    if name in SECRET_LIKE_NAMES:
        return "secret-like"
    if name in {"readme.md", "readme.rst"}:
        return "documentation"
    if lowered.startswith("docs/") and name.endswith((".md", ".rst")):
        return "documentation"
    if name in {"license", "license.md", "copying"}:
        return "license"
    if name in {"pyproject.toml", "requirements.txt", "package.json", "tsconfig.json", "vite.config.ts", "next.config.js"}:
        return "dependency-or-config"
    if _looks_like_test_path(lowered, name):
        return "test"
    if lowered.startswith(".github/"):
        return "ci"
    if is_source_suffix(Path(name).suffix):
        return "source"
    return "other"


def _looks_like_test_path(lowered: str, name: str) -> bool:
    if "/tests/" in f"/{lowered}" or "/__tests__/" in f"/{lowered}":
        return True
    if name.startswith("test_"):
        return True
    return name.endswith(
        (
            "_test.py",
            ".test.py",
            ".test.js",
            ".test.jsx",
            ".test.ts",
            ".test.tsx",
            ".spec.js",
            ".spec.jsx",
            ".spec.ts",
            ".spec.tsx",
        )
    )


def _extract_python_symbols(root: Path, path: Path) -> tuple[list[SymbolRecord], list[ImportRecord]]:
    relative = _relative_path(root, path)
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return [], []

    symbols: list[SymbolRecord] = []
    imports: list[ImportRecord] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            symbols.append(
                SymbolRecord(
                    name=node.name,
                    kind="class",
                    path=relative,
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", None),
                )
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
            symbols.append(
                SymbolRecord(
                    name=node.name,
                    kind=kind,
                    path=relative,
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", None),
                )
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportRecord(module=alias.name, path=relative, line=node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            imports.append(ImportRecord(module=module, path=relative, line=node.lineno))

    symbols.sort(key=lambda item: (item.path, item.line, item.name))
    imports.sort(key=lambda item: (item.path, item.line, item.module))
    return symbols, imports


def _detect_technologies(root: Path, files: list[FileRecord]) -> list[str]:
    paths = {file.path.lower().replace("\\", "/") for file in files}
    suffixes = {file.suffix for file in files}
    tech: set[str] = set()

    if "pyproject.toml" in paths or "requirements.txt" in paths or ".py" in suffixes:
        tech.add("Python")
    if "package.json" in paths:
        tech.add("Node.js")
    if suffixes.intersection({".js", ".jsx", ".mjs", ".cjs"}):
        tech.add("JavaScript")
    if "tsconfig.json" in paths or suffixes.intersection({".ts", ".tsx", ".mts", ".cts"}):
        tech.add("TypeScript")
    if any(path.endswith((".tsx", ".jsx")) for path in paths):
        tech.add("React")
    if ".go" in suffixes:
        tech.add("Go")
    if ".rs" in suffixes:
        tech.add("Rust")
    if ".java" in suffixes:
        tech.add("Java")
    if suffixes.intersection({".cs"}):
        tech.add("C#")
    if suffixes.intersection({".c", ".h", ".cc", ".cpp", ".cxx", ".hpp"}):
        tech.add("C/C++")
    if any(path.startswith(".github/workflows/") for path in paths):
        tech.add("GitHub Actions")

    requirements = root / "requirements.txt"
    if requirements.exists():
        text = _read_small_text(requirements).lower()
        if "fastapi" in text:
            tech.add("FastAPI")
        if "django" in text:
            tech.add("Django")
        if "pytest" in text:
            tech.add("pytest")

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        text = _read_small_text(pyproject).lower()
        if "fastapi" in text:
            tech.add("FastAPI")
        if "pytest" in text:
            tech.add("pytest")

    package_json = root / "package.json"
    if package_json.exists():
        text = _read_small_text(package_json).lower()
        if "react" in text:
            tech.add("React")
        if "next" in text:
            tech.add("Next.js")
        if "vite" in text:
            tech.add("Vite")
        if "express" in text:
            tech.add("Express")
        if "jest" in text or "vitest" in text:
            tech.add("JS test runner")

    return sorted(tech)


def _detect_entrypoints(files: list[FileRecord]) -> list[str]:
    entrypoints: list[str] = []
    for file in files:
        name = file.path.rsplit("/", maxsplit=1)[-1].lower()
        if name in ENTRYPOINT_NAMES and file.role == "source":
            entrypoints.append(file.path)
    return sorted(entrypoints)


def _detect_repository_warnings(report: ScanReport) -> list[str]:
    warnings: list[str] = []
    paths = {file.path.lower().replace("\\", "/") for file in report.files}
    roles = Counter(file.role for file in report.files)

    if "readme.md" not in paths and "readme.rst" not in paths:
        warnings.append("README file was not found.")
    if roles["test"] == 0:
        warnings.append("No test files were detected.")
    if any(file.role == "secret-like" for file in report.files):
        warnings.append("Secret-like files exist. They should not be sent to external AI providers.")

    fallback = fallback_languages(report)
    if fallback:
        warnings.append(
            "Fallback-only language support for: "
            + ", ".join(fallback)
            + ". File/path/keyword/embedding search still works, but symbol-level answers may be incomplete."
        )
    return warnings


def _read_small_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")[:200_000]
    except (UnicodeDecodeError, OSError):
        return ""


def _relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()