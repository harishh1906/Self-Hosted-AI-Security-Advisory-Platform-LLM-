from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from app.db.database import get_db
from app.db import crud
from app.auth.dependencies import get_current_user_or_service

router = APIRouter(prefix="/internal/config", tags=["Configuration"])

@router.get("/", response_model=List[Dict[str, Any]])
def get_all_settings(
    identity: dict = Depends(get_current_user_or_service),
    db: Session = Depends(get_db)
):
    """Retrieve all system settings."""
    settings = crud.get_all_settings(db)
    return [
        {
            "key": s.setting_key,
            "value": s.setting_value,
            "description": s.description,
            "updated_at": s.updated_at
        } for s in settings
    ]

@router.get("/{key}")
def get_setting(
    key: str,
    identity: dict = Depends(get_current_user_or_service),
    db: Session = Depends(get_db)
):
    """Retrieve a specific system setting."""
    setting = crud.get_setting(db, key)
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    return {
        "key": setting.setting_key,
        "value": setting.setting_value,
        "description": setting.description,
        "updated_at": setting.updated_at
    }

@router.put("/{key}")
def update_setting(
    key: str,
    payload: Dict[str, Any],
    identity: dict = Depends(get_current_user_or_service),
    db: Session = Depends(get_db)
):
    """Update a system setting."""
    if "value" not in payload:
        raise HTTPException(status_code=400, detail="Missing 'value' in payload")
    
    setting = crud.update_setting(
        db, 
        key, 
        payload["value"], 
        payload.get("description")
    )
    
    # Sync to worker control file
    from app.config import sync_worker_config
    sync_worker_config(db)
    
    # Audit log
    crud.create_audit_log(
        db=db,
        action="update_system_setting",
        payload={"key": key, "new_value": payload["value"]},
        user_id=identity.get("user_id"),
        service_name=identity.get("service_name"),
        org_id=identity.get("org_id")
    )
    
    return {
        "key": setting.setting_key,
        "value": setting.setting_value,
        "status": "updated"
    }
