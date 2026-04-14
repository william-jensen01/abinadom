"""
Shared ChromaDB HTTP client factory.

Reads connection settings from environment variables:
    CHROMADB_HOST  — hostname or IP of the ChromaDB server (default: localhost)
    CHROMADB_PORT  — port number (default: 8000)

Both server.py and the Phase 6 loader import from here so connection config lives in one place.
"""

import os

import chromadb


def get_chromadb_client() -> chromadb.HttpClient:
    """
    Return an HttpClient connected to the ChromaDB server.

    Connection parameters are read from environment variables:
        CHROMADB_HOST  (default: "localhost")
        CHROMADB_PORT  (default: 8000)
    """
    host = os.environ.get("CHROMADB_HOST", "localhost")
    port = int(os.environ.get("CHROMADB_PORT", "8000"))
    return chromadb.HttpClient(host=host, port=port)
