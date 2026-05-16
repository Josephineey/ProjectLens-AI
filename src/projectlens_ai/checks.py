from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover - Python 3.11+ path is used in this environment.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


SECRET_LIKE_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "secrets.json",
    "credentials.json",
}

REQUIRED_GITIGNORE_PATTERNS = {
    ".venv/",
    "__pycache__/",
    ".env",
    ".projectlens/",
    "*.sqlite",
    "projectlens-output.md",
}


@dataclass(frozen=True)
class CheckResult:
    code: str
    status: str
    title: str
    message: str
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChecksReport:
    root: str
    results: tuple[CheckResult, ...]

    @property
    def pass_count(self) -> int:
        return _count_status(self.results, "pass")

    @property
    def warn_count(self) -> int:
        return _count_status(self.results, "warn")

    @property
    def fail_count(self) -> int:
        return _count_status(self.results, "fail")

    @property
    def info_count(self) -> int:
        return _count_status(self.results, "info")

    @property
    def is_passing(self) -> bool:
        return self.fail_count == 0


def run_project_checks(root: str | Path) -> ChecksReport:
    root_path = Path(root).expanduser().resolve()
    results = [
        _check_readme(root_path),
        _check_license(root_path),
        _check_pyproject(root_path),
        _check_tests(root_path),
        _check_gitignore(root_path),
        _check_secret_like_files(root_path),
        _check_config_example(root_path),
        _check_ci_workflow(root_path),
        _check_generated_artifacts(root_path),
        _check_local_index(root_path),
    ]
    return ChecksReport(root=str(root_path), results=tuple(results))


def _check_readme(root: Path) -> CheckResult:
    path = root / "README.md"
    if not path.exists():
        return CheckResult("readme", "fail", "README", "README.md is missing.", ("README.md",))
    text = _safe_read_text(path)
    if len(text.strip()) < 600:
        return CheckResult("readme", "warn", "README", "README.md exists but looks too short for a public project.", ("README.md",))
    lower = text.lower()
    expected = ("quick start", "configuration", "usage", "roadmap")
    missing = [heading for heading in expected if heading not in lower]
    if missing:
        return CheckResult(
            "readme",
            "warn",
            "README",
            f"README.md exists, but these public-project sections may be missing: {', '.join(missing)}.",
            ("README.md",),
        )
    return CheckResult("readme", "pass", "README", "README.md is present and contains core public-project sections.", ("README.md",))


def _check_license(root: Path) -> CheckResult:
    path = root / "LICENSE"
    if not path.exists():
        return CheckResult("license", "warn", "License", "LICENSE is missing; public repos should declare a license.", ("LICENSE",))
    text = _safe_read_text(path).lower()
    if "mit license" in text or "permission is hereby granted" in text:
        return CheckResult("license", "pass", "License", "LICENSE is present and looks like MIT.", ("LICENSE",))
    return CheckResult("license", "warn", "License", "LICENSE exists, but the license type was not recognized.", ("LICENSE",))


def _check_pyproject(root: Path) -> CheckResult:
    path = root / "pyproject.toml"
    if not path.exists():
        return CheckResult("pyproject", "fail", "Python package metadata", "pyproject.toml is missing.", ("pyproject.toml",))
    try:
        data = tomllib.loads(_safe_read_text(path))
    except tomllib.TOMLDecodeError as error:
        return CheckResult("pyproject", "fail", "Python package metadata", f"pyproject.toml is invalid TOML: {error}.", ("pyproject.toml",))

    project = data.get("project") if isinstance(data, dict) else None
    if not isinstance(project, dict):
        return CheckResult("pyproject", "fail", "Python package metadata", "pyproject.toml has no [project] table.", ("pyproject.toml",))
    missing = [key for key in ("name", "version", "description", "requires-python") if not project.get(key)]
    scripts = project.get("scripts")
    if missing:
        return CheckResult("pyproject", "warn", "Python package metadata", f"pyproject.toml is missing: {', '.join(missing)}.", ("pyproject.toml",))
    if not isinstance(scripts, dict) or "projectlens" not in scripts:
        return CheckResult("pyproject", "warn", "Python package metadata", "pyproject.toml has no projectlens console script.", ("pyproject.toml",))
    return CheckResult("pyproject", "pass", "Python package metadata", "pyproject.toml has package metadata and console script.", ("pyproject.toml",))


