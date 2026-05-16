# ProjectLens AI

ProjectLens AI is a local-first developer tool for understanding unfamiliar
code repositories. It scans a project, builds a structured map, persists a local
SQLite index, suggests useful questions, exports AI-friendly repository packs,
and prepares semantic search over code chunks without sending code to an LLM by
default.

## Why This Exists

Large AI coding tools are powerful, but they often start by reading files on
demand. ProjectLens takes a different first step: it builds a repeatable local
map of the repository before any AI model is asked to explain it.

That keeps the early workflow cheap, private, and easier to inspect. Later, the
AI layer can use this map to send only the most relevant code sections to a
model instead of sending the whole repository every time.

## Current Stage

This repository is in the local retrieval, quality-check, MCP integration, language capability, and eval stage: scanner,
repository pack, SQLite index, config, code chunking, guarded embedding setup,
semantic search, hybrid search, source-grounded ask, checks, and the first local
retrieval layer, a language capability report, retrieval evals, and a stdio MCP server for AI clients.

Available now:

- `projectlens scan <path>`: scan a repository and print a local summary.
- `projectlens pack <path>`: export an AI-friendly Markdown repository digest.
- `projectlens index <path>`: persist scan results into `.projectlens/index.sqlite`.
- `projectlens status <path>`: show saved index status.
- `projectlens capabilities <path>`: show language parser coverage, confidence, and fallback status.
- `projectlens config init/show/set`: manage local ProjectLens configuration.
- `projectlens search <query> <path>`: find relevant files without calling an AI model.
- `projectlens search <query> <path> --semantic`: search stored embedding vectors when embeddings exist.
- `projectlens search <query> <path> --hybrid`: combine keyword, symbol, path, file role, and semantic signals.
- `projectlens ask <query> <path>`: show source-grounded evidence with file and line references.
- `projectlens checks <path>`: run README, tests, packaging, secret, gitignore, and CI readiness checks.
- `projectlens eval <path>`: run answer-key based retrieval quality checks.
- `projectlens embed status <path>`: show package/backend availability.
- `projectlens embed test <path>`: safely test model loading with one tiny probe.
- `projectlens embed build <path>`: build embeddings for stored code chunks.
- `projectlens prompts`: show good questions to ask about a repository.
- `projectlens doctor`: show which capabilities are currently available.
- `projectlens-mcp --root <path>`: expose ProjectLens tools to MCP clients over stdio.

Coming later:

- LLM-backed `projectlens ask` answer generation on top of the existing evidence mode.

## Quick Start

```powershell
python -m venv .venv
.venv\Scripts\Activate
python -m pip install -e .
projectlens scan .
projectlens index .
projectlens status .
projectlens capabilities .
projectlens config init .
projectlens config show .
projectlens search "database connection" .
projectlens search "database connection" . --indexed
projectlens ask "where is configuration handled?" .
projectlens prompts
projectlens doctor
```


## Usage

Use `scan` when you want a quick local map of a repository. Use `index` when you
want ProjectLens to persist that map into SQLite. Use `embed build` after the
index is ready and the local model has been downloaded. Use `search --hybrid`
when you want a ranked file list, and use `ask` when you want source-grounded
snippets with file and line references.

```powershell
projectlens scan .
projectlens index .
projectlens embed test .
projectlens embed build .
projectlens search "database connection" . --hybrid
projectlens ask "where is configuration handled?" .
projectlens checks .
projectlens eval .
```
For development without installing:

```powershell
python -m projectlens_ai scan .
```

## Mental Model

Think of ProjectLens as a map maker for codebases.

First, it walks through the repository locally. It looks at folders, file names,
dependency files, test folders, and Python symbols such as functions and
classes. This step does not require an API key and does not send code anywhere.

The SQLite index then saves this local map so future layers can reuse it. When
semantic search is enabled, ProjectLens embeds code chunks from this index and
stores the vectors locally. Later, source-grounded Q&A can use these signals to
select the right files before an LLM is asked to answer.

