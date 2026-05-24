import os
import requests
import time
import logging
import threading
from typing import Dict, Tuple, Optional

from app import tracing

logger = logging.getLogger(__name__)

# Serialize all Ollama HTTP calls — the Quadro P1000 (4GB VRAM) runs one model
# runner with Parallel=1. Concurrent connections cause the scheduler to deadlock:
# the second request's runner hangs waiting for VRAM already occupied by the first.
_ollama_lock = threading.Lock()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/generate"
MODEL_NAME = os.getenv("DEFAULT_MODEL_NAME", "gemma4:e2b")
FALLBACK_MODEL = None  # No fallback - Gemma 4 only (prevents cascade failures and VRAM explosion)

# ── Server-tunable LLM generation parameters ──
# All configurable via docker-compose environment for hardware-specific tuning
LLM_NUM_PREDICT = int(os.getenv("LLM_NUM_PREDICT", "512"))       # Output token cap
LLM_NUM_CTX = int(os.getenv("LLM_NUM_CTX", "4096"))             # Context window (must fit in VRAM)
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))    # Low = deterministic

# Retry configuration (Production-safe: fail fast, no retry storms)
MAX_RETRIES = 1  # No retry storm - Gemma 4 responds in <10s normally
INITIAL_BACKOFF = 0.5  # seconds
BACKOFF_MULTIPLIER = 2.0
MAX_BACKOFF = 5.0     # Cap backoff to 5s to keep responsiveness
REQUEST_TIMEOUT = int(os.getenv("LLM_REQUEST_TIMEOUT", "180"))  # 3 min (fails before Nginx 5 min)

def query_llm(
    prompt: str,
    model: Optional[str] = None,
    fallback_model: Optional[str] = None,
    org_id: Optional[str] = None,
    correlation_id: Optional[str] = None
) -> Tuple[str, Dict, bool]:
    """
    Query LLM with retry and failover logic.
    
    Args:
        prompt: The prompt to send to the LLM
        model: Optional model name to use (defaults to MODEL_NAME)
        fallback_model: Fallback model to use if primary fails
        org_id: Organization ID for logging
        correlation_id: Correlation ID for logging
    
    Returns:
        tuple: (response_text, token_usage_dict, used_fallback)
        - response_text: The LLM response
        - token_usage_dict: Contains 'prompt_eval_count', 'eval_count', 'total_tokens' if available
        - used_fallback: True if fallback model was used
    """
    # Use provided model or fall back to default (gemma4:e2b)
    model_to_use = model or MODEL_NAME
    # Fallback disabled - Gemma 4 only (no cascade failures)
    fallback_to_use = fallback_model if fallback_model is not None else FALLBACK_MODEL
    used_fallback = False
    
    # Try primary model first
    try:
        response_text, token_usage = _query_llm_with_retry(
            prompt=prompt,
            model=model_to_use,
            org_id=org_id,
            correlation_id=correlation_id
        )
        return response_text, token_usage, used_fallback
    except Exception as e:
        # If no fallback available, fail fast with clean error
        if fallback_to_use is None:
            logger.warning(
                f"Primary model failed after all retries, no fallback configured",
                extra={
                    "correlation_id": correlation_id,
                    "org_id": org_id,
                    "selected_model": model_to_use,
                    "primary_model": model_to_use,
                    "actual_model_used": None,
                    "error": str(e),
                    "decision_reason": f"Model {model_to_use} failed, fallback disabled"
                }
            )
            raise
        # If primary model fails after all retries, log WARNING and try fallback ONCE
        if fallback_to_use != model_to_use:
            logger.warning(
                f"Primary model failed after all retries, attempting fallback",
                extra={
                    "correlation_id": correlation_id,
                    "org_id": org_id,
                    "selected_model": model_to_use,
                    "primary_model": model_to_use,
                    "fallback_model": fallback_to_use,
                    "error": str(e),
                    "decision_reason": f"Primary model {model_to_use} failed, using fallback {fallback_to_use}"
                }
            )
            used_fallback = True
            try:
                # Fallback: try once with retry (but only if fallback is different)
                response_text, token_usage = _query_llm_with_retry(
                    prompt=prompt,
                    model=fallback_to_use,
                    org_id=org_id,
                    correlation_id=correlation_id
                )
                return response_text, token_usage, used_fallback
            except Exception as fallback_error:
                # Fallback also failed - this is final failure
                logger.error(
                    f"Fallback model also failed after all retries",
                    extra={
                        "correlation_id": correlation_id,
                        "org_id": org_id,
                        "selected_model": model_to_use,
                        "primary_model": model_to_use,
                        "fallback_model": fallback_to_use,
                        "actual_model_used": None,
                        "error": str(fallback_error),
                        "decision_reason": f"Both primary {model_to_use} and fallback {fallback_to_use} failed"
                    },
                    exc_info=True
                )
                raise fallback_error
        else:
            # No fallback available, log WARNING and re-raise original error
            logger.warning(
                f"Primary model failed after all retries, no fallback available",
                extra={
                    "correlation_id": correlation_id,
                    "org_id": org_id,
                    "selected_model": model_to_use,
                    "primary_model": model_to_use,
                    "actual_model_used": None,
                    "error": str(e),
                    "decision_reason": f"Model {model_to_use} failed, no fallback configured"
                }
            )
            raise

