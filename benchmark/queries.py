"""
Canonical query set for the vector DB benchmark.

CANONICAL_QUERIES is the standard workload run against all three DBs
(ChromaDB, Weaviate, Qdrant) to produce comparable recall@k scores.

All queries use k=10 (D-08). Paragraph queries cover 4 doctrinal themes
(D-09). Citation queries include at least one filtered query (D-10).
"""

from typing import Any

# 8 entries: 6 paragraph queries (>=5 required) + 2 citation queries (>=2 required).
# Total >=7 required by SPEC Req 6.
CANONICAL_QUERIES: list[dict[str, Any]] = [
    # --- Theme 1: Doctrinal core (faith, atonement, resurrection) ---
    {
        "query_text": "the Atonement of Jesus Christ brings healing and hope to all who repent",
        "k": 10,
        "collection": "paragraphs",
        "filter": None,
    },
    {
        "query_text": "faith in the resurrection of Jesus Christ overcomes death and despair",
        "k": 10,
        "collection": "paragraphs",
        "filter": None,
    },
    # --- Theme 2: Scripture application (prophets applying scripture in teaching) ---
    {
        "query_text": "how the prophets applied the scriptures to teach eternal truths to the Saints",
        "k": 10,
        "collection": "paragraphs",
        "filter": None,
    },
    # --- Theme 3: Historical and prophetic events ---
    {
        "query_text": "the restoration of the gospel through the Prophet Joseph Smith",
        "k": 10,
        "collection": "paragraphs",
        "filter": None,
    },
    # --- Theme 4: Practical living (family, temple, missionary) ---
    {
        "query_text": "family prayer and scripture study strengthen the home and bring the Spirit",
        "k": 10,
        "collection": "paragraphs",
        "filter": None,
    },
    {
        "query_text": "temple worship and missionary service as expressions of faithful discipleship",
        "k": 10,
        "collection": "paragraphs",
        "filter": None,
    },
    # --- Citation queries ---
    # D-10: At least one citation query uses filter={"book_name": "John"}
    {
        "query_text": "light of the world",
        "k": 10,
        "collection": "citations",
        "filter": {"book_name": "John"},
    },
    {
        "query_text": "love one another as I have loved you",
        "k": 10,
        "collection": "citations",
        "filter": None,
    },
]
