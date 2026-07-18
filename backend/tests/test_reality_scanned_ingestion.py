"""Pin the ingest except-narrowing in scripts/reality/scanned_ingestion.py:
an audit/invariant failure (AssertionError, SystemExit) inside
`common.ingest` must propagate out of `_process_document` untouched, never
absorbed into `ingest_error` the way an ordinary ingestion Exception is.
Synthetic fixtures only -- no real corpus, matching the reality-script
convention (see test_reality_common.py) of never touching real documents
from the offline test suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.reality import scanned_ingestion


class TestIngestExceptionNarrowing:
    def test_assertion_error_from_ingest_propagates(self, monkeypatch):
        def _boom(store, pdf_path):
            raise AssertionError("audit invariant violated")

        monkeypatch.setattr(scanned_ingestion.common, "ingest", _boom)
        with pytest.raises(AssertionError, match="audit invariant violated"):
            scanned_ingestion._process_document(Path("dummy.pdf"), "scan-A", max_chunks=5)

    def test_system_exit_from_ingest_propagates(self, monkeypatch):
        def _boom(store, pdf_path):
            raise SystemExit("network audit failed")

        monkeypatch.setattr(scanned_ingestion.common, "ingest", _boom)
        with pytest.raises(SystemExit, match="network audit failed"):
            scanned_ingestion._process_document(Path("dummy.pdf"), "scan-A", max_chunks=5)

    def test_ordinary_exception_from_ingest_still_recorded_as_finding(self, monkeypatch):
        """Regression guard: narrowing the except clause must not change the
        existing "ingest failure IS a finding, keep going" behavior for any
        exception that isn't the audit/invariant pair above."""

        def _boom(store, pdf_path):
            raise ValueError("could not open pdf")

        monkeypatch.setattr(scanned_ingestion.common, "ingest", _boom)
        report = scanned_ingestion._process_document(Path("dummy.pdf"), "scan-A", max_chunks=5)
        assert "ingest_error" in report
        assert "could not open pdf" in report["ingest_error"]
