from __future__ import annotations

import json
from contextlib import closing
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .chunks import build_chunks
from .language_support import build_language_capabilities, language_capabilities_to_dicts
from .models import ChunkRecord, FileRecord, ImportRecord, ScanReport, SymbolRecord
from .scanner import scan_repository


SCHEMA_VERSION = 3
INDEX_DIR_NAME = ".projectlens"
INDEX_FILE_NAME = "index.sqlite"


@dataclass(frozen=True)
class IndexStats:
    root: str
    index_path: str
    schema_version: int
    created_at_utc: str
    file_count: int
    symbol_count: int
    import_count: int
    chunk_count: int
    embedding_count: int
    technologies: tuple[str, ...]
    entrypoints: tuple[str, ...]
    warnings: tuple[str, ...]


def default_index_path(root: str | Path) -> Path:
    return Path(root).expanduser().resolve() / INDEX_DIR_NAME / INDEX_FILE_NAME


def build_index(root: str | Path, index_path: str | Path | None = None) -> IndexStats:
    report = scan_repository(root)
    chunks = build_chunks(report)
    output_path = Path(index_path).expanduser().resolve() if index_path else default_index_path(report.root)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    created_at_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(sqlite3.connect(output_path)) as connection:
        _create_schema(connection)
        _clear_existing_rows(connection)
        _write_metadata(connection, report, output_path, created_at_utc)
        _write_files(connection, report.files)
        _write_symbols(connection, report.symbols)
        _write_imports(connection, report.imports)
        _write_chunks(connection, chunks)
        connection.commit()

    return IndexStats(
        root=report.root,
        index_path=str(output_path),
        schema_version=SCHEMA_VERSION,
        created_at_utc=created_at_utc,
        file_count=report.file_count,
        symbol_count=report.symbol_count,
        import_count=len(report.imports),
        chunk_count=len(chunks),
        embedding_count=0,
        technologies=tuple(report.technologies),
        entrypoints=tuple(report.entrypoints),
        warnings=tuple(report.warnings),
    )


def load_index_stats(root: str | Path, index_path: str | Path | None = None) -> IndexStats | None:
    path = Path(index_path).expanduser().resolve() if index_path else default_index_path(root)
    if not path.exists():
        return None

    with closing(sqlite3.connect(path)) as connection:
        metadata = _read_metadata(connection)
        file_count = _count_rows(connection, "files")
        symbol_count = _count_rows(connection, "symbols")
        import_count = _count_rows(connection, "imports")
        chunk_count = _count_rows(connection, "chunks")
        embedding_count = _count_rows(connection, "embeddings")

    return IndexStats(
        root=metadata.get("root", str(Path(root).expanduser().resolve())),
        index_path=str(path),
        schema_version=int(metadata.get("schema_version", "0")),
        created_at_utc=metadata.get("created_at_utc", "unknown"),
        file_count=file_count,
        symbol_count=symbol_count,
        import_count=import_count,
        chunk_count=chunk_count,
        embedding_count=embedding_count,
        technologies=tuple(_loads_list(metadata.get("technologies", "[]"))),
        entrypoints=tuple(_loads_list(metadata.get("entrypoints", "[]"))),
        warnings=tuple(_loads_list(metadata.get("warnings", "[]"))),
    )


def load_index_report(root: str | Path, index_path: str | Path | None = None) -> ScanReport:
    path = Path(index_path).expanduser().resolve() if index_path else default_index_path(root)
    if not path.exists():
        raise FileNotFoundError(f"ProjectLens index not found: {path}")

    with closing(sqlite3.connect(path)) as connection:
        metadata = _read_metadata(connection)
        files = [
            FileRecord(path=row[0], size_bytes=row[1], suffix=row[2], role=row[3])
            for row in connection.execute("SELECT path, size_bytes, suffix, role FROM files ORDER BY path")
        ]
        symbols = [
            SymbolRecord(name=row[0], kind=row[1], path=row[2], line=row[3], end_line=row[4])
            for row in connection.execute(
                "SELECT name, kind, path, line, end_line FROM symbols ORDER BY path, line, name"
            )
        ]
        imports = [
            ImportRecord(module=row[0], path=row[1], line=row[2])
            for row in connection.execute("SELECT module, path, line FROM imports ORDER BY path, line, module")
        ]

    report = ScanReport(
        root=metadata.get("root", str(Path(root).expanduser().resolve())),
        files=files,
        symbols=symbols,
        imports=imports,
        technologies=_loads_list(metadata.get("technologies", "[]")),
        entrypoints=_loads_list(metadata.get("entrypoints", "[]")),
        warnings=_loads_list(metadata.get("warnings", "[]")),
    )
    report.language_capabilities = build_language_capabilities(report)
    return report


