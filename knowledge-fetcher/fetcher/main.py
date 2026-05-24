"""
Knowledge Fetcher — Main Entry Point
Scheduled worker that fetches vulnerability feeds and drops them into the inbox.
Runs on a configurable interval (default: every 6 hours).
"""
import os
import sys
import json
import time
import logging
import schedule
from datetime import datetime, timezone
from fetcher.config import FETCH_INTERVAL_HOURS, STATE_FILE, INBOX_PATH
from fetcher.sources.nvd import fetch_nvd
from fetcher.sources.cisa_kev import fetch_cisa_kev
from fetcher.writer import write_batch

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("knowledge-fetcher")


def load_state() -> dict:
    """Load last fetch timestamps from state file."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_state(state: dict):
    """Persist fetch timestamps."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except IOError as e:
        logger.error(f"Failed to save state: {e}")


def run_fetch_cycle():
    """Execute one full fetch cycle across all sources."""
    cycle_start = time.time()
    state = load_state()
    now = datetime.now(timezone.utc).isoformat()
    
    logger.info("=" * 60)
    logger.info(f"Starting fetch cycle at {now}")
    logger.info("=" * 60)
    
    total_docs = 0
    errors = []
    
    # 1. NVD (National Vulnerability Database)
    try:
        logger.info("Fetching NVD CVEs...")
        nvd_docs = fetch_nvd(last_fetched=state.get("nvd_last_fetched"))
        if nvd_docs:
            write_batch(nvd_docs, "NVD")
            total_docs += len(nvd_docs)
        state["nvd_last_fetched"] = now
    except Exception as e:
        logger.error(f"NVD fetch cycle failed: {e}", exc_info=True)
        errors.append(f"NVD: {str(e)}")
    
    # 2. CISA KEV (Known Exploited Vulnerabilities)
    try:
        logger.info("Fetching CISA KEV...")
        kev_docs = fetch_cisa_kev(last_fetched=state.get("cisa_kev_last_fetched"))
        if kev_docs:
            write_batch(kev_docs, "CISA_KEV")
            total_docs += len(kev_docs)
        state["cisa_kev_last_fetched"] = now
    except Exception as e:
        logger.error(f"CISA KEV fetch cycle failed: {e}", exc_info=True)
        errors.append(f"CISA_KEV: {str(e)}")
    
    # Save state
    save_state(state)
    
    elapsed = time.time() - cycle_start
    logger.info(
        f"Fetch cycle complete: {total_docs} documents, {len(errors)} errors, "
        f"{elapsed:.1f}s elapsed"
    )
    
    if errors:
        logger.warning(f"Errors during fetch: {errors}")


def main():
    """Main entry point — run once immediately, then schedule."""
    logger.info(f"Knowledge Fetcher starting")
    logger.info(f"  Interval: every {FETCH_INTERVAL_HOURS} hours")
    logger.info(f"  Inbox: {INBOX_PATH}")
    
    # Ensure inbox directory exists
    os.makedirs(INBOX_PATH, exist_ok=True)
    
    # Run immediately on startup
    run_fetch_cycle()
    
    # Schedule recurring runs
    current_interval = FETCH_INTERVAL_HOURS
    schedule.every(current_interval).hours.do(run_fetch_cycle)
    
    logger.info(f"Scheduler active. Next run in {current_interval} hours.")
    
    config_file = os.path.join(INBOX_PATH, ".system_worker_config.json")
    
    while True:
        schedule.run_pending()
        
        # Hot-reload check for interval updates
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
                new_interval = config.get("fetcher_interval_hours", FETCH_INTERVAL_HOURS)
                if new_interval != current_interval:
                    logger.info(f"Interval update detected: {current_interval}h -> {new_interval}h")
                    schedule.clear()
                    schedule.every(new_interval).hours.do(run_fetch_cycle)
                    current_interval = new_interval
            except Exception as e:
                logger.error(f"Failed to reload config: {e}")
        
        time.sleep(60)  # Check every minute


if __name__ == "__main__":
    main()
