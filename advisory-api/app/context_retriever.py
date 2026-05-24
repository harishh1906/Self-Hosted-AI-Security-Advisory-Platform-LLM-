import logging
from app.embedding import embed_text
from app.vector_store import search_similar
from app.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)

def retrieve_context(query: str, org_id: str = None) -> tuple[str, bool]:
    """
    CRITICAL FIX: Pass org_id to vector search for multi-tenant isolation.
    
    Circuit Breaker: Skips RAG if circuit is open (failure rate too high).
    
    Returns:
        tuple: (context_string, rag_available)
        - context_string: Retrieved context or empty string if unavailable
        - rag_available: True if RAG was successfully used, False if degraded mode
    """
    # Circuit breaker: Skip RAG if circuit is open
    if circuit_breaker.should_skip_rag():
        logger.info(
            "Circuit breaker open - skipping RAG",
            extra={
                "circuit_state": circuit_breaker.get_state()["state"]
            }
        )
        return "", False

    try:
        vector = embed_text(query)
        results = search_similar(vector, org_id=org_id)

        context = "\n".join(
            r.payload["text"] for r in results if "text" in r.payload
        )

        # If we used an org_id filter and got no matches, fall back to shared KB.
        if not context and org_id is not None:
            results = search_similar(vector, org_id="global")
            context = "\n".join(
                r.payload["text"] for r in results if "text" in r.payload
            )

        return context, bool(context)
    except Exception as e:
        # Graceful degradation: RAG unavailable but service continues
        logger.warning(
            f"RAG context retrieval failed (degraded mode)",
            extra={"error": str(e)}
        )
        return "", False
