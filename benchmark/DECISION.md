# Vector DB Benchmark Decision

## Decision: Weaviate

> **Weaviate** is selected for Phase 24 production migration.

Weaviate outperforms both ChromaDB and Qdrant across every latency dimension that matters for interactive MCP use: serial p50 of 42ms beats ChromaDB's 51ms and Qdrant's 93ms; filtered query p50 of 51ms is 4x faster than ChromaDB's 220ms; cold-start of 34ms is the lowest of the three. It also achieves the highest concurrency throughput (215 q/s), near-zero memory overhead during upsert (0.02 MB), and passes the ANN fidelity gate at recall@k10=0.9875.

---

## Metric Comparison

| Metric | ChromaDB | Weaviate | Qdrant |
|--------|----------|----------|--------|
| Upsert speed (rec/s) | 1.06 | 4.41 | 4.38 |
| Upsert time (s) | 5490.3 | 1323.7 | 1333.4 |
| Serial p50 (ms) | 51.23 | 42.26 | 93.40 |
| Serial p95 (ms) | 220.02 | 51.00 | 234.95 |
| Serial p99 (ms) | 223.39 | 54.76 | 243.45 |
| Unfiltered p50 (ms) | 50.97 | 43.66 | 93.02 |
| Filtered p50 (ms) | 220.12 | 51.26 | 234.49 |
| Concurrency p50 (ms) | 67.79 | 88.56 | 91.21 |
| Concurrency throughput (q/s) | 177.24 | 214.82 | 175.87 |
| Memory delta (MB) | 116.05 | 0.02 | 70.39 |
| Cold-start (ms) | 63.81 | 33.70 | 114.96 |
| Warm mean (ms) | 51.34 | 31.19 | 77.65 |
| Determinism (stddev ms) | 1.0 (exact) | 1.0 (exact) | 1.0 (exact) |
| recall@k10 | baseline | 0.9875 | 0.975 |
| recall@k50 | baseline | 0.9725 | 0.9725 |

---

## Dimension Analysis

### Upsert Speed

Weaviate (4.41 rec/s, 1323.7s) and Qdrant (4.38 rec/s, 1333.4s) are essentially tied, both loading all 5,838 talks in roughly 22 minutes. ChromaDB was dramatically slower at 1.06 rec/s (5490.3s — over 1.5 hours), consistent with its known single-threaded Python HTTP client behavior under concurrent inserts. For production migration, Weaviate's upsert speed is 4.2x faster than ChromaDB.

### Query Latency (Serial)

Weaviate achieves the lowest p50 (42.3ms), p95 (51.0ms), and p99 (54.8ms) of the three — notably, its p95 and p99 are lower than ChromaDB's p50 (51.2ms). Qdrant's serial p50 (93.4ms) is 2.2x higher than Weaviate and its tail latencies (p95=235ms, p99=243ms) are the worst of the group. ChromaDB's tail behavior (p95=220ms, p99=223ms) is also poor, likely reflecting GIL contention and ChromaDB's Python-based query path.

### Unfiltered vs Filtered Latency

All three DBs show minimal overhead for unfiltered queries (pure ANN path). The critical difference appears in filtered queries: Weaviate handles metadata-filtered queries at 51.3ms — comparable to its unfiltered p50 (43.7ms), a difference of only 7.6ms. ChromaDB's filtered p50 (220.1ms) is 4.3x slower than its unfiltered path, and Qdrant's filtered p50 (234.5ms) is 2.5x slower than its unfiltered path. Since the MCP `search` tool uses metadata filters (speaker, year, session), this dimension is operationally significant. Weaviate's pre-filtering index design makes it the clear winner here.

### Concurrency

Under 20-worker concurrent load, Weaviate achieves the highest throughput (214.8 q/s) followed closely by ChromaDB (177.2 q/s) and Qdrant (175.9 q/s). Weaviate's p50 rises to 88.6ms at 20 workers (a 2.1x degradation ratio from serial) while ChromaDB's p50 rises to 67.8ms (1.3x degradation). However, this system is personal-use with no multi-user concurrency requirement — all three DBs comfortably exceed any realistic request rate for a single-user MCP tool. Weaviate's absolute throughput leadership is a bonus, not a requirement.

### Memory

Weaviate's upsert memory delta is effectively zero (0.02 MB), meaning it offloads all data immediately to its server-side storage. ChromaDB uses 116 MB of Python-side memory during upsert — significant for a machine also running Ollama. Qdrant uses 70.4 MB. At query time, all three use negligible additional memory. Weaviate's zero-copy upsert path is a clear win for co-hosting with Ollama on a personal machine.

