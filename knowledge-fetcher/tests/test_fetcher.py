"""
Tests for Knowledge Fetcher — NVD source normalization and CISA KEV parsing.
Mocks HTTP calls to test normalization logic without internet access.
"""
import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

# Add parent to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════
# NVD Source Tests
# ══════════════════════════════════════════════════════════════

SAMPLE_NVD_RESPONSE = {
    "totalResults": 1,
    "vulnerabilities": [
        {
            "cve": {
                "id": "CVE-2026-12345",
                "published": "2026-04-28T00:00:00.000",
                "descriptions": [
                    {
                        "lang": "en",
                        "value": "A remote code execution vulnerability exists in Apache Struts 2.x"
                    }
                ],
                "metrics": {
                    "cvssMetricV31": [
                        {
                            "cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"},
                            "baseSeverity": "CRITICAL"
                        }
                    ]
                },
                "weaknesses": [
                    {
                        "description": [
                            {"lang": "en", "value": "CWE-502"}
                        ]
                    }
                ],
                "configurations": [
                    {
                        "nodes": [
                            {
                                "cpeMatch": [
                                    {"criteria": "cpe:2.3:a:apache:struts:2.5.32:*:*:*:*:*:*:*"}
                                ]
                            }
                        ]
                    }
                ],
                "references": [
                    {"url": "https://nvd.nist.gov/vuln/detail/CVE-2026-12345"}
                ]
            }
        }
    ]
}


class TestNVDNormalization:
    """Test NVD CVE normalization without HTTP calls."""

    def test_normalize_single_cve(self):
        """Test that a valid NVD response is normalized correctly."""
        from fetcher.sources.nvd import _normalize_nvd_cve

        item = SAMPLE_NVD_RESPONSE["vulnerabilities"][0]
        doc = _normalize_nvd_cve(item)

        assert doc is not None
        assert doc["source_id"] == "CVE-2026-12345"
        assert doc["source"] == "NVD"
        assert doc["category"] == "vulnerability"
        assert doc["severity"] == "Critical"
        assert doc["cvss_score"] == 9.8
        assert "CWE-502" in doc["cwe_ids"]
        assert doc["org_id"] == "global"
        assert "cve" in doc["tags"]
        assert "critical" in doc["tags"]
        assert len(doc["text"]) > 0
        assert "CVE-2026-12345" in doc["text"]

    def test_normalize_missing_description(self):
        """Test normalization handles missing description gracefully."""
        from fetcher.sources.nvd import _normalize_nvd_cve

        item = {"cve": {"id": "CVE-2026-99999", "descriptions": []}}
        doc = _normalize_nvd_cve(item)
        assert doc is None  # Should skip entries without descriptions

    def test_normalize_missing_cve_id(self):
        """Test normalization handles missing CVE ID."""
        from fetcher.sources.nvd import _normalize_nvd_cve

        item = {"cve": {"id": "", "descriptions": [{"lang": "en", "value": "test"}]}}
        doc = _normalize_nvd_cve(item)
        assert doc is None

    def test_severity_mapping(self):
        """Test NVD severity string mapping."""
        from fetcher.sources.nvd import _map_nvd_severity

        assert _map_nvd_severity("CRITICAL") == "Critical"
        assert _map_nvd_severity("HIGH") == "High"
        assert _map_nvd_severity("MEDIUM") == "Medium"
        assert _map_nvd_severity("LOW") == "Low"
        assert _map_nvd_severity("NONE") == "Low"
        assert _map_nvd_severity("UNKNOWN") == "Medium"  # Default fallback

    @patch("fetcher.sources.nvd.requests.get")
    def test_fetch_nvd_with_mock(self, mock_get):
        """Test full fetch cycle with mocked HTTP."""
        from fetcher.sources.nvd import fetch_nvd

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_NVD_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        docs = fetch_nvd()
        assert len(docs) == 1
        assert docs[0]["source_id"] == "CVE-2026-12345"
        mock_get.assert_called_once()

    @patch("fetcher.sources.nvd.requests.get")
    def test_fetch_nvd_handles_http_error(self, mock_get):
        """Test that HTTP errors are handled gracefully."""
        from fetcher.sources.nvd import fetch_nvd
        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError("Network unreachable")

        docs = fetch_nvd()
        assert docs == []  # Should return empty, not crash


# ══════════════════════════════════════════════════════════════
# CISA KEV Tests
# ══════════════════════════════════════════════════════════════

