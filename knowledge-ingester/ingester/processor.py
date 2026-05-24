"""
Knowledge Document Processor
Reads JSON files from inbox, embeds text, deduplicates, and upserts to Qdrant.
"""
import uuid
import logging
from typing import List, Dict, Tuple
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    Filter, FieldCondition, MatchValue, FilterSelector
)
from ingester.config import (
    QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME,
    EMBEDDING_MODEL, EMBEDDING_DIMENSION,
    MAX_TEXT_LENGTH, BATCH_SIZE
)

logger = logging.getLogger(__name__)

# Load embedding model once
_model = SentenceTransformer(EMBEDDING_MODEL)

# Qdrant client
_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def ensure_collection():
    """Create Qdrant collection if it doesn't exist."""
    collections = _client.get_collections().collections
    if COLLECTION_NAME not in [c.name for c in collections]:
        _client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=EMBEDDING_DIMENSION,
                distance=Distance.COSINE
            )
        )
        logger.info(f"Created Qdrant collection: {COLLECTION_NAME}")


def embed_text(text: str) -> list:
    """Convert text to 384-dim embedding vector."""
    return _model.encode(text).tolist()


def document_exists(source_id: str) -> bool:
    """Check if a document with this source_id already exists in Qdrant."""
    try:
        results = _client.scroll(
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


def delete_by_source_id(source_id: str):
    """Delete existing document by source_id (for updates)."""
    try:
        _client.delete(
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
    except Exception as e:
        logger.warning(f"Delete failed for {source_id}: {e}")


def process_documents(documents: List[Dict]) -> Tuple[int, int, int]:
    """
    Process a list of canonical knowledge documents.
    
    Returns:
        Tuple of (created, updated, skipped) counts.
    """
    ensure_collection()
    
    created = 0
    updated = 0
    skipped = 0
    points_batch = []
    
    for doc in documents:
        source_id = doc.get("source_id", "")
        text = doc.get("text", "")
        
        if not source_id or not text:
            skipped += 1
            continue
        
        # Sanitize text length
        text = text[:MAX_TEXT_LENGTH]
        
        # Check for existing document
        exists = document_exists(source_id)
        
        if exists:
            # Update: delete old, insert new
            delete_by_source_id(source_id)
            updated += 1
        else:
            created += 1
        
        # Embed
        try:
            vector = embed_text(text)
        except Exception as e:
            logger.error(f"Embedding failed for {source_id}: {e}")
            skipped += 1
            continue
        
        # Build Qdrant payload
        payload = {
            "text": text,
            "source_id": source_id,
            "source": doc.get("source", "unknown"),
            "category": doc.get("category", "vulnerability"),
            "title": doc.get("title", "")[:500],
            "severity": doc.get("severity", "Medium"),
            "cvss_score": doc.get("cvss_score"),
            "cwe_ids": doc.get("cwe_ids", []),
            "affected_products": doc.get("affected_products", [])[:10],
            "remediation": doc.get("remediation", "")[:MAX_TEXT_LENGTH],
            "tags": doc.get("tags", []),
            "published_date": doc.get("published_date", ""),
            "org_id": doc.get("org_id", "global"),
            "fetched_at": doc.get("fetched_at", "")
        }
        
        points_batch.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload=payload
            )
        )
        
        # Upsert in batches
        if len(points_batch) >= BATCH_SIZE:
            _flush_batch(points_batch)
            points_batch = []
    
    # Flush remaining
    if points_batch:
        _flush_batch(points_batch)
    
    logger.info(
        f"Processing complete: {created} created, {updated} updated, {skipped} skipped"
    )
    return created, updated, skipped


def _flush_batch(points: List[PointStruct]):
    """Upsert a batch of points to Qdrant."""
    try:
        _client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )
        logger.debug(f"Flushed batch of {len(points)} points to Qdrant")
    except Exception as e:
        logger.error(f"Qdrant batch upsert failed: {e}", exc_info=True)
        raise


def get_collection_stats() -> Dict:
    """Get Qdrant collection statistics."""
    try:
        info = _client.get_collection(COLLECTION_NAME)
        return {
            "collection": COLLECTION_NAME,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": info.status.value if info.status else "unknown"
        }
    except Exception as e:
        logger.error(f"Failed to get collection stats: {e}")
        return {"collection": COLLECTION_NAME, "error": str(e)}