### Cold-Start vs Warm Latency

Weaviate's cold-start (33.7ms) is the fastest, essentially matching its warm mean (31.2ms) — a 1.08x ratio indicating no meaningful cold-path penalty. ChromaDB's cold-start (63.8ms) is moderate, 1.24x above its warm mean (51.3ms). Qdrant's cold-start (114.96ms) is notable but represents a significant improvement from the smoke test anomaly (369ms). The full-run result suggests the 369ms smoke test cold-start was partly a first-query artifact under a lighter-loaded index — with 5,838 records fully indexed, Qdrant's cold-start settled to 115ms. While 115ms is still 3.4x slower than warm (77.7ms) and 3.4x slower than Weaviate's cold-start, it is within acceptable range for a personal-use system that restarts occasionally (a single slow first-query after restart is not user-facing in the MCP context). That said, Weaviate's 34ms cold-start eliminates even that concern.

### Determinism

All three databases returned a stability score of 1.0 across all 8 canonical queries — each DB returned the same neighbor set on every repeated execution. This is expected: ChromaDB uses exact kNN (deterministic by definition), while Weaviate and Qdrant's HNSW indexes happen to be deterministic at this corpus size and query distribution. No winner or loser here.

### ANN Fidelity (recall@k)

recall@k measures how closely Weaviate's and Qdrant's approximate nearest neighbor results match ChromaDB's exact kNN baseline. All three DBs use identical embedding vectors (nomic-embed-text via Ollama), so recall@k differences reflect HNSW index approximation variation, not differences in retrieval quality or semantic accuracy. A score of 1.0 means the ANN index returns the same neighbors as an exact search; values >= 0.95 indicate the ANN index is effectively exact for this workload.

Weaviate: recall@k10=0.9875, recall@k50=0.9725. Qdrant: recall@k10=0.975, recall@k50=0.9725. Both databases pass the ANN fidelity gate with comfortable margins — at k=10, Weaviate returns the correct top-10 neighbors 98.75% of the time, and Qdrant 97.5% of the time. The 1.25-percentage-point advantage for Weaviate at k10 is marginal in practice. Both DBs are effectively returning exact-kNN-quality results for this 5,838-talk corpus.

---

## Rationale

Weaviate wins on the metrics that directly affect MCP user experience: serial p50 (42ms, the best), p95/p99 tail latency (both under 55ms — dramatically better than ChromaDB's 220ms and Qdrant's 235ms), filtered query latency (51ms vs 4–5x higher for the others), cold-start (34ms, lowest), warm mean (31ms, lowest), and concurrency throughput (215 q/s, highest). The only dimension where Weaviate does not lead is concurrency p50 under 20-worker load (89ms vs ChromaDB's 68ms), which is irrelevant for a personal-use single-user system. Qdrant is disqualified from first place by its serial p50 of 93ms (2.2x Weaviate) and filtered p50 of 234ms (4.6x Weaviate) — both would produce noticeably sluggish MCP responses. ChromaDB's poor tail latency (p95/p99 around 220ms), 4x slower upsert, and 116MB memory overhead during migration make it the weakest option despite being the incumbent. All three DBs pass the ANN fidelity gate; correctness is not a differentiator.

---

## Phase 24 Notes

**Schema management:** Weaviate collections are schema-bound. The four collection schemas (Talks, Paragraphs, Citations, Footnotes) were established in `loaders/weaviate_loader.py` via `_ensure_schema()`. If new metadata properties need to be added in a future phase, Weaviate requires collection deletion and recreation (or a schema migration) — properties cannot be added to existing collections without downtime. Phase 24 should finalize the schema before migration to avoid this.

**Upsert path for production migration:** The production pipeline uses `extractors/phase6_chromadb_loader.py`. Phase 24 will need to either (a) wire `loaders/weaviate_loader.py` into `scripts/run_pipeline.py` as a replacement loader, or (b) run the benchmark loader's upsert path (`benchmark/runner.py --db weaviate --reset`) directly against the production Docker instance. Option (b) is simpler and already validated by this benchmark run.

**Collection name constants:** `loaders/weaviate_loader.py` uses its own class-name constants. Phase 24 should verify these align with `config/pipeline_config.py` collection name constants or consolidate them to avoid drift.

**Docker stack:** The benchmark run used `infra/docker-compose.vector-dbs.yml`. The production migration will need to update `docker-compose.yml` (the MCP server stack) to add a Weaviate service, and `server.py` to replace the ChromaDB client with the Weaviate client via `loaders/weaviate_loader.py`.
