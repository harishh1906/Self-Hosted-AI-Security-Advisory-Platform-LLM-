"""
Knowledge Ingestion Audit Logger
Records every ingestion event to PostgreSQL for compliance tracking.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import sessionmaker, declarative_base
from ingester.config import DATABASE_URL

logger = logging.getLogger(__name__)

Base = declarative_base()


class KnowledgeIngestionLog(Base):
    """Audit trail for every knowledge ingestion event."""
    __tablename__ = "knowledge_ingestion_logs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False, index=True)
    batch_file = Column(String(255), nullable=False)
    documents_total = Column(Integer, nullable=False, default=0)
    documents_created = Column(Integer, nullable=False, default=0)
    documents_updated = Column(Integer, nullable=False, default=0)
    documents_skipped = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="success")
    error = Column(Text, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Database setup
_engine = None
_SessionLocal = None


def _get_engine():
    """Lazy engine creation to allow startup without DB."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine)
        # Create table if not exists
        Base.metadata.create_all(bind=_engine)
        logger.info("Audit database initialized")
    return _engine


def _get_session():
    """Get a database session."""
    _get_engine()
    return _SessionLocal()


def log_ingestion(
    source: str,
    batch_file: str,
    documents_total: int,
    documents_created: int,
    documents_updated: int,
    documents_skipped: int,
    status: str = "success",
    error: str = None,
    processing_time_ms: int = None
):
    """
    Record an ingestion event in the audit log.
    Non-blocking: failures are logged but don't stop processing.
    """
    try:
        session = _get_session()
        log_entry = KnowledgeIngestionLog(
            source=source,
            batch_file=batch_file,
            documents_total=documents_total,
            documents_created=documents_created,
            documents_updated=documents_updated,
            documents_skipped=documents_skipped,
            status=status,
            error=error[:2000] if error else None,
            processing_time_ms=processing_time_ms
        )
        session.add(log_entry)
        session.commit()
        session.close()
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")


def get_ingestion_stats() -> dict:
    """Get summary statistics from the ingestion audit log."""
    try:
        session = _get_session()
        from sqlalchemy import func as sqlfunc

        total_runs = session.query(sqlfunc.count(KnowledgeIngestionLog.id)).scalar() or 0
        total_created = session.query(
            sqlfunc.sum(KnowledgeIngestionLog.documents_created)
        ).scalar() or 0
        total_updated = session.query(
            sqlfunc.sum(KnowledgeIngestionLog.documents_updated)
        ).scalar() or 0
        last_run = session.query(
            sqlfunc.max(KnowledgeIngestionLog.created_at)
        ).scalar()
        error_count = session.query(
            sqlfunc.count(KnowledgeIngestionLog.id)
        ).filter(KnowledgeIngestionLog.status == "error").scalar() or 0

        session.close()

        return {
            "total_ingestion_runs": total_runs,
            "total_documents_created": int(total_created),
            "total_documents_updated": int(total_updated),
            "total_errors": error_count,
            "last_ingestion_at": last_run.isoformat() if last_run else None
        }
    except Exception as e:
        logger.error(f"Failed to get ingestion stats: {e}")
        return {"error": str(e)}
