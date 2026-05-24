import logging
import time
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.schemas import FindingInput
from app.auth.dependencies import get_current_user_or_service
from app.db.database import get_db
from app.db.crud import create_advisory, create_audit_log
from app.config import MODEL_VERSION, PROMPT_VERSION, GUARDRAIL_VERSION
from app.metrics import metrics
from app.drift.detector import detect_drift, update_baseline
from app.analytics.service import record_analytics
from app.model_health import model_health_tracker
from app.advisory_engine import generate_advisory
from app.adapters.scanner_adapter import ScannerFindingInput, adapt_scanner_to_finding

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Security Advisories"])

@router.post("/login")
def login(username: str, role: str = "security_analyst"):
    """
    Generate JWT token for testing.
    In production, this should validate credentials against a user database.
    """
    from app.auth.jwt import create_access_token
    token = create_access_token(data={"sub": username, "role": role})
    return {"access_token": token, "token_type": "bearer"}

@router.post("/api/v1/scanner/analyze")
def scanner_analyze(
    scanner_input: ScannerFindingInput,
    identity: dict = Depends(get_current_user_or_service),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """
    Dedicated endpoint for the Scanner Platform.
    Adapts scanner-specific JSON format to internal FindingInput.
    """
    service_name = identity.get("service_name", "scanner-platform")
    finding = adapt_scanner_to_finding(scanner_input, scanner_name=service_name)
    return analyze_finding(finding, identity, db, background_tasks, request)

@router.post("/analyze")
def analyze_finding(
    finding: FindingInput,
    identity: dict = Depends(get_current_user_or_service),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """
    Analyze a security finding and generate advisory.
    
    Supports both:
    - User JWT authentication (Authorization: Bearer <token>)
    - Service-to-service HMAC (X-Service-Name, X-Service-Signature, X-Timestamp)
    
    Multi-tenancy: org_id from finding or identity token.
    
    Correlation ID: Accepts X-Request-ID header, generates if missing.
    """
    if request:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    else:
        request_id = str(uuid.uuid4())
    
    start_time = time.time()
    metrics.increment("requests_total")
    
    org_id_for_log = finding.org_id or identity.get("org_id")
    service_name = identity.get("service_name") if identity.get("auth_type") == "service" else None
    user_id = identity.get("user_id") if identity.get("auth_type") == "user" else None
    
    logger.info(
        f"Request started",
        extra={
            "correlation_id": request_id,
            "org_id": org_id_for_log,
            "service_name": service_name,
            "user_id": user_id,
            "finding_title": finding.title[:100],
            "model_version": MODEL_VERSION,
            "active_model": finding.active_model,
            "rollback_flag": finding.rollback_flag
        }
    )
    
    try:
        # Enforce org_id consistency
        finding_org_id = finding.org_id
        identity_org_id = identity.get("org_id")
        
        if finding_org_id and identity_org_id and finding_org_id != identity_org_id:
            raise HTTPException(
                status_code=400,
                detail="org_id mismatch between finding and identity"
            )
        
        org_id = finding_org_id or identity_org_id
        
        if not org_id:
            raise HTTPException(
                status_code=400,
                detail="org_id required for multi-tenant isolation"
            )
        
        from app.ollama_client import MODEL_NAME, FALLBACK_MODEL

        # Runtime rollback flag
        if finding.rollback_flag:
            active_model = None
        else:
            active_model = finding.active_model
            if not active_model:
                from app.optimization.engine import get_active_models
                active_models_list = get_active_models(org_id, None)
                if active_models_list:
                    active_model = active_models_list[0].get("active_model")
        
        if not active_model:
            active_model = MODEL_NAME
        
        # Generate advisory
        llm_start_time = time.time()
        result, rag_available, policy, token_usage, used_fallback, applied_policy_params, degradation_used, explainability_data = generate_advisory(
            finding,
            org_id=org_id,
            active_model=active_model,
            correlation_id=request_id
        )
        llm_latency_ms = (time.time() - llm_start_time) * 1000
        total_latency_ms = (time.time() - start_time) * 1000
        
        if used_fallback:
            metrics.increment("fallback_count")
            logger.warning(
                f"Model failover occurred",
                extra={
                    "correlation_id": request_id,
                    "org_id": org_id,
                    "primary_model": active_model,
                    "fallback_model": FALLBACK_MODEL
                }
            )
        
        actual_model_used = FALLBACK_MODEL if used_fallback else active_model
        policy_id = policy.get("policy_id")
        
        input_tokens = token_usage.get("prompt_eval_count")
        output_tokens = token_usage.get("eval_count")
        total_tokens = token_usage.get("total_tokens", 0) or (input_tokens or 0) + (output_tokens or 0)
        
        # AI Output Drift Detection
        drift_status, drift_reasons = detect_drift(
            endpoint="analyze",
            policy_id=policy_id,
            advisory_result=result,
            org_id=org_id,
            correlation_id=request_id
        )
        
        drift_adjusted = drift_status == "DRIFT_DETECTED"
        model_health_tracker.record_request(
            model_name=actual_model_used,
            latency_ms=llm_latency_ms,
            used_fallback=used_fallback,
            drift_adjusted=drift_adjusted
        )
        
        model_selection_decision = {
            "selected_model": actual_model_used,
            "primary_model": active_model,
            "used_fallback": used_fallback,
            "fallback_model": FALLBACK_MODEL if used_fallback else None,
            "selection_timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if not finding.active_model and policy_id is not None:
            active_models_list = get_active_models(org_id, policy_id)
            if active_models_list:
                active_model = active_models_list[0].get("active_model", active_model)
        
        original_confidence = result["advisory"].confidence
        drift_fallback_notice = None
        
        if drift_status == "DRIFT_DETECTED":
            adjusted_confidence = max(0.1, original_confidence - 0.1)
            result["advisory"].confidence = round(adjusted_confidence, 2)
            drift_fallback_notice = f"Drift detected: {', '.join(drift_reasons)}. Confidence adjusted from {original_confidence:.2f} to {adjusted_confidence:.2f}."
        
        self_healing_notice = explainability_data.get("fallback_notice")
        fallback_notice = None
        if self_healing_notice and drift_fallback_notice:
            fallback_notice = f"{self_healing_notice} {drift_fallback_notice}"
        elif self_healing_notice:
            fallback_notice = self_healing_notice
        elif drift_fallback_notice:
            fallback_notice = drift_fallback_notice
            
            logger.warning(
                f"Drift detected - confidence lowered",
                extra={
                    "correlation_id": request_id,
                    "org_id": org_id,
                    "policy_id": policy_id,
                    "original_confidence": original_confidence,
                    "adjusted_confidence": adjusted_confidence,
                    "drift_reasons": drift_reasons
                }
            )
        
        # Save to database
        try:
            advisory_record = create_advisory(db, finding, result, org_id=org_id)
            
            advisory = result["advisory"]
            remediation_steps_count = len(advisory.remediation_steps) if advisory.remediation_steps else 0
            description_length = len(advisory.risk_summary or "") + len(advisory.business_impact or "")
            
            create_audit_log(
                db=db,
                action="analyze_finding",
                payload={
                    "finding_title": finding.title,
                    "finding_description": finding.description,
                    "scanner": finding.scanner,
                    "model": MODEL_VERSION,
                    "model_version": MODEL_VERSION,
                    "prompt_version": PROMPT_VERSION,
                    "guardrail_version": GUARDRAIL_VERSION,
                    "confidence": result["advisory"].confidence,
                    "risk_score": result["risk_assessment"]["risk_score"],
                    "risk_level": result["risk_assessment"]["risk_level"],
                    "remediation_steps_count": remediation_steps_count,
                    "description_length": description_length,
                    "severity": advisory.severity,
                    "advisory_id": advisory_record.id,
                    "auth_type": identity.get("auth_type"),
                    "rag_available": rag_available,
                    "llm_latency_ms": llm_latency_ms,
                    "total_latency_ms": total_latency_ms,
                    "correlation_id": request_id,
                    "policy_id": policy_id,
                    "policy_risk_tolerance": policy.get("risk_tolerance"),
                    "policy_verbosity": policy.get("verbosity"),
                    "policy_compliance_mode": policy.get("compliance_mode"),
                    "policy_remediation_style": policy.get("remediation_style"),
                    "drift_status": drift_status,
                    "drift_reasons": drift_reasons,
                    "active_model": active_model,
                    "fallback_notice": fallback_notice,
                    "response_time_ms": total_latency_ms,
                    "model_confidence": result["advisory"].confidence,
                    "used_fallback": used_fallback,
                    "model_selection_decision": model_selection_decision,
                    "applied_policy_params": applied_policy_params,
                    "degradation_used": degradation_used,
                    "decision_reason": explainability_data.get("decision_reason"),
                    "primary_model": explainability_data.get("primary_model"),
                    "fallback_model": explainability_data.get("fallback_model"),
                    "actual_model_used": explainability_data.get("actual_model_used"),
                    "model_name_used": actual_model_used,
                    "model_selection": {
                        "selected_model": explainability_data.get("actual_model_used"),
                        "primary_model": explainability_data.get("primary_model"),
                        "fallback_model": explainability_data.get("fallback_model"),
                        "used_fallback": used_fallback,
                        "force_model": finding.force_model,
                        "model_override": finding.model_override
                    }
                },
                user_id=user_id,
                service_name=service_name,
                org_id=org_id,
                policy_id=policy_id
            )
            
            metrics.increment("success_count")
            metrics.record_latency(total_latency_ms)
            metrics.record_tokens(total_tokens)

            if not rag_available:
                metrics.increment("degraded_total")
            if degradation_used:
                metrics.increment("self_healing_count")
            if drift_status == "DRIFT_DETECTED":
                metrics.increment("drift_count")

            from app.circuit_breaker import circuit_breaker
            circuit_breaker.record_request(success=True, failed=False)

            if background_tasks:
                background_tasks.add_task(update_baseline, "analyze", policy_id, result, org_id)
            else:
                try:
                    update_baseline("analyze", policy_id, result, org_id)
                except Exception as e:
                    logger.warning(f"Baseline update failed: {e}")

            if drift_status == "DRIFT_DETECTED":
                logger.warning(
                    f"AI output drift detected",
                    extra={
                        "correlation_id": request_id,
                        "org_id": org_id,
                        "policy_id": policy_id,
                        "drift_status": drift_status,
                        "drift_reasons": drift_reasons
                    }
                )
            
            if background_tasks:
                background_tasks.add_task(
                    record_analytics,
                    org_id=org_id,
                    endpoint="analyze",
                    policy_id=policy_id,
                    policy_risk_tolerance=policy.get("risk_tolerance"),
                    policy_verbosity=policy.get("verbosity"),
                    policy_compliance_mode=policy.get("compliance_mode"),
                    tokens_used=total_tokens,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=total_latency_ms,
                    llm_latency_ms=llm_latency_ms,
                    success="success",
                    correlation_id=request_id,
                    model_name=actual_model_used
                )
            else:
                try:
                    record_analytics(
                        org_id=org_id,
                        endpoint="analyze",
                        policy_id=policy_id,
                        policy_risk_tolerance=policy.get("risk_tolerance"),
                        policy_verbosity=policy.get("verbosity"),
                        policy_compliance_mode=policy.get("compliance_mode"),
                        tokens_used=total_tokens,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=total_latency_ms,
                        llm_latency_ms=llm_latency_ms,
                        success="success",
                        correlation_id=request_id,
                        model_name=actual_model_used
                    )
                except Exception as e:
                    logger.warning(f"Analytics recording failed: {e}")
            
            logger.info(
                f"Request completed successfully",
                extra={
                    "correlation_id": request_id,
                    "org_id": org_id,
                    "service_name": service_name,
                    "model_version": MODEL_VERSION,
                    "active_model": active_model,
                    "rag_available": rag_available,
                    "llm_latency_ms": llm_latency_ms,
                    "total_latency_ms": total_latency_ms,
                    "response_time_ms": total_latency_ms,
                    "metrics": {
                        "p50": {"label": "P50", "value": total_latency_ms, "color": "#6366f1"},
                        "p95": {"label": "P95", "value": total_latency_ms, "color": "#06b6d4"},
                        "p99": {"label": "P99", "value": total_latency_ms, "color": "#f59e0b"}
                    },
                    "model_confidence": result["advisory"].confidence,
                    "risk_score": result["risk_assessment"]["risk_score"],
                    "policy_id": policy_id,
                    "policy_risk_tolerance": policy.get("risk_tolerance"),
                    "policy_verbosity": policy.get("verbosity"),
                    "tokens_used": total_tokens,
                    "drift_status": drift_status,
                    "rollback_flag": finding.rollback_flag,
                    "used_fallback": used_fallback
                }
            )
            
            return {
                "finding": finding.title,
                "advisory": result["advisory"].model_dump(),
                "risk_assessment": result["risk_assessment"]
            }
        except SQLAlchemyError as e:
            total_latency_ms = (time.time() - start_time) * 1000
            metrics.increment("failures_total")
            metrics.record_latency(total_latency_ms)
            from app.circuit_breaker import circuit_breaker
            circuit_breaker.record_request(success=False, failed=True)
            
            try:
                record_analytics(
                    org_id=org_id_for_log or "unknown",
                    endpoint="analyze",
                    policy_id=policy_id if 'policy_id' in locals() else None,
                    policy_risk_tolerance=policy.get("risk_tolerance") if 'policy' in locals() else None,
                    policy_verbosity=policy.get("verbosity") if 'policy' in locals() else None,
                    policy_compliance_mode=policy.get("compliance_mode") if 'policy' in locals() else None,
                    tokens_used=total_tokens if 'total_tokens' in locals() else 0,
                    input_tokens=input_tokens if 'input_tokens' in locals() else None,
                    output_tokens=output_tokens if 'output_tokens' in locals() else None,
                    latency_ms=total_latency_ms,
                    llm_latency_ms=llm_latency_ms if 'llm_latency_ms' in locals() else None,
                    success="failure",
                    error_type="database_error",
                    correlation_id=request_id
                )
            except Exception:
                pass
            
            db.rollback()
            logger.error(
                f"Database error",
                extra={
                    "correlation_id": request_id,
                    "org_id": org_id_for_log,
                    "total_latency_ms": total_latency_ms
                },
                exc_info=True
            )
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable"
            )
    except ValueError as e:
        total_latency_ms = (time.time() - start_time) * 1000
        metrics.increment("failures_total")
        metrics.record_latency(total_latency_ms)
        from app.circuit_breaker import circuit_breaker
        circuit_breaker.record_request(success=False, failed=True)
        
        try:
            record_analytics(
                org_id=org_id_for_log or "unknown",
                endpoint="analyze",
                policy_id=policy_id if 'policy_id' in locals() else None,
                policy_risk_tolerance=policy.get("risk_tolerance") if 'policy' in locals() else None,
                policy_verbosity=policy.get("verbosity") if 'policy' in locals() else None,
                policy_compliance_mode=policy.get("compliance_mode") if 'policy' in locals() else None,
                tokens_used=total_tokens if 'total_tokens' in locals() else 0,
                input_tokens=input_tokens if 'input_tokens' in locals() else None,
                output_tokens=output_tokens if 'output_tokens' in locals() else None,
                latency_ms=total_latency_ms,
                llm_latency_ms=llm_latency_ms if 'llm_latency_ms' in locals() else None,
                success="failure",
                error_type="validation_error",
                correlation_id=request_id
            )
        except Exception:
            pass
        
        logger.warning(
            f"Validation error",
            extra={
                "correlation_id": request_id,
                "org_id": org_id_for_log,
                "error": str(e),
                "total_latency_ms": total_latency_ms
            }
        )
        raise HTTPException(status_code=502, detail=f"LLM processing failed: {str(e)}")
    except HTTPException:
        total_latency_ms = (time.time() - start_time) * 1000
        metrics.increment("failures_total")
        metrics.record_latency(total_latency_ms)
        from app.circuit_breaker import circuit_breaker
        circuit_breaker.record_request(success=False, failed=True)
        
        logger.warning(
            f"HTTP exception",
            extra={
                "correlation_id": request_id,
                "org_id": org_id_for_log,
                "total_latency_ms": total_latency_ms
            }
        )
        raise
    except Exception as e:
        total_latency_ms = (time.time() - start_time) * 1000
        metrics.increment("failures_total")
        metrics.record_latency(total_latency_ms)
        from app.circuit_breaker import circuit_breaker
        circuit_breaker.record_request(success=False, failed=True)
        
        try:
            record_analytics(
                org_id=org_id_for_log or "unknown",
                endpoint="analyze",
                policy_id=policy_id if 'policy_id' in locals() else None,
                policy_risk_tolerance=policy.get("risk_tolerance") if 'policy' in locals() else None,
                policy_verbosity=policy.get("verbosity") if 'policy' in locals() else None,
                policy_compliance_mode=policy.get("compliance_mode") if 'policy' in locals() else None,
                tokens_used=total_tokens if 'total_tokens' in locals() else 0,
                input_tokens=input_tokens if 'input_tokens' in locals() else None,
                output_tokens=output_tokens if 'output_tokens' in locals() else None,
                latency_ms=total_latency_ms,
                llm_latency_ms=llm_latency_ms if 'llm_latency_ms' in locals() else None,
                success="error",
                error_type="internal_error",
                correlation_id=request_id
            )
        except Exception:
            pass
        
        logger.error(
            f"Internal error",
            extra={
                "correlation_id": request_id,
                "org_id": org_id_for_log,
                "service_name": service_name,
                "model_version": MODEL_VERSION,
                "total_latency_ms": total_latency_ms
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error. Request ID: {request_id}"
        )
