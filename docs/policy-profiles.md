# AI Policy Profiles - Tenant-Aware AI Behavior
**Implementation Complete** ✅

---

## OVERVIEW

AI Policy Profiles allow per-organization customization of AI advisory behavior while maintaining:
- ✅ Output schema consistency
- ✅ Security guardrails (unchanged)
- ✅ Confidence thresholds (unchanged)
- ✅ No policy can weaken security

---

## POLICY MODEL

**Table:** `ai_policy_profiles`

**Fields:**
- `id`: Primary key
- `org_id`: Unique organization identifier (one policy per org)
- `risk_tolerance`: `low` | `medium` | `high`
- `verbosity`: `concise` | `balanced` | `detailed`
- `compliance_mode`: `none` | `soc2` | `iso` | `hipaa`
- `remediation_style`: `practical` | `strict` | `educational`
- `created_at`: Timestamp
- `updated_at`: Timestamp (auto-updated)

---

## POLICY RESOLUTION

### Default Policy
If no policy exists for an organization:
```python
{
    "risk_tolerance": "medium",
    "verbosity": "balanced",
    "compliance_mode": "none",
    "remediation_style": "practical"
}
```

### Caching
- **TTL:** 5 minutes
- **Thread-safe:** Yes
- **Invalidation:** On policy update
- **Fallback:** Default policy on cache miss or error

### Resolution Flow
```
Request → Load Policy (org_id) → Check Cache → 
  Cache Hit? → Return cached policy
  Cache Miss? → Load from DB → Cache → Return
  DB Miss? → Return default policy → Cache default
```

---

## PROMPT SHAPING

### How It Works

1. **Base Prompt:** Standard advisory prompt (unchanged output format)
2. **Policy Instructions:** Added before output format section
3. **Output Schema:** **NEVER modified** - always preserved

### Policy → Prompt Mapping

| Policy Setting | Prompt Instruction |
|----------------|-------------------|
| `risk_tolerance: low` | "Emphasize conservative risk assessment. Prioritize security over convenience." |
| `risk_tolerance: high` | "Focus on practical risk assessment. Balance security with operational needs." |
| `verbosity: concise` | "Keep explanations brief and to the point. Focus on essential information only." |
| `verbosity: detailed` | "Provide comprehensive explanations. Include context and background where helpful." |
| `compliance_mode: soc2` | "Align recommendations with SOC 2 controls. Emphasize access controls and monitoring." |
| `compliance_mode: iso` | "Align recommendations with ISO 27001 standards. Emphasize risk management and controls." |
| `compliance_mode: hipaa` | "Align recommendations with HIPAA requirements. Emphasize data protection and privacy controls." |
| `remediation_style: strict` | "Provide strict, immediate remediation steps. Prioritize security fixes over operational continuity." |
| `remediation_style: educational` | "Include educational context in remediation steps. Explain why each step is important." |

### Example Shaped Prompt

**Base Prompt:**
```
You are a senior cybersecurity advisor for an enterprise SOC.

You MUST respond using the EXACT format below.
...
---START---
```

**With Policy (SOC 2, strict, detailed):**
```
You are a senior cybersecurity advisor for an enterprise SOC.

You MUST respond using the EXACT format below.

POLICY GUIDANCE:
- Align recommendations with SOC 2 controls. Emphasize access controls and monitoring.
- Provide strict, immediate remediation steps. Prioritize security fixes over operational continuity.
- Provide comprehensive explanations. Include context and background where helpful.

---START---
```

**Output format remains EXACTLY the same** ✅

---

## SAFETY GUARANTEES

### Guardrails Still Enforced
- ✅ Confidence threshold: Still ≥ 0.6
- ✅ Severity validation: Still enforced
- ✅ Content length checks: Still enforced
- ✅ Remediation steps: Still required

### No Security Weakening
- Policies **cannot** lower confidence thresholds
- Policies **cannot** bypass validation
- Policies **cannot** skip guardrails
- Policies **only** modify prompt instructions

---

## OBSERVABILITY

### Logging

**Request Start:**
```json
{
  "correlation_id": "abc-123",
  "org_id": "org-456",
  "policy_id": 1,
  "policy_risk_tolerance": "low",
  "policy_verbosity": "detailed"
}
```

**Request Success:**
```json
{
  "correlation_id": "abc-123",
  "org_id": "org-456",
  "policy_id": 1,
  "policy_risk_tolerance": "low",
  "policy_verbosity": "detailed",
  "total_latency_ms": 15000.2
}
```

### Audit Logs

Policy information included in every audit log entry.

---

## EXAMPLE POLICY CONFIGURATIONS

