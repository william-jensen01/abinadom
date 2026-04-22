---
phase: 21-db-loaders
verified: 2026-04-22T23:00:00Z
status: human_needed
score: 12/13 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run integration tests against live Docker instances — docker compose -f infra/docker-compose.vector-dbs.yml up -d, then pipenv run py -m pytest tests/test_loaders_chromadb.py tests/test_loaders_weaviate.py tests/test_loaders_qdrant.py -v"
    expected: "All 3 round-trip tests pass — each test inserts a TalkBundle (talk_id=9999) and queries back a record with matching talk_id in metadata"
    why_human: "Docker is not running in CI; port-check fixtures skip the tests automatically; round-trip correctness (upsert + query returns expected data) cannot be verified without the live DB instances"
---

# Phase 21: DB Loaders Verification Report

**Phase Goal:** Deliver standalone DB loaders (ChromaDB, Weaviate, Qdrant) that accept pre-computed embedding vectors and load TalkBundles into benchmark vector database instances — completing the loader layer so Phase 22 can run the benchmark harness against all three DBs.
**Verified:** 2026-04-22T23:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | weaviate-client==4.20.5 and qdrant-client==1.17.1 are installed and importable | VERIFIED | `import weaviate; import qdrant_client` exits 0 and prints OK; Pipfile contains pinned entries |
| 2 | tests/test_phase6.py passes with zero failures — all unpack sites updated to 4-element form | VERIFIED | 73 passed (test_shared_transforms.py + test_phase6.py); `grep "doc, meta, doc_id = " tests/test_phase6.py` returns 0 |
| 3 | tests/conftest.py provides 5 session-scoped port-check and talk_bundle fixtures | VERIFIED | 5 `scope="session"` decorators found at lines 34, 41, 48, 55, 171 |
| 4 | All prepare_* functions return 4-element (doc, meta, id, vector|None) tuples | VERIFIED | `prepare_talk_bundle_rich` called with mock_embed produces tuples with vector len=768; backward compat: embed_fn=None default confirmed |
| 5 | prepare_talk_bundle_rich() metadata preserves Python lists (topics, verse_list) | VERIFIED | `rich_metadata({'topics': ['Grace', 'Faith']})` preserves list type; confirmed programmatically |
| 6 | BaseLoader ABC is importable from loaders and enforces load(bundle) -> None | VERIFIED | `list(BaseLoader.__abstractmethods__)` returns `['load']` |
| 7 | embed() helper in loaders/embeddings.py returns list[float] of length 768 | VERIFIED | test_embeddings.py: 3 passed (2 mock tests + live Ollama test); `def embed` and `OLLAMA_URL` present |
| 8 | ChromaDBLoader accepts a TalkBundle with pre-computed vectors and upserts all 4 collections | VERIFIED | Class inherits BaseLoader; `load()` calls `prepare_talk_bundle_rich(*bundle, embed_fn=self.embed_fn)`; iterates all 4 CHROMADB_COLLECTION_NAMES keys |
| 9 | ChromaDBLoader is independent from extractors/phase6_chromadb_loader.py | VERIFIED | `grep "from extractors" loaders/chromadb_loader.py` returns 0 matches |
| 10 | WeaviateLoader creates 4 typed-schema classes with idempotent creation, generate_uuid5, failed_objects check, and close() | VERIFIED | `grpc_port=50051`, `generate_uuid5` import and usage, `col.batch.failed_objects` check, `def close()` — all confirmed in code |
| 11 | QdrantLoader creates 4 collections with COSINE distance, payload indexes, _str_to_uint64 hashing, original string in payload["_doc_id"] | VERIFIED | All patterns confirmed in code; `_str_to_uint64("para_1")` returns integer 8257259555650349213 |
| 12 | Backward compat gates (test_shared_transforms.py + test_phase6.py) pass after tuple extension | VERIFIED | 73 passed, 1 warning; no failures |
| 13 | Round-trip insert+query passes against live ChromaDB, Weaviate, and Qdrant instances | HUMAN NEEDED | Docker not running; tests auto-skip via port-check fixture (D-08); cannot verify without live DB |