def _query_llm_with_retry(
    prompt: str,
    model: str,
    org_id: Optional[str] = None,
    correlation_id: Optional[str] = None
) -> Tuple[str, Dict]:
    """
    Query LLM with exponential backoff retry.
    
    Args:
        prompt: The prompt to send to the LLM
        model: Model name to use
        org_id: Organization ID for logging
        correlation_id: Correlation ID for logging
    
    Returns:
        tuple: (response_text, token_usage_dict)
    """
    backoff = INITIAL_BACKOFF
    last_exception = None
    
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(
                f"Querying LLM: {model}",
                extra={"correlation_id": correlation_id, "org_id": org_id, "timeout": REQUEST_TIMEOUT}
            )
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json",  # Force JSON output mode
                "options": {
                    "num_predict": LLM_NUM_PREDICT,   # Tuned for server VRAM capacity
                    "temperature": LLM_TEMPERATURE,    # Low for deterministic security output
                    "num_ctx": LLM_NUM_CTX             # Must fit in GPU VRAM (4 GB Quadro P1000)
                }
            }

            with tracing.start_generation(
                "ollama-generate",
                model=model,
                input=prompt,
                metadata={
                    "org_id": org_id,
                    "correlation_id": correlation_id,
                    "attempt": attempt + 1,
                    "num_predict": LLM_NUM_PREDICT,
                    "num_ctx": LLM_NUM_CTX,
                    "temperature": LLM_TEMPERATURE,
                },
            ) as gen_obs:
                # Acquire lock before talking to Ollama — prevents concurrent runner
                # contention on the Quadro P1000 which only supports one active request.
                lock_wait_start = time.time()
                if not _ollama_lock.acquire(blocking=True, timeout=REQUEST_TIMEOUT):
                    raise TimeoutError(f"LLM queue timeout: another request held Ollama for >{REQUEST_TIMEOUT}s")
                lock_wait_s = time.time() - lock_wait_start
                if lock_wait_s > 1.0:
                    logger.info(
                        f"LLM queued {lock_wait_s:.1f}s waiting for prior request to finish",
                        extra={"correlation_id": correlation_id, "org_id": org_id}
                    )
                try:
                    response = requests.post(OLLAMA_URL, json=payload, timeout=REQUEST_TIMEOUT)
                    response.raise_for_status()
                    result = response.json()
                finally:
                    _ollama_lock.release()

                response_text = result.get("response", "")

                # Extract token usage if available (Ollama API provides these fields)
                prompt_eval_count = result.get("prompt_eval_count") or 0
                eval_count = result.get("eval_count") or 0

                token_usage = {
                    "prompt_eval_count": prompt_eval_count if result.get("prompt_eval_count") is not None else None,
                    "eval_count": eval_count if result.get("eval_count") is not None else None,
                    "total_tokens": prompt_eval_count + eval_count
                }

                gen_obs.update(
                    output=response_text,
                    usage={"input": prompt_eval_count, "output": eval_count, "total": prompt_eval_count + eval_count},
                    metadata={
                        "eval_duration_ns": result.get("eval_duration"),
                        "total_duration_ns": result.get("total_duration"),
                        "queue_wait_s": round(lock_wait_s, 3),
                    },
                )

            # Log retry if not first attempt
            if attempt > 0:
                logger.info(
                    f"LLM query succeeded on retry",
                    extra={
                        "correlation_id": correlation_id,
                        "org_id": org_id,
                        "model": model,
                        "attempt": attempt + 1
                    }
                )

            return response_text, token_usage
            
        except requests.exceptions.ReadTimeout as e:
            # Fail fast on timeout - no retry queue amplification
            logger.warning(
                f"LLM timeout — failing fast",
                extra={
                    "correlation_id": correlation_id,
                    "org_id": org_id,
                    "model": model,
                    "attempt": attempt + 1,
                    "timeout": REQUEST_TIMEOUT
                }
            )
            raise
        except Exception as e:
            last_exception = e
            if attempt < MAX_RETRIES - 1:
                # Exponential backoff
                wait_time = min(backoff, MAX_BACKOFF)
                logger.warning(
                    f"LLM query failed, retrying",
                    extra={
                        "correlation_id": correlation_id,
                        "org_id": org_id,
                        "model": model,
                        "attempt": attempt + 1,
                        "max_retries": MAX_RETRIES,
                        "wait_time": wait_time,
                        "error": str(e)
                    }
                )
                time.sleep(wait_time)
                backoff *= BACKOFF_MULTIPLIER
            else:
                # Last attempt failed - log WARNING (fallback will be attempted by caller)
                logger.warning(
                    f"LLM query failed after all retries",
                    extra={
                        "correlation_id": correlation_id,
                        "org_id": org_id,
                        "model": model,
                        "attempts": MAX_RETRIES,
                        "error": str(e)
                    }
                )
    
    # All retries exhausted
    raise last_exception