### 1. Financial Institution (SOC 2, Strict)

```python
{
    "org_id": "org-financial-001",
    "risk_tolerance": "low",
    "verbosity": "detailed",
    "compliance_mode": "soc2",
    "remediation_style": "strict"
}
```

**Effect:**
- Conservative risk assessment
- Comprehensive explanations
- SOC 2-aligned recommendations
- Strict, immediate remediation

### 2. Healthcare Provider (HIPAA, Educational)

```python
{
    "org_id": "org-healthcare-001",
    "risk_tolerance": "medium",
    "verbosity": "detailed",
    "compliance_mode": "hipaa",
    "remediation_style": "educational"
}
```

**Effect:**
- Balanced risk assessment
- Detailed explanations with context
- HIPAA-aligned recommendations
- Educational remediation steps

### 3. Startup (Fast-Moving, Practical)

```python
{
    "org_id": "org-startup-001",
    "risk_tolerance": "high",
    "verbosity": "concise",
    "compliance_mode": "none",
    "remediation_style": "practical"
}
```

**Effect:**
- Practical risk assessment
- Brief, actionable advice
- No specific compliance alignment
- Quick-win remediation steps

See `app/policy_examples.py` for more examples.

---

## EXAMPLE AUDIT LOG ENTRY

### Database Record

```json
{
  "id": 12345,
  "org_id": "org-financial-001",
  "user_id": null,
  "service_name": "scanner-core",
  "policy_id": 1,
  "action": "analyze_finding",
  "payload": {
    "finding_title": "SQL Injection in Login Form",
    "finding_description": "User input directly concatenated into SQL query",
    "scanner": "burp-suite",
    "model": "mistral:7b-instruct",
    "model_version": "mistral:7b-instruct",
    "prompt_version": "1.0.0",
    "guardrail_version": "1.0.0",
    "confidence": 0.85,
    "risk_score": 92,
    "risk_level": "Critical",
    "advisory_id": 67890,
    "auth_type": "service",
    "rag_available": true,
    "llm_latency_ms": 12000.5,
    "total_latency_ms": 15000.2,
    "correlation_id": "abc-123-def-456",
    "policy_id": 1,
    "policy_risk_tolerance": "low",
    "policy_verbosity": "detailed",
    "policy_compliance_mode": "soc2",
    "policy_remediation_style": "strict"
  },
  "created_at": "2026-01-09T12:00:15Z"
}
```

### Key Fields:
- `policy_id`: Links to `ai_policy_profiles.id`
- `payload.policy_*`: Full policy snapshot at time of request
- `org_id`: Organization identifier
- All other standard audit fields preserved

---

## API USAGE

### Creating/Updating Policy

```python
from app.db.crud import create_or_update_policy_profile
from app.db.database import SessionLocal

db = SessionLocal()
policy = create_or_update_policy_profile(
    db=db,
    org_id="org-financial-001",
    risk_tolerance="low",
    verbosity="detailed",
    compliance_mode="soc2",
    remediation_style="strict"
)
```

### Policy Takes Effect
- **Immediately** after creation/update
- Cache invalidated automatically
- Next request for that org_id uses new policy

---

## PERFORMANCE TRACKING BY POLICY

### Metrics Available

All metrics include policy context in audit logs:
- Request count by `policy_id`
- Latency by `policy_risk_tolerance`
- Success rate by `policy_compliance_mode`
- Degraded count by `policy_verbosity`

### Example Query

```sql
-- Average latency by policy risk tolerance
SELECT 
    payload->>'policy_risk_tolerance' as risk_tolerance,
    AVG((payload->>'total_latency_ms')::float) as avg_latency_ms
FROM audit_logs
WHERE action = 'analyze_finding'
GROUP BY payload->>'policy_risk_tolerance';
```

---

## FILES CREATED/MODIFIED

1. **`app/db/models.py`** - Added `AIPolicyProfile` model
2. **`app/policy_loader.py`** - Policy loading with 5-min TTL cache
3. **`app/prompt_shaper.py`** - Prompt shaping based on policy
4. **`app/db/crud.py`** - Policy CRUD operations
5. **`app/advisory_engine.py`** - Policy integration
6. **`app/main.py`** - Policy tracking in logs and audit
7. **`app/policy_examples.py`** - Example configurations

---

## SAFETY SUMMARY

✅ **Output Schema:** Never modified  
✅ **Guardrails:** Always enforced  
✅ **Confidence Thresholds:** Unchanged  
✅ **Security:** Cannot be weakened by policy  
✅ **Observability:** Full policy tracking  

---

**AI Policy Profiles are production-ready** ✅