## Language Support

ProjectLens uses English names for commands, files, code identifiers, and
GitHub-facing documentation. Turkish notes may live under `docs/` only as
learning material.

Current parser support:

- Python: deep support through the standard library `ast` parser.
- JavaScript and TypeScript: structured support through ProjectLens' built-in JS/TS parser.
- Go, Rust, Java, C#, PHP, Ruby, C/C++, and other recognized source files: fallback support.

Fallback support means ProjectLens can still scan, pack, index, search, embed,
and show file-level evidence. It does not claim reliable function/class/import
maps for that language yet.

Use this command to see what ProjectLens can and cannot understand in a specific
repository:

```powershell
projectlens capabilities .
projectlens capabilities . --json
```

## Configuration

ProjectLens stores local settings in `.projectlens/config.toml`. This file is
ignored by git because it can contain machine-specific preferences.

```powershell
projectlens config init .
projectlens config show .
projectlens config set embedding.backend openai .
projectlens config set embedding.backend local .
```

Important settings:

- `embedding.backend = "local"`: free default; code stays on your machine.
- `embedding.backend = "openai"`: optional quality mode; code chunks are sent to OpenAI for embeddings.
- `embedding.backend = "disabled"`: no semantic search; keyword/symbol/path search still works.
- `llm.provider = "none"`: no standalone answer generation yet.
- `runtime.privacy_mode = true`: prefer local/private behavior by default.

## SQLite Index

`projectlens index` saves the scanner output into a local SQLite database under
`.projectlens/index.sqlite`.

```powershell
projectlens index C:\path\to\repo
projectlens status C:\path\to\repo
projectlens search "database connection" C:\path\to\repo --indexed
```

The index stores repository metadata, files, Python symbols, imports, code
chunks, and embedding vectors when they have been built.

## Embeddings

Embeddings turn text or code chunks into numeric vectors so ProjectLens can find
meaning-related code, not only exact word matches.

There are three separate states:

- Package available: the Python dependency exists.
- Model cached: the configured local model is already downloaded and loadable.
- Embeddings built: vectors for this repository have been written to SQLite.

ProjectLens keeps these states separate so a full repository build does not hang
silently while trying to download a model.

```powershell
projectlens embed status .
projectlens embed test .
projectlens embed test . --download-model
projectlens embed build .
projectlens embed build . --limit 5
projectlens search "database connection" . --semantic
```

Install local embedding support when you are ready to download and run the local
model:

```powershell
python -m pip install "projectlens-ai[local-embeddings]"
```

The default local model is `sentence-transformers/all-MiniLM-L6-v2`. It is free
and keeps code chunks on your machine. `projectlens embed test .` checks only the
local cache. `projectlens embed test . --download-model` explicitly allows the
first model download. For reliability on Windows/local setups, ProjectLens
sets `HF_HUB_DISABLE_XET=1` by default unless the user has already configured
that environment variable.

OpenAI embeddings can be enabled later with:

```powershell
projectlens config set embedding.backend openai .
```

## Local Search

`projectlens search` is the first retrieval layer, a language capability report, retrieval evals, and a stdio MCP server for AI clients. Without `--semantic`, it does
not call an LLM and does not require embeddings. It combines three cheap
signals:

- keyword matches in file contents,
- symbol matches in Python function/class names,
- path matches in filenames and folders.

```powershell
projectlens search "database connection" C:\path\to\repo
```

With `--semantic`, ProjectLens uses stored embedding vectors from SQLite. That
mode requires `projectlens embed build` to have completed for the active backend
and model.

Hybrid search is available through `--hybrid`. It combines keyword, symbol, path,
semantic score, file role, and role-aware reranking. Normal implementation
questions prefer source code over tests unless the query is explicitly about
tests.
## Source-Grounded Ask

`projectlens ask` does not call an LLM yet. It uses hybrid search to retrieve the
most relevant files and chunks, then prints source evidence with file paths and
line numbers.

```powershell
projectlens ask "where is configuration handled?" C:\path\to\repo
```

