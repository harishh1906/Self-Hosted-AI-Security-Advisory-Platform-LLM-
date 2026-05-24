"""
Tests for Knowledge Ingester — processor logic, audit logging, and main loop.
Mocks Qdrant and PostgreSQL to test logic without live services.
"""
import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════
# Sample Documents
# ══════════════════════════════════════════════════════════════

SAMPLE_BATCH = {
    "source": "NVD",
    "fetched_at": "2026-04-28T06:00:00Z",
    "document_count": 2,
    "documents": [
        {
            "source_id": "CVE-2026-12345",
            "source": "NVD",
            "category": "vulnerability",
            "title": "CVE-2026-12345 - RCE in Apache Struts",
            "text": "CVE-2026-12345: A remote code execution vulnerability in Apache Struts 2.x",
            "severity": "Critical",
            "cvss_score": 9.8,
            "cwe_ids": ["CWE-502"],
            "affected_products": ["apache/struts"],
            "remediation": "Upgrade to Apache Struts 2.5.33",
            "references": ["https://nvd.nist.gov/vuln/detail/CVE-2026-12345"],
            "tags": ["cve", "critical", "cwe502"],
            "published_date": "2026-04-28",
            "org_id": "global",
            "fetched_at": "2026-04-28T06:00:00Z"
        },
        {
            "source_id": "CVE-2026-67890",
            "source": "NVD",
            "category": "vulnerability",
            "title": "CVE-2026-67890 - SQLi in WordPress Plugin",
            "text": "CVE-2026-67890: SQL injection in WP Contact Form plugin",
            "severity": "High",
            "cvss_score": 8.1,
            "cwe_ids": ["CWE-89"],
            "affected_products": ["wordpress/contact-form"],
            "remediation": "Update plugin to version 5.2.1",
            "references": [],
            "tags": ["cve", "high", "cwe89"],
            "published_date": "2026-04-27",
            "org_id": "global",
            "fetched_at": "2026-04-28T06:00:00Z"
        }
    ]
}


# ══════════════════════════════════════════════════════════════
# Processor Tests
# ══════════════════════════════════════════════════════════════

class TestProcessor:
    """Test document processing logic with mocked Qdrant."""

    @patch("ingester.processor._client")
    @patch("ingester.processor._model")
    def test_process_new_documents(self, mock_model, mock_client):
        """Test processing new documents (not yet in Qdrant)."""
        from ingester.processor import process_documents

        # Mock embedding
        mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 384)

        # Mock Qdrant: collection exists, no duplicates
        mock_client.get_collections.return_value = MagicMock(
            collections=[MagicMock(name="security_knowledge")]
        )
        mock_client.scroll.return_value = ([], None)  # No existing docs
        mock_client.upsert.return_value = None

        created, updated, skipped = process_documents(SAMPLE_BATCH["documents"])

        assert created == 2
        assert updated == 0
        assert skipped == 0
        assert mock_client.upsert.called

    @patch("ingester.processor._client")
    @patch("ingester.processor._model")
    def test_process_duplicate_documents(self, mock_model, mock_client):
        """Test that existing documents are updated (delete + re-insert)."""
        from ingester.processor import process_documents

        mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 384)

        mock_client.get_collections.return_value = MagicMock(
            collections=[MagicMock(name="security_knowledge")]
        )
        # Mock: document already exists
        mock_client.scroll.return_value = ([MagicMock()], None)
        mock_client.delete.return_value = None
        mock_client.upsert.return_value = None

        created, updated, skipped = process_documents(SAMPLE_BATCH["documents"])

        assert created == 0
        assert updated == 2
        assert skipped == 0
        assert mock_client.delete.called

    @patch("ingester.processor._client")
    @patch("ingester.processor._model")
    def test_process_skips_empty_docs(self, mock_model, mock_client):
        """Test that documents without source_id or text are skipped."""
        from ingester.processor import process_documents

        mock_client.get_collections.return_value = MagicMock(
            collections=[MagicMock(name="security_knowledge")]
        )

        bad_docs = [
            {"source_id": "", "text": "has text but no id"},
            {"source_id": "CVE-001", "text": ""},
        ]

        created, updated, skipped = process_documents(bad_docs)
        assert skipped == 2
        assert created == 0


# ══════════════════════════════════════════════════════════════
# Main Loop Tests
# ══════════════════════════════════════════════════════════════

class TestMainLoop:
    """Test the inbox processing loop."""

    def test_process_file(self, tmp_path):
        """Test processing a single JSON file from inbox."""
        from ingester.main import process_file
        
        # Write sample batch to temp file
        batch_file = tmp_path / "nvd_test.json"
        batch_file.write_text(json.dumps(SAMPLE_BATCH))
    
        # Create processed directory
        processed_dir = tmp_path / ".processed"
    
        # Patch BOTH the config and the local variable in main
        with patch("ingester.main.process_documents") as mock_process, \
             patch("ingester.main.log_ingestion") as mock_log, \
             patch("ingester.main.PROCESSED_DIR", str(processed_dir)):
            
            mock_process.return_value = (2, 0, 0)
            process_file(batch_file)

            mock_process.assert_called_once()
            mock_log.assert_called_once()

            # File should be moved to processed
            assert not batch_file.exists()
            assert (processed_dir / "nvd_test.json").exists()

    def test_process_invalid_json(self, tmp_path):
        """Test handling of invalid JSON files."""
        from ingester.main import process_file
        
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json{{{")

        processed_dir = tmp_path / ".processed"

        with patch("ingester.main.log_ingestion") as mock_log, \
             patch("ingester.main.PROCESSED_DIR", str(processed_dir)):
            
            process_file(bad_file)

            # Should log error but not crash
            mock_log.assert_called_once()
            # Verify it was logged as an error
            args, kwargs = mock_log.call_args
            assert kwargs.get("status") == "error"


# ══════════════════════════════════════════════════════════════
# Integration Test — Full Pipeline (file → process → verify)
# ══════════════════════════════════════════════════════════════

class TestPipelineIntegration:
    """End-to-end pipeline test with all externals mocked."""

    def test_full_pipeline(self, tmp_path):
        """Write batch file → process → verify counts."""
        # Step 1: Write batch file (simulating fetcher output)
        batch_file = tmp_path / "nvd_20260428T060000.json"
        batch_file.write_text(json.dumps(SAMPLE_BATCH))

        # Step 2: Process it (simulating ingester)
        from ingester.main import process_file
        from ingester import config

        processed_dir = tmp_path / ".processed"
        config.PROCESSED_DIR = str(processed_dir)

        with patch("ingester.main.process_documents") as mock_process, \
             patch("ingester.main.log_ingestion") as mock_log:
            mock_process.return_value = (2, 0, 0)

            process_file(batch_file)

            # Verify
            mock_process.assert_called_once()
            docs_passed = mock_process.call_args[0][0]
            assert len(docs_passed) == 2
            assert docs_passed[0]["source_id"] == "CVE-2026-12345"
            assert docs_passed[1]["source_id"] == "CVE-2026-67890"

            # Audit logged
            mock_log.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
