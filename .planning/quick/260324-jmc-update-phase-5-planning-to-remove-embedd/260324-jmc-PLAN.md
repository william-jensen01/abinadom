---
id: 260324-jmc
type: quick
autonomous: true
description: "Update Phase 5 (ChromaDB Loader) planning documents to remove embedding concerns -- ChromaDB will store documents and metadata without automatic embedding. Embedding will be handled separately."
---

# Quick Task: Update Phase 5 Planning to Remove Embedding

## Objective

Rewrite all Phase 5 planning documents (CONTEXT, RESEARCH, DISCUSSION-LOG, VALIDATION, and all 3 PLANs) to remove references to embedding. ChromaDB will be used as a document + metadata store without automatic vector embedding. The "document text" decisions (D-01 through D-04) become about what text to store, not what to embed. The default `all-MiniLM-L6-v2` embedding model references are removed. The verification plan's "sample semantic queries" section is removed or replaced with document retrieval checks.

## Tasks

### Task 1: Update 05-CONTEXT.md -- remove embedding language from decisions
- Rename "Document Text (What to Embed)" to "Document Text (What to Store)"
- Update D-01 through D-04 to say "store" instead of "embed"
- Update D-07 to remove "not embedded"
- Update D-09 to remove "even though the parent paragraph is not embedded"
- Remove "Embedding function choice" from Claude's Discretion
- Update specifics to remove "Embedding quality" language

### Task 2: Update 05-RESEARCH.md -- remove embedding references
- Update constraint echoes of D-01 through D-04
- Remove embedding function choice from discretion
- Remove embedding model comparison rows
- Update any "embed" language to "store"

### Task 3: Update 05-DISCUSSION-LOG.md -- rename embed section
- Rename "Document Text (What to Embed)" to "Document Text (What to Store)"
- Remove "Embedding function choice" from Claude's Discretion

### Task 4: Update 05-01-PLAN.md -- remove embedding language from transformation plan
- Update objective and context interfaces
- Remove "embed" language from behavior and action sections
- Ensure "documents" field is described as stored text, not embedded text

### Task 5: Update 05-02-PLAN.md -- remove embedding references from insertion plan
- Update "Document texts to embed" in docstrings
- Update batch_embeddings references (these come from ChromaDB API, keep as API artifact)

### Task 6: Update 05-03-PLAN.md -- replace semantic query verification with document retrieval
- Remove "sample semantic queries" from verification report (requires embeddings)
- Replace with document retrieval verification (get by ID, verify content)
- Update tests to match

### Task 7: Update ROADMAP.md Phase 5 description if needed

## Verification

All files updated consistently. No remaining references to "embed" in the context of this system choosing to embed (ChromaDB API terms like `batch_embeddings` in tuple unpacking are acceptable as they come from the API).
