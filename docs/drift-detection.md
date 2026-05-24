# AI Output Drift Detection
**Implementation Complete** ✅

---

## OVERVIEW

AI Output Drift Detection monitors AI behavior over time to detect:
- Slow degradation in output quality
- Prompt/model behavior changes
- Distribution shifts in severity/risk scores

**Goal:** Alert before customers notice quality issues.

---

## BASELINE MODEL

**Table:** `ai_output_baselines`

**Key:** `(org_id, endpoint, policy_id)` - Unique baseline per organization+endpoint+policy combination

**Fields:**
- `org_id`: Organization ID (multi-tenancy isolation)
- `endpoint`: Endpoint name (default: "analyze")
- `policy_id`: Policy profile ID (NULL for default policy)
- `confidence_median`: Rolling 7-day median confidence
- `remediation_steps_count_median`: Rolling 7-day median step count
- `description_length_median`: Rolling 7-day median description length
- `severity_distribution`: JSON distribution of severities (e.g., `{"Low": 0.2, "Medium": 0.5, "High": 0.2, "Critical": 0.1}`)
- `risk_score_distribution`: JSON with median, p25, p75 (e.g., `{"median": 65, "p25": 45, "p75": 85}`)
- `sample_count`: Number of samples in baseline
- `last_updated`: Timestamp of last update

---

## DRIFT DETECTION

### Comparison Window
- **Current:** Single observation (current request)
- **Baseline:** Previous 7 days (rolling median)
- **Minimum Samples:** Configurable via `min_samples_for_baseline` (default: 10)

### Detection Thresholds (Configurable)

**File:** `app/config.py`

```python
DRIFT_THRESHOLDS = {
    "confidence_drop_percent": 5.0,  # 5% drop in confidence
    "remediation_steps_variance_percent": 30.0,  # ±30% variance in remediation steps
    "severity_distribution_shift_threshold": 0.1,  # If severity appears < 10% in baseline, it's a shift
    "risk_score_median_shift_points": 10,  # 10 point shift in median risk score
    "min_samples_for_baseline": 10  # Minimum samples required for valid baseline
}
```

### Drift Checks

1. **Confidence Drop**
   - Compares current confidence vs baseline median
   - Triggers if drop > 5%

2. **Remediation Steps Variance**
   - Compares current step count vs baseline median
   - Triggers if variance > ±30%

3. **Severity Distribution Shift**
   - Compares current severity vs baseline distribution
   - Triggers if current severity appears less than threshold (default: 10%) in baseline

4. **Risk Score Median Shift**
   - Compares current risk score vs baseline median
   - Triggers if shift > 10 points

---

## OUTPUT

### Status
- `DRIFT_DETECTED`: One or more drift conditions met
- `STABLE`: No drift detected

### Reason Codes (Machine Readable)

Examples:
- `CONFIDENCE_DROP_7.5%`
- `REMEDIATION_STEPS_VARIANCE_45.2%`
- `SEVERITY_DISTRIBUTION_SHIFT_Critical`
- `RISK_SCORE_SHIFT_15_POINTS`

---

## INTEGRATION

### Flow

```
Generate Advisory → Extract Metrics → Detect Drift → 
  Log Result → Update Baseline → Return Response
```

### Location
- **File:** `app/main.py`
- **Runs:** After advisory generation, before audit log
- **Non-blocking:** Drift detection errors don't block requests

---

## EXAMPLE ALERT LOGS

### Drift Detected (Structured Log)

```json
{
  "timestamp": "2026-01-09T12:00:15Z",
  "level": "WARNING",
  "message": "AI output drift detected",
  "correlation_id": "abc-123-def-456",
  "org_id": "org-financial-001",
  "policy_id": 1,
  "endpoint": "analyze",
  "reason_codes": [
    "CONFIDENCE_DROP_7.5%",
    "REMEDIATION_STEPS_VARIANCE_45.2%",
    "RISK_SCORE_SHIFT_12_POINTS"
  ],
  "current_confidence": 0.72,
  "baseline_confidence": 0.78
}
```

