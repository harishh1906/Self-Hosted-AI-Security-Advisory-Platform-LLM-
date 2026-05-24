import requests
import logging
import time
import os
from app.ollama_client import OLLAMA_BASE_URL, MODEL_NAME

logger = logging.getLogger(__name__)

def ensure_model_pulled():
    """
    Ensures the configured LLM model is pulled and available in Ollama.
    This runs on API startup to guarantee readiness.
    """
    try:
        # 1. Check if model is already pulled
        logger.info(f"Verifying Ollama model readiness: {MODEL_NAME}")
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        
        models = resp.json().get("models", [])
        if any(m.get("name") == MODEL_NAME for m in models):
            logger.info(f"Model {MODEL_NAME} is already available.")
            return True

        # 2. Model not found, start pull process
        logger.info(f"Model {MODEL_NAME} not found. Initiating auto-pull (this may take several minutes)...")
        
        # Use streaming pull to avoid timeout
        pull_resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/pull",
            json={"name": MODEL_NAME},
            stream=True,
            timeout=None
        )
        pull_resp.raise_for_status()
        
        for line in pull_resp.iter_lines():
            if line:
                import json
                status = json.loads(line)
                if status.get("status") == "success":
                    logger.info(f"Successfully pulled model: {MODEL_NAME}")
                    return True
                # Log progress occasionally
                if "completed" in status:
                    percent = (status["completed"] / status["total"]) * 100 if status.get("total") else 0
                    if int(percent) % 25 == 0:
                        logger.info(f"Pulling {MODEL_NAME}: {percent:.1f}%")
        
        return True
    except Exception as e:
        logger.error(f"Failed to ensure Ollama model is pulled: {e}")
        return False
