from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10 only
    import tomli as tomllib  # type: ignore[no-redef]


CONFIG_DIR_NAME = ".projectlens"
CONFIG_FILE_NAME = "config.toml"
VALID_EMBEDDING_BACKENDS = {"local", "openai", "disabled"}
VALID_LLM_PROVIDERS = {"none", "openai", "anthropic", "local"}
LOCAL_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"


@dataclass(frozen=True)
class EmbeddingConfig:
    backend: str = "local"
    model: str = LOCAL_EMBEDDING_MODEL


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "none"
    model: str = ""


@dataclass(frozen=True)
class RuntimeConfig:
    max_context_tokens: int = 12_000
    privacy_mode: bool = True


@dataclass(frozen=True)
class ProjectLensConfig:
    embedding: EmbeddingConfig = EmbeddingConfig()
    llm: LLMConfig = LLMConfig()
    runtime: RuntimeConfig = RuntimeConfig()
    path: str | None = None
    exists: bool = False


def default_config_path(root: str | Path) -> Path:
    return Path(root).expanduser().resolve() / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def default_config(path: str | Path | None = None, *, exists: bool = False) -> ProjectLensConfig:
    return ProjectLensConfig(path=str(path) if path else None, exists=exists)


def load_config(root: str | Path, config_path: str | Path | None = None) -> ProjectLensConfig:
    path = Path(config_path).expanduser().resolve() if config_path else default_config_path(root)
    if not path.exists():
        return default_config(path, exists=False)

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    embedding = raw.get("embedding", {})
    llm = raw.get("llm", {})
    runtime = raw.get("runtime", {})

    config = ProjectLensConfig(
        embedding=EmbeddingConfig(
            backend=str(embedding.get("backend", "local")),
            model=str(embedding.get("model", LOCAL_EMBEDDING_MODEL)),
        ),
        llm=LLMConfig(
            provider=str(llm.get("provider", "none")),
            model=str(llm.get("model", "")),
        ),
        runtime=RuntimeConfig(
            max_context_tokens=int(runtime.get("max_context_tokens", 12_000)),
            privacy_mode=bool(runtime.get("privacy_mode", True)),
        ),
        path=str(path),
        exists=True,
    )
    validate_config(config)
    return config


def init_config(root: str | Path, config_path: str | Path | None = None, *, force: bool = False) -> ProjectLensConfig:
    path = Path(config_path).expanduser().resolve() if config_path else default_config_path(root)
    if path.exists() and not force:
        return load_config(root, path)

    path.parent.mkdir(parents=True, exist_ok=True)
    config = default_config(path, exists=True)
    path.write_text(render_config(config), encoding="utf-8")
    return load_config(root, path)


def set_config_value(
    root: str | Path,
    key: str,
    value: str,
    config_path: str | Path | None = None,
) -> ProjectLensConfig:
    path = Path(config_path).expanduser().resolve() if config_path else default_config_path(root)
    config = load_config(root, path) if path.exists() else init_config(root, path)
    data = config_to_dict(config)
    section, field = _split_key(key)
    converted = _convert_value(section, field, value)
    data[section][field] = converted
    if key == "embedding.backend":
        current_model = str(data["embedding"].get("model", ""))
        if converted == "openai" and current_model == LOCAL_EMBEDDING_MODEL:
            data["embedding"]["model"] = OPENAI_EMBEDDING_MODEL
        elif converted == "local" and current_model == OPENAI_EMBEDDING_MODEL:
            data["embedding"]["model"] = LOCAL_EMBEDDING_MODEL
        elif converted == "disabled":
            data["embedding"]["model"] = ""
    updated = dict_to_config(data, path=str(path), exists=True)
    validate_config(updated)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_config(updated), encoding="utf-8")
    return updated


def config_to_dict(config: ProjectLensConfig) -> dict[str, dict[str, Any]]:
    return {
        "embedding": {
            "backend": config.embedding.backend,
            "model": config.embedding.model,
        },
        "llm": {
            "provider": config.llm.provider,
            "model": config.llm.model,
        },
        "runtime": {
            "max_context_tokens": config.runtime.max_context_tokens,
            "privacy_mode": config.runtime.privacy_mode,
        },
    }


def dict_to_config(data: dict[str, dict[str, Any]], *, path: str | None, exists: bool) -> ProjectLensConfig:
    embedding = data.get("embedding", {})
    llm = data.get("llm", {})
    runtime = data.get("runtime", {})
    return ProjectLensConfig(
        embedding=EmbeddingConfig(
            backend=str(embedding.get("backend", "local")),
            model=str(embedding.get("model", LOCAL_EMBEDDING_MODEL)),
        ),
        llm=LLMConfig(
            provider=str(llm.get("provider", "none")),
            model=str(llm.get("model", "")),
        ),
        runtime=RuntimeConfig(
            max_context_tokens=int(runtime.get("max_context_tokens", 12_000)),
            privacy_mode=bool(runtime.get("privacy_mode", True)),
        ),
        path=path,
        exists=exists,
    )


def render_config(config: ProjectLensConfig) -> str:
    return "\n".join(
        [
            "# ProjectLens AI configuration",
            "# This file controls local/remote AI-related behavior.",
            "",
            "[embedding]",
            f"backend = {quote(config.embedding.backend)}",
            f"model = {quote(config.embedding.model)}",
            "",
            "[llm]",
            f"provider = {quote(config.llm.provider)}",
            f"model = {quote(config.llm.model)}",
            "",
            "[runtime]",
            f"max_context_tokens = {config.runtime.max_context_tokens}",
            f"privacy_mode = {str(config.runtime.privacy_mode).lower()}",
            "",
        ]
    )


def quote(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def validate_config(config: ProjectLensConfig) -> None:
    if config.embedding.backend not in VALID_EMBEDDING_BACKENDS:
        raise ValueError(
            f"Invalid embedding.backend '{config.embedding.backend}'. "
            f"Expected one of: {', '.join(sorted(VALID_EMBEDDING_BACKENDS))}"
        )
    if config.llm.provider not in VALID_LLM_PROVIDERS:
        raise ValueError(
            f"Invalid llm.provider '{config.llm.provider}'. "
            f"Expected one of: {', '.join(sorted(VALID_LLM_PROVIDERS))}"
        )
    if config.runtime.max_context_tokens <= 0:
        raise ValueError("runtime.max_context_tokens must be greater than zero.")


def _split_key(key: str) -> tuple[str, str]:
    if "." not in key:
        raise ValueError("Config key must use section.field format, for example embedding.backend")
    section, field = key.split(".", 1)
    allowed = config_to_dict(default_config())
    if section not in allowed or field not in allowed[section]:
        valid = [f"{section_name}.{field_name}" for section_name, fields in allowed.items() for field_name in fields]
        raise ValueError(f"Unknown config key '{key}'. Valid keys: {', '.join(valid)}")
    return section, field


def _convert_value(section: str, field: str, value: str) -> Any:
    if section == "runtime" and field == "max_context_tokens":
        return int(value)
    if section == "runtime" and field == "privacy_mode":
        lowered = value.lower()
        if lowered not in {"true", "false"}:
            raise ValueError("runtime.privacy_mode must be true or false")
        return lowered == "true"
    return value
