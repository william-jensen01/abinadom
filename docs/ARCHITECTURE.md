# Architecture

## Data flow

```
 Church API ──fetch──▶ JSON files (committed) ─┐
                                               ├──build──▶ db/core.N.db
 BYU SCI release ──▶ db/sci/core.N.db (raw) ───┘           db/content.N.db
                                                               │
                                               run_pipeline ──▶ Weaviate ◀── server.py
```

- **`scripts/fetch.py`** is the only step that uses the network. It saves Church data (titles, callings, previews, topics) as JSON in the repo.
- **`scripts/build.py`** runs offline and can be repeated safely. It copies the raw SCI release, works out each talk's Church URI, merges in the JSON and writes `db/core.N.db` / `content.N.db`. `SCI_DB_VERSION` selects which release the code reads (`db/__init__.py`).
- **`scripts/run_pipeline.py`** takes each talk through the extractors and the loader. It resumes by skipping talks already in Weaviate; `--force` reprocesses them.
- **`server.py`** answers MCP tool calls (`search`, `get_talk`, `find_by_scripture`, `corpus_stats`, `get_talk_citations`) against Weaviate. Query embeddings come from the same llama-server as the load step.

See `docs/update/HOW_UPDATES_WORK.md` for when to run each step.

## Pipeline steps

| Step (in order) | Code | Output model |
|---|---|---|
| Talk metadata | `extractors/talk_metadata.py` | `models/talk_metadata.py` |
| Paragraphs | `extractors/paragraphs.py` | `models/paragraph_data.py` |
| Citations | `extractors/citations.py` | `models/citation_data.py` |
| Footnotes | `extractors/footnotes.py` | `models/footnote_data.py` |
| Validation | `extractors/validation.py` | `models/validation_report.py` |
| Load | `loaders/` | Weaviate collections |

- `extractors/pipeline.py` runs paragraphs → citations → footnotes for one talk, parsing each paragraph's HTML once and sharing it through `ParagraphHTMLContext`.
- `loaders/shared_transforms.prepare_talk_bundle` turns a talk's step outputs into records and embeds them per talk in batches. The embedder (`config/embedding.py`) is injected into the loader. When diagnosing embedding behaviour, check what `run_pipeline.py` / `server.py` pass in.
- Collection names live in `config/pipeline_config.WEAVIATE_COLLECTION_NAMES`: `ConferenceTalks`, `ConferenceTalkParagraphs`, `ConferenceTalkCitations` and `ConferenceTalkFootnotes`.
- Weaviate UUIDs are `generate_uuid5(doc_id)`. The `doc_id` formats are `talk_{id}`, `para_{id}`, `cite_{citation_id}_{paragraph_id}` and `fn_{id}` (`loaders/shared_transforms.py`). That makes reloads overwrite instead of duplicating, and `server.py` looks talks up by the same IDs. Changing a format breaks both.

## SQLite layer

`db/__init__.py` gives every query a 5-second limit (`DEFAULT_TIMEOUT`). When a query hits the limit, `select` logs a warning and returns `[]`; it does not raise. An empty result can therefore mean the query was too slow.

## Embeddings

`config/embedding.py` calls llama-server (`nomic-embed-text`) at `EMBEDDING_URL`. nomic needs a task prefix:
- Loading embeds with `task="document"`, which is the default.
- The server embeds queries with `task="query"`.

Using the wrong one raises no error; search results just get worse.

## Server

- **Transport:** HTTP on `FASTMCP_HOST:FASTMCP_PORT` (default port 7363), with a `/health` route.
- **Auth:** ScaleKit OAuth is enabled only when `SCALEKIT_ENVIRONMENT_URL`, `SCALEKIT_RESOURCE_ID` and `MCP_BASE_URL` are all set. Otherwise the server runs in local mode with no auth.
- **Startup:** the server checks the embedding server and that every Weaviate collection exists and isn't empty.

