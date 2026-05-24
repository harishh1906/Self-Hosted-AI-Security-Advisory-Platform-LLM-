import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import Base, engine
from app.db import models  # REQUIRED: forces model registration
from app.vector_store import init_collection
from app.ollama_setup import ensure_model_pulled

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Create database tables on startup (must be after models are imported)
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan context manager for startup/shutdown events."""
    # Initialize Vector DB collection
    init_collection()
    
    # Ensure LLM model is pulled (runs in background thread to not block event loop)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, ensure_model_pulled)
    
    # Initialize default system settings
    init_default_settings()
    
    yield
    
    # Shutdown: flush pending Langfuse traces so nothing is lost
    from app import tracing
    tracing.flush()

def init_default_settings():
    """Seed the database with default system settings if they don't exist."""
    from app.db.database import SessionLocal
    from app.db import crud
    from app.ollama_client import MODEL_NAME, FALLBACK_MODEL
    
    db = SessionLocal()
    try:
        defaults = [
            ("fetcher_interval_hours", 6, "Interval for NVD/CISA KEV fetching"),
            ("ingester_interval_seconds", 60, "Polling rate for the knowledge inbox"),
            ("primary_model", MODEL_NAME, "Default LLM for advisories"),
            ("fallback_model", FALLBACK_MODEL, "Failover LLM"),
            ("sla_threshold_ms", 8000, "Target latency for LLM requests"),
        ]
        
        for key, value, desc in defaults:
            if not crud.get_setting(db, key):
                crud.update_setting(db, key, value, desc)
                logger.info(f"Seeded default setting: {key} = {value}")
        
        # Sync to worker control file on startup
        from app.config import sync_worker_config
        sync_worker_config(db)
    except Exception as e:
        logger.error(f"Failed to initialize default settings: {e}")
    finally:
        db.close()

app = FastAPI(
    title="VirtueThreatX Advisory API",
    version="0.3.0",
    description="On-prem AI advisory and risk assessment engine",
    lifespan=lifespan
)

# CORS Configuration for Production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and register routers
from app.routers.advisory import router as advisory_router
from app.routers.analytics import router as analytics_router
from app.routers.model import router as model_router
from app.routers.optimization import router as optimization_router
from app.routers.health import router as health_router
from app.routers.knowledge import router as knowledge_router
from app.routers.config import router as config_router

app.include_router(advisory_router)
app.include_router(analytics_router)
app.include_router(model_router)
app.include_router(optimization_router)
app.include_router(health_router)
app.include_router(knowledge_router)
app.include_router(config_router)
