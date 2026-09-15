"""Unit tests for upload filename duplicate detection (no live DB/API)."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.documents import (
    _filename_stem,
    _resolve_upload_filename,
    classify_filename_conflict,
)
from app.db.models import SourceFormat


def _doc(filename: str, source_format: SourceFormat) -> SimpleNamespace:
    return SimpleNamespace(
        id="doc-1",
        filename=filename,
        title=filename,
        source_format=source_format,
    )


def test_filename_stem_strips_extension_case_insensitively():
    assert _filename_stem("Report.PDF") == "Report"
    assert _filename_stem("report.docx") == "report"


def test_resolve_upload_filename_keeps_original_when_no_rename():
    assert _resolve_upload_filename("report.pdf", None, ".pdf") == "report.pdf"
    assert _resolve_upload_filename("report.pdf", "  ", ".pdf") == "report.pdf"


def test_resolve_upload_filename_applies_rename_and_keeps_real_extension():
    assert _resolve_upload_filename("report.pdf", "Q3 Summary", ".pdf") == "Q3 Summary.pdf"
    # Client may include an extension; we strip it and keep the upload's type.
    assert _resolve_upload_filename("report.pdf", "Q3.docx", ".pdf") == "Q3.pdf"
    # Path segments are discarded.
    assert _resolve_upload_filename("report.pdf", r"C:\tmp\safe.pdf", ".pdf") == "safe.pdf"


def test_resolve_upload_filename_rejects_empty_rename():
    for bad in (".pdf", "   .docx  ", "."):
        with pytest.raises(HTTPException) as exc:
            _resolve_upload_filename("report.pdf", bad, ".pdf")
        assert exc.value.status_code == 400


def test_no_conflict_when_nothing_matches():
    assert classify_filename_conflict([], SourceFormat.PDF, False) is None


def test_same_name_same_type_is_blocked():
    conflicts = [_doc("Report.pdf", SourceFormat.PDF)]
    result = classify_filename_conflict(conflicts, SourceFormat.PDF, confirm_different_type=False)
    assert result is not None
    code, docs = result
    assert code == "duplicate_exact"
    assert docs == conflicts

    # confirm_different_type must not bypass an exact type match
    result_confirmed = classify_filename_conflict(
        conflicts, SourceFormat.PDF, confirm_different_type=True
    )
    assert result_confirmed is not None
    assert result_confirmed[0] == "duplicate_exact"


def test_same_name_different_type_prompts_unless_confirmed():
    conflicts = [_doc("report.pdf", SourceFormat.PDF)]
    blocked = classify_filename_conflict(conflicts, SourceFormat.DOCX, confirm_different_type=False)
    assert blocked is not None
    assert blocked[0] == "duplicate_name_different_type"

    allowed = classify_filename_conflict(conflicts, SourceFormat.DOCX, confirm_different_type=True)
    assert allowed is None


def test_same_type_wins_when_both_same_and_different_exist():
    conflicts = [
        _doc("report.pdf", SourceFormat.PDF),
        _doc("report.docx", SourceFormat.DOCX),
    ]
    result = classify_filename_conflict(conflicts, SourceFormat.PDF, confirm_different_type=True)
    assert result is not None
    assert result[0] == "duplicate_exact"
    assert all(d.source_format == SourceFormat.PDF for d in result[1])
