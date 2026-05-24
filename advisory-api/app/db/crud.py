from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.db.models import Advisory, AuditLog, AIPolicyProfile, SystemSettings

def create_advisory(db: Session, finding, result, org_id: str = None):
    """
    HIGH PRIORITY FIX: Database errors are handled at caller level (main.py),
    but we ensure proper transaction handling here.
    """
    db_advisory = Advisory(
        org_id=org_id,  # Multi-tenancy isolation
        finding_title=finding.title,
        severity=result["advisory"].severity,
        risk_score=result["risk_assessment"]["risk_score"],
        advisory={
            "advisory": result["advisory"].model_dump(),
            "risk_assessment": result["risk_assessment"]
        }
    )

    db.add(db_advisory)
    db.commit()
    db.refresh(db_advisory)
    return db_advisory

def create_audit_log(
    db: Session,
    action: str,
    payload: dict,
    user_id: str = None,
    service_name: str = None,
    org_id: str = None,
    policy_id: int = None
):
    """
    Create an audit log entry for compliance tracking.
    Database errors are handled at caller level.
    """
    log = AuditLog(
        org_id=org_id,
        user_id=user_id,
        service_name=service_name,
        policy_id=policy_id,
        action=action,
        payload=payload
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log

def get_policy_profile(db: Session, org_id: str) -> AIPolicyProfile:
    """Get AI policy profile for organization."""
    return db.query(AIPolicyProfile).filter(
        AIPolicyProfile.org_id == org_id
    ).first()

def create_or_update_policy_profile(
    db: Session,
    org_id: str,
    risk_tolerance: str = "medium",
    verbosity: str = "balanced",
    compliance_mode: str = "none",
    remediation_style: str = "practical"
) -> AIPolicyProfile:
    """
    Create or update AI policy profile for organization.
    """
    policy = get_policy_profile(db, org_id)
    
    if policy:
        # Update existing
        policy.risk_tolerance = risk_tolerance
        policy.verbosity = verbosity
        policy.compliance_mode = compliance_mode
        policy.remediation_style = remediation_style
    else:
        # Create new
        policy = AIPolicyProfile(
            org_id=org_id,
            risk_tolerance=risk_tolerance,
            verbosity=verbosity,
            compliance_mode=compliance_mode,
            remediation_style=remediation_style
        )
        db.add(policy)
    
    db.commit()
    db.refresh(policy)
    
    # Invalidate cache
    from app.policy_loader import policy_cache
    policy_cache.invalidate(org_id)
    
    return policy

def get_setting(db: Session, key: str):
    """Get a system setting by key."""
    return db.query(SystemSettings).filter(SystemSettings.setting_key == key).first()

def update_setting(db: Session, key: str, value: any, description: str = None):
    """Update or create a system setting."""
    setting = get_setting(db, key)
    if setting:
        setting.setting_value = value
        if description:
            setting.description = description
    else:
        setting = SystemSettings(
            setting_key=key,
            setting_value=value,
            description=description
        )
        db.add(setting)
    
    db.commit()
    db.refresh(setting)
    return setting

def get_all_settings(db: Session):
    """Get all system settings."""
    return db.query(SystemSettings).all()
