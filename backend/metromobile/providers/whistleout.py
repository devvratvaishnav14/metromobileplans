"""WhistleOut Canada -- trusted_secondary source.

WhistleOut is a well-known cell-plan comparison site. Its full search results sit
behind query-string URLs that its robots.txt disallows, but the
``/Widgets/MobilePhonePopularPlans`` widget is explicitly ``Allow``-ed and
server-renders a small, rotating table of current plans across several carriers
(with a "Last Updated" date). We read that widget.

Everything here lands as ``trusted_secondary`` -> ``secondary_confirmed``,
confidence-capped, and NOT ranking-eligible on its own (see
:mod:`metromobile.validation`). It exists so plans from carriers we cannot fetch
directly (Bell, Public Mobile, Fido, ...) are at least visible, pending an
official source or cross-check.
"""

from __future__ import annotations

import html as _html
import re

from ..normalize import clean_text, parse_data_amount, parse_price, slugify
from .base import NormalizedPlan, ParseError, SecondaryAdapter

BASE = "https://www.whistleout.ca"
PARSER_VERSION = "whistleout-popularwidget-2026-09-07"

# supplier name -> (canonical slug, display name, network, plan model)
# slug matches our official adapters where one exists (Chatr) so records unify.
_PROVIDERS: dict[str, tuple[str, str, str | None, str | None]] = {
    "7-eleven speakout": ("7-eleven-speakout", "7-Eleven SpeakOut", "Rogers", "prepaid"),
    "bell": ("bell", "Bell", "Bell", "postpaid"),
    "bell mobility": ("bell", "Bell", "Bell", "postpaid"),
    "chatr wireless": ("chatr", "Chatr Mobile", "Rogers", "prepaid"),
    "chatr": ("chatr", "Chatr Mobile", "Rogers", "prepaid"),
    "fido": ("fido", "Fido", "Rogers", "postpaid"),
    "koodo mobile": ("koodo", "Koodo Mobile", "TELUS", "postpaid"),
    "koodo": ("koodo", "Koodo Mobile", "TELUS", "postpaid"),
    "public mobile": ("public-mobile", "Public Mobile", "TELUS", "prepaid"),
    "rogers": ("rogers", "Rogers", "Rogers", "postpaid"),
    "telus": ("telus", "TELUS", "TELUS", "postpaid"),
    "virgin plus": ("virgin-plus", "Virgin Plus", "Bell", "postpaid"),
    "lucky mobile": ("lucky-mobile", "Lucky Mobile", "Bell", "prepaid"),
    "freedom mobile": ("freedom-mobile", "Freedom Mobile", "Freedom (Videotron/Quebecor)", "mixed"),
    "fizz": ("fizz", "Fizz", "Videotron", "prepaid"),
    "sasktel": ("sasktel", "SaskTel", "SaskTel", "postpaid"),
}

_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S)
_HREF_RE = re.compile(
    r'href="(/CellPhones/Carriers/([^/]+)/Personal/([^"?]+)(\?contract=(\d+)[^"]*)?)"'
)
_SUPPLIER_RE = re.compile(r'data-supplier="([^"]+)"')
_LI_RE = re.compile(r"<li\b[^>]*>(.*?)</li>", re.S)
_POPOVER_RE = re.compile(r'data-content="([^"]{3,200})"')
_KBPS_RE = re.compile(r"(\d+)\s*Kbps", re.I)
_UPFRONT_RE = re.compile(r"\$(\d+(?:\.\d+)?)\s*Upfront", re.I)
_CONTRACT_RE = re.compile(r"Contract \((\d+)\s*mths?\)", re.I)
_PRICE_RE = re.compile(
    r"\$(\d+(?:\.\d+)?)\s*(?:/\s*mth|per month|Per\s+(\d+)\s+(Day|Days|Month|Months))", re.I
)
_LASTUPD_RE = re.compile(r"Last Updated\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")


def _text(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _html.unescape(s))).strip()


class WhistleOutAdapter(SecondaryAdapter):
    slug = "whistleout"
    display_name = "WhistleOut Canada"
    network = None
    plan_model = None
    homepage_url = "https://www.whistleout.ca/"
    source_url = "https://www.whistleout.ca/Widgets/MobilePhonePopularPlans"
    source_kind = "secondary_page"
    source_description = (
        "WhistleOut Canada 'popular plans' widget (robots-permitted). "
        "Rotating sample; secondary data, not ranking-eligible on its own."
    )
    parser_version = PARSER_VERSION

    def fetch(self):
        return self._get(self.source_url)

    def parse(self, content: bytes) -> list[NormalizedPlan]:
        html = content.decode("utf-8", errors="replace")
        last_updated = (_LASTUPD_RE.search(_text(html)) or [None, None])[1]
        out: list[NormalizedPlan] = []
        seen: set[tuple[str, str]] = set()

        for row in _ROW_RE.findall(html):
            href = _HREF_RE.search(row)
            sup = _SUPPLIER_RE.search(row)
            if not href or not sup:
                continue
            supplier = sup.group(1).strip()
            pslug, pname, network, pmodel = _PROVIDERS.get(
                supplier.lower(), (slugify(supplier), supplier, None, None)
            )
            wo_slug = href.group(3)
            contract_months = (int(href.group(5)) if href.group(5) else 0) or None
            external_id = wo_slug + (f"--c{contract_months}" if contract_months else "")
            if (pslug, external_id) in seen:
                continue
            seen.add((pslug, external_id))

            lis = [_text(li) for li in _LI_RE.findall(row)]
            popovers = [_html.unescape(p) for p in _POPOVER_RE.findall(row)]
            blob = " ".join(lis + popovers)

            plan = _row_to_plan(
                row=row, lis=lis, popovers=popovers, blob=blob,
                external_id=external_id, wo_slug=wo_slug, supplier=supplier,
                contract_months=contract_months,
                source_url=BASE + href.group(1),
                provider=(pslug, pname, network, pmodel),
                last_updated=last_updated,
            )
            out.append(plan)

        if not out:
            raise ParseError(
                "WhistleOut: no plan rows found in the popular-plans widget -- "
                "markup changed."
            )
        return out


