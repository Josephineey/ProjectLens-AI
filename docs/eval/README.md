# ProjectLens Eval Cases

Eval cases are small answer keys for repository retrieval quality.

Each case asks one natural-language question and lists the file or files that
ProjectLens should find near the top of the ranked results. This makes retrieval
quality measurable instead of purely subjective.

## Format

```json
{
  "name": "my-repo-eval",
  "cases": [
    {
      "id": "database-config",
      "query": "where is the database connection configured?",
      "expected_paths": ["src/database.py"],
      "top_k": 5,
      "require_ask_source": true
    }
  ]
}
```

## Run

```powershell
projectlens eval . --cases docs/eval/projectlens-self.json
projectlens eval . --cases docs/eval/projectlens-self.json --json
```

Eval is not a replacement for unit tests. It checks whether ProjectLens can find
and cite the expected files for codebase-understanding questions.