SAMPLE_KEV_RESPONSE = {
    "vulnerabilities": [
        {
            "cveID": "CVE-2026-11111",
            "vendorProject": "Microsoft",
            "product": "Exchange Server",
            "vulnerabilityName": "Microsoft Exchange RCE",
            "shortDescription": "A remote code execution vulnerability in Exchange Server.",
            "requiredAction": "Apply updates per vendor instructions.",
            "dueDate": "2026-05-15",
            "dateAdded": "2026-04-27",
            "knownRansomwareCampaignUse": "Known"
        }
    ]
}


class TestCISAKEVNormalization:
    """Test CISA KEV normalization."""

    def test_normalize_kev_entry(self):
        """Test single KEV entry normalization."""
        from fetcher.sources.cisa_kev import _normalize_kev

        doc = _normalize_kev(SAMPLE_KEV_RESPONSE["vulnerabilities"][0])

        assert doc is not None
        assert doc["source_id"] == "KEV-CVE-2026-11111"
        assert doc["source"] == "CISA_KEV"
        assert doc["severity"] == "Critical"
        assert "actively-exploited" in doc["tags"]
        assert "ransomware" in doc["tags"]
        assert "ACTIVELY EXPLOITED" in doc["title"]
        assert "Apply updates" in doc["remediation"]

    @patch("fetcher.sources.cisa_kev.requests.get")
    def test_fetch_cisa_kev_with_mock(self, mock_get):
        """Test full KEV fetch with mocked HTTP."""
        from fetcher.sources.cisa_kev import fetch_cisa_kev

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_KEV_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        docs = fetch_cisa_kev()
        assert len(docs) == 1
        assert docs[0]["source_id"] == "KEV-CVE-2026-11111"

    @patch("fetcher.sources.cisa_kev.requests.get")
    def test_fetch_kev_delta_filtering(self, mock_get):
        """Test that delta filtering skips old entries."""
        from fetcher.sources.cisa_kev import fetch_cisa_kev

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_KEV_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Last fetched AFTER the entry was added → should be filtered
        docs = fetch_cisa_kev(last_fetched="2026-04-28T00:00:00Z")
        assert len(docs) == 0


# ══════════════════════════════════════════════════════════════
# Writer Tests
# ══════════════════════════════════════════════════════════════

class TestWriter:
    """Test the inbox file writer."""

    def test_write_batch(self, tmp_path):
        """Test writing a batch to the inbox."""
        from fetcher.writer import write_batch
        from fetcher import config

        # Override inbox path to temp dir
        original = config.INBOX_PATH
        config.INBOX_PATH = str(tmp_path)

        try:
            docs = [
                {"source_id": "CVE-2026-00001", "text": "Test vulnerability"},
                {"source_id": "CVE-2026-00002", "text": "Another vulnerability"},
            ]
            filepath = write_batch(docs, "TEST")

            assert os.path.exists(filepath)
            with open(filepath, "r") as f:
                batch = json.load(f)

            assert batch["source"] == "TEST"
            assert batch["document_count"] == 2
            assert len(batch["documents"]) == 2
        finally:
            config.INBOX_PATH = original

    def test_write_empty_batch(self, tmp_path):
        """Test writing empty batch returns empty string."""
        from fetcher.writer import write_batch
        from fetcher import config

        original = config.INBOX_PATH
        config.INBOX_PATH = str(tmp_path)

        try:
            result = write_batch([], "TEST")
            assert result == ""
        finally:
            config.INBOX_PATH = original


# ══════════════════════════════════════════════════════════════
# Canonical Schema Validation Tests
# ══════════════════════════════════════════════════════════════

class TestCanonicalSchema:
    """Verify all documents conform to the canonical schema."""

    REQUIRED_FIELDS = [
        "source_id", "source", "category", "title", "text",
        "severity", "tags", "org_id", "fetched_at"
    ]

    def test_nvd_document_schema(self):
        """Verify NVD documents have all required fields."""
        from fetcher.sources.nvd import _normalize_nvd_cve

        item = SAMPLE_NVD_RESPONSE["vulnerabilities"][0]
        doc = _normalize_nvd_cve(item)

        for field in self.REQUIRED_FIELDS:
            assert field in doc, f"Missing field: {field}"
        assert isinstance(doc["tags"], list)
        assert isinstance(doc["text"], str)
        assert len(doc["text"]) > 0

    def test_kev_document_schema(self):
        """Verify KEV documents have all required fields."""
        from fetcher.sources.cisa_kev import _normalize_kev

        doc = _normalize_kev(SAMPLE_KEV_RESPONSE["vulnerabilities"][0])

        for field in self.REQUIRED_FIELDS:
            assert field in doc, f"Missing field: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
