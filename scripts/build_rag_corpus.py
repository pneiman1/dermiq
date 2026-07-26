"""Build + embed the RAG knowledge corpus and write it to Snowflake.

Reads the marts, generates the document set (dermiq.rag.corpus), embeds each with
the local sentence-transformers model, and full-refreshes the rag_corpus table.
Run manually or on a schedule (airflow/dags/weekly_rag_refresh.py). See ADR-008.
"""
from __future__ import annotations

from platform_core.config import get_settings
from platform_core.rag import Embedder, RagDocument, write_corpus
from platform_core.utils.logging import configure_logging, get_logger
from platform_core.warehouse.connection import get_snowflake_connection

from dermiq.rag.corpus import build_documents

log = get_logger(__name__)


def main() -> None:
    configure_logging()
    settings = get_settings()
    tenant = settings.default_tenant_id

    with get_snowflake_connection(database=settings.snowflake_database) as conn:
        docs = build_documents(conn, tenant)
        embedder = Embedder()
        vectors = embedder.encode([d["text"] for d in docs])
        rag_docs = [
            RagDocument(
                doc_id=d["doc_id"],
                title=d["title"],
                source=d["source"],
                text=d["text"],
                embedding=vectors[i].tolist(),
            )
            for i, d in enumerate(docs)
        ]
        n = write_corpus(conn, rag_docs, tenant)

    print(f"\n=== RAG corpus built: {n} documents embedded + written (dim={vectors.shape[1]}) ===")
    for d in docs:
        print(f"  [{d['source']:<34}] {d['title']}")


if __name__ == "__main__":
    main()
