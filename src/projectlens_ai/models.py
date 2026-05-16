from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class FileRecord:
    path: str
    size_bytes: int
    suffix: str
    role: str


@dataclass(frozen=True)
class SymbolRecord:
    name: str
    kind: str
    path: str
    line: int
    end_line: int | None = None


@dataclass(frozen=True)
class ImportRecord:
    module: str
    path: str
    line: int


@dataclass(frozen=True)
class ChunkRecord:
    path: str
    chunk_kind: str
    label: str
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True)
class LanguageCapability:
    language: str
    file_count: int
    source_file_count: int
    symbol_count: int
    import_count: int
    support_level: str
    parser: str
    confidence: str
    notes: tuple[str, ...] = ()


@dataclass
class ScanReport:
    root: str
    files: list[FileRecord] = field(default_factory=list)
    symbols: list[SymbolRecord] = field(default_factory=list)
    imports: list[ImportRecord] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    language_capabilities: list[LanguageCapability] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def symbol_count(self) -> int:
        return len(self.symbols)

    @property
    def total_size_bytes(self) -> int:
        return sum(file.size_bytes for file in self.files)

    def as_dict(self) -> dict:
        return asdict(self)