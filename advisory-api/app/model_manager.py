"""
Dynamic Model Manager
Supports hot-reload of model configuration without service restart.
Provides cluster-wide consistency via database.
"""
import logging
import threading
import time
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app.ollama_client import MODEL_NAME
from app.db.models import ModelConfiguration
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)

class ModelManager:
    """Thread-safe model manager with hot-reload and cluster-wide consistency."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._default_model = MODEL_NAME
        self._model_configs: Dict[str, Dict] = {}  # org_id -> {model_name, enabled, etc}
        self._cache_ttl = 60  # Cache for 60 seconds
        self._cache_timestamps: Dict[str, float] = {}
    
    def _load_from_db(self, config_key: str) -> Optional[str]:
        """Load model configuration from database (cluster-wide source of truth)."""
        db: Session = SessionLocal()
        try:
            config = db.query(ModelConfiguration).filter(
                ModelConfiguration.config_key == config_key
            ).first()
            
            if config and config.enabled == "true":
                return config.model_name
            return None
        except Exception as e:
            logger.error(f"Failed to load model config from DB: {e}", exc_info=True)
            return None
        finally:
            db.close()
    
    def _save_to_db(
        self,
        config_key: str,
        model_name: str,
        enabled: bool = True,
        updated_by: Optional[str] = None,
        correlation_id: Optional[str] = None
    ):
        """Save model configuration to database (cluster-wide source of truth)."""
        db: Session = SessionLocal()
        try:
            config = db.query(ModelConfiguration).filter(
                ModelConfiguration.config_key == config_key
            ).first()
            
            if config:
                config.model_name = model_name
                config.enabled = "true" if enabled else "false"
                config.updated_by = updated_by
                config.correlation_id = correlation_id
            else:
                config = ModelConfiguration(
                    config_key=config_key,
                    model_name=model_name,
                    enabled="true" if enabled else "false",
                    updated_by=updated_by,
                    correlation_id=correlation_id
                )
                db.add(config)
            
            db.commit()
            
            # Invalidate cache
            with self._lock:
                if config_key in self._cache_timestamps:
                    del self._cache_timestamps[config_key]
                if config_key.startswith("org:"):
                    org_id = config_key.replace("org:", "")
                    if org_id in self._model_configs:
                        del self._model_configs[org_id]
            
        except Exception as e:
            logger.error(f"Failed to save model config to DB: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()
    
    def get_default_model(self) -> str:
        """Get default model name (prioritizes SystemSettings, then legacy ModelConfiguration)."""
        with self._lock:
            # Check cache - reload every 60 seconds
            cache_key = "default"
            current_time = time.time()
            if cache_key in self._cache_timestamps:
                cache_age = current_time - self._cache_timestamps[cache_key]
                if cache_age < self._cache_ttl:
                    return self._default_model
            
            # 1. Try new SystemSettings (Enterprise primary_model)
            db: Session = SessionLocal()
            try:
                from app.db.models import SystemSettings
                setting = db.query(SystemSettings).filter(SystemSettings.setting_key == "primary_model").first()
                if setting:
                    self._default_model = setting.setting_value
                    self._cache_timestamps[cache_key] = current_time
                    return self._default_model
            except Exception as e:
                logger.warning(f"Failed to load primary_model from SystemSettings: {e}")
            finally:
                db.close()

            # 2. Fallback to legacy ModelConfiguration
            db_model = self._load_from_db("default")
            if db_model:
                self._default_model = db_model
                self._cache_timestamps[cache_key] = current_time
                logger.debug(f"Reloaded default model from legacy DB: {db_model}")
            else:
                self._cache_timestamps[cache_key] = current_time
            
            return self._default_model
    
    def set_default_model(
        self,
        model_name: str,
        updated_by: Optional[str] = None,
        correlation_id: Optional[str] = None
    ):
        """Update default model (hot-reload with cluster-wide consistency)."""
        with self._lock:
            old_model = self._default_model
            self._default_model = model_name
            self._cache_timestamps["default"] = time.time()
        
        # Save to database for cluster-wide consistency
        self._save_to_db("default", model_name, enabled=True, updated_by=updated_by, correlation_id=correlation_id)
        
        logger.info(
            f"Default model updated (cluster-wide)",
            extra={
                "old_model": old_model,
                "new_model": model_name,
                "correlation_id": correlation_id
            }
        )
    
    def get_org_model(self, org_id: str) -> Optional[str]:
        """Get model for specific organization (with cluster-wide consistency, 60s reload)."""
        cache_key = f"org:{org_id}"
        current_time = time.time()
        
        with self._lock:
            # Check cache timestamp - reload every 60 seconds
            if cache_key in self._cache_timestamps:
                cache_age = current_time - self._cache_timestamps[cache_key]
                if cache_age < self._cache_ttl:
                    # Cache still valid, check in-memory cache
                    if org_id in self._model_configs:
                        config = self._model_configs[org_id]
                        if config.get("enabled", True):
                            return config.get("model_name")
                    # Cached as not found
                    return None
                # Cache expired, reload from database
        
        # Load from database (60s reload ensures all instances stay in sync)
        db_model = self._load_from_db(cache_key)
        if db_model:
            with self._lock:
                self._model_configs[org_id] = {
                    "model_name": db_model,
                    "enabled": True
                }
                self._cache_timestamps[cache_key] = current_time
            logger.debug(f"Reloaded org model from database: org_id={org_id}, model={db_model}")
            return db_model
        
        # Not found in DB, cache the negative result
        with self._lock:
            self._cache_timestamps[cache_key] = current_time
        return None
    
    def set_org_model(
        self,
        org_id: str,
        model_name: str,
        enabled: bool = True,
        updated_by: Optional[str] = None,
        correlation_id: Optional[str] = None
    ):
        """Set model for specific organization (hot-reload with cluster-wide consistency)."""
        with self._lock:
            self._model_configs[org_id] = {
                "model_name": model_name,
                "enabled": enabled
            }
            self._cache_timestamps[f"org:{org_id}"] = time.time()
        
        # Save to database for cluster-wide consistency
        self._save_to_db(f"org:{org_id}", model_name, enabled=enabled, updated_by=updated_by, correlation_id=correlation_id)
        
        logger.info(
            f"Organization model updated (cluster-wide)",
            extra={
                "org_id": org_id,
                "model_name": model_name,
                "enabled": enabled,
                "correlation_id": correlation_id
            }
        )
    
    def get_all_configs(self) -> Dict:
        """Get all model configurations."""
        with self._lock:
            return {
                "default_model": self._default_model,
                "org_configs": self._model_configs.copy()
            }

# Global model manager instance
model_manager = ModelManager()