**Log Location:** Application logs (structured JSON format)  
**Alert Action:** Monitor drift frequency and investigate if > 5% of requests show drift

### Stable (No Drift)

```json
{
  "timestamp": "2026-01-09T12:00:15Z",
  "level": "INFO",
  "message": "Request completed successfully",
  "correlation_id": "abc-123-def-456",
  "org_id": "org-financial-001",
  "policy_id": 1,
  "drift_status": "STABLE",
  "drift_reasons": []
}
```

---

## EXAMPLE AUDIT LOG ENTRY (WITH DRIFT)

```json
{
  "id": 12345,
  "org_id": "org-financial-001",
  "policy_id": 1,
  "action": "analyze_finding",
  "payload": {
    "finding_title": "SQL Injection",
    "confidence": 0.72,
    "risk_score": 88,
    "correlation_id": "abc-123-def-456",
    "drift_status": "DRIFT_DETECTED",
    "drift_reasons": [
      "CONFIDENCE_DROP_7.5%",
      "RISK_SCORE_SHIFT_12_POINTS"
    ]
  },
  "created_at": "2026-01-09T12:00:15Z"
}
```

---

## BASELINE CALCULATION

### Method
- **Source:** Audit logs (last 7 days)
- **Filter:** By `org_id`, `endpoint`, and `policy_id` (multi-tenant isolation)
- **Metrics:** Calculated from `payload` fields
- **Update:** Recalculated on each request (non-blocking, can be optimized to async)

### Metrics Extracted from Audit Log Payload
- `confidence`: From `payload.confidence`
- `risk_score`: From `payload.risk_score`
- `severity`: From `payload.severity` (for severity distribution)
- `remediation_steps_count`: From `payload.remediation_steps_count`
- `description_length`: From `payload.description_length`

All metrics are stored in the audit log payload for efficient baseline calculation.

---

## CONFIGURATION KNOBS

### Adjust Thresholds

**File:** `app/config.py`

```python
DRIFT_THRESHOLDS = {
    "confidence_drop_percent": 5.0,  # Adjust sensitivity
    "remediation_steps_variance_percent": 30.0,
    "severity_distribution_shift_threshold": 0.1,  # Adjust threshold (0.0-1.0)
    "risk_score_median_shift_points": 10,
    "min_samples_for_baseline": 10  # Adjust minimum samples required
}
```

All thresholds are configurable in `app/config.py`. Changes take effect on restart.

---

## SAFETY

✅ **Non-blocking:** Drift detection errors don't block requests  
✅ **No content storage:** Only metrics stored, no advisory content  
✅ **Production-safe:** Fail-safe defaults, graceful error handling  
✅ **Observable:** Full logging with correlation IDs  

---

## FILES CREATED/MODIFIED

1. `app/db/models.py` - Added `AIOutputBaseline` model with `org_id` for multi-tenancy
2. `app/drift/detector.py` - Drift detection logic with org-scoped baselines
3. `app/config.py` - Drift thresholds configuration
4. `app/main.py` - Drift detection integration (runs after advisory generation)
5. `app/drift/__init__.py` - Module init

## MULTI-TENANCY

✅ **Organization Isolation:** Baselines are scoped by `org_id`  
✅ **Policy-Specific Baselines:** Separate baselines per policy profile  
✅ **Endpoint-Specific:** Baselines tracked per endpoint (currently "analyze")  
✅ **Secure:** All queries filter by `org_id` to prevent cross-tenant data leakage

---

## MONITORING

### Key Metrics to Watch

1. **Drift Detection Rate**
   - Query: Count of `drift_status = "DRIFT_DETECTED"` per day
   - Alert: If > 5% of requests show drift

2. **Most Common Drift Reasons**
   - Query: Group by `drift_reasons`
   - Alert: If specific reason appears frequently

3. **Baseline Coverage**
   - Query: Count of baselines with `sample_count >= 10`
   - Alert: If coverage drops

---

**AI Output Drift Detection is production-ready** ✅

