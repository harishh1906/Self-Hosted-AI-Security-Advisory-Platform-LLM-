import os
import uuid
import logging
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    Filter, FieldCondition, MatchValue, FilterSelector
)

logger = logging.getLogger(__name__)

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = "security_knowledge"

client = QdrantClient(
    host=QDRANT_HOST,
    port=QDRANT_PORT,
)

def init_collection():
    collections = client.get_collections().collections
    if COLLECTION_NAME not in [c.name for c in collections]:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=384,
                distance=Distance.COSINE
            )
        )

def upsert_document(doc_id: str, vector: list[float], payload: dict):
    """
    Qdrant requires numeric or UUID point IDs.
    Store human-readable IDs inside payload.
    """
    point_id = str(uuid.uuid4())

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    **payload,
                    "source_id": doc_id
                }
            )
        ]
    )

def search_similar(vector: list[float], limit: int = 5, org_id: str = None):
    """
    CRITICAL FIX: Make Qdrant fully multi-tenant by filtering by org_id.
    If org_id is provided, only return results for that organization.
    """
    query_filter = None
    if org_id:
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="org_id",
                    match=MatchValue(value=org_id)
                )
            ]
        )
    
    return client.search(
        collection_name=COLLECTION_NAME,
        query_vector=vector,
        query_filter=query_filter,  # Multi-tenant isolation
        limit=limit
    )


# ── Knowledge Base Management Functions ──
# Used by knowledge-ingester service and admin API endpoints

def document_exists(source_id: str) -> bool:
    """Check if a document with this source_id already exists in Qdrant."""
    try:
        results = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(must=[
                FieldCondition(
                    key="source_id",
                    match=MatchValue(value=source_id)
                )
            ]),
            limit=1
        )
        return len(results[0]) > 0
    except Exception as e:
        logger.warning(f"Dedup check failed for {source_id}: {e}")
        return False


def delete_by_source_id(source_id: str) -> bool:
    """Delete existing document(s) by source_id. Returns True if successful."""
    try:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(must=[
                    FieldCondition(
                        key="source_id",
                        match=MatchValue(value=source_id)
                    )
                ])
            )
        )
        logger.info(f"Deleted document: {source_id}")
        return True
    except Exception as e:
        logger.error(f"Delete failed for {source_id}: {e}")
        return False


def get_collection_stats() -> dict:
    """Get Qdrant collection statistics for admin/monitoring."""
    try:
        info = client.get_collection(COLLECTION_NAME)
        return {
            "collection": COLLECTION_NAME,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": info.status.value if info.status else "unknown"
        }
    except Exception as e:
        logger.error(f"Failed to get collection stats: {e}")
        return {"collection": COLLECTION_NAME, "error": str(e)}


def search_knowledge(query_vector: list[float], limit: int = 10, source: str = None) -> list:
    """
    Search knowledge base with optional source filter.
    Used by admin debug endpoint.
    """
    query_filter = None
    if source:
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="source",
                    match=MatchValue(value=source)
                )
            ]
        )
    
    return client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        query_filter=query_filter,
        limit=limit
    )
