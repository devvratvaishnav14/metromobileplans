"""Chatr Mobile adapter.

Source: https://www.chatrwireless.com/plans  (official plans page, plain HTTPS GET,
no login, no anti-bot, robots.txt allows it).

The page server-renders its full state into
``<script id="app-root-state" type="application/json">``. Inside it, one or more
``"plans"`` arrays hold the curated current plan cards, each a fully structured
object (name, plan code, price object, data breakdown, feature list). We read
those objects directly -- nothing is inferred that the object does not state.

If the ``#app-root-state`` script disappears, stops being valid JSON, or contains
no recognizable plan objects, :func:`parse` raises ``ParseError`` so the refresh
fails loudly instead of publishing empty or guessed data.
"""

from __future__ import annotations

import json
import re

from ..normalize import clean_text, parse_data_amount, parse_price
from .base import AutomatedAdapter, NormalizedPlan, ParseError

_APP_STATE_RE = re.compile(
    r'<script id="app-root-state" type="application/json">(.*?)</script>',
    re.S,
)
_SPEED_RE = re.compile(r"at\s+(?P<tier>[0-9A-Za-z]+G[^.]*?)(?:\.|$)", re.I)
_MINUTES_RE = re.compile(r"(\d+)\s*minutes?\b", re.I)
_DATA_POLICY_RE = re.compile(r"\((https?://[^)]*data-management[^)]*)\)", re.I)

PARSER_VERSION = "chatr-appstate-2026-09-02"


class ChatrAdapter(AutomatedAdapter):
    slug = "chatr"
    display_name = "Chatr Mobile"
    network = "Rogers"
    plan_model = "prepaid"
    homepage_url = "https://www.chatrwireless.com/"
    source_url = "https://www.chatrwireless.com/plans"
    source_mode = "official_automated"
    verification_method = "automated_fetch"
    source_kind = "official_page"
    source_description = (
        "Chatr's official plans page. Plans are read from the page-embedded "
        "#app-root-state JSON (the same data the page renders)."
    )
    parser_version = PARSER_VERSION

    def fetch(self):  # -> FetchResult
        return self._get(self.source_url)

    # ------------------------------------------------------------------
    def parse(self, content: bytes) -> list[NormalizedPlan]:
        html = content.decode("utf-8", errors="replace")
        m = _APP_STATE_RE.search(html)
        if not m:
            raise ParseError(
                "Chatr: <script id='app-root-state'> not found -- page structure changed."
            )
        try:
            state = json.loads(m.group(1))
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ParseError(f"Chatr: app-root-state is not valid JSON ({exc}).") from exc

        raw_plans = _collect_plan_objects(state)
        if not raw_plans:
            raise ParseError(
                "Chatr: no 'plans' array with plan objects found in app-root-state."
            )

        prepaid_stated = bool(re.search(r"prepaid (phone )?plans", html, re.I))
        no_contracts_stated = bool(re.search(r"no contracts?", html, re.I))

        by_id: dict[str, NormalizedPlan] = {}
        for rp in raw_plans:
            plan = _normalize_one(
                rp, prepaid_stated=prepaid_stated, no_contracts_stated=no_contracts_stated
            )
            by_id.setdefault(plan.external_id, plan)  # first occurrence wins
        return list(by_id.values())


# ----------------------------------------------------------------------
def _collect_plan_objects(node: object) -> list[dict]:
    found: list[dict] = []

    def walk(n: object) -> None:
        if isinstance(n, dict):
            for key, value in n.items():
                if (
                    key == "plans"
                    and isinstance(value, list)
                    and value
                    and all(isinstance(i, dict) for i in value)
                    and any(("planName" in i or "planCode" in i) for i in value)
                ):
                    found.extend(value)
                else:
                    walk(value)
        elif isinstance(n, list):
            for item in n:
                walk(item)

    walk(node)
    return found