def _check_tests(root: Path) -> CheckResult:
    tests_dir = root / "tests"
    if not tests_dir.exists():
        return CheckResult("tests", "fail", "Tests", "tests/ directory is missing.", ("tests/",))
    test_files = sorted(path.relative_to(root).as_posix() for path in tests_dir.rglob("test_*.py"))
    if not test_files:
        return CheckResult("tests", "fail", "Tests", "No test_*.py files were found under tests/.", ("tests/",))
    if len(test_files) < 3:
        return CheckResult("tests", "warn", "Tests", f"Only {len(test_files)} test file(s) found; coverage may be thin.", tuple(test_files))
    return CheckResult("tests", "pass", "Tests", f"Found {len(test_files)} test files.", tuple(test_files[:5]))


def _check_gitignore(root: Path) -> CheckResult:
    path = root / ".gitignore"
    if not path.exists():
        return CheckResult("gitignore", "fail", "Git ignore rules", ".gitignore is missing.", (".gitignore",))
    lines = {line.strip() for line in _safe_read_text(path).splitlines() if line.strip() and not line.strip().startswith("#")}
    missing = sorted(pattern for pattern in REQUIRED_GITIGNORE_PATTERNS if pattern not in lines)
    if missing:
        return CheckResult("gitignore", "warn", "Git ignore rules", f".gitignore is missing patterns: {', '.join(missing)}.", (".gitignore",))
    return CheckResult("gitignore", "pass", "Git ignore rules", ".gitignore protects local env, secrets, generated outputs, and local indexes.", (".gitignore",))


def _check_secret_like_files(root: Path) -> CheckResult:
    present: list[str] = []
    for name in sorted(SECRET_LIKE_FILENAMES):
        candidate = root / name
        if candidate.exists():
            present.append(candidate.relative_to(root).as_posix())
    if present:
        return CheckResult(
            "secrets",
            "fail",
            "Secret-like files",
            "Secret-like files are present. ProjectLens does not read them, but verify they are ignored and never committed.",
            tuple(present),
        )
    return CheckResult("secrets", "pass", "Secret-like files", "No root-level secret-like files were found.")


def _check_config_example(root: Path) -> CheckResult:
    path = root / "config-example.toml"
    if not path.exists():
        return CheckResult("config-example", "warn", "Config example", "config-example.toml is missing.", ("config-example.toml",))
    text = _safe_read_text(path).lower()
    if "embedding" not in text or "privacy_mode" not in text:
        return CheckResult("config-example", "warn", "Config example", "config-example.toml exists but does not document core settings.", ("config-example.toml",))
    return CheckResult("config-example", "pass", "Config example", "config-example.toml documents core local settings.", ("config-example.toml",))


def _check_ci_workflow(root: Path) -> CheckResult:
    workflows = root / ".github" / "workflows"
    if not workflows.exists():
        return CheckResult("ci", "warn", "CI workflow", "No GitHub Actions workflow found yet.", (".github/workflows/",))
    files = sorted(path.relative_to(root).as_posix() for path in workflows.glob("*.yml")) + sorted(
        path.relative_to(root).as_posix() for path in workflows.glob("*.yaml")
    )
    if not files:
        return CheckResult("ci", "warn", "CI workflow", "GitHub workflows directory exists but has no YAML workflow.", (".github/workflows/",))
    return CheckResult("ci", "pass", "CI workflow", f"Found {len(files)} GitHub Actions workflow file(s).", tuple(files))


def _check_generated_artifacts(root: Path) -> CheckResult:
    generated = ["projectlens-output.md"]
    present = [name for name in generated if (root / name).exists()]
    if not present:
        return CheckResult("generated-artifacts", "pass", "Generated artifacts", "No known generated report artifacts are present at the repo root.")
    gitignore = _safe_read_text(root / ".gitignore") if (root / ".gitignore").exists() else ""
    unignored = [name for name in present if name not in gitignore]
    if unignored:
        return CheckResult("generated-artifacts", "warn", "Generated artifacts", "Generated artifacts exist and may not be ignored.", tuple(unignored))
    return CheckResult("generated-artifacts", "info", "Generated artifacts", "Generated report artifacts exist but are ignored by git.", tuple(present))


def _check_local_index(root: Path) -> CheckResult:
    path = root / ".projectlens" / "index.sqlite"
    if not path.exists():
        return CheckResult("local-index", "info", "Local ProjectLens index", "No local ProjectLens index found; run `projectlens index .` when needed.")
    return CheckResult("local-index", "info", "Local ProjectLens index", "Local ProjectLens index exists and is ignored by git.", (".projectlens/index.sqlite",))


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""


def _count_status(results: tuple[CheckResult, ...], status: str) -> int:
    return sum(1 for result in results if result.status == status)
