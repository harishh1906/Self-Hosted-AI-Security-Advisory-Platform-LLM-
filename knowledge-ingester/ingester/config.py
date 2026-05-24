"""
Knowledge Ingester Configuration
All settings driven by environment variables for Docker deployment.
"""
import os

# ── Qdrant ──
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = "security_knowledge"

# ── PostgreSQL ──
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://virtue:virtuepass@postgres:5432/virtue"
)

# ── Inbox ──
INBOX_PATH = os.getenv("INBOX_PATH", "/data/knowledge-inbox")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
PROCESSED_DIR = os.path.join(INBOX_PATH, ".processed")

# ── Embedding ──
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

# ── Safety ──
MAX_TEXT_LENGTH = 10000
BATCH_SIZE = 50  # Upsert in batches of 50 to Qdrant
