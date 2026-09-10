"""`draft-manifest bell`: pre-fill a manifest from a saved capture, then require
a human review before import."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from metromobile.cli import _require_reviewed, _strip_jsonc
from metromobile.drafting import DraftError, build_draft_manifest, capture_to_html
from metromobile.models import Plan
from metromobile.pipeline import run_manual_import

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
BELL_MHTML = FIXTURES / "bell" / "rendered_plans_sample.mhtml"      # "Mobility only" tab
BELL_HTML = FIXTURES / "bell" / "rendered_plans_sample.html"
BELL_STREAMING = FIXTURES / "bell" / "rendered_plans_streaming.html"  # "With Streaming" tab
KOODO_HTML = FIXTURES / "koodo" / "rendered_plans_sample.html"
FREEDOM_HTML = FIXTURES / "freedom-mobile" / "rendered_plans_sample.html"
EMPTY = FIXTURES / "manual_example" / "capture.html"  # has prices but no plan cards


def test_mhtml_unwraps_to_the_rendered_html():
    html = capture_to_html(BELL_MHTML.read_bytes(), suffix="mhtml")
    assert "card-plan" in html and "Select - 60 GB" in html


def test_extracts_every_plan_with_source_text():
    m = build_draft_manifest("bell", BELL_MHTML)
    assert m["_draft"]["reviewed"] is False
    assert m["provider"]["slug"] == "bell"
    assert m["_draft"]["plan_count"] == 3          # "Rate plans" + "additional lines" excluded

    by_name = {p["plan_name"]: p for p in m["plans"]}
    assert set(by_name) == {
        "Select - 60 GB",
        "Select - 100 GB (with U.S. roaming)",
        "Ultra - Unlimited (with U.S./Mexico roaming)",
    }

    p = by_name["Select - 60 GB"]
    # the struck-through figure is the UNCONDITIONAL regular price
    assert p["regular_price_cad"] == 75.0
    # the Mobility-only big price combines an AutoPay credit AND a promo/new-activation
    # credit that Bell does not itemise -> a conditional PROMO price, never autopay_price_cad
    assert p.get("autopay_price_cad") is None
    assert p["promo_price_cad"] == 65.0
    assert "AutoPay" in p["promo_conditions"] and "new-activation" in p["promo_conditions"]
    assert p["promo_stacks_conditions"] == "requires automatic payments (AutoPay)"
    assert p["promo_expiry_known"] is False       # no verified current expiry date
    # no streaming capture here -> no bundle tier
    assert p.get("bundle_price_cad") is None
    assert p.get("monthly_price_cad") is None
    assert p["data_full_speed_gb"] == 60.0
    assert p.get("data_total_gb") is None            # throttled-unlimited: no hard cap
    assert p["data_unlimited"] is True
    assert p["data_unlimited_is_full_speed"] is False
    assert p["throttle_speed"] == "512 Kbps"
    assert p["network_technology"] == "5G+"
    assert p["max_download_mbps"] == 2000.0
    assert p["canada_wide_calling"] is True and p["unlimited_text"] is True
    assert p["autopay_required"] is True
    assert p["plan_type"] == "postpaid" and p["byod"] is True
    assert p["_review"]["status"] == "draft-unreviewed"
    assert any("per-line" in n or "per line" in n for n in p["_review"]["price_notes"])


def test_two_captures_separate_universal_from_bundle_pricing():
    m = build_draft_manifest("bell", BELL_MHTML, streaming_capture_path=BELL_STREAMING)
    p = {x["plan_name"]: x for x in m["plans"]}["Select - 60 GB"]
    assert p["regular_price_cad"] == 75.0     # unconditional, from the struck price
    assert p.get("autopay_price_cad") is None  # AutoPay share not separable
    assert p["promo_price_cad"] == 65.0        # conditional promo (Mobility-only big price)
    assert p["bundle_price_cad"] == 50.0       # streaming tier (With-Streaming big price)
    assert "streaming bundle" in p["bundle_conditions"]
    assert m["_draft"]["secondary_capture_file"] == BELL_STREAMING.name
    assert any("confirmed by both" in n for n in p["_review"]["price_notes"])


def test_exclusive_partner_offer_is_marked_restricted(tmp_path: Path):
    html = (BELL_HTML).read_text().replace(
        "<p>with U.S. roaming</p>",
        "<p>with U.S. roaming</p><p>Exclusive Partner Offer</p>",
    )
    f = tmp_path / "bell-partner.html"
    f.write_text(html)
    p = {x["plan_name"]: x for x in build_draft_manifest("bell", f)["plans"]}
    sel100 = p["Select - 100 GB (with U.S. roaming)"]
    assert sel100["eligibility_restricted"] is True
    assert "partner offer" in sel100["eligibility_conditions"].lower()


def test_us_mexico_and_unlimited_full_speed_are_read_from_the_card():
    m = build_draft_manifest("bell", BELL_HTML)
    by_name = {p["plan_name"]: p for p in m["plans"]}

    sel100 = by_name["Select - 100 GB (with U.S. roaming)"]
    assert sel100["includes_us"] is True
    assert "includes_mexico" not in sel100 or sel100["includes_mexico"] is None

    ultra = by_name["Ultra - Unlimited (with U.S./Mexico roaming)"]
    assert ultra["includes_us"] is True and ultra["includes_mexico"] is True
    assert ultra["data_unlimited"] is True
    assert ultra["data_unlimited_is_full_speed"] is True   # "unlimited data at our fastest speeds"
    assert "data_total_gb" not in ultra or ultra["data_total_gb"] is None
    assert ultra["hotspot_data_gb"] == 50.0                # from the hotspot clause
    # roaming note is complete, not truncated at "U.S."
    assert ultra["international_roaming_note"] == (
        "5 GB/day of data roaming; in the U.S. and Mexico; then unlimited at 512 Kbps"
    )


def test_unclear_fields_stay_null_and_are_flagged():
    m = build_draft_manifest("bell", BELL_HTML)
    p = {x["plan_name"]: x for x in m["plans"]}["Select - 60 GB"]
    # not on the card -> not set, and called out for the reviewer
    for f in ("activation_fee_cad", "contract_required", "promo_ends_at"):
        assert f not in p
        assert f in p["_review"]["check_these_nulls_against_the_page"]
    assert p["_review"]["confidence"] in ("low", "medium")


def test_generated_file_is_valid_jsonc():
    from metromobile.cli import _DRAFT_HEADER

    m = build_draft_manifest("bell", BELL_MHTML)
    text = _DRAFT_HEADER + "\n" + json.dumps(m, indent=2)
    assert json.loads(_strip_jsonc(text))["_draft"]["plan_count"] == 3


def test_no_plan_cards_raises_draft_error_not_a_guess():
    with pytest.raises(DraftError):
        build_draft_manifest("bell", EMPTY)


def test_pdf_capture_is_rejected(tmp_path: Path):
    pdf = tmp_path / "bell.pdf"
    pdf.write_bytes(b"%PDF-1.4 ...")
    with pytest.raises(DraftError, match="PDF"):
        build_draft_manifest("bell", pdf)


def test_koodo_draft_separates_regular_from_conditional_and_flags_student():
    m = build_draft_manifest("koodo", KOODO_HTML)
    assert m["provider"]["slug"] == "koodo"
    by = {p["plan_name"]: p for p in m["plans"]}
    assert set(by) == {
        "Koodo 20GB (5G)",
        "Koodo 60GB (5G, Canada-US-Mexico roaming)",
        "Koodo 10GB (5G, Student deal)",
        "Koodo 250MB (3G)",
    }

    p = by["Koodo 20GB (5G)"]
    assert p["regular_price_cad"] == 55.0        # struck-through = unconditional
    assert p["promo_price_cad"] == 45.0          # current (with $10 mixed discounts)
    assert p.get("autopay_price_cad") is None    # promo/autopay share not itemised
    assert p["promo_stacks_conditions"] == "requires auto-pay by bank account"
    assert p["promo_expiry_known"] is False
    assert p["data_total_gb"] == 20.0 and p["data_hard_cap"] is True
    assert p["data_unlimited"] is False          # Shock-Free = hard cap
    assert p["network_technology"] == "5G" and p["has_5g"] is True
    assert p.get("includes_us") is None          # "International SMS" alone != Canada-US

    us = by["Koodo 60GB (5G, Canada-US-Mexico roaming)"]
    assert us["includes_us"] is True and us["includes_mexico"] is True

    student = by["Koodo 10GB (5G, Student deal)"]
    assert student["eligibility_restricted"] is True
    assert "student" in student["eligibility_conditions"].lower()

    starter = by["Koodo 250MB (3G)"]
    assert starter["regular_price_cad"] == 15.0 and starter.get("promo_price_cad") is None
    assert starter["data_total_gb"] == 0.25      # 250 MB -> GB


def test_freedom_draft_keeps_domestic_and_roam_beyond_separate():
    m = build_draft_manifest("freedom-mobile", FREEDOM_HTML)
    assert m["provider"]["slug"] == "freedom-mobile"
    by = {p["plan_name"]: p for p in m["plans"]}
    assert set(by) == {
        "Total Freedom 10GB + Roam Beyond 1GB",
        "Total Freedom 125GB + Roam Beyond 5GB",
        "Total Freedom 175GB + Roam Beyond 10GB",
        "Total Freedom 175GB + Roam Beyond 10GB (Post-Secondary Student Offer)",
    }

    p = by["Total Freedom 125GB + Roam Beyond 5GB"]
    # domestic vs roaming data are separate -- NEVER added
    assert p["data_full_speed_gb"] == 125.0
    assert p["attributes"]["roam_beyond_data_gb"] == 5.0
    assert "SEPARATE" in p["international_roaming_note"]
    assert p["international_roaming"] is True
    # domestic data is explicitly Canada-U.S.-Mexico
    assert p["includes_us"] is True and p["includes_mexico"] is True
    # unlimited-after-throttle, no hard cap
    assert p["data_unlimited"] is True and p["data_unlimited_is_full_speed"] is False
    assert p["data_hard_cap"] is False
    # network-dependent throttle policy: never a single flat number
    assert p["throttle_speed"] == (
        "256 Kbps down / 128 Kbps up on the Freedom network; 128 Kbps down / 64 "
        "Kbps up on partner networks (Nationwide, U.S. & Mexico)"
    )
    assert p["attributes"]["throttle_policy"] == {
        "freedom_network": {"down_kbps": 256, "up_kbps": 128},
        "partner_nationwide_us_mexico": {"down_kbps": 128, "up_kbps": 64},
        "overage_fees": False,
        "resets": "end of current billing cycle",
        "source": "Freedom Mobile Unlimited Plans Data Policy (plan-page footnote)",
    }
    # Digital Discount price is conditional; regular = shown + $5 (stated flat discount)
    assert p["autopay_price_cad"] == 45.0 and p["autopay_discount_cad"] == 5.0
    assert p["regular_price_cad"] == 50.0
    assert p["autopay_required"] is True
    assert "Digital Discount" in p["attributes"]["regular_price_basis"]  # derived, not printed
    assert p["network_technology"] == "5G+" and p["has_5g"] is True
    assert p["promo_name"] == "BACK TO SCHOOL OFFER!" and p.get("promo_price_cad") is None

    # the ordinary 175GB plan is untouched -- NOT restricted, NOT duplicated
    base = by["Total Freedom 175GB + Roam Beyond 10GB"]
    assert base.get("eligibility_restricted") is None
    assert base["regular_price_cad"] == 55.0 and base.get("promo_price_cad") is None

    # the student offer is a SEPARATE, eligibility-gated variant of the same plan
    student = by["Total Freedom 175GB + Roam Beyond 10GB (Post-Secondary Student Offer)"]
    assert student["eligibility_restricted"] is True
    assert "student" in student["eligibility_conditions"].lower()
    assert student["regular_price_cad"] == 55.0        # same underlying plan
    assert student["autopay_price_cad"] == 50.0
    assert student["promo_price_cad"] == 45.0          # student effective price, stored separately
    assert student["promo_duration_months"] == 18
    assert student["student_offer"] is True
    assert student["attributes"]["student_offer_details"]["duration_months"] == 18
    assert student["attributes"]["student_offer_details"]["underlying_plan_external_id"] == base["external_id"]


def test_bc_selected_capture_has_no_region_warning():
    m = build_draft_manifest("freedom-mobile", FREEDOM_HTML)  # <option value="BC" selected>
    assert not any("REGION MISMATCH" in w for w in m["_draft"]["page_warnings"])


def test_region_mismatch_is_flagged(tmp_path: Path):
    """A capture with the province picker set to ON must warn, loudly."""
    on_html = FREEDOM_HTML.read_text().replace(
        '<option value="BC" selected="">BC</option>\n        <option value="MB">MB</option>\n        <option value="ON">ON</option>',
        '<option value="BC">BC</option>\n        <option value="MB">MB</option>\n        <option value="ON" selected="">ON</option>',
    )
    assert 'value="ON" selected' in on_html  # sanity: the swap applied
    f = tmp_path / "freedom-on.html"
    f.write_text(on_html)
    m = build_draft_manifest("freedom-mobile", f)
    assert any("REGION MISMATCH" in w and "ON" in w for w in m["_draft"]["page_warnings"])


def test_unsupported_provider_is_rejected():
    with pytest.raises(DraftError, match="only implemented"):
        build_draft_manifest("rogers", BELL_MHTML)
    with pytest.raises(DraftError, match="only implemented"):
        build_draft_manifest("telus", BELL_MHTML)


# --- the review gate + import ------------------------------------------
def test_import_refuses_an_unreviewed_draft():
    m = build_draft_manifest("bell", BELL_MHTML)
    with pytest.raises(Exception) as exc:  # typer.BadParameter
        _require_reviewed(m, Path("x.plans.jsonc"))
    assert "unreviewed auto-draft" in str(exc.value)


def test_import_accepts_the_draft_once_reviewed(session):
    m = build_draft_manifest("bell", BELL_MHTML)
    m["_draft"]["reviewed"] = True
    _require_reviewed(m, Path("x"))  # no raise now

    outcome = run_manual_import(
        session, manifest=m, capture_path=BELL_MHTML, operator="devvrat",
        verified_at=dt.datetime.now(dt.timezone.utc), source_mode="official_manual",
    )
    assert outcome.status == "success"
    plans = session.query(Plan).filter_by(provider_slug="bell").all()
    assert len(plans) == 3
    assert all(p.source_mode == "official_manual" for p in plans)
    assert all(p.verified_by == "devvrat" for p in plans)
    # the auto-extraction record is kept as provenance
    sel = next(p for p in plans if p.plan_name == "Select - 60 GB")
    assert "_review" in sel.attributes.get("operator_supplied_extra", {})
