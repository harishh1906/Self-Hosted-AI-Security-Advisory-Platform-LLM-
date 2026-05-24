import os
import time
import torch
import logging
import threading
from sentence_transformers import SentenceTransformer

# Hardening: Force total offline mode to prevent hangs on HF Hub checks
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"

logger = logging.getLogger(__name__)
_lock = threading.Lock()

# Hardening: Force single-thread to avoid deadlocks
torch.set_num_threads(1)

# Load once per container - Force CPU and Local Only
logger.info("Initializing SentenceTransformer model (CPU mode)...")
_model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
logger.info("SentenceTransformer model loaded successfully.")

def embed_text(text: str) -> list[float]:
    """
    Convert input text into a 384-dimensional embedding vector with strict locking.
    """
    # Timeout prevents a hung encode() from holding the lock forever and
    # deadlocking all subsequent requests that wait to acquire it.
    if not _lock.acquire(timeout=30.0):
        raise TimeoutError("Embedding lock timed out after 30s — encode() may be stuck")
    try:
        start_time = time.perf_counter()
        logger.info(f"Embedding start... (text length: {len(text)})")
        vector = _model.encode(text, show_progress_bar=False)
        elapsed = time.perf_counter() - start_time
        logger.info(f"Embedding complete in {elapsed:.4f}s")
        return vector.tolist()
    except Exception as e:
        logger.error(f"Embedding generation failed: {str(e)}")
        raise
    finally:
        _lock.release()

