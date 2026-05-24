"""
Knowledge Base Admin API Router
Provides endpoints for monitoring, searching, and managing the knowledge base.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from app.auth.dependencies import get_current_user_or_service
from app.embedding import embed_text
from app.vector_store import (
    get_collection_stats,
    search_knowledge,
    delete_by_source_id,
    document_exists
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.get("/stats")
def knowledge_stats(identity: dict = Depends(get_current_user_or_service)):
    """
    Get knowledge base statistics.
    
    Returns:
    - Qdrant collection stats (document count, vector count)
    - Ingestion audit stats (if available)
    """
    # Qdrant stats
    qdrant_stats = get_collection_stats()
    
    # Ingestion stats from PostgreSQL
    ingestion_stats = _get_ingestion_stats_safe()
    
    return {
        "qdrant": qdrant_stats,
        "ingestion": ingestion_stats
    }


@router.get("/search")
def knowledge_search(
    query: str = Query(..., min_length=3, max_length=500, description="Search query text"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    source: str = Query(None, description="Filter by source (NVD, CISA_KEV, CWE-20)"),
    identity: dict = Depends(get_current_user_or_service)
):
    """
    Search the knowledge base directly (debug/admin endpoint).
    
    Returns matching documents with scores.
    """
    try:
        query_vector = embed_text(query)
        results = search_knowledge(query_vector, limit=limit, source=source)
        
        return {
            "query": query,
            "source_filter": source,
            "results_count": len(results),
            "results": [
                {
                    "score": round(r.score, 4),
                    "source_id": r.payload.get("source_id", ""),
                    "source": r.payload.get("source", ""),
                    "title": r.payload.get("title", ""),
                    "severity": r.payload.get("severity", ""),
                    "text_preview": r.payload.get("text", "")[:300],
                    "tags": r.payload.get("tags", []),
                    "org_id": r.payload.get("org_id", ""),
                    "published_date": r.payload.get("published_date", ""),
                    "fetched_at": r.payload.get("fetched_at", "")
                }
                for r in results
            ]
        }
    except Exception as e:
        logger.error(f"Knowledge search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Knowledge search failed")


@router.delete("/{source_id}")
def knowledge_delete(
    source_id: str,
    identity: dict = Depends(get_current_user_or_service)
):
    """
    Delete a specific knowledge document by source_id.
    Requires authentication.
    """
    if not document_exists(source_id):
        raise HTTPException(status_code=404, detail=f"Document not found: {source_id}")
    
    success = delete_by_source_id(source_id)
    if not success:
        raise HTTPException(status_code=500, detail="Delete failed")
    
    logger.info(
        f"Knowledge document deleted via API",
        extra={
            "source_id": source_id,
            "deleted_by": identity.get("user_id") or identity.get("service_name")
        }
    )
    
    return {"status": "deleted", "source_id": source_id}


def _get_ingestion_stats_safe() -> dict:
    """Get ingestion stats from PostgreSQL (non-blocking)."""
    try:
        from sqlalchemy import func as sqlfunc, Column, Integer, String, Text, DateTime
        from sqlalchemy.orm import Session
        from app.db.database import SessionLocal
        
        db: Session = SessionLocal()
        try:
            # Check if table exists by trying a simple query
            result = db.execute(
                sqlfunc.text("SELECT COUNT(*) FROM knowledge_ingestion_logs")
            )
            total_runs = result.scalar() or 0
            
            result = db.execute(
                sqlfunc.text(
                    "SELECT SUM(documents_created), SUM(documents_updated), "
                    "MAX(created_at) FROM knowledge_ingestion_logs"
                )
            )
            row = result.fetchone()
            
            return {
                "total_ingestion_runs": total_runs,
                "total_documents_created": int(row[0] or 0) if row else 0,
                "total_documents_updated": int(row[1] or 0) if row else 0,
                "last_ingestion_at": row[2].isoformat() if row and row[2] else None
            }
        finally:
            db.close()
    except Exception:
        # Table may not exist yet (ingester hasn't run)
        return {"status": "ingester_not_initialized"}
