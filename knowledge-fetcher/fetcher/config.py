"""
Knowledge Fetcher Configuration
All settings driven by environment variables for Docker deployment.
"""
import os

# ── Feed Source Configuration ──
NVD_API_KEY = os.getenv("NVD_API_KEY", "")  # Optional: increases rate limit 5x
NVD_BASE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_RESULTS_PER_PAGE = 100  # Max 2000, but 100 is safer for memory

CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

MITRE_CWE_URL = "https://cwe.mitre.org/data/xml/cwec_latest.xml.zip"

# ── Scheduling ──
FETCH_INTERVAL_HOURS = int(os.getenv("FETCH_INTERVAL_HOURS", "6"))

# ── Output ──
INBOX_PATH = os.getenv("INBOX_PATH", "/data/knowledge-inbox")

# ── State Tracking ──
STATE_FILE = os.path.join(INBOX_PATH, ".fetch_state.json")

# ── Limits ──
MAX_TEXT_LENGTH = 10000  # Sanitization: cap document text at 10KB
MAX_DOCUMENTS_PER_BATCH = 500  # Safety: don't flood the inbox
REQUEST_TIMEOUT = 30  # seconds
