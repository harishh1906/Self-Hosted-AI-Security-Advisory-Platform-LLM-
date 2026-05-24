# AI Advisory Service - Integration Contract
**Version:** 1.0  
**Status:** ⚠️ Pending Critical Fixes (See INTEGRATION_READINESS_REVIEW.md)

---

## ENDPOINT

```
POST http://ai-advisory:8000/analyze
```

**Network:** Internal Docker network only (not exposed publicly)

---

## REQUEST

### Headers (Service-to-Service)

| Header | Required | Example | Notes |
|--------|----------|---------|-------|
| `X-Service-Name` | ✅ Yes | `scanner-core` | Service identifier |
| `X-Service-Signature` | ✅ Yes | `a1b2c3...` | HMAC-SHA256 signature |
| `X-Timestamp` | ✅ Yes | `1704800000` | Unix timestamp (within 5 min) |
| `X-Body-Hash` | ✅ Yes | `e3b0c4...` | SHA256 of request body JSON |
| `X-Org-ID` | ✅ Yes | `org-123` | Organization ID |
| `Content-Type` | ✅ Yes | `application/json` | |

### Request Body

```json
{
  "title": "Broken Access Control",
  "description": "User can access admin endpoint without authorization",
  "severity": "Critical",
  "evidence": "HTTP 200 response from /admin/users",
  "affected_asset": "Admin API",
  "scanner": "burp-suite",
  "org_id": "org-123"
}
```

### Field Specifications

| Field | Type | Required | Max Length | Format |
|-------|------|----------|------------|--------|
| `title` | string | ✅ Yes | 500 | - |
| `description` | string | ✅ Yes | 10000 | - |
| `severity` | string | ❌ No | 50 | Low/Medium/High/Critical |
| `evidence` | string | ❌ No | 5000 | - |
| `affected_asset` | string | ❌ No | 200 | - |
| `scanner` | string | ❌ No | 100 | - |
| `org_id` | string | ✅ Yes | 100 | `[a-zA-Z0-9_-]+` |

---

## RESPONSE (FROZEN SCHEMA)

### Success (200 OK)

```json
{
  "finding": "Broken Access Control",
  "advisory": {
    "risk_summary": "Unauthorized access to administrative endpoints...",
    "business_impact": "Potential data breach and compliance violations...",
    "severity": "Critical",
    "remediation_steps": [
      "Implement role-based access control (RBAC)",
      "Add authentication checks to all admin endpoints",
      "Enable audit logging for access attempts"
    ],
    "confidence": 0.85
  },
  "risk_assessment": {
    "risk_score": 92,
    "risk_level": "Critical",
    "sla": "24h",
    "justification": "Critical risk based on severity, asset criticality, and AI confidence"
  }
}
```

### Error Responses

#### 400 Bad Request (Validation Error)
```json
{
  "detail": "org_id required for multi-tenant isolation"
}
```

#### 401 Unauthorized (Auth Failure)
```json
{
  "detail": "Invalid service signature"
}
```

#### 500 Internal Server Error
```json
{
  "detail": "Internal server error. Request ID: abc123"
}
```

#### 503 Service Unavailable
```json
{
  "detail": "Service temporarily unavailable"
}
```

---

## SIGNATURE GENERATION (Python)

```python
import hmac
import hashlib
import time
import json

SERVICE_SECRET_KEY = os.getenv("SERVICE_SECRET_KEY")

def generate_service_headers(service_name: str, body: dict) -> dict:
    """Generate HMAC signature headers for service authentication."""
    timestamp = str(int(time.time()))
    body_json = json.dumps(body, sort_keys=True, separators=(',', ':'))
    body_hash = hashlib.sha256(body_json.encode()).hexdigest()
    
    message = f"{service_name}:{timestamp}:{body_hash}".encode()
    signature = hmac.new(
        SERVICE_SECRET_KEY.encode(),
        message,
        hashlib.sha256
    ).hexdigest()
    
    return {
        "X-Service-Name": service_name,
        "X-Service-Signature": signature,
        "X-Timestamp": timestamp,
        "X-Body-Hash": body_hash,
        "X-Org-ID": body.get("org_id"),
        "Content-Type": "application/json"
    }
```

### Example Usage

```python
import requests

finding = {
    "title": "Broken Access Control",
    "description": "User can access admin endpoint",
    "severity": "Critical",
    "org_id": "org-123"
}

headers = generate_service_headers("scanner-core", finding)

response = requests.post(
    "http://ai-advisory:8000/analyze",
    json=finding,
    headers=headers,
    timeout=150  # 120s LLM + 30s buffer
)

if response.status_code == 200:
    advisory = response.json()
    # Use advisory["advisory"] and advisory["risk_assessment"]
else:
    error = response.json()
    # Handle error["detail"]
```

---

## TIMEOUTS & RETRIES

- **Request Timeout:** 150 seconds (120s LLM + 30s buffer)
- **Retry Strategy:** Exponential backoff (2s, 4s, 8s) for 5xx errors
- **Max Retries:** 3 attempts

---

## MULTI-TENANCY REQUIREMENTS

1. **org_id MUST be provided** in request body or `X-Org-ID` header
2. **org_id MUST match** between finding and service identity (if both provided)
3. **org_id format:** Alphanumeric, hyphens, underscores only (`[a-zA-Z0-9_-]+`)
4. **Data isolation:** All advisories and audit logs scoped by `org_id`

---

## PERFORMANCE CHARACTERISTICS

- **Typical Response Time:** 10-30 seconds (LLM inference)
- **P95 Response Time:** 60 seconds
- **P99 Response Time:** 120 seconds (timeout)
- **Throughput:** ~2-5 requests/second (limited by LLM)

---

## DEPENDENCIES

- **Ollama LLM:** Must be running and model loaded
- **Qdrant:** Must be running (graceful degradation if unavailable)
- **PostgreSQL:** Must be running (required for persistence)

---

## MONITORING

Monitor these metrics:
- Request rate by `org_id`
- Response time (p50, p95, p99)
- Error rate (4xx, 5xx)
- LLM timeout rate
- Database connection pool usage

---

## SECURITY NOTES

1. **Internal Network Only:** Service not exposed to internet
2. **HMAC Required:** All service calls must include valid signature
3. **Timestamp Window:** 5 minutes (prevents replay attacks)
4. **org_id Validation:** Enforced at multiple layers
5. **Error Sanitization:** Internal errors not exposed to clients

---

**Last Updated:** 2026-01-09  
**Next Review:** After critical fixes implemented

