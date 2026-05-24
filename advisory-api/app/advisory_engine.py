import logging
import sys
from typing import Dict
from app.schemas import FindingInput, AdvisoryStructuredResponse
from app.prompt_shaper import ADVISORY_PROMPT
from app.ollama_client import query_llm, MODEL_NAME, FALLBACK_MODEL
from app.utils import parse_advisory_output
from app.risk_engine import calculate_risk_score
from app.context_retriever import retrieve_context
from app.validators.advisory_guardrails import validate_advisory
from app.policy_loader import load_policy
from app.prompt_shaper import shape_prompt
from app.model_manager import model_manager
from app.model_health import model_health_tracker
from app.config import SLA_LATENCY_THRESHOLD_MS
from app.performance_intelligence import performance_intelligence
from app import tracing

logger = logging.getLogger(__name__)

def generate_advisory(
    finding: FindingInput,
    org_id: str = None,
    active_model: str = None,
    correlation_id: str = None
) -> tuple[dict, bool, Dict, Dict, bool, Dict, bool, Dict]:
    """
    Generate advisory for a security finding with multi-model failover.
    
    Args:
        finding: Finding input data
        org_id: Organization ID
        active_model: Optional active model to use (overrides default)
        correlation_id: Correlation ID for logging
    
    Returns:
        tuple: (result_dict, rag_available, policy, token_usage, used_fallback, applied_policy_params, degradation_used, explainability_data)
        - result_dict: Advisory and risk assessment
        - rag_available: True if RAG was used, False if degraded mode
        - policy: Policy profile used for this request
        - token_usage: Token usage metadata from LLM
        - used_fallback: True if fallback model was used
        - applied_policy_params: Policy parameters applied from scanner (if any)
        - degradation_used: True if verbosity or severity sensitivity degradation was applied
    """
    # 🔹 Langfuse: open top-level trace — closed automatically via 'with' block
    with tracing.start_trace(
        "generate-advisory",
        input={"title": finding.title, "severity": finding.severity, "asset": finding.affected_asset},
        user_id=org_id or "default",
        session_id=org_id or "default",
        metadata={"correlation_id": correlation_id},
    ) as _trace:
        try:
            # 🔹 Load AI policy profile for organization
            with tracing.start_span("load-policy"):
                policy = load_policy(org_id) if org_id else load_policy("default")
            
            # 🔹 Apply optimized policy instructions from scanner (if provided)
            # These override the loaded policy for this request only
            # Policy overrides are applied to system prompt via shape_prompt() - preserves output schema
            applied_policy_params = {}
            original_policy = policy.copy()  # Keep original for logging
            
            if finding.risk_tolerance:
                policy["risk_tolerance"] = finding.risk_tolerance
                applied_policy_params["risk_tolerance"] = finding.risk_tolerance
            if finding.verbosity:
                policy["verbosity"] = finding.verbosity
                applied_policy_params["verbosity"] = finding.verbosity
            if finding.remediation_style:
                policy["remediation_style"] = finding.remediation_style
                applied_policy_params["remediation_style"] = finding.remediation_style
            
            # Log applied policy parameters (comprehensive logging)
            if applied_policy_params:
                logger.info(
                    f"Optimized policy parameters applied from scanner",
                    extra={
                        "correlation_id": correlation_id,
                        "org_id": org_id,
                        "policy_id": policy.get("policy_id"),
                        "applied_policy_params": applied_policy_params,
                        "original_policy": {
                            "risk_tolerance": original_policy.get("risk_tolerance"),
                            "verbosity": original_policy.get("verbosity"),
                            "remediation_style": original_policy.get("remediation_style")
                        },
                        "updated_policy": {
                            "risk_tolerance": policy.get("risk_tolerance"),
                            "verbosity": policy.get("verbosity"),
                            "remediation_style": policy.get("remediation_style")
                        },
                        "decision_reason": finding.decision_reason,
                        "note": "Policy overrides applied to system prompt only, output schema preserved"
                    }
                )
            
            # 🔹 Check model health for load-aware degradation
            # Determine model to use first to check its health
            model_to_check = active_model or finding.active_model
            if not model_to_check and org_id:
                model_to_check = model_manager.get_org_model(org_id)
            if not model_to_check:
                model_to_check = model_manager.get_default_model()
            
            # Load-aware verbosity degradation and self-healing intelligence
            original_verbosity = policy.get("verbosity", "balanced")
            degraded_verbosity = original_verbosity
            severity_sensitivity_reduction = 0.0  # Track if we need to reduce severity sensitivity
            fallback_notice = None  # Track fallback notices for audit logs
            
            if model_to_check:
                model_health = model_health_tracker.get_model_health(model_to_check)
                
                # 1. Detect latency spikes (SLA-based verbosity degradation)
                if model_health and model_health["avg_latency_ms"] > SLA_LATENCY_THRESHOLD_MS:
                    # Degrade verbosity: detailed -> balanced -> concise
                    if original_verbosity == "detailed":
                        degraded_verbosity = "balanced"
                    elif original_verbosity == "balanced":
                        degraded_verbosity = "concise"
                    # concise stays concise
                    
                    if degraded_verbosity != original_verbosity:
                        fallback_notice = f"Latency spike detected ({model_health['avg_latency_ms']:.1f}ms > {SLA_LATENCY_THRESHOLD_MS}ms). Verbosity reduced from {original_verbosity} to {degraded_verbosity}."
                        logger.info(
                            f"Self-healing: Latency spike detected, verbosity reduced",
                            extra={
                                "correlation_id": correlation_id,
                                "org_id": org_id,
                                "model_name": model_to_check,
                                "original_verbosity": original_verbosity,
                                "degraded_verbosity": degraded_verbosity,
                                "avg_latency_ms": model_health["avg_latency_ms"],
                                "sla_threshold_ms": SLA_LATENCY_THRESHOLD_MS
                            }
                        )
                        # Update policy with degraded verbosity
                        policy = policy.copy()
                        policy["verbosity"] = degraded_verbosity
                
                # 2. Detect confidence drop patterns (self-healing)
                if performance_intelligence.should_trigger_self_healing(model_to_check):
                    confidence_trend = performance_intelligence.get_confidence_trend(model_to_check)
                    
                    # Reduce verbosity if not already reduced
                    if degraded_verbosity == original_verbosity:
                        if original_verbosity == "detailed":
                            degraded_verbosity = "balanced"
                        elif original_verbosity == "balanced":
                            degraded_verbosity = "concise"
                    
                    # Reduce severity sensitivity
                    severity_sensitivity_reduction = 0.1  # 10% reduction
                    
                    confidence_notice = f"Confidence drop detected ({confidence_trend['drop_percent']:.1f}% decline). Verbosity reduced from {original_verbosity} to {degraded_verbosity}, severity sensitivity reduced by 10%."
                    if fallback_notice:
                        fallback_notice = f"{fallback_notice} {confidence_notice}"
                    else:
                        fallback_notice = confidence_notice
                    
                    logger.warning(
                        f"Self-healing triggered: Confidence drop pattern detected",
                        extra={
                            "correlation_id": correlation_id,
                            "org_id": org_id,
                            "model_name": model_to_check,
                            "confidence_drop_percent": confidence_trend["drop_percent"],
                            "recent_avg": confidence_trend["recent_avg"],
                            "older_avg": confidence_trend["older_avg"],
                            "original_verbosity": original_verbosity,
                            "adjusted_verbosity": degraded_verbosity,
                            "severity_sensitivity_reduction": severity_sensitivity_reduction
                        }
                    )
                    
                    # Update policy with self-healing adjustments
                    policy = policy.copy()
                    policy["verbosity"] = degraded_verbosity
                    policy["severity_sensitivity_reduction"] = severity_sensitivity_reduction
            
            # 🔹 RAG: fetch relevant security knowledge (CRITICAL FIX: pass org_id for multi-tenant isolation)
            with tracing.start_span("rag-retrieval") as _rag_span:
                context, rag_available = retrieve_context(finding.description, org_id=org_id)
                _rag_span.update(output={"rag_available": rag_available, "context_chars": len(context) if context else 0})

            # 🔹 Fetch prompt from Langfuse Registry (remote) or fallback to local code
            base_prompt = tracing.get_prompt("advisory-base", ADVISORY_PROMPT)
            
            # 🔹 Shape prompt based on policy (modifies instructions, preserves output format)
            shaped_prompt = shape_prompt(base_prompt, policy)
            
            # 🔹 Build prompt with finding details
            # Using a safer replacement method to avoid KeyError on JSON braces in the prompt
            replacements = {
                "title": finding.title,
                "description": finding.description,
                "severity": finding.severity or "Unknown",
                "evidence": finding.evidence or "Not provided",
                "asset": finding.affected_asset or "Unknown"
            }
            
            prompt = shaped_prompt
            for key, value in replacements.items():
                # Support both {variable} and {{variable}} styles
                prompt = prompt.replace(f"{{{{{key}}}}}", str(value)).replace(f"{{{key}}}", str(value))

            if context:
                prompt += f"\n\nREFERENCE CONTEXT:\n{context}"

            # 🔹 Determine model to use (with hot-reload support, model_override, and force_model)
            # Priority: force_model > model_override > active_model > org_config > default
            # Log model selection decision for auditability
            model_selection_reason = []
            model_to_use = None
            primary_model = None
            fallback_model = FALLBACK_MODEL  # Fallback disabled by default to prevent resource exhaustion
            
            # Check force_model first (highest priority, but fallback still allowed)
            if finding.force_model:
                model_to_use = finding.force_model
                primary_model = finding.force_model
                model_selection_reason.append(f"force_model:{model_to_use}")
                logger.info(
                    f"Force model override applied (fallback still allowed)",
                    extra={
                        "correlation_id": correlation_id,
                        "org_id": org_id,
                        "force_model": finding.force_model,
                        "fallback_model": fallback_model
                    }
                )
            
            # Check model_override if force_model not provided
            elif finding.model_override:
                model_to_use = finding.model_override
                primary_model = finding.model_override
                model_selection_reason.append(f"model_override:{model_to_use}")
                logger.info(
                    f"Model override from scanner applied",
                    extra={
                        "correlation_id": correlation_id,
                        "org_id": org_id,
                        "model_override": finding.model_override
                    }
                )
            
            # Fall back to other sources if neither force_model nor model_override provided
            if not model_to_use:
                model_to_use = active_model or finding.active_model
                if model_to_use:
                    primary_model = model_to_use
                    model_selection_reason.append(f"request_payload:{model_to_use}")
                
                if not model_to_use and org_id:
                    # Check org-specific model from model manager
                    model_to_use = model_manager.get_org_model(org_id)
                    if model_to_use:
                        primary_model = model_to_use
                        model_selection_reason.append(f"org_config:{model_to_use}")
                
                if not model_to_use:
                    # Use default from model manager (supports hot-reload)
                    model_to_use = model_manager.get_default_model()
                    primary_model = model_to_use
                    model_selection_reason.append(f"default:{model_to_use}")
            
            # Ensure primary_model is set
            if not primary_model:
                primary_model = model_to_use
            
            # Generate decision_reason if not provided
            decision_reason = finding.decision_reason
            if not decision_reason:
                decision_reason = f"Model selected via: {' -> '.join(model_selection_reason)}"
            
            # Log model selection decision with explainability fields (comprehensive logging)
            logger.info(
                f"Model selection decision (explainable AI)",
                extra={
                    "correlation_id": correlation_id,
                    "org_id": org_id,
                    "policy_id": policy.get("policy_id"),
                    "selected_model": model_to_use,
                    "primary_model": primary_model,
                    "fallback_model": fallback_model,
                    "decision_reason": decision_reason,
                    "selection_reason": " -> ".join(model_selection_reason),
                    "request_active_model": active_model or finding.active_model,
                    "force_model": finding.force_model,
                    "model_override": finding.model_override,
                    "applied_policy_params": applied_policy_params,
                    "rollback_flag": finding.rollback_flag if hasattr(finding, 'rollback_flag') else None
                }
            )
            
            # 🔹 Call LLM with failover support
            # Fallback to default model if override fails (force_model or model_override)
            try:
                raw_output, token_usage, used_fallback = query_llm(
                    prompt=prompt,
                    model=model_to_use,
                    fallback_model=fallback_model,
                    org_id=org_id,
                    correlation_id=correlation_id
                )
                
                # Log fallback if used (comprehensive logging)
                if used_fallback:
                    logger.warning(
                        f"Model failover occurred (override model failed, using fallback)",
                        extra={
                            "correlation_id": correlation_id,
                            "org_id": org_id,
                            "policy_id": policy.get("policy_id"),
                            "primary_model": model_to_use,
                            "fallback_model": fallback_model,
                            "force_model": finding.force_model,
                            "model_override": finding.model_override,
                            "applied_policy_params": applied_policy_params
                        }
                    )
            except Exception as e:
                # If both models fail, log and re-raise
                logger.error(
                    f"All models failed (primary and fallback)",
                    extra={
                        "correlation_id": correlation_id,
                        "org_id": org_id,
                        "policy_id": policy.get("policy_id"),
                        "primary_model": model_to_use,
                        "fallback_model": fallback_model,
                        "force_model": finding.force_model,
                        "model_override": finding.model_override,
                        "applied_policy_params": applied_policy_params,
                        "error": str(e)
                    },
                    exc_info=True
                )
                raise
            
            # 🔹 Parse LLM output and validate — wrapped in a span for observability
            with tracing.start_span("parse-and-validate") as _parse_span:
                try:
                    parsed = parse_advisory_output(raw_output)
                except Exception as parse_error:
                    logger.error(
                        f"Failed to parse LLM output (both JSON and text format failed)",
                        extra={
                            "correlation_id": correlation_id,
                            "org_id": org_id,
                            "model": model_to_use if not used_fallback else fallback_model,
                            "used_fallback": used_fallback,
                            "error": str(parse_error),
                            "output_preview": raw_output[:500] if raw_output else "No output"
                        },
                        exc_info=True
                    )
                    raise ValueError(f"LLM returned invalid output that could not be parsed: {str(parse_error)}")

                advisory = AdvisoryStructuredResponse(**parsed)

                # 🔹 Validate advisory against trust guarantees
                validate_advisory(advisory)
                _parse_span.update(output={"severity": advisory.severity, "confidence": advisory.confidence})

            # 🔹 Record confidence for performance intelligence
            # Use actual model that was used (fallback or primary)
            actual_model_used = fallback_model if used_fallback else model_to_use
            performance_intelligence.record_confidence(actual_model_used, advisory.confidence)
            
            # 🔹 Deterministic risk scoring (with self-healing severity sensitivity reduction)
            # Apply severity sensitivity reduction if self-healing was triggered
            ai_severity_for_scoring = advisory.severity
            if severity_sensitivity_reduction > 0:
                # Reduce severity sensitivity by downgrading severity one level
                severity_map = {"Critical": "High", "High": "Medium", "Medium": "Low", "Low": "Low"}
                ai_severity_for_scoring = severity_map.get(ai_severity_for_scoring, ai_severity_for_scoring)
                logger.info(
                    f"Severity sensitivity reduced (self-healing)",
                    extra={
                        "correlation_id": correlation_id,
                        "org_id": org_id,
                        "original_severity": advisory.severity,
                        "adjusted_severity": ai_severity_for_scoring,
                        "reduction_percent": severity_sensitivity_reduction * 100
                    }
                )
            
            risk = calculate_risk_score(
                scanner_severity=finding.severity or "Medium",
                ai_severity=ai_severity_for_scoring,
                confidence=advisory.confidence,
                asset=finding.affected_asset or "Default"
            )

            # Track if degradation was used (verbosity or severity sensitivity reduction)
            degradation_used = (
                degraded_verbosity != original_verbosity or
                severity_sensitivity_reduction > 0
            )
            
            # Prepare explainability data for logging and audit
            # Includes all required fields: selected_model, fallback_model, decision_reason
            explainability_data = {
                "decision_reason": decision_reason,
                "selected_model": model_to_use,  # The model that was selected to use
                "primary_model": primary_model,
                "fallback_model": fallback_model,
                "actual_model_used": actual_model_used,
                "fallback_notice": fallback_notice  # Include self-healing notices
            }

            # 🔹 Langfuse: record quality scores on the trace
            _risk_score = risk.get("risk_score", 0) if isinstance(risk, dict) else getattr(risk, "risk_score", 0)
            _trace.update(output={
                "severity": advisory.severity,
                "confidence": advisory.confidence,
                "risk_score": _risk_score,
                "used_fallback": used_fallback,
                "rag_available": rag_available,
                "actual_model_used": actual_model_used,
            })
            tracing.add_score(_trace.trace_id, "confidence", float(advisory.confidence))
            if _risk_score:
                tracing.add_score(_trace.trace_id, "risk_score", float(_risk_score) / 100.0)

            return {
                "advisory": advisory,
                "risk_assessment": risk
            }, rag_available, policy, token_usage, used_fallback, applied_policy_params, degradation_used, explainability_data

        except Exception:
            # Langfuse: record the error on the trace before re-raising
            _trace.update(output={"error": True})
            raise
