from __future__ import annotations

from pathlib import Path

from .models import ChunkRecord, ScanReport, SymbolRecord
from .scanner import SECRET_LIKE_NAMES


CHUNKABLE_ROLES = {"source", "test", "documentation", "dependency-or-config"}
MAX_FILE_CHARS = 20_000


def build_chunks(report: ScanReport) -> list[ChunkRecord]:
    root = Path(report.root)
    symbols_by_path: dict[str, list[SymbolRecord]] = {}
    for symbol in report.symbols:
        if symbol.end_line is not None:
            symbols_by_path.setdefault(symbol.path, []).append(symbol)

    chunks: list[ChunkRecord] = []
    for file in report.files:
        if file.role not in CHUNKABLE_ROLES:
            continue
        if file.path.rsplit("/", maxsplit=1)[-1] in SECRET_LIKE_NAMES:
            continue

        lines = _read_lines(root / file.path)
        if not lines:
            continue

        file_symbols = symbols_by_path.get(file.path, [])
        if file_symbols:
            for symbol in file_symbols:
                text = _slice_lines(lines, symbol.line, symbol.end_line or symbol.line)
                if text.strip():
                    chunks.append(
                        ChunkRecord(
                            path=file.path,
                            chunk_kind=symbol.kind,
                            label=symbol.name,
                            start_line=symbol.line,
                            end_line=symbol.end_line or symbol.line,
                            text=text,
                        )
                    )
            continue

        text = "".join(lines)
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS].rstrip() + "\n[ProjectLens: file chunk truncated]\n"
        chunks.append(
            ChunkRecord(
                path=file.path,
                chunk_kind="file",
                label=file.path,
                start_line=1,
                end_line=len(lines),
                text=text,
            )
        )
    return chunks


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    except (UnicodeDecodeError, OSError):
        return []


def _slice_lines(lines: list[str], start_line: int, end_line: int) -> str:
    start_index = max(start_line - 1, 0)
    end_index = min(end_line, len(lines))
    return "".join(lines[start_index:end_index])
