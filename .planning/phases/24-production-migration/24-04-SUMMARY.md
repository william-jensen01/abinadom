---
plan: 24-04
phase: 24-production-migration
status: complete
wave: 1
tasks_total: 2
tasks_complete: 2
commits:
  - b29689b
  - c8d2381
key-files:
  modified:
    - config/pipeline_config.py
    - Pipfile
    - docker-compose.yml
    - infra/.env.example
    - .env.example
    - CLAUDE.md
  deleted:
    - config/chromadb_client.py
---

# Plan 24-04 Summary: Config + Infrastructure Cleanup

## Objective Achieved

All ChromaDB configuration replaced with Weaviate equivalents. Docker stack updated with
co-located Weaviate service. Production infrastructure ready for Weaviate pipeline (MIGR-03).

## Tasks Completed

### Task 1 -- Update pipeline_config.py, delete chromadb_client.py, update Pipfile
**Commit:** b29689b

- config/pipeline_config.py: CHROMADB_BATCH_SIZE/COLLECTION_NAMES replaced with
  WEAVIATE_BATCH_SIZE=50 and PascalCase WEAVIATE_COLLECTION_NAMES
  (ConferenceTalks, ConferenceTalkParagraphs, ConferenceTalkCitations, ConferenceTalkFootnotes)
- config/chromadb_client.py: deleted via git rm (pre-deletion check passed -- loaders/chromadb_loader.py
  imports chromadb directly, not from config/chromadb_client.py)
- Pipfile: chromadb and qdrant-client moved from [packages] to [dev-packages];
  production installs no longer pull in benchmark-only deps

### Task 2 -- Update docker-compose.yml, infra/.env.example, CLAUDE.md
**Commit:** c8d2381

- docker-compose.yml: weaviate service added (pinned 1.37.1), weaviate_data named volume,
  both services on proxy network; mcp-server gets depends_on: weaviate: condition: service_healthy
- infra/.env.example: WEAVIATE_HOST=weaviate, WEAVIATE_PORT=8080, WEAVIATE_GRPC_PORT=50051 added;
  CHROMADB_* vars removed
- .env.example: CHROMADB_DATA_PATH section replaced with WEAVIATE_HOST/PORT/GRPC_PORT vars
- CLAUDE.md: project structure index updated (chromadb_client.py out; weaviate_client.py in;
  phase6_chromadb_loader out; phase6_weaviate_loader in)

## Deviations

- Root .env.example also updated (deviation from plan scope which only specified infra/.env.example)
  because the root template also referenced CHROMADB_DATA_PATH. Orchestrator corrected apostrophe
  corruption introduced by the subagent before committing.

## Self-Check: PASSED

- docker compose config parses without error
- grep weaviate:1.37.1 docker-compose.yml -- 1 match
- grep weaviate_data docker-compose.yml -- 2 matches
- grep depends_on docker-compose.yml -- 1 match (service_healthy condition)
- grep WEAVIATE_HOST infra/.env.example -- 1 match
- grep CHROMADB infra/.env.example -- 0 matches
- from config.pipeline_config import WEAVIATE_COLLECTION_NAMES, WEAVIATE_BATCH_SIZE exits 0
- ls config/chromadb_client.py -- file not found (deleted)
- chromadb + qdrant-client in [dev-packages] only
