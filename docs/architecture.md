# ProjectLens AI Architecture

ProjectLens is built as a small core with multiple interfaces.

## Core

- Scanner: walks the repository and classifies files.
- Symbol parser: extracts Python symbols through `ast` and JavaScript/TypeScript symbols through the built-in structured parser.
- Packer: turns the scan result into an AI-friendly Markdown digest.
- Search: combines keyword, symbol, and path signals to find relevant files before any LLM call.
- Index store: persists scan results into `.projectlens/index.sqlite` using SQLite.
- Chunks: splits code into function/class/file units that can be embedded later.
- Embeddings: manages local, OpenAI, or disabled embedding backends.
- Embedding store: writes chunk vectors into SQLite when a backend is ready.
- Semantic search: compares a query vector with stored chunk vectors.
- Hybrid search: merges lexical file evidence and semantic chunk evidence into one ranked result list.
- Ask: turns top hybrid results into source snippets with file and line references.
- Checks: runs deterministic local project-readiness checks for README, tests, package metadata, secrets, gitignore, and CI.
- Language support: reports parser coverage, confidence, and fallback-only languages.
- Eval: runs answer-key based retrieval tests and reports search rank, source citation, and confidence.

## Interfaces

- CLI: terminal commands such as `projectlens scan`, `projectlens pack`, and `projectlens search`.
- MCP: stdio server that lets AI clients call ProjectLens tools.
- UI: optional future layer.

## Guarded Embedding Flow

Embedding has three gates:

1. Dependency gate: is the Python package installed?
2. Model gate: is the configured local model cached and loadable?
3. Repository gate: have this repository's chunks been embedded into SQLite?

`projectlens embed test .` checks the first two gates with one tiny probe.
`projectlens embed build .` writes repository vectors only after the backend is
ready. Model downloading is explicit through `--download-model`.

## Naming Policy

Product commands, code identifiers, filenames, and GitHub-facing documentation
use English. Turkish text is only used in learning notes for the developer.

## Language Support Flow

ProjectLens separates file-level support from symbol-level support.

- Python uses `ast`, so it is marked as `deep` with high confidence.
- JavaScript and TypeScript use a built-in structured parser, so they are marked as `structured` with medium confidence.
- Other recognized code languages are marked as `fallback`: they are scanned, packed, indexed, searched, and embedded, but ProjectLens does not claim complete symbol maps for them.

The `projectlens capabilities` command and the pack output expose this boundary
explicitly. This is important because a repo analysis tool should not pretend it
understands every language equally well.
## Hybrid Search Flow

Hybrid search uses two retrieval lanes:

1. Lexical lane: keyword, path, symbol, and file role evidence from the saved SQLite index.
2. Semantic lane: query embeddings compared with stored chunk embeddings.

The merge step normalizes both lanes, gives a small bonus when both agree on the
same file, and applies role-aware ranking so implementation questions prefer
source code over tests and docs.
## Source-Grounded Ask Flow

`projectlens ask` is an evidence mode, not an LLM answer mode yet. It runs hybrid
search, selects the top files, extracts bounded snippets around the best matching
chunk or query line, and prints them with stable file/line references.

This keeps the first answer layer auditable. A later LLM-backed mode can use the
same evidence pack as context instead of reading the whole repository.
## Checks And Reports Flow

`projectlens checks` is a deterministic quality gate. It does not call an LLM.
It checks public-project readiness signals such as README structure, LICENSE,
pyproject metadata, tests, gitignore safety, secret-like files, config example,
GitHub Actions, generated artifacts, and local ProjectLens index state.

The command returns a human-readable report by default and JSON with `--json` so
future CI or eval layers can consume the same result.
## MCP Server Flow

The MCP layer is an interface, not a second implementation of ProjectLens.
`mcp_tools.py` contains pure Python wrapper functions that return JSON-safe
objects. `mcp_server.py` registers those wrappers with the official MCP Python
SDK through `FastMCP`.

The flow is:

1. An MCP client starts `projectlens-mcp --root <repo>` as a child process.
2. The client and server exchange JSON-RPC messages over stdio.
3. The client calls tools such as `projectlens_search_code`, `projectlens_language_capabilities`, or `projectlens_run_checks`.
4. ProjectLens reads the local repository/index and returns structured results.

This keeps the CLI, tests, and MCP server aligned because they share the same
scanner, index, search, ask, and checks modules.
## Eval Flow

`projectlens eval` turns repo understanding into a measurable check. An eval
suite is a JSON file with natural-language queries and expected file paths.

For each case, ProjectLens:

1. Runs hybrid search against the local SQLite index.
2. Checks whether any expected path appears within the case's `top_k` results.
3. Runs source-grounded `ask` and checks whether the expected file was cited.
4. Assigns a conservative confidence label based on rank, ask evidence, and language support level.

This makes retrieval quality visible before an LLM-backed answer mode is added.