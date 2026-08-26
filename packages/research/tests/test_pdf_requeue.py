from pathlib import Path

def test_pdf_requeue_script_is_narrow_and_audited():
    text=(Path(__file__).resolve().parents[3]/"scripts/requeue_pdf_candidates.py").read_text()
    assert 'status=="UNSUPPORTED_CONTENT_TYPE"' in text
    assert 'endswith(".pdf")' in text
    assert '"PDF_REQUEUED"' in text
    assert 'candidate.status="PENDING_REVIEW"' in text
