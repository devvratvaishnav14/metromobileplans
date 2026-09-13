"""The production bootstrap must reproduce the frozen V1 official dataset on a
fresh database, through the normal verified import pipeline.

This mirrors `metromobile bootstrap`: Bell/Koodo/Freedom via official_manual
import of the reviewed `fixtures/ranking/v1_dataset.json`, then Chatr via an
official_automated refresh of the committed snapshot. If these counts or the
Top-5s drift, a deploy should fail — same as the CLI command's own assertion.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from sqlalchemy import select

from metromobile.models import Plan
from metromobile.pipeline import run_manual_import, run_refresh
from metromobile.ranking import OVERALL, RankingContext, rank_plans

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
DATASET = json.loads((FIXTURES / "ranking" / "v1_dataset.json").read_text())
EVIDENCE = FIXTURES / "manual_example" / "capture.html"
CHATR_SNAPSHOT = FIXTURES / "chatr" / "plans_page.html"
VERIFIED_AT = dt.datetime(2026, 9, 9, 12, 0, tzinfo=dt.timezone.utc)


def _bootstrap(session, now: dt.datetime) -> None:
    for slug in ("bell", "koodo", "freedom-mobile"):
        block = DATASET[slug]
        run_manual_import(
            session,
            manifest={"provider": block["provider"], "source": block["source"], "plans": block["plans"]},
            capture_path=EVIDENCE,
            operator="V1 approved snapshot (2026-09-09)",
            verified_at=VERIFIED_AT,
            source_mode="official_manual",
        )
    run_refresh("chatr", session, fixture_path=CHATR_SNAPSHOT)


def test_fresh_database_reproduces_the_approved_official_dataset(session):
    now = dt.datetime(2026, 9, 10, 12, 0, tzinfo=dt.timezone.utc)
    _bootstrap(session, now)

    official = session.scalars(
        select(Plan).where(Plan.source_mode != "trusted_secondary")
    ).all()
    verified = [p for p in official if p.verification_status == "verified"]
    rankable = [p for p in official if p.is_rankable]
    restricted = [p for p in official if p.eligibility_restricted]

    assert len(verified) == 29
    assert len(rankable) == 27
    assert len(restricted) == 2

    # both restricted plans are the eligibility-gated student offers, kept but
    # held out of the default ranking
    restricted_ids = {p.external_id for p in restricted}
    assert restricted_ids == {
        "koodo-10gb-5g-student-deal",
        "total-freedom-175gb-roam-beyond-10gb-post-secondary-student-offer",
    }
    assert all(not p.is_rankable for p in restricted)

    # source modes are preserved: Chatr automated, the rest manual
    modes = {p.provider_slug: p.source_mode for p in official}
    assert modes["chatr"] == "official_automated"
    assert modes["bell"] == modes["koodo"] == modes["freedom-mobile"] == "official_manual"

    # Bell provenance points at the official carrier page, not the aggregator
    bell = next(p for p in official if p.provider_slug == "bell")
    assert "bell.ca" in bell.source_url

    # Freedom provenance points at the stable top-level plans page, not the
    # deeper BYOP route that no longer resolves to a usable public page
    freedom = [p for p in official if p.provider_slug == "freedom-mobile"]
    assert freedom and all(
        p.source_url == "https://shop.freedommobile.ca/en-CA/plans" for p in freedom
    )


def test_bootstrap_is_idempotent(session):
    now = dt.datetime(2026, 9, 10, 12, 0, tzinfo=dt.timezone.utc)
    _bootstrap(session, now)
    first = session.scalars(select(Plan)).all()
    _bootstrap(session, now)  # re-run
    second = session.scalars(select(Plan)).all()
    assert len(first) == len(second)  # upserts, no duplicates


def test_bootstrap_repairs_a_partially_populated_database(session):
    """A failed earlier deploy left only Bell + Koodo + Chatr. Re-running the
    imports must add the missing Freedom provider and reach 29 / 27 without
    disturbing or duplicating the plans already there."""
    now = dt.datetime(2026, 9, 10, 12, 0, tzinfo=dt.timezone.utc)

    # partial state: everything except Freedom
    for slug in ("bell", "koodo"):
        block = DATASET[slug]
        run_manual_import(
            session,
            manifest={"provider": block["provider"], "source": block["source"], "plans": block["plans"]},
            capture_path=EVIDENCE, operator="V1 approved snapshot (2026-09-09)",
            verified_at=VERIFIED_AT, source_mode="official_manual",
        )
    run_refresh("chatr", session, fixture_path=CHATR_SNAPSHOT)

    partial = session.scalars(select(Plan)).all()
    assert not any(p.provider_slug == "freedom-mobile" for p in partial)
    bell_ids_before = {p.external_id for p in partial if p.provider_slug == "bell"}

    # reconcile: run every import again (idempotent for the present providers)
    _bootstrap(session, now)

    official = session.scalars(
        select(Plan).where(Plan.source_mode != "trusted_secondary")
    ).all()
    assert sum(1 for p in official if p.verification_status == "verified") == 29
    assert sum(1 for p in official if p.is_rankable) == 27
    assert {p.external_id for p in official if p.provider_slug == "bell"} == bell_ids_before
    assert sum(1 for p in official if p.provider_slug == "freedom-mobile") == 10


def test_bootstrapped_database_gives_the_frozen_best_overall_top5(session):
    now = dt.datetime(2026, 9, 10, 12, 0, tzinfo=dt.timezone.utc)
    _bootstrap(session, now)
    res = rank_plans(session, OVERALL, RankingContext(), now, limit=5)
    assert [r.plan.external_id for r in res.results] == [
        "total-freedom-175gb-roam-beyond-10gb",
        "total-freedom-125gb-roam-beyond-5gb",
        "total-freedom-250gb-roam-beyond-10gb",
        "total-freedom-70gb-roam-beyond-1gb",
        "total-freedom-250gb-roam-beyond-20gb",
    ]
