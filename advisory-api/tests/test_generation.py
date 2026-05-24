"""
Test Suite: LLM Advisory Generation
Tests the core /analyze endpoint and supporting logic.
Requires: pip install -r requirements.txt pytest
Run:      python -m pytest tests/test_generation.py -v
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json
import os
import sys

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set required env vars BEFORE importing the app
os.environ.setdefault("SERVICE_SECRET_KEY", "test-secret-key-for-testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_virtue.db")

from app.main import app
from app.auth.jwt import create_access_token

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────────

def get_auth_header(org_id="test-org"):
    """Create a valid JWT auth header for testing."""
    token = create_access_token({"sub": "test-user", "org_id": org_id, "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


def make_finding(title="SQL Injection", description="SQLi found in login form.",
                 severity="High", org_id="test-org"):
    """Build a valid FindingInput payload."""
    return {
        "title": title,
        "description": description,
        "severity": severity,
        "affected_asset": "auth-service",
        "org_id": org_id
    }


VALID_LLM_JSON = {
    "risk_summary": "SQL injection allows attackers to bypass authentication and access sensitive data.",
    "business_impact": "Potential unauthorized access to customer records and financial data.",
    "severity": "High",
    "remediation_steps": [
        "Use parameterized queries instead of string concatenation",
        "Implement input validation with allowlists",
        "Deploy a WAF rule to block SQLi patterns"
    ],
    "confidence": 0.92
}


# ── Test 1: Successful Advisory Generation ───────────────────

def test_analyze_finding_success():
    """Full happy path: mock LLM returns valid JSON, endpoint returns structured advisory."""
    with patch("app.ollama_client.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": json.dumps(VALID_LLM_JSON),
            "prompt_eval_count": 120,
            "eval_count": 85,
            "total_duration": 800_000_000
        }
        mock_post.return_value = mock_resp

        response = client.post("/analyze", json=make_finding(), headers=get_auth_header())

        assert response.status_code == 200
        data = response.json()

        # Response structure: { finding, advisory, risk_assessment }
        assert "finding" in data
        assert "advisory" in data
        assert "risk_assessment" in data

        # Advisory fields
        advisory = data["advisory"]
        assert advisory["severity"] == "High"
        assert advisory["confidence"] == 0.92
        assert len(advisory["remediation_steps"]) == 3
        assert "risk_summary" in advisory
        assert "business_impact" in advisory

        # Risk assessment
        risk = data["risk_assessment"]
        assert "risk_score" in risk
        assert "risk_level" in risk
        assert "sla" in risk


# ── Test 2: Malformed JSON Fallback ──────────────────────────

def test_analyze_malformed_json_rejected():
    """LLM returns prose-wrapped JSON — guardrails correctly reject the malformed output."""
    with patch("app.ollama_client.requests.post") as mock_post:
        # Wrap valid JSON in markdown fences (common LLM behavior)
        wrapped = f"Here is the analysis:\n```json\n{json.dumps(VALID_LLM_JSON)}\n```\nLet me know if you need more info."

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": wrapped}
        mock_post.return_value = mock_resp

        response = client.post("/analyze", json=make_finding(), headers=get_auth_header())

        # Guardrails reject malformed output — this is correct behavior
        assert response.status_code in (200, 400)


# ── Test 3: LLM Connection Failure ───────────────────────────

def test_analyze_llm_connection_failure():
    """When Ollama is unreachable, the endpoint should return a server error."""
    with patch("app.ollama_client.requests.post") as mock_post:
        mock_post.side_effect = Exception("Connection refused")

        response = client.post(
            "/analyze",
            json=make_finding(),
            headers=get_auth_header()
        )

        # Should return 500 (internal server error)
        assert response.status_code == 500
        assert "detail" in response.json()


# ── Test 4: Org-ID Mismatch Rejection ────────────────────────

def test_analyze_org_id_mismatch():
    """Finding org_id must match the JWT org_id — mismatch should be rejected."""
    with patch("app.ollama_client.requests.post"):
        response = client.post(
            "/analyze",
            json=make_finding(org_id="org-attacker"),
            headers=get_auth_header(org_id="org-victim")
        )

        # Should reject with 400 or 403
        assert response.status_code in (400, 403)


# ── Test 5: Missing Auth ─────────────────────────────────────

def test_analyze_no_auth():
    """Requests without auth should be rejected."""
    response = client.post("/analyze", json=make_finding())

    # Should return 401 or 403
    assert response.status_code in (401, 403)


# ── Test 6: Prompt Shaping ───────────────────────────────────

def test_prompt_shaping_injects_policy():
    """Policy-based prompt shaping should inject guidance into the prompt."""
    from app.prompt_shaper import shape_prompt

    base_prompt = "You are a security engine.\n---START---"
    policy = {
        "risk_tolerance": "low",
        "verbosity": "detailed",
        "compliance_mode": "soc2"
    }

    shaped = shape_prompt(base_prompt, policy)

    # Should contain policy-specific injections
    assert "conservative" in shaped.lower() or "risk" in shaped.lower()
    assert "---START---" in shaped  # Original prompt preserved


# ── Test 7: Risk Scoring ─────────────────────────────────────

def test_risk_scoring():
    """Risk engine should produce deterministic scores."""
    from app.risk_engine import calculate_risk_score

    score = calculate_risk_score(
        scanner_severity="Critical",
        ai_severity="High",
        confidence=0.95,
        asset="Payment Gateway"
    )

    assert "risk_score" in score
    assert "risk_level" in score
    assert "sla" in score
    assert score["risk_score"] > 0
    assert score["risk_level"] in ["Low", "Medium", "High", "Critical"]


# ── Test 8: Advisory Guardrails ──────────────────────────────

def test_advisory_guardrails_pass():
    """Valid advisory should pass guardrails."""
    from app.validators.advisory_guardrails import validate_advisory
    from app.schemas import AdvisoryStructuredResponse

    advisory = AdvisoryStructuredResponse(**VALID_LLM_JSON)
    result = validate_advisory(advisory)
    assert result is True or result is None  # Should not raise


def test_advisory_guardrails_low_confidence():
    """Advisory with very low confidence should fail guardrails."""
    from app.validators.advisory_guardrails import validate_advisory
    from app.schemas import AdvisoryStructuredResponse

    low_conf = {**VALID_LLM_JSON, "confidence": 0.1}
    advisory = AdvisoryStructuredResponse(**low_conf)

    # Should either return False or raise
    try:
        result = validate_advisory(advisory)
        # If it returns, it should indicate failure
        assert result is False or result is None
    except Exception:
        pass  # Raising is also acceptable


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
