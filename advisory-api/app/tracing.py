"""
Langfuse LLM observability — gracefully no-ops when LANGFUSE_PUBLIC_KEY / SECRET_KEY not set.

Usage:
    from app.tracing import start_trace, start_span, start_generation, add_score

    with start_trace("generate-advisory", user_id=org_id, session_id=org_id) as t:
        with start_span("rag-retrieval") as s:
            s.update(output={"docs": 3})
        with start_generation("ollama-call", model="gemma4:e2b", input=prompt) as g:
            g.update(output=response, usage={"input": 120, "output": 45})
        add_score(t.trace_id, "confidence", 0.87)
"""
import os
import logging
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

_client = None


def _init_client():
    global _client
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sk = os.getenv("LANGFUSE_SECRET_KEY", "")
    if not pk or not sk:
        logger.debug("Langfuse env vars not set — observability disabled")
        return
    try:
        from langfuse import get_client
        _client = get_client()
        base_url = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
        logger.info(f"Langfuse observability enabled (base_url={base_url})")
    except Exception as exc:
        logger.warning(f"Langfuse init failed — tracing disabled: {exc}")


_init_client()


class _Noop:
    """Returned by all context managers when Langfuse is disabled — everything is a no-op."""
    trace_id: Optional[str] = None

    def update(self, **_) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


@contextmanager
def start_trace(name: str, **kwargs):
    """Top-level pipeline trace. Wraps the entire advisory generation call."""
    if _client is None:
        yield _Noop()
        return

    # Separate trace-level attributes from general metadata
    user_id = kwargs.pop("user_id", None)
    session_id = kwargs.pop("session_id", None)
    
    try:
        # In newer Langfuse SDKs, we use 'span' for the root observation if it's the current one
        ctx = _client.start_as_current_observation(
            name=name, 
            as_type="span", 
            user_id=user_id,
            session_id=session_id,
            **kwargs
        )
    except Exception as exc:
        # Fallback for SDK version mismatch or init error
        try:
            ctx = _client.start_as_current_observation(name=name, as_type="trace")
        except Exception:
            logger.debug(f"Langfuse trace init failure: {exc}")
            yield _Noop()
            return

    # Use the context manager normally. 
    # Application exceptions thrown in at 'yield' will be handled by ctx.__exit__
    with ctx as t:
        yield t


@contextmanager
def start_span(name: str, **kwargs):
    """Logical pipeline step (policy load, RAG retrieval, parse, etc.)."""
    if _client is None:
        yield _Noop()
        return
    
    try:
        ctx = _client.start_as_current_observation(
            name=name, as_type="span", **kwargs
        )
    except Exception as exc:
        logger.debug(f"Langfuse span init error: {exc}")
        yield _Noop()
        return

    with ctx as s:
        yield s


@contextmanager
def start_generation(name: str, **kwargs):
    """LLM call observation — records model, token counts, and latency."""
    if _client is None:
        yield _Noop()
        return

    try:
        ctx = _client.start_as_current_observation(
            name=name, as_type="generation", **kwargs
        )
    except Exception as exc:
        logger.debug(f"Langfuse generation init error: {exc}")
        yield _Noop()
        return

    with ctx as g:
        yield g


def add_score(trace_id: Optional[str], name: str, value: float, **kwargs) -> None:
    """Attach a numeric quality score to a trace (confidence, risk_score, etc.)."""
    if _client is None or not trace_id:
        return
    try:
        _client.score(trace_id=trace_id, name=name, value=value, **kwargs)
    except Exception as exc:
        logger.debug(f"Langfuse score error: {exc}")


def get_prompt(name: str, fallback: str) -> str:
    """
    Fetch a prompt from Langfuse Registry. 
    Falls back to local string if registry is unavailable or prompt name doesn't exist.
    """
    if _client is None:
        return fallback
    try:
        # Fetch the 'production' tagged version of the prompt
        prompt_obj = _client.get_prompt(name, type="chat")
        # For Langfuse, we usually store the system message as the first item
        # If it's a simple text prompt, it returns the string
        if hasattr(prompt_obj, "prompt"):
            return prompt_obj.prompt
        return str(prompt_obj)
    except Exception as exc:
        logger.debug(f"Langfuse Registry fetch failed for '{name}': {exc}")
        return fallback


def flush() -> None:
    """Force-flush pending observations (call at shutdown or in tests)."""
    if _client is not None:
        try:
            _client.flush()
        except Exception:
            pass
