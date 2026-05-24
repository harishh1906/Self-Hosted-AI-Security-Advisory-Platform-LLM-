"""
NVD (National Vulnerability Database) Feed Source
Fetches CVEs via NVD API 2.0 with delta support (lastModStartDate).
"""
import logging
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from fetcher.config import (
    NVD_BASE_URL, NVD_API_KEY, NVD_RESULTS_PER_PAGE,
    MAX_TEXT_LENGTH, MAX_DOCUMENTS_PER_BATCH, REQUEST_TIMEOUT
)

logger = logging.getLogger(__name__)


def fetch_nvd(last_fetched: Optional[str] = None) -> List[Dict]:
    """
    Fetch CVEs from NVD API 2.0.
    
    Args:
        last_fetched: ISO timestamp of last successful fetch. If None, fetches last 7 days.
    
    Returns:
        List of canonical knowledge documents.
    """
    documents = []
    
    # Calculate date range
    if last_fetched:
        try:
            start_date = datetime.fromisoformat(last_fetched.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            start_date = datetime.now(timezone.utc) - timedelta(days=7)
    else:
        start_date = datetime.now(timezone.utc) - timedelta(days=7)
    
    end_date = datetime.now(timezone.utc)
    
    # NVD API requires specific date format
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%S.000")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%S.000")
    
    logger.info(
        f"Fetching NVD CVEs",
        extra={"start_date": start_str, "end_date": end_str}
    )
    
    headers = {}
    if NVD_API_KEY:
        headers["apiKey"] = NVD_API_KEY
    
    start_index = 0
    total_results = None
    
    while True:
        params = {
            "lastModStartDate": start_str,
            "lastModEndDate": end_str,
            "startIndex": start_index,
            "resultsPerPage": NVD_RESULTS_PER_PAGE
        }
        
        try:
            response = requests.get(
                NVD_BASE_URL,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"NVD API request failed: {e}")
            break
        except Exception as e:
            logger.error(f"NVD response parse failed: {e}")
            break
        
        if total_results is None:
            total_results = data.get("totalResults", 0)
            logger.info(f"NVD total results: {total_results}")
        
        vulnerabilities = data.get("vulnerabilities", [])
        if not vulnerabilities:
            break
        
        for item in vulnerabilities:
            doc = _normalize_nvd_cve(item)
            if doc:
                documents.append(doc)
        
        # Safety cap
        if len(documents) >= MAX_DOCUMENTS_PER_BATCH:
            logger.warning(
                f"Reached batch limit ({MAX_DOCUMENTS_PER_BATCH}), stopping pagination"
            )
            break
        
        start_index += NVD_RESULTS_PER_PAGE
        if start_index >= total_results:
            break
        
        # Rate limiting: NVD allows 5 req/30s without key, 50 req/30s with key
        wait_time = 0.6 if NVD_API_KEY else 6.0
        time.sleep(wait_time)
    
    logger.info(f"NVD fetch complete: {len(documents)} documents")
    return documents


def _normalize_nvd_cve(item: dict) -> Optional[Dict]:
    """Convert a single NVD CVE item to canonical knowledge document."""
    try:
        cve = item.get("cve", {})
        cve_id = cve.get("id", "")
        
        if not cve_id:
            return None
        
        # Extract description (English preferred)
        descriptions = cve.get("descriptions", [])
        description = ""
        for desc in descriptions:
            if desc.get("lang") == "en":
                description = desc.get("value", "")
                break
        if not description and descriptions:
            description = descriptions[0].get("value", "")
        
        if not description:
            return None
        
        # Extract CVSS score (v3.1 preferred, then v3.0, then v2.0)
        cvss_score = None
        severity = "Medium"
        metrics = cve.get("metrics", {})
        
        for version_key in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
            metric_list = metrics.get(version_key, [])
            if metric_list:
                cvss_data = metric_list[0].get("cvssData", {})
                cvss_score = cvss_data.get("baseScore")
                base_severity = metric_list[0].get("baseSeverity") or cvss_data.get("baseSeverity")
                if base_severity:
                    severity = _map_nvd_severity(base_severity)
                break
        
        # Extract CWE IDs
        cwe_ids = []
        weaknesses = cve.get("weaknesses", [])
        for weakness in weaknesses:
            for desc in weakness.get("description", []):
                cwe_val = desc.get("value", "")
                if cwe_val.startswith("CWE-"):
                    cwe_ids.append(cwe_val)
        
        # Extract affected products (CPE)
        affected_products = []
        configurations = cve.get("configurations", [])
        for config in configurations[:5]:  # Limit to 5 configs
            for node in config.get("nodes", []):
                for match in node.get("cpeMatch", [])[:5]:
                    criteria = match.get("criteria", "")
                    if criteria:
                        # Extract readable product name from CPE
                        parts = criteria.split(":")
                        if len(parts) >= 5:
                            vendor = parts[3]
                            product = parts[4]
                            version = parts[5] if len(parts) > 5 else "*"
                            affected_products.append(
                                f"{vendor}/{product}" + (f" {version}" if version != "*" else "")
                            )
        
        # Extract references
        references = []
        for ref in cve.get("references", [])[:5]:
            url = ref.get("url", "")
            if url:
                references.append(url)
        
        # Build remediation text from references and known patterns
        remediation = _build_remediation(cve_id, affected_products, references)
        
        # Build comprehensive text for embedding
        text_parts = [
            f"{cve_id}: {description}",
        ]
        if affected_products:
            text_parts.append(f"Affected: {', '.join(affected_products[:10])}")
        if cwe_ids:
            text_parts.append(f"Weakness: {', '.join(cwe_ids)}")
        if remediation:
            text_parts.append(f"Remediation: {remediation}")
        
        text = "\n".join(text_parts)[:MAX_TEXT_LENGTH]
        
        # Build tags
        tags = ["cve", severity.lower()]
        tags.extend([cwe.lower().replace("-", "") for cwe in cwe_ids[:5]])
        if cvss_score and cvss_score >= 9.0:
            tags.append("critical-cvss")
        
        published = cve.get("published", "")
        
        return {
            "source_id": cve_id,
            "source": "NVD",
            "category": "vulnerability",
            "title": f"{cve_id} - {description[:100]}",
            "text": text,
            "severity": severity,
            "cvss_score": cvss_score,
            "cwe_ids": cwe_ids,
            "affected_products": affected_products[:10],
            "remediation": remediation[:MAX_TEXT_LENGTH] if remediation else "",
            "references": references,
            "tags": tags,
            "published_date": published,
            "org_id": "global",
            "fetched_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.warning(f"Failed to normalize NVD CVE: {e}")
        return None


def _map_nvd_severity(nvd_severity: str) -> str:
    """Map NVD severity strings to our schema."""
    mapping = {
        "CRITICAL": "Critical",
        "HIGH": "High",
        "MEDIUM": "Medium",
        "LOW": "Low",
        "NONE": "Low"
    }
    return mapping.get(nvd_severity.upper(), "Medium")


def _build_remediation(cve_id: str, affected_products: list, references: list) -> str:
    """Build remediation text from available data."""
    parts = [f"Apply vendor patches for {cve_id}."]
    if affected_products:
        parts.append(f"Update affected components: {', '.join(affected_products[:5])}.")
    parts.append("Monitor vendor advisories for specific version fixes.")
    if references:
        parts.append(f"Reference: {references[0]}")
    return " ".join(parts)