**Score:** 12/13 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `Pipfile` | Pinned weaviate-client==4.20.5, qdrant-client==1.17.1 | VERIFIED | Both entries present under [packages] |
| `tests/conftest.py` | 5 session fixtures: chromadb_available, weaviate_available, qdrant_available, ollama_available, talk_bundle | VERIFIED | 5 session-scoped fixtures at lines 34, 41, 48, 55, 171 |
| `tests/test_loaders_chromadb.py` | ChromaDB round-trip test with chromadb_available + talk_bundle fixtures | VERIFIED | Class TestChromaDBLoader with test_round_trip_paragraph; skips cleanly when Docker not running |
| `tests/test_loaders_weaviate.py` | Weaviate near-vector test with teardown close() | VERIFIED | Class TestWeaviateLoader with teardown_method calling loader.close() |
| `tests/test_loaders_qdrant.py` | Qdrant vector search test with qdrant_available + talk_bundle fixtures | VERIFIED | Class TestQdrantLoader |
| `tests/test_embeddings.py` | embed() unit tests with mock and live fixtures | VERIFIED | 3 passed (mock + live Ollama; live runs because Ollama is running) |
| `loaders/shared_transforms.py` | 4-element tuples, _rich variants, prepare_talk_bundle_rich() | VERIFIED | All functions confirmed; 471 lines; substantive |
| `loaders/__init__.py` | BaseLoader ABC with abstract load() | VERIFIED | class BaseLoader(ABC); `@abstractmethod` on `load()`; `__abstractmethods__ == frozenset({'load'})` |
| `loaders/embeddings.py` | embed() helper calling Ollama | VERIFIED | `def embed`, `OLLAMA_URL = "http://localhost:11434"`, ollama.Client call |
| `loaders/chromadb_loader.py` | ChromaDBLoader(BaseLoader) | VERIFIED | class ChromaDBLoader(BaseLoader); substantive load() implementation |
| `loaders/weaviate_loader.py` | WeaviateLoader(BaseLoader) | VERIFIED | class WeaviateLoader(BaseLoader); substantive load() + _ensure_schema() + close() |
| `loaders/qdrant_loader.py` | QdrantLoader(BaseLoader) | VERIFIED | class QdrantLoader(BaseLoader); substantive load() + _ensure_collections() |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `loaders/chromadb_loader.py` | `loaders/shared_transforms.py` | `prepare_talk_bundle_rich(*bundle, embed_fn=self.embed_fn)` | WIRED | Line 65: direct call with bundle splat and embed_fn injection |
| `loaders/chromadb_loader.py` | `config/pipeline_config.py` | `CHROMADB_COLLECTION_NAMES[key]` | WIRED | Line 22 import; line 68 usage; values confirmed: conference_talks, conference_talk_paragraphs, etc. |
| `loaders/weaviate_loader.py` | `loaders/__init__.py` (BaseLoader) | `from loaders import BaseLoader` | WIRED | Line 25 import; WeaviateLoader(BaseLoader) at line 31 |
| `loaders/weaviate_loader.py` | `weaviate.util.generate_uuid5` | `uuid=generate_uuid5(doc_id)` | WIRED | Line 24 import; line 232 usage in batch.add_object |
| `loaders/qdrant_loader.py` | `_str_to_uint64` | `id=_str_to_uint64(doc_id)` | WIRED | Function defined at line 33; used at line 116 inside PointStruct |
| `tests/test_loaders_chromadb.py` | `tests/conftest.py` | `chromadb_available, talk_bundle` fixtures | WIRED | Test method signature accepts both fixtures; conftest.py provides them at session scope |
| `loaders/__init__.py` | `loaders/shared_transforms.py` | `from loaders.shared_transforms import TalkBundle` | WIRED | Line 14; TalkBundle used as type hint in BaseLoader.load() |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `loaders/chromadb_loader.py` | `records` dict | `prepare_talk_bundle_rich(*bundle, embed_fn=self.embed_fn)` | Yes — walks TalkBundle dataclasses, calls embed_fn per record, returns populated tuples | FLOWING |
| `loaders/weaviate_loader.py` | `records` dict | `prepare_talk_bundle_rich(*bundle, embed_fn=self.embed_fn)` | Yes — same as above; rich_metadata preserves list types for Weaviate arrays | FLOWING |
| `loaders/qdrant_loader.py` | `records` dict | `prepare_talk_bundle_rich(*bundle, embed_fn=self.embed_fn)` | Yes — same as above; payload extended with _doc_id and _doc for retrieval | FLOWING |
| `loaders/embeddings.py` | return value | `ollama.Client(host=url).embed(model=model, input=text).embeddings[0]` | Yes — live Ollama call; test_embeddings.py live test passes (Ollama running) | FLOWING |