def _normalize_one(rp: dict, *, prepaid_stated: bool, no_contracts_stated: bool) -> NormalizedPlan:
    code = rp.get("planCode") or rp.get("planName")
    if not code:
        raise ParseError(f"Chatr: plan object without planCode/planName: {rp!r:.200}")
    external_id = str(code)

    price = rp.get("price")
    if not isinstance(price, dict) or price.get("amount") is None:
        raise ParseError(f"Chatr: plan {external_id} has no usable price object.")

    amount = parse_price(price.get("amount"))
    sale = parse_price(price.get("salePriceAmount"))
    current = sale if sale is not None else amount
    frequency = (price.get("frequency") or "").strip().lower()
    period_length = price.get("periodLength")

    if frequency.startswith("mo"):
        price_period = "monthly"
        term_months = None
    elif frequency.startswith("year") or frequency == "yr":
        price_period = "annual"
        term_months = int(period_length) if isinstance(period_length, (int, float)) else 12
    else:
        price_period = None
        term_months = int(period_length) if isinstance(period_length, (int, float)) else None

    discounting = bool(price.get("discounting"))
    promo_price = current if (discounting and current != amount) else None
    # Chatr's price is unconditional -- no bundle / AutoPay price games. The
    # "AutoPay bonus" is BONUS DATA, not a price discount.
    regular_price = amount
    monthly_price = amount if price_period == "monthly" else None

    apd = rp.get("additionalPlanDetails") or {}
    d_base = parse_data_amount(apd.get("basePlanData")).gb
    d_bonus = parse_data_amount(apd.get("autopayBonusData")).gb
    d_promo = parse_data_amount(apd.get("promotionData")).gb
    total = parse_data_amount(apd.get("totalData"))
    d_total = total.gb
    if d_total is None and total.unlimited is None:
        # fall back to base + bonus only if both are concrete numbers
        if d_base is not None or d_bonus is not None:
            d_total = (d_base or 0.0) + (d_bonus or 0.0)

    details = rp.get("details") if isinstance(rp.get("details"), list) else []
    data_feature_text = _first_feature_text(details, wanted_type="data")
    speed_tier = None
    has_5g = None
    network_tech = None
    max_mbps = None
    throttled_note = None
    if data_feature_text:
        sm = _SPEED_RE.search(data_feature_text)
        if sm:
            speed_tier = clean_text(sm.group("tier"))
        # match the network generation only where it describes speed ("at 4G speeds"),
        # never a substring of a data amount like "25GB"
        gen = re.search(r"\bat\s+(5G\+?|4G|3G)\b", data_feature_text, re.I)
        if gen:
            network_tech = gen.group(1).upper()
            has_5g = network_tech.startswith("5G")
        mb = re.search(r"up to\s+(\d+(?:\.\d+)?)\s*Mbps", data_feature_text, re.I)
        if mb:
            max_mbps = float(mb.group(1))
        tm = re.search(r"(After using up your data allowance[^.]*\.)", data_feature_text)
        if tm:
            throttled_note = clean_text(tm.group(1))

    # Chatr's data-management text describes continued (throttled) use after the
    # allowance -> the data is unlimited, speed-capped after the full-speed bucket.
    # In that model there is NO finite total cap: data_total_gb stays null.
    if throttled_note and re.search(r"slower speed", throttled_note, re.I):
        data_unlimited = True
        data_unlimited_full_speed = False
        data_hard_cap = False
        data_full_speed = d_total   # the full-speed bucket
        d_total = None              # not a total cap
    elif total.unlimited is True:
        data_unlimited = True
        data_unlimited_full_speed = None
        data_hard_cap = None
        data_full_speed = None
        d_total = None
    elif total.unlimited is False:
        data_unlimited = False
        data_unlimited_full_speed = None
        data_hard_cap = True
        data_full_speed = d_total
    else:
        data_unlimited = None
        data_unlimited_full_speed = None
        data_hard_cap = None
        data_full_speed = d_total

    mf1 = clean_text(rp.get("planMainFeature1Text"))
    mf2 = clean_text(rp.get("planMainFeature2Text"))
    included = clean_text(rp.get("includedServices"))
    talk_blob = " ".join(filter(None, [mf1, included]))
    if re.search(r"unlimited\s+canada[- ]wide\s+talk", talk_blob, re.I):
        canada_wide_calling = True
    elif _MINUTES_RE.search(talk_blob):
        canada_wide_calling = False
    else:
        canada_wide_calling = None

    text_blob = " ".join(filter(None, [mf2, included]))
    unlimited_text = True if re.search(r"unlimited[^.]*text", text_blob, re.I) else None
    international_text = True if re.search(r"international\s+text", text_blob, re.I) else None
    can_us_mex_note = mf2 if (mf2 and re.search(r"\bU\.?S\.?\b", mf2, re.I)) else None
    # the plan's scope is explicitly "Canada-Wide Talk & International Text" -- US
    # texting is included but US calling/data is not part of these plans
    includes_us = False
    includes_mexico = False

    # the page states "No contracts ... simple, affordable prepaid plans"
    contract_required = False if no_contracts_stated else None

    autopay_bonus = clean_text(rp.get("autoPayBonus"))

    policy_url = None
    if data_feature_text:
        pm = _DATA_POLICY_RE.search(data_feature_text)
        if pm:
            policy_url = pm.group(1)

    campaign = rp.get("campaign") if isinstance(rp.get("campaign"), dict) else None
    badge = None
    if campaign:
        deal = campaign.get("deal")
        if isinstance(deal, dict) and deal.get("dealText"):
            badge = clean_text(deal["dealText"])
        elif isinstance(campaign.get("offer"), dict) and campaign["offer"].get("offerName"):
            badge = clean_text(campaign["offer"]["offerName"])
        elif campaign.get("campaignTitle"):
            badge = clean_text(campaign["campaignTitle"])
    # only a real discount is a "promo"; a marketing badge is not a plan condition
    promo_conditions = badge if promo_price is not None else None

    return NormalizedPlan(
        external_id=external_id,
        plan_name=clean_text(rp.get("name")),
        plan_local_name=clean_text(rp.get("planLocalName")),
        price_cad=current,
        price_period=price_period,
        term_months=term_months,
        monthly_price_cad=monthly_price,
        regular_price_cad=regular_price,
        promo_price_cad=promo_price,
        promo_conditions=promo_conditions,
        data_base_gb=d_base,
        data_bonus_gb=d_bonus,
        data_promo_gb=d_promo,
        data_total_gb=d_total,
        data_full_speed_gb=data_full_speed,
        data_unlimited=data_unlimited,
        data_unlimited_is_full_speed=data_unlimited_full_speed,
        data_hard_cap=data_hard_cap,
        throttled_after_note=throttled_note,
        throttle_speed=None,  # Chatr states "a slower speed" but no number
        overage_note=throttled_note,
        network_speed_tier=speed_tier,
        network_technology=network_tech,
        max_download_mbps=max_mbps,
        has_5g=has_5g,
        plan_type="prepaid",  # stated on the page and Chatr's only model; basis in attributes
        contract_required=contract_required,
        canada_wide_calling=canada_wide_calling,
        unlimited_text=unlimited_text,
        international_text=international_text,
        can_us_mex_note=can_us_mex_note,
        includes_us=includes_us,
        includes_mexico=includes_mexico,
        autopay_required=False,  # bonus data for autopay; base plan works without it
        autopay_note=autopay_bonus,
        conditions=included,
        availability="online",
        attributes={
            "source_record": rp,
            "data_feature_text": data_feature_text,
            "data_management_policy_url": policy_url,
            "best_deal_flag": bool(rp.get("bestDeal")),
            "badge": badge,
            "plan_type_basis": (
                "page states 'Prepaid phone plans'" if prepaid_stated
                else "Chatr is a prepaid-only brand (provider-level)"
            ),
            "raw_price": price,
            "raw_additional_plan_details": apd,
        },
    )


def _first_feature_text(details: list, *, wanted_type: str) -> str | None:
    for f in details:
        if not isinstance(f, dict):
            continue
        if (f.get("type") or "").lower() == wanted_type or "data" in (f.get("title") or "").lower():
            txt = f.get("text") or f.get("title")
            if txt:
                return " ".join(str(txt).split())
    return None
