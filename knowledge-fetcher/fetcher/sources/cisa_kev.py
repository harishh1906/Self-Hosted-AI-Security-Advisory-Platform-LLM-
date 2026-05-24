"""
CISA Known Exploited Vulnerabilities (KEV) Feed Source
Fetches actively exploited vulnerabilities from CISA's KEV catalog.
"""
import logging
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional
from fetcher.config import CISA_KEV_URL, MAX_TEXT_LENGTH, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


def fetch_cisa_kev(last_fetched: Optional[str] = None) -> List[Dict]:
    """
    Fetch CISA Known Exploited Vulnerabilities.
    
    Args:
        last_fetched: ISO timestamp — only return entries added after this date.
    
    Returns:
        List of canonical knowledge documents.
    """
    documents = []
    
    try:
        response = requests.get(CISA_KEV_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"CISA KEV fetch failed: {e}")
        return []
    except Exception as e:
        logger.error(f"CISA KEV parse failed: {e}")
        return []
    
    vulnerabilities = data.get("vulnerabilities", [])
    logger.info(f"CISA KEV total entries: {len(vulnerabilities)}")
    
    # Parse last_fetched for delta filtering
    cutoff_date = None
    if last_fetched:
        try:
            cutoff_date = datetime.fromisoformat(last_fetched.replace("Z", "+00:00")).date()
        except (ValueError, TypeError):
            cutoff_date = None
    
    for vuln in vulnerabilities:
        # Delta filter: skip entries older than last fetch
        date_added = vuln.get("dateAdded", "")
        if cutoff_date and date_added:
            try:
                entry_date = datetime.strptime(date_added, "%Y-%m-%d").date()
                if entry_date <= cutoff_date:
                    continue
            except ValueError:
                pass
        
        doc = _normalize_kev(vuln)
        if doc:
            documents.append(doc)
    
    logger.info(f"CISA KEV fetch complete: {len(documents)} new documents")
    return documents


def _normalize_kev(vuln: dict) -> Optional[Dict]:
    """Convert a CISA KEV entry to canonical knowledge document."""
    try:
        cve_id = vuln.get("cveID", "")
        if not cve_id:
            return None
        
        vendor = vuln.get("vendorProject", "Unknown")
        product = vuln.get("product", "Unknown")
        name = vuln.get("vulnerabilityName", "")
        description = vuln.get("shortDescription", "")
        action = vuln.get("requiredAction", "")
        due_date = vuln.get("dueDate", "")
        date_added = vuln.get("dateAdded", "")
        known_ransomware = vuln.get("knownRansomwareCampaignUse", "Unknown")
        
        # Build comprehensive text
        text_parts = [
            f"{cve_id}: {name}",
            f"Description: {description}",
            f"Vendor: {vendor}, Product: {product}",
            f"CISA Required Action: {action}",
        ]
        if due_date:
            text_parts.append(f"Remediation Due Date: {due_date}")
        if known_ransomware and known_ransomware.lower() == "known":
            text_parts.append("WARNING: Known ransomware campaign use detected.")
        
        text = "\n".join(text_parts)[:MAX_TEXT_LENGTH]
        
        # Tags
        tags = ["cve", "cisa-kev", "actively-exploited"]
        if known_ransomware and known_ransomware.lower() == "known":
            tags.append("ransomware")
        
        return {
            "source_id": f"KEV-{cve_id}",
            "source": "CISA_KEV",
            "category": "vulnerability",
            "title": f"[ACTIVELY EXPLOITED] {cve_id} - {name[:80]}",
            "text": text,
            "severity": "Critical",  # All KEV entries are effectively critical
            "cvss_score": None,
            "cwe_ids": [],
            "affected_products": [f"{vendor}/{product}"],
            "remediation": action[:MAX_TEXT_LENGTH] if action else "",
            "references": [f"https://nvd.nist.gov/vuln/detail/{cve_id}"],
            "tags": tags,
            "published_date": date_added,
            "org_id": "global",
            "fetched_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.warning(f"Failed to normalize KEV entry: {e}")
        return None