def _row_to_plan(*, row, lis, popovers, blob, external_id, wo_slug, supplier,
                 contract_months, source_url, provider, last_updated) -> NormalizedPlan:
    pslug, pname, network, pmodel = provider

    # --- price ---------------------------------------------------------
    pm = _PRICE_RE.search(blob)
    price = period = monthly = term = None
    if pm:
        price = parse_price(pm.group(1))
        if pm.group(2):  # "Per N Day(s)/Month(s)"
            n = int(pm.group(2))
            unit = (pm.group(3) or "").lower()
            if unit.startswith("day") and n >= 300:
                period, term = "annual", 12
            elif unit.startswith("month") and n >= 6:
                period, term = "annual", n
            else:
                period, monthly = "monthly", price
        else:
            period, monthly = "monthly", price

    prepaid_marker = bool(re.search(r"top-?up|per\s+\d+\s+day", blob, re.I))
    plan_type = "prepaid" if prepaid_marker else ("postpaid" if contract_months is not None or "/mth" in blob else pmodel)

    # --- data ---------------------------------------------------------
    data_li = next((x for x in lis if re.search(r"data|unlimited", x, re.I)), "")
    d = parse_data_amount(data_li)
    data_total = d.gb
    data_unlimited = d.unlimited
    if re.search(r"no data included", data_li, re.I):
        data_total, data_unlimited = 0.0, False

    throttle = None
    unlimited_full_speed = None
    km = _KBPS_RE.search(blob)
    if km and re.search(r"capp?ed|thereafter|slower", blob, re.I):
        throttle = f"{km.group(1)} Kbps"
        if data_unlimited or re.search(r"once all included data", blob, re.I):
            data_unlimited = True
            unlimited_full_speed = False

    bonus = None
    bm = re.search(r"(\d+(?:\.\d+)?)\s*GB bonus", blob, re.I) or re.search(
        r"includes\s+(\d+(?:\.\d+)?)\s*GB bonus", blob, re.I
    )
    if bm:
        bonus = float(bm.group(1))

    overage_note = None
    overage_per_gb = None
    om = re.search(r"Additional data \$(\d+(?:\.\d+)?)/(MB|GB)", blob, re.I)
    if om:
        rate = float(om.group(1))
        overage_note = f"Additional data ${om.group(1)}/{om.group(2).upper()} (per WhistleOut)"
        overage_per_gb = round(rate * 1024, 2) if om.group(2).upper() == "MB" else rate

    tech = "4G" if re.search(r"\bat 4G speeds\b", blob, re.I) else (
        "5G" if re.search(r"\bat 5G speeds\b", blob, re.I) else None
    )

    # --- contract ---------------------------------------------------
    contract_required = None
    if contract_months:
        contract_required = True
    elif re.search(r"no contract", blob, re.I) or plan_type == "prepaid":
        contract_required = False

    # --- geography (WhistleOut sometimes tags a plan to one province) --
    geo_note = None
    regions = None
    rm = re.search(r"[-_](QC|ON|BC|AB|MB|SK|NS|NB|NL|PE)$", wo_slug)
    if rm:
        regions = [rm.group(1)]
        geo_note = f"WhistleOut lists this plan for {rm.group(1)}"

    # --- promo / deal ---------------------------------------------
    deal = None
    dm = re.search(r"Deal:\s*(.+)$", " | ".join(lis))
    if dm:
        deal = clean_text(dm.group(1).split(" | ")[0])
    for p in popovers:
        if deal and deal[:20] in p:
            deal = clean_text(p)

    upfront = None
    um = _UPFRONT_RE.search(blob)
    if um:
        upfront = parse_price(um.group(1))

    name = clean_text(re.sub(r"[-_]+", " ", wo_slug)) or external_id

    return NormalizedPlan(
        external_id=external_id,
        plan_name=name,
        price_cad=price,
        price_period=period,
        term_months=term,
        monthly_price_cad=monthly,
        regular_price_cad=price,
        promo_conditions=deal,
        promo_name=("Sign-up deal" if deal else None),
        data_base_gb=(round(data_total - bonus, 2) if (data_total and bonus) else None),
        data_bonus_gb=bonus,
        data_total_gb=data_total,
        data_full_speed_gb=data_total,
        data_unlimited=data_unlimited,
        data_unlimited_is_full_speed=unlimited_full_speed,
        throttle_speed=throttle,
        overage_note=overage_note,
        overage_rate_per_gb_cad=overage_per_gb,
        network_technology=tech,
        plan_type=plan_type,
        contract_required=contract_required,
        contract_length_months=contract_months,
        available_regions=regions,
        geo_availability_note=geo_note,
        availability="online",
        conditions=clean_text(" · ".join(x for x in lis if not x.lower().startswith("deal:"))),
        attributes={
            "_provider": {
                "slug": pslug, "display_name": pname, "network": network, "plan_model": pmodel,
            },
            "_source_url": source_url,
            "_aggregator": "WhistleOut Canada",
            "whistleout_slug": wo_slug,
            "whistleout_last_updated": last_updated,
            "whistleout_upfront_cad": upfront,
            "row_items": lis,
            "row_popovers": popovers,
        },
    )
