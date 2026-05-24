"""
Knowledge Ingester — Main Entry Point
Polls the inbox directory for new JSON files, processes them, and moves to .processed.
"""
import os
import sys
import json
import time
import shutil
import logging
from pathlib import Path
from ingester.config import INBOX_PATH, POLL_INTERVAL_SECONDS, PROCESSED_DIR
from ingester.processor import process_documents, get_collection_stats
from ingester.audit import log_ingestion

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("knowledge-ingester")


def process_inbox():
    """Scan inbox for new JSON files and process them."""
    inbox = Path(INBOX_PATH)
    if not inbox.exists():
        return
    
    # Find all .json files (not .tmp, not in .processed)
    json_files = sorted(
        f for f in inbox.glob("*.json")
        if not f.name.startswith(".")
    )
    
    if not json_files:
        return
    
    logger.info(f"Found {len(json_files)} files to process")
    
    for filepath in json_files:
        process_file(filepath)


def process_file(filepath: Path):
    """Process a single JSON batch file."""
    start_time = time.time()
    filename = filepath.name
    
    logger.info(f"Processing: {filename}")
    
    try:
        # Read and parse
        with open(filepath, "r", encoding="utf-8") as f:
            batch = json.load(f)
        
        source = batch.get("source", "unknown")
        documents = batch.get("documents", [])
        
        if not documents:
            logger.info(f"Empty batch: {filename}")
            _move_to_processed(filepath)
            log_ingestion(
                source=source,
                batch_file=filename,
                documents_total=0,
                documents_created=0,
                documents_updated=0,
                documents_skipped=0,
                status="empty"
            )
            return
        
        # Process documents
        created, updated, skipped = process_documents(documents)
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        # Audit log
        log_ingestion(
            source=source,
            batch_file=filename,
            documents_total=len(documents),
            documents_created=created,
            documents_updated=updated,
            documents_skipped=skipped,
            status="success",
            processing_time_ms=elapsed_ms
        )
        
        # Move to processed
        _move_to_processed(filepath)
        
        logger.info(
            f"Processed {filename}: {created} created, {updated} updated, "
            f"{skipped} skipped, {elapsed_ms}ms"
        )
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filename}: {e}")
        _move_to_processed(filepath, error=True)
        log_ingestion(
            source="unknown",
            batch_file=filename,
            documents_total=0,
            documents_created=0,
            documents_updated=0,
            documents_skipped=0,
            status="error",
            error=f"Invalid JSON: {str(e)}"
        )
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Failed to process {filename}: {e}", exc_info=True)
        log_ingestion(
            source="unknown",
            batch_file=filename,
            documents_total=0,
            documents_created=0,
            documents_updated=0,
            documents_skipped=0,
            status="error",
            error=str(e),
            processing_time_ms=elapsed_ms
        )


def _move_to_processed(filepath: Path, error: bool = False):
    """Move processed file out of inbox."""
    try:
        target_dir = Path(PROCESSED_DIR)
        if error:
            target_dir = target_dir / "errors"
        target_dir.mkdir(parents=True, exist_ok=True)
        
        dest = target_dir / filepath.name
        shutil.move(str(filepath), str(dest))
    except Exception as e:
        logger.warning(f"Failed to move {filepath.name}: {e}")


def main():
    """Main entry point — poll inbox on interval."""
    logger.info("Knowledge Ingester starting")
    logger.info(f"  Inbox: {INBOX_PATH}")
    logger.info(f"  Poll interval: {POLL_INTERVAL_SECONDS}s")
    
    # Ensure directories exist
    os.makedirs(INBOX_PATH, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    
    # Process any existing files immediately
    process_inbox()
    
    # Log initial Qdrant stats
    stats = get_collection_stats()
    logger.info(f"Qdrant stats: {stats}")
    
    # Poll loop
    current_interval = POLL_INTERVAL_SECONDS
    config_file = os.path.join(INBOX_PATH, ".system_worker_config.json")
    
    while True:
        try:
            process_inbox()
        except Exception as e:
            logger.error(f"Poll cycle error: {e}", exc_info=True)
            
        # Hot-reload check for interval updates
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
                new_interval = config.get("ingester_interval_seconds", POLL_INTERVAL_SECONDS)
                if new_interval != current_interval:
                    logger.info(f"Poll interval update detected: {current_interval}s -> {new_interval}s")
                    current_interval = new_interval
            except Exception as e:
                logger.error(f"Failed to reload config: {e}")
        
        time.sleep(current_interval)


if __name__ == "__main__":
    main()
