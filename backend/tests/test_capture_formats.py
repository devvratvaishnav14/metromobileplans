"""Manual captures are kept verbatim as evidence -- an .mhtml is recorded as
what it is, not disguised as HTML."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from metromobile.models import RawDocument
from metromobile.pipeline import capture_content_type, run_manual_import

MANIFEST = {
    "provider": {"slug": "bell", "display_name": "Bell", "network": "Bell", "plan_model": "postpaid"},
    "source": {"url": "https://www.bell.ca/Mobility/Cell_phone_plans", "kind": "capture"},
    "plans": [{
        "external_id": "bell-x", "plan_name": "Unlimited 100GB", "plan_type": "postpaid",
        "price_period": "monthly", "monthly_price_cad": 85, "data_total_gb": 100,
        "data_unlimited": True, "canada_wide_calling": True, "unlimited_text": True,
        "availability": "online",
    }],
}

# a minimal but real MHTML container
_MHTML = (
    b"From: <Saved by Blink>\r\n"
    b'Snapshot-Content-Location: https://www.bell.ca/Mobility/Cell_phone_plans\r\n'
    b"Subject: Cell phone plans\r\n"
    b"Date: Sun, 6 Sep 2026 12:00:00 -0700\r\n"
    b'MIME-Version: 1.0\r\n'
    b'Content-Type: multipart/related; type="text/html"; boundary="----=_NextPart_000"\r\n\r\n"'
    b"------=_NextPart_000\r\nContent-Type: text/html\r\n\r\n"
    b"<html><body><h1>Bell plans</h1><p>Unlimited 100GB - $85/mo.</p></body></html>\r\n"
    b"------=_NextPart_000--\r\n" * 40
)


def test_content_type_by_extension():
    assert capture_content_type("x/y.mhtml") == "multipart/related"
    assert capture_content_type("x/y.mht") == "multipart/related"
    assert capture_content_type("x/y.html") == "text/html"
    assert capture_content_type("x/y.pdf") == "application/pdf"
    assert capture_content_type("x/y.weird") == "application/octet-stream"


def test_mhtml_capture_is_stored_as_multipart_related(session, tmp_path: Path):
    cap = tmp_path / "2026-09-06.mhtml"
    cap.write_bytes(_MHTML)

    run_manual_import(
        session, manifest=MANIFEST, capture_path=cap, operator="tester",
        verified_at=dt.datetime.now(dt.timezone.utc), source_mode="official_manual",
    )

    raw = session.query(RawDocument).one()
    assert raw.retrieval == "manual_import"
    assert raw.content_type == "multipart/related"          # not text/html
    assert raw.storage_path.endswith(".mhtml")              # real extension kept
    assert Path(raw.storage_path).exists()
    assert raw.byte_size == len(_MHTML)
    assert "2026-09-06.mhtml" in (raw.notes or "")


def test_verified_at_defaults_to_now_when_omitted(session, tmp_path: Path):
    cap = tmp_path / "cap.mhtml"
    cap.write_bytes(_MHTML)
    before = dt.datetime.now(dt.timezone.utc)
    run_manual_import(
        session, manifest=MANIFEST, capture_path=cap, operator="tester",
        verified_at=None, source_mode="official_manual",  # omitted
    )
    after = dt.datetime.now(dt.timezone.utc)
    p = session.query(RawDocument).one()
    assert p.captured_at.replace(tzinfo=dt.timezone.utc) >= before - dt.timedelta(seconds=2)
    assert p.captured_at.replace(tzinfo=dt.timezone.utc) <= after + dt.timedelta(seconds=2)