Data-flow confirmed: `prepare_talk_bundle_rich` with a mock embed_fn produces records with talk_id=9999, paragraphs with vector len=768, and list-type metadata fields preserved.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| weaviate + qdrant_client importable | `pipenv run py -c "import weaviate; import qdrant_client; print('OK')"` | OK | PASS |
| BaseLoader ABC enforces load() | `pipenv run py -c "from loaders import BaseLoader; print(list(BaseLoader.__abstractmethods__))"` | `['load']` | PASS |
| ChromaDBLoader inherits BaseLoader | `pipenv run py -c "from loaders.chromadb_loader import ChromaDBLoader; print(ChromaDBLoader.__bases__)"` | `(<class 'loaders.BaseLoader'>,)` | PASS |
| WeaviateLoader inherits BaseLoader | `pipenv run py -c "from loaders.weaviate_loader import WeaviateLoader; print(WeaviateLoader.__bases__)"` | `(<class 'loaders.BaseLoader'>,)` | PASS |
| QdrantLoader _str_to_uint64 produces integer | `pipenv run py -c "from loaders.qdrant_loader import _str_to_uint64; print(_str_to_uint64('para_1'))"` | `8257259555650349213` | PASS |
| prepare_talk_bundle_rich produces real vectors | Full trace with mock embed (see Data-Flow section) | vector len=768, talk_id=9999 in meta | PASS |
| Backward compat tests | `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_phase6.py -x -q` | 73 passed | PASS |
| Embeddings tests | `pipenv run py -m pytest tests/test_embeddings.py -x -q` | 3 passed | PASS |
| Loader integration tests (no Docker) | `pipenv run py -m pytest tests/test_loaders_*.py -v` | 3 skipped (correct — D-08) | PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| BENCH-02 | 21-01, 21-02, 21-03 | User can load talk bundles into benchmark ChromaDB instance | SATISFIED | `loaders/chromadb_loader.py` exists with ChromaDBLoader(BaseLoader); load() confirmed wired to prepare_talk_bundle_rich + CHROMADB_COLLECTION_NAMES upsert |
| BENCH-03 | 21-01, 21-02, 21-04 | User can load talk bundles into Weaviate with schema creation and UUID mapping | SATISFIED | `loaders/weaviate_loader.py` exists; _ensure_schema() creates 4 typed classes; generate_uuid5 used; grpc_port=50051; failed_objects checked; close() present |
| BENCH-04 | 21-01, 21-02, 21-05 | User can load talk bundles into Qdrant with collection creation and payload indexes | SATISFIED | `loaders/qdrant_loader.py` exists; _ensure_collections() creates 4 collections with COSINE+768; payload indexes for talk_id/conference_year/speaker_name; _str_to_uint64 for point IDs; _doc_id in payload |

No orphaned requirements: REQUIREMENTS.md traceability maps BENCH-02, BENCH-03, BENCH-04 to Phase 21 only. BENCH-01/05/06 map to Phase 20 and are correctly absent from Phase 21 plans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `loaders/chromadb_loader.py` | 54 | `# Do NOT pass embedding_function=` comment | Info | Intentional — correctly documents Pitfall 4 avoidance; not a stub |

No TODO, FIXME, PLACEHOLDER, empty returns, or hardcoded stubs found in any loader file. All `return {}` instances are guarded by `not validation_report.is_valid` checks (documented skip-and-log behavior per D-07).

### Human Verification Required

### 1. Round-Trip Integration Tests (All 3 DBs)

**Test:** Start Docker Compose with all three vector DBs (`docker compose -f infra/docker-compose.vector-dbs.yml up -d`), then run:
```
pipenv run py -m pytest tests/test_loaders_chromadb.py tests/test_loaders_weaviate.py tests/test_loaders_qdrant.py -v
```
**Expected:** All 3 tests pass. Each test:
- ChromaDB: inserts talk_id=9999 bundle, queries paragraphs collection, returns `talk_id == 9999` in metadata and `"para_"` in returned ID
- Weaviate: near_vector query on Paragraph class returns `props.get("talk_id") == 9999`
- Qdrant: query_points on paragraphs collection returns `payload["_doc_id"]` containing `"para_"` and `payload["talk_id"] == 9999`
**Why human:** Docker is not running. Port-check fixtures (D-08) auto-skip all 3 tests when target ports are unreachable. This is correct behavior per the design, but means round-trip correctness cannot be confirmed without the live services.

### Gaps Summary

No automated gaps. All 12 programmatically verifiable truths pass. The one pending item is the live Docker round-trip — this is a known design constraint (D-08) that requires running services to validate, not a code defect.

---

_Verified: 2026-04-22T23:00:00Z_
_Verifier: Claude (gsd-verifier)_