This is intentionally conservative: ProjectLens shows grounded evidence first,
then a future LLM-backed mode can write a natural-language answer from that
evidence.

## Repository Pack

`projectlens pack` creates a structured Markdown file containing the repository
summary, directory tree, important files, detected symbols, warnings, and safe
file contents.

Use it when another AI assistant cannot directly access your local repository
but can accept a Markdown file as context.

```powershell
projectlens pack C:\path\to\repo -o repo-pack.md
```



## Evaluation

`projectlens eval` measures whether ProjectLens can find expected files for
codebase-understanding questions. It uses a JSON answer key: each case contains a
query and one or more expected paths.

```powershell
projectlens eval .
projectlens eval . --cases docs/eval/projectlens-self.json
projectlens eval . --json
```

The eval report shows search rank, whether `ask` cited the expected source file,
and a confidence label. Confidence is intentionally conservative: fallback-only
languages or lower-ranked hits are reported as medium or low instead of being
presented as perfect answers.
## MCP Integration

ProjectLens can run as a stdio MCP server. MCP clients start the command as a
child process and call ProjectLens tools through standard input/output. The
server exposes the same local-first capabilities as the CLI:

- `projectlens_repository_overview`
- `projectlens_scan_repository`
- `projectlens_index_repository`
- `projectlens_language_capabilities`
- `projectlens_status`
- `projectlens_search_code`
- `projectlens_ask_codebase`
- `projectlens_run_checks`
- `projectlens_run_eval`

Install the optional MCP dependency:

```powershell
python -m pip install -e ".[mcp]"
```

Start the server manually only for smoke testing. In normal use, the MCP client
starts it for you:

```powershell
projectlens-mcp --root C:\path\to\repo
```

A Codex-style TOML configuration generally needs a command and args entry like
this:

```toml
[mcp_servers.projectlens]
command = "projectlens-mcp"
args = ["--root", "C:\\path\\to\\repo"]
```

Claude Desktop and Cursor use the same idea: point their MCP configuration to
the `projectlens-mcp` command and pass `--root` with the repository path.

## MCP Prompt Examples

When ProjectLens is connected to an MCP client, users do not need to know the
low-level `scan`, `index`, or `search` commands. For broad repository
understanding, the client should start with `projectlens_repository_overview` as
a planning map. Quick summaries may stop there; deep or source-cited answers
should continue with focused search or ask calls. After overview, clients should
avoid repeating scan/status/capabilities calls unless the user asks for the raw
output or a field is missing.

Start with the compact overview when you want a fast first answer:

```text
Use ProjectLens to inspect this repository:
C:\path\to\repo

Start with the compact overview tool first. Then explain in simple Turkish:
- what the project does
- how to run it
- which files matter most
- what architecture or patterns it uses
```

Minimal prompt also works:

```text
Use ProjectLens to inspect this repository:
C:\path\to\repo

Explain in simple Turkish:
- what the project does
- how to run it
- which files matter most
- what architecture or patterns it uses
```

For Turkish users asking about English code, it can help to ask the client to
translate the natural-language question into technical search queries before
calling ProjectLens:

```text
ProjectLens ile şu repoyu incele:
C:\path\to\repo

Bana Türkçe cevap ver. ProjectLens araması yaparken Türkçe sorularımı İngilizce
teknik query'lere çevir. Örneğin "veritabanı bağlantısı" için "database
connection", "sqlite connect", "db config" gibi birkaç sorgu varyasyonu dene.
Cevabında kullandığın dosya/satır kaynaklarını belirt.
```
## Roadmap

1. Repo scanner and CLI foundation.
2. Symbol map and AI-friendly `pack` export.
3. SQLite index and hybrid search.
4. Source-grounded `ask` mode and prompt cookbook.
5. Config, cost/privacy status, and `doctor`.
6. Project checks and learning reports.
7. MCP integration.
7.5. Language support and capability reporting.
8. Eval system, final polish, and release readiness.