def load_chunks(root: str | Path, index_path: str | Path | None = None) -> list[ChunkRecord]:
    path = Path(index_path).expanduser().resolve() if index_path else default_index_path(root)
    if not path.exists():
        raise FileNotFoundError(f"ProjectLens index not found: {path}")

    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            """
            SELECT path, chunk_kind, label, start_line, end_line, text
            FROM chunks
            ORDER BY path, start_line, label
            """
        ).fetchall()
    return [
        ChunkRecord(
            path=row[0],
            chunk_kind=row[1],
            label=row[2],
            start_line=row[3],
            end_line=row[4],
            text=row[5],
        )
        for row in rows
    ]


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            size_bytes INTEGER NOT NULL,
            suffix TEXT NOT NULL,
            role TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            path TEXT NOT NULL,
            line INTEGER NOT NULL,
            end_line INTEGER,
            FOREIGN KEY(path) REFERENCES files(path)
        );

        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            path TEXT NOT NULL,
            line INTEGER NOT NULL,
            FOREIGN KEY(path) REFERENCES files(path)
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            chunk_kind TEXT NOT NULL,
            label TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            text TEXT NOT NULL,
            FOREIGN KEY(path) REFERENCES files(path)
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id INTEGER NOT NULL,
            backend TEXT NOT NULL,
            model TEXT NOT NULL,
            vector_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY(chunk_id) REFERENCES chunks(id)
        );

        CREATE INDEX IF NOT EXISTS idx_symbols_path ON symbols(path);
        CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
        CREATE INDEX IF NOT EXISTS idx_imports_path ON imports(path);
        CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
        CREATE INDEX IF NOT EXISTS idx_embeddings_chunk ON embeddings(chunk_id);
        """
    )


def _clear_existing_rows(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM metadata")
    connection.execute("DELETE FROM embeddings")
    connection.execute("DELETE FROM chunks")
    connection.execute("DELETE FROM imports")
    connection.execute("DELETE FROM symbols")
    connection.execute("DELETE FROM files")


def _write_metadata(
    connection: sqlite3.Connection,
    report: ScanReport,
    index_path: Path,
    created_at_utc: str,
) -> None:
    values = {
        "schema_version": str(SCHEMA_VERSION),
        "created_at_utc": created_at_utc,
        "root": report.root,
        "index_path": str(index_path),
        "technologies": json.dumps(report.technologies),
        "entrypoints": json.dumps(report.entrypoints),
        "warnings": json.dumps(report.warnings),
        "language_capabilities": json.dumps(language_capabilities_to_dicts(report.language_capabilities)),
        "total_size_bytes": str(report.total_size_bytes),
    }
    connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", sorted(values.items()))


def _write_files(connection: sqlite3.Connection, files: list[FileRecord]) -> None:
    connection.executemany(
        "INSERT INTO files(path, size_bytes, suffix, role) VALUES (?, ?, ?, ?)",
        [(file.path, file.size_bytes, file.suffix, file.role) for file in files],
    )


def _write_symbols(connection: sqlite3.Connection, symbols: list[SymbolRecord]) -> None:
    connection.executemany(
        "INSERT INTO symbols(name, kind, path, line, end_line) VALUES (?, ?, ?, ?, ?)",
        [(symbol.name, symbol.kind, symbol.path, symbol.line, symbol.end_line) for symbol in symbols],
    )


def _write_imports(connection: sqlite3.Connection, imports: list[ImportRecord]) -> None:
    connection.executemany(
        "INSERT INTO imports(module, path, line) VALUES (?, ?, ?)",
        [(record.module, record.path, record.line) for record in imports],
    )


def _write_chunks(connection: sqlite3.Connection, chunks: list[ChunkRecord]) -> None:
    connection.executemany(
        """
        INSERT INTO chunks(path, chunk_kind, label, start_line, end_line, text)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (chunk.path, chunk.chunk_kind, chunk.label, chunk.start_line, chunk.end_line, chunk.text)
            for chunk in chunks
        ],
    )


def _read_metadata(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute("SELECT key, value FROM metadata").fetchall()
    return {key: value for key, value in rows}


def _count_rows(connection: sqlite3.Connection, table: str) -> int:
    try:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.OperationalError:
        return 0


def _loads_list(value: str) -> list[str]:
    loaded = json.loads(value)
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded]
