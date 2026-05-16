from __future__ import annotations

import re
from pathlib import Path

from .models import ImportRecord, SymbolRecord


JS_TS_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}

_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?P<async>async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\b"
)
_DEFAULT_FUNCTION_RE = re.compile(r"^\s*export\s+default\s+(?P<async>async\s+)?function\b")
_CLASS_RE = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)\b")
_INTERFACE_RE = re.compile(r"^\s*(?:export\s+)?interface\s+(?P<name>[A-Za-z_$][\w$]*)\b")
_TYPE_RE = re.compile(r"^\s*(?:export\s+)?type\s+(?P<name>[A-Za-z_$][\w$]*)\b")
_ENUM_RE = re.compile(r"^\s*(?:export\s+)?enum\s+(?P<name>[A-Za-z_$][\w$]*)\b")
_ARROW_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*"
    r"(?P<async>async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)"
    r"(?:\s*:\s*[^=]+?)?\s*=>"
)
_VAR_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?P<async>async\s+)?function\b"
)
_IMPORT_FROM_RE = re.compile(r"^\s*import\s+(?:type\s+)?(?:.+?)\s+from\s+[\"'](?P<module>[^\"']+)[\"']")
_IMPORT_SIDE_EFFECT_RE = re.compile(r"^\s*import\s+[\"'](?P<module>[^\"']+)[\"']")
_EXPORT_FROM_RE = re.compile(r"^\s*export\s+(?:type\s+)?(?:\*|\{.*\})\s+from\s+[\"'](?P<module>[^\"']+)[\"']")
_REQUIRE_RE = re.compile(r"\brequire\(\s*[\"'](?P<module>[^\"']+)[\"']\s*\)")


def extract_js_ts_symbols(root: Path, path: Path) -> tuple[list[SymbolRecord], list[ImportRecord]]:
    relative = path.relative_to(root).as_posix()
    try:
        source = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError):
        return [], []

    block_clean_source = _strip_block_comments(source)
    original_lines = source.splitlines()
    match_lines = [_line_for_matching(line) for line in block_clean_source.splitlines()]

    symbols = _extract_symbols(relative, path.suffix.lower(), match_lines)
    imports = _extract_imports(relative, original_lines)
    symbols.sort(key=lambda item: (item.path, item.line, item.name, item.kind))
    imports.sort(key=lambda item: (item.path, item.line, item.module))
    return symbols, imports


def _extract_symbols(relative: str, suffix: str, lines: list[str]) -> list[SymbolRecord]:
    symbols: list[SymbolRecord] = []
    seen: set[tuple[str, str, int]] = set()

    for index, line in enumerate(lines):
        match = _FUNCTION_RE.match(line)
        if match:
            name = match.group("name")
            kind = _function_kind(name, suffix, async_prefix=bool(match.group("async")))
            _append_symbol(symbols, seen, name, kind, relative, index, lines)
            continue

        match = _DEFAULT_FUNCTION_RE.match(line)
        if match:
            name = _default_export_name(relative)
            kind = _function_kind(name, suffix, async_prefix=bool(match.group("async")))
            _append_symbol(symbols, seen, name, kind, relative, index, lines)
            continue

        match = _CLASS_RE.match(line)
        if match:
            _append_symbol(symbols, seen, match.group("name"), "class", relative, index, lines)
            continue

        match = _INTERFACE_RE.match(line)
        if match:
            _append_symbol(symbols, seen, match.group("name"), "interface", relative, index, lines)
            continue

        match = _TYPE_RE.match(line)
        if match:
            _append_symbol(symbols, seen, match.group("name"), "type", relative, index, lines)
            continue

        match = _ENUM_RE.match(line)
        if match:
            _append_symbol(symbols, seen, match.group("name"), "enum", relative, index, lines)
            continue

        match = _ARROW_RE.match(line)
        if match:
            name = match.group("name")
            kind = _function_kind(name, suffix, async_prefix=bool(match.group("async")))
            _append_symbol(symbols, seen, name, kind, relative, index, lines)
            continue

        match = _VAR_FUNCTION_RE.match(line)
        if match:
            name = match.group("name")
            kind = _function_kind(name, suffix, async_prefix=bool(match.group("async")))
            _append_symbol(symbols, seen, name, kind, relative, index, lines)

    return symbols


def _extract_imports(relative: str, lines: list[str]) -> list[ImportRecord]:
    imports: list[ImportRecord] = []
    seen: set[tuple[str, int]] = set()
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        modules: list[str] = []
        for regex in (_IMPORT_FROM_RE, _IMPORT_SIDE_EFFECT_RE, _EXPORT_FROM_RE):
            match = regex.search(line)
            if match:
                modules.append(match.group("module"))
        modules.extend(match.group("module") for match in _REQUIRE_RE.finditer(line))
        for module in modules:
            key = (module, index)
            if key in seen:
                continue
            seen.add(key)
            imports.append(ImportRecord(module=module, path=relative, line=index))
    return imports


def _append_symbol(
    symbols: list[SymbolRecord],
    seen: set[tuple[str, str, int]],
    name: str,
    kind: str,
    relative: str,
    start_index: int,
    lines: list[str],
) -> None:
    line = start_index + 1
    key = (name, kind, line)
    if key in seen:
        return
    seen.add(key)
    symbols.append(
        SymbolRecord(
            name=name,
            kind=kind,
            path=relative,
            line=line,
            end_line=_find_end_line(lines, start_index),
        )
    )


def _function_kind(name: str, suffix: str, *, async_prefix: bool) -> str:
    if re.match(r"^use[A-Z0-9]", name):
        return "hook"
    if suffix in {".jsx", ".tsx"} and name[:1].isupper():
        return "component"
    return "async_function" if async_prefix else "function"


def _default_export_name(relative: str) -> str:
    stem = Path(relative).stem
    if stem.lower() in {"index", "main", "app"}:
        return "default_export"
    cleaned = re.sub(r"[^A-Za-z0-9_$]", "_", stem)
    return cleaned or "default_export"


def _find_end_line(lines: list[str], start_index: int) -> int:
    depth = 0
    started = False
    for index in range(start_index, len(lines)):
        line = lines[index]
        for char in line:
            if char == "{":
                depth += 1
                started = True
            elif char == "}" and started:
                depth -= 1
                if depth <= 0:
                    return index + 1
        if not started and line.rstrip().endswith((";", ")")):
            return index + 1
    return start_index + 1


def _strip_block_comments(source: str) -> str:
    output: list[str] = []
    index = 0
    in_block = False
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if in_block:
            if char == "*" and next_char == "/":
                output.extend((" ", " "))
                index += 2
                in_block = False
                continue
            output.append("\n" if char == "\n" else " ")
            index += 1
            continue
        if char == "/" and next_char == "*":
            output.extend((" ", " "))
            index += 2
            in_block = True
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _line_for_matching(line: str) -> str:
    return _mask_string_literals(_strip_line_comment(line))


def _strip_line_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char == "/" and index + 1 < len(line) and line[index + 1] == "/":
            return line[:index]
    return line


def _mask_string_literals(line: str) -> str:
    output: list[str] = []
    quote: str | None = None
    escaped = False
    for char in line:
        if quote:
            output.append(" ")
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            output.append(" ")
            continue
        output.append(char)
    return "".join(output)