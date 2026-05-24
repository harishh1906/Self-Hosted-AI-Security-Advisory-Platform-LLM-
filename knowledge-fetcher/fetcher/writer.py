"""
Knowledge Document Writer
Writes normalized documents as JSON files to the shared inbox volume.
Each batch gets a timestamped file to avoid conflicts.
"""
import os
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict
from fetcher.config import INBOX_PATH

logger = logging.getLogger(__name__)


def write_batch(documents: List[Dict], source: str) -> str:
    """
    Write a batch of documents to the inbox as a single JSON file.
    
    Args:
        documents: List of canonical knowledge documents
        source: Source identifier (e.g., "NVD", "CISA_KEV")
    
    Returns:
        Path to the written file
    """
    if not documents:
        logger.info(f"No documents to write for source: {source}")
        return ""
    
    os.makedirs(INBOX_PATH, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    filename = f"{source.lower()}_{timestamp}.json"
    filepath = os.path.join(INBOX_PATH, filename)
    
    batch = {
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "document_count": len(documents),
        "documents": documents
    }
    
    # Write atomically: write to temp file, then rename
    temp_path = filepath + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(batch, f, ensure_ascii=False, indent=2)
        
        os.replace(temp_path, filepath)
        
        logger.info(
            f"Wrote {len(documents)} documents to inbox",
            extra={
                "source": source,
                "filepath": filepath,
                "document_count": len(documents)
            }
        )
        return filepath
    except Exception as e:
        logger.error(f"Failed to write batch: {e}")
        # Cleanup temp file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise
