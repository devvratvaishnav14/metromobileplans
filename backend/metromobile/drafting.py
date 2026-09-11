"""Turn an operator's saved official capture into a *draft* import manifest.

`metromobile draft-manifest bell --capture <file>` inspects the saved page and
pre-fills a `.plans.jsonc` with every plan and field it can pattern-match. Rules:

* the capture is the only factual source -- nothing is fetched or invented;
* anything not confidently found stays ``null``;
* every auto-filled value is recorded with its source text under ``_review``;
* the whole file is marked ``_draft.reviewed = false`` -- ``metromobile import``
  refuses it until a human has checked it against the page and flipped that.

If the capture can't be parsed into at least one plausible plan, we raise
``DraftError`` and the CLI falls back to the blank template instead of guessing.
"""

from __future__ import annotations

import datetime as dt
import email
import email.policy
import re
from pathlib import Path

from bs4 import BeautifulSoup

from .normalize import parse_data_amount, parse_price, slugify


class DraftError(RuntimeError):
    """Automatic extraction was not reliable enough to produce a draft."""


DRAFT_TOOL_VERSION = "draft-manifest/3 (bell, koodo, freedom-mobile)"

_PRICE_MO = re.compile(r"\$\s?(\d{1,3}(?:\.\d{2})?)\s*/\s*(?:mo|mth|month)\b", re.I)
_GB = re.compile(r"(\d{1,4})\s*GB\b", re.I)
_TECH = re.compile(r"\b(5G\+|5G|4G\s*LTE|LTE|4G|3G)(?![A-Za-z0-9])", re.I)
_PLANISH_NAME = re.compile(
    r"\d+\s*GB|unlimited|\bselect\b|\bultra\b|\bessential\b|\bpremium\b|\bplus\b|\blite\b|\bstarter\b",
    re.I,
)
_HAS_DATA_SPEC = re.compile(r"\d+\s*GB\s+of\s+data|unlimited\s+data|GB\s+of\s+data", re.I)
# "60 GB of data at up to 2 Gbps"
_FULLSPEED = re.compile(r"(\d{1,4})\s*GB\s+of\s+data\s+at\s+up\s+to\s+([\d.]+)\s*(Gbps|Mbps)", re.I)
_THROTTLE = re.compile(r"unlimited\s+data\s+at\s+up\s+to\s+(\d+)\s*Kbps\s+thereafter", re.I)
_UNLIMITED_FULLSPEED = re.compile(
    r"unlimited\s+data\s+at\s+(?:our\s+)?(?:fastest[^.]*?)?up\s+to\s+([\d.]+)\s*(Gbps|Mbps)", re.I
)
_HOTSPOT_GB = re.compile(r"\(?\s*(\d{1,4})\s*GB/mo\.?\s*at\s+up\s+to[^)]*?hotspot|Hotspot[^.]*?\(\s*(\d{1,4})\s*GB", re.I)
_PRICE_GUARANTEE = re.compile(r"PRICE\s+GUARANTEED\s+FOR\s+(\d+)\s+YEARS?", re.I)


# ---------------------------------------------------------------------------
def capture_to_html(raw: bytes, *, suffix: str) -> str:
    """MHTML -> the rendered HTML part; plain .html -> itself. .pdf -> unsupported."""
    suffix = suffix.lower().lstrip(".")
    if suffix == "pdf":
        raise DraftError(
            "PDF captures can't be auto-extracted -- re-save the page as "
            "'Web Page, Single File' (.mhtml) or fill the template manually."
        )
    if suffix in ("mhtml", "mht") or raw[:200].lstrip().lower().startswith(b"mime-version"):
        try:
            msg = email.message_from_bytes(raw, policy=email.policy.default)
        except Exception as exc:  # pragma: no cover - defensive
            raise DraftError(f"could not parse the MHTML container: {exc}") from exc
        html_parts = [
            p for p in msg.walk() if p.get_content_type() == "text/html"
        ]
        if not html_parts:
            raise DraftError("no text/html part found inside the MHTML capture")
        part = html_parts[0]
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    # assume HTML
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
def _clean_soup(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template", "iframe"]):
        tag.decompose()
    return soup


def _plan_cards(soup: BeautifulSoup) -> list:
    """Bell renders each plan as a `.card-plan` (a.k.a. rate-plan card). Fall back
    to a generic heuristic if that class is gone."""
    named = soup.select(
        "[class*='card-plan'], [class*='rate-plan-card'], [class*='rateplan-inner'], "
        "[class*='ratePlanCard'], [data-testid*='rate-plan']"
    )
    cards = []
    for c in named:
        h = c.find(["h2", "h3", "h4", "h5"])
        txt = c.get_text(" ", strip=True)
        if h and _PRICE_MO.search(txt) and _HAS_DATA_SPEC.search(txt) and _PLANISH_NAME.search(h.get_text()):
            cards.append(c)
    if cards:
        return cards
    # heuristic fallback
    out = []
    for el in soup.find_all(["div", "article", "li", "section"]):
        txt = el.get_text(" ", strip=True)
        h = el.find(["h2", "h3", "h4", "h5"])
        if not h or not (80 <= len(txt) <= 2400):
            continue
        if not (_PRICE_MO.search(txt) and _HAS_DATA_SPEC.search(txt)):
            continue
        if not _PLANISH_NAME.search(h.get_text()):
            continue
        if any(id(d) in {id(o) for o in out} for d in el.descendants if getattr(d, "name", None)):
            continue
        out.append(el)
    return out


def _page_warnings(soup: BeautifulSoup, *, raw_html: str = "") -> list[str]:
    t = soup.get_text(" ", strip=True)
    w = []
    # Bell always renders a province <select> listing every province; only warn if
    # BC is not the active one.
    bc_active = bool(
        re.search(r'name="province"\s+content="BC"', raw_html)
        or re.search(r'"province"\s*:\s*"BC"', raw_html)
        or re.search(r'value="BC"[^>]*\bselected\b', raw_html)        # Freedom province <select>
        or re.search(r'<option[^>]*\bselected\b[^>]*>\s*(?:BC|British Columbia)\s*<', raw_html, re.I)
        or re.search(r'value="BC"[^>]*\b(checked|aria-current)', raw_html)
        or re.search(r"current region:\s*(?:<[^>]+>\s*)*British Columbia", raw_html, re.I)
    )
    # explicit non-BC region signal that the operator actively chose (not just a
    # CDN geolocation header) -- e.g. a province <select> with ON selected.
    other_region = re.search(
        r'<option[^>]*value="(?!BC)(ON|AB|MB|QC|SK|NS|NB|NL|PE)"[^>]*\bselected\b',
        raw_html,
    ) or re.search(r'\bregion=(?!BC)(ON|AB|MB|QC|SK|NS|NB|NL|PE);', raw_html)
    if other_region and not bc_active:
        who = other_region.group(1) or other_region.group(2)
        w.append(
            f"REGION MISMATCH: this capture appears to be for {who}, not British "
            f"Columbia. The carrier shows regional pricing -- re-save the page with "
            f"the region/province set to BC (or a Metro Vancouver postal code) and "
            f"re-run draft-manifest. The prices below may be wrong for BC."
        )
    elif not bc_active and re.search(r"select your province|choose your province|current region", t, re.I):
        w.append(
            "Could not confirm British Columbia is the active region in this capture "
            "-- verify the pricing is BC (the carrier shows regional pricing)."
        )
    if re.search(r"Mobility account not found|new or existing Bell customer", t, re.I):
        w.append("A login / account modal was open in the capture; ignore that content.")
    if "footnote" in t.lower():
        w.append("Prices carry footnotes (bundle, autopay, credits) -- check each against the captures.")
    return w


_COND_BUNDLE = re.compile(
    r"with eligible streaming|bundle with streaming|when you bundle|streaming bundle|"
    r"Bell Internet|home internet",
    re.I,
)
_COND_AUTOPAY = re.compile(
    r"Autopay credit|automatic payments|pre-?authorized (?:debit|payment)|with AutoPay", re.I
)
_COND_PROMO = re.compile(
    r"promotional credit|promo credit|for \d+ months|first \d+ months|limited[- ]time",
    re.I,
)
_PRICE_NUM = re.compile(r"\$\s*(\d[\d,]*(?:\s*\.\s*\d{1,2})?)")


def _price_num(text: str | None) -> float | None:
    if not text:
        return None
    m = _PRICE_NUM.search(text)
    if not m:
        return None
    return float(m.group(1).replace(" ", "").replace(",", ""))


def _card_price_rows(card) -> list[dict]:
    """Bell renders each price as a row: a big ``.big-price`` (what you pay), a
    struck-through ``<s>`` regular price, and a ``.g-card-plan__caption`` naming the
    credits the big price assumes. Returns those rows in document order; the
    'Average price per line for N lines' rows are marked ``per_line``."""
    price_block = card.select_one("[class*='g-card-plan__price']") or card
    rows: list[dict] = []
    for bp in price_block.select("div.big-price"):
        row = bp
        for _ in range(3):
            if row.parent is None:
                break
            row = row.parent
            if row.select_one("div.big-price") and (row.select_one("s") or row.select_one("[class*='brs-current']")):
                break
        struck_el = row.select_one("s") or row.select_one("[class*='brs-current']")
        cap_el = row.select_one("[class*='g-card-plan__caption']")
        if cap_el is None:
            nxt = row.find_next(class_=re.compile("g-card-plan__caption"))
            cap_el = nxt
        caption = re.sub(r"\s+", " ", cap_el.get_text(" ", strip=True)) if cap_el else ""
        rows.append(
            {
                "shown": _price_num(bp.get_text(" ", strip=True)),
                "struck": _price_num(struck_el.get_text(" ", strip=True)) if struck_el else None,
                "caption": caption,
                "per_line": bool(re.search(r"average price per line", caption, re.I)),
            }
        )
    return rows


_COND_PROMO_CREDIT = re.compile(
    r"promotional credit|promo credit|new[- ]activation|bill credit|limited[- ]time|"
    r"for \d+ months|first \d+ months",
    re.I,
)


def _classify_price_caption(caption: str, flag: str) -> str:
    """What conditions does this big-price assume?
    -> 'bundle' | 'autopay_promo' | 'autopay' | 'promo' | 'regular'.

    'autopay_promo' = the discount combines an AutoPay credit AND a promotional /
    new-activation credit that Bell does NOT itemise -- AutoPay's share can't be
    separated, so the figure is a conditional *promo* price, not an AutoPay price."""
    blob = f"{flag} {caption}"
    if _COND_BUNDLE.search(blob):
        return "bundle"
    has_autopay = bool(_COND_AUTOPAY.search(blob))
    has_promo = bool(_COND_PROMO_CREDIT.search(blob))
    if has_autopay and has_promo:
        return "autopay_promo"
    if has_autopay:
        return "autopay"
    if has_promo:
        return "promo"
    return "regular"


def _bell_price_dom(card, flag: str) -> dict:
    """DOM-based price tiers for one Bell card. The struck-through figure is the
    unconditional regular price; the big price is a conditional tier keyed by its
    caption. Nothing is collapsed to a single number."""
    notes: list[str] = []
    out: dict = {
        "regular_price_cad": None,
        "autopay_price_cad": None,
        "autopay_conditions": None,
        "bundle_price_cad": None,
        "bundle_conditions": None,
        "promo_price_cad": None,
        "promo_conditions": None,
        "promo_stacks_conditions": None,
        "pricing_notes": None,
        "autopay_seen": False,
        "notes": notes,
        "_regular_seen_from": None,
    }
    rows = _card_price_rows(card)
    single = [r for r in rows if not r["per_line"]]
    per_line = [r for r in rows if r["per_line"]]
    if not single:
        notes.append("no price row found in the card DOM")
        return out

    r0 = single[0]
    observed: list[dict] = []
    seen_amounts: set[tuple] = set()
    for r in single:
        cap = re.sub(r"\s*footnote \d+.*$", "", r["caption"]).strip() or flag or "price shown"
        for amt, lbl in ((r["shown"], cap), (r["struck"], "regular (struck-through)")):
            if amt is None:
                continue
            key = (amt, lbl)
            if key in seen_amounts:
                continue
            seen_amounts.add(key)
            observed.append({"amount": amt, "label": lbl[:90]})
    out["pricing_notes"] = observed or None

    if r0["struck"] is not None and r0["struck"] != r0["shown"]:
        out["regular_price_cad"] = r0["struck"]
        out["_regular_seen_from"] = "struck-through price"

    kind = _classify_price_caption(r0["caption"], flag)
    cap = r0["caption"]
    out["autopay_seen"] = bool(_COND_AUTOPAY.search(f"{flag} {cap}"))

    _PROMO_COND_TEXT = (
        "price requires automatic payments (AutoPay) AND Bell's promotional / "
        "new-activation eligibility (Bell states 'includes Autopay credit and "
        "promotional credit'; footnotes tie the credit to a new activation with "
        "pre-authorized debit set up within 31 days). AutoPay's share is not "
        "itemised, so no standalone autopay_price_cad is recorded."
    )
    if kind == "bundle":
        out["bundle_price_cad"] = r0["shown"]
        conds = ["requires an eligible Crave / Netflix / Disney+ streaming bundle "
                 "(applied as a $15/mo bill credit; lost if the plan changes)"]
        if _COND_AUTOPAY.search(cap):
            conds.append("plus automatic payments (AutoPay)")
        if _COND_PROMO_CREDIT.search(cap):
            conds.append("plus Bell's promotional / new-activation eligibility")
        out["bundle_conditions"] = "; ".join(conds)
    elif kind == "autopay_promo":
        # AutoPay + promo credit, not separable -> a conditional PROMO price.
        out["promo_price_cad"] = r0["shown"]
        out["promo_conditions"] = _PROMO_COND_TEXT
        out["promo_stacks_conditions"] = "requires automatic payments (AutoPay)"
        out["promo_expiry_known"] = False  # no verifiable current expiry date
        notes.append(
            "the discounted price combines an AutoPay credit and a promotional / "
            "new-activation credit that Bell does not itemise -> stored as "
            "promo_price_cad (conditional), NOT autopay_price_cad. If Bell's "
            "footnotes give a real expiry date, set promo_ends_at + "
            "promo_expiry_known=true."
        )
    elif kind == "autopay":
        out["autopay_price_cad"] = r0["shown"]
        out["autopay_conditions"] = (
            "requires pre-authorized debit / automatic payments set up within 31 days"
        )
    elif kind == "promo":
        out["promo_price_cad"] = r0["shown"]
        out["promo_conditions"] = (re.sub(r"\s*footnote \d+.*$", "", cap).strip()
                                   or "promotional credit -- see footnotes")
        out["promo_expiry_known"] = False
        notes.append("set promo_ends_at / promo_expiry_known from the footnotes if a date is stated")
    else:  # regular
        if out["regular_price_cad"] is None:
            out["regular_price_cad"] = r0["shown"]
            out["_regular_seen_from"] = "the only price shown (no visible conditions)"

    if per_line:
        pls = sorted({r["shown"] for r in per_line if r["shown"] is not None})
        if pls:
            notes.append(f"per-line average prices (multi-line only, not a plan price): {pls}")
    return out



_ROAM = re.compile(
    r"(\d+(?:\.\d+)?)\s*GB/day of data roaming(?:\s+in\s+(.+?))?"
    r"(?=,\s*unlimited data|\s+footnote\s+\d+|$)",
    re.I,
)
_ROAM_THROTTLE = re.compile(
    r"GB/day of data roaming.{0,90}?unlimited data at up to (\d+)\s*Kbps thereafter", re.I
)


def _card_name(card, card_text: str) -> str | None:
    h = card.find(["h2", "h3", "h4", "h5"])
    name = re.sub(r"\s+", " ", h.get_text(" ", strip=True)) if h else None
    if not name or len(name) > 90:
        return None
    # Bell reuses one heading for roaming variants ("Ultra - Unlimited") and puts
    # the distinguisher in the card body ("with U.S./Mexico roaming").
    qual = re.search(
        re.escape(name) + r"\s+(with\s+[A-Za-z./ &+-]{2,40}?\s*roaming)", card_text, re.I
    )
    if qual:
        name = f"{name} ({qual.group(1).strip()})"
    return name


def _card_text(card) -> str:
    card_text = re.sub(r"\s+", " ", card.get_text(" ", strip=True))
    # Bell repeats every price for screen readers ("$50/mo. 50 dollars per
    # month.") -- strip the spoken duplication so it doesn't pollute notes.
    card_text = re.sub(r"\s*\d+(?:\.\d+)? dollars per month\.?", "", card_text, flags=re.I)
    card_text = re.sub(r"\s*dollars per month\.?", "", card_text, flags=re.I)
    return card_text


def _bell_streaming_bundle_prices(streaming_html: str) -> dict:
    """From the 'With Streaming' capture: {plan_name -> {bundle_price_cad,
    bundle_conditions, struck}}. Only the bundle tier + its regular-price
    cross-check are taken from this capture."""
    soup = _clean_soup(streaming_html)
    out: dict[str, dict] = {}
    for card in _plan_cards(soup):
        ct = _card_text(card)
        name = _card_name(card, ct)
        if not name:
            continue
        flag_el = card.select_one("[class*='small-flag']")
        flag = re.sub(r"\s+", " ", flag_el.get_text(" ", strip=True)) if flag_el else ""
        pr = _bell_price_dom(card, flag)
        out[name] = {
            "bundle_price_cad": pr.get("bundle_price_cad"),
            "bundle_conditions": pr.get("bundle_conditions"),
            "struck": pr.get("regular_price_cad"),
        }
    return out


def extract_bell_plans(html: str, *, streaming_html: str | None = None) -> dict:
    soup = _clean_soup(html)
    if not _PRICE_MO.search(soup.get_text(" ", strip=True)):
        raise DraftError(
            "no monthly price ($__/mo.) found -- the rendered plan grid may not have "
            "been saved (scroll the whole page, then re-save)."
        )

    cards = _plan_cards(soup)
    if not cards:
        raise DraftError(
            "no recognizable Bell plan cards in the capture -- the plan grid may not "
            "have rendered before saving, or Bell changed its markup. Fill the "
            "template by hand."
        )

    streaming = _bell_streaming_bundle_prices(streaming_html) if streaming_html else {}
    streaming_matched: set[str] = set()

    seen: set[str] = set()
    drafts: list[dict] = []
    for card in cards:
        card_text = _card_text(card)
        name = _card_name(card, card_text)
        if not name:
            continue
        flag_el = card.select_one("[class*='small-flag']")
        card_flag = re.sub(r"\s+", " ", flag_el.get_text(" ", strip=True)) if flag_el else ""

        review_src: dict[str, str] = {}
        auto: list[str] = []
        plan: dict = {
            "external_id": "",
            "plan_type": "postpaid",
            "price_period": "monthly",
            "byod": True,
            "availability": "online",
        }

        def put(field, value, snippet=None):
            plan[field] = value
            auto.append(field)
            if snippet:
                review_src[field] = snippet

        put("plan_name", name, name)
        ext = slugify(f"bell-{name}")
        if ext in seen:
            continue
        seen.add(ext)
        plan["external_id"] = ext or f"bell-plan-{len(drafts) + 1}"

        # --- price: separate tiers, never collapsed to one number --------
        pr = _bell_price_dom(card, card_flag)
        price_notes = pr["notes"]
        for f in ("regular_price_cad", "autopay_price_cad", "autopay_conditions",
                  "bundle_price_cad", "bundle_conditions", "promo_price_cad",
                  "promo_conditions", "promo_stacks_conditions", "promo_expiry_known"):
            if pr.get(f) is not None:
                put(f, pr[f], pr.get("_regular_seen_from") if f == "regular_price_cad" else None)
        pricing_notes = list(pr.get("pricing_notes") or [])

        # merge the bundle tier + regular-price cross-check from the streaming capture
        s = streaming.get(name)
        if s:
            streaming_matched.add(name)
            if s.get("bundle_price_cad") is not None:
                put("bundle_price_cad", s["bundle_price_cad"], "from the With-Streaming capture")
                put("bundle_conditions", s["bundle_conditions"], "from the With-Streaming capture")
            if s.get("struck") is not None and plan.get("regular_price_cad") is not None:
                if s["struck"] == plan["regular_price_cad"]:
                    price_notes.append(
                        f"regular price ${plan['regular_price_cad']:g} confirmed by both "
                        f"the Mobility-only and With-Streaming captures"
                    )
                else:
                    price_notes.append(
                        f"REGULAR PRICE MISMATCH: Mobility-only shows "
                        f"${plan['regular_price_cad']:g}, With-Streaming shows "
                        f"${s['struck']:g} -- reconcile before import"
                    )
            if s.get("bundle_price_cad") is not None:
                pricing_notes.append(
                    {"amount": s["bundle_price_cad"],
                     "label": "with streaming bundle (from the With-Streaming capture)"}
                )
        elif streaming:
            price_notes.append(
                "no matching plan in the With-Streaming capture -- bundle price not set"
            )

        if pricing_notes:
            plan["pricing_notes"] = pricing_notes
        any_tier = any(
            plan.get(f) is not None
            for f in ("regular_price_cad", "autopay_price_cad", "bundle_price_cad",
                      "promo_price_cad")
        )
        if pr.get("autopay_seen") or plan.get("autopay_price_cad") is not None:
            put("autopay_required", True, "card shows an AutoPay-conditional price")
        if plan.get("promo_price_cad") is not None and "promo_expiry_known" not in plan:
            plan["promo_expiry_known"] = False  # no verified current expiry date

        # --- restricted eligibility (partner / employer / exclusive offers) ---
        elig = re.search(
            r"(exclusive partner offer|partner offer|exclusive offer|"
            r"employee[e']?s?\s+plan|corporate plan|invite[- ]only|"
            r"eligible (?:employees|members|partners))",
            card_text, re.I,
        )
        if elig:
            put("eligibility_restricted", True, elig.group(0))
            put("eligibility_conditions",
                f"Bell restricts this plan: '{elig.group(0)}' -- verify the exact "
                f"eligibility condition from the capture before ranking it for anyone.")
            price_notes.append(
                "RESTRICTED OFFER: this plan is not available to an ordinary customer "
                "-- it is kept for reference but excluded from the default ranking."
            )

        # --- data ------------------------------------------------------
        fm = _FULLSPEED.search(card_text)
        thr = _THROTTLE.search(card_text)
        ufs = _UNLIMITED_FULLSPEED.search(card_text)
        if fm:
            gb = float(fm.group(1))
            mbps = float(fm.group(2)) * (1000 if fm.group(3).lower() == "gbps" else 1)
            put("data_full_speed_gb", gb, fm.group(0))
            put("max_download_mbps", mbps, f"up to {fm.group(2)} {fm.group(3)}")
            if thr:
                # "N GB at full speed, then unlimited at 512 Kbps" -> unlimited data
                # with a full-speed bucket, NOT a hard N GB cap.
                put("data_unlimited", True, thr.group(0))
                plan["data_unlimited_is_full_speed"] = False
                put("throttle_speed", f"{thr.group(1)} Kbps", thr.group(0))
                plan["data_hard_cap"] = False
            else:
                put("data_total_gb", gb, fm.group(0))
                plan["data_hard_cap"] = True
        elif ufs and "unlimited" in name.lower():
            mbps = float(ufs.group(1)) * (1000 if ufs.group(2).lower() == "gbps" else 1)
            put("data_unlimited", True, ufs.group(0))
            plan["data_unlimited_is_full_speed"] = True
            put("max_download_mbps", mbps, f"up to {ufs.group(1)} {ufs.group(2)}")
            plan["data_hard_cap"] = False
            if thr:  # a throttle line here is usually for hotspot only
                review_src["_note"] = "a '512 Kbps thereafter' clause exists -- check if it's for data or hotspot only"

        # --- network -------------------------------------------------
        tm = _TECH.search(card_text)
        if re.search(r"5G\s*/\s*5G\+|5G\+", card_text):
            put("network_technology", "5G+", "5G/5G+ network access")
            plan["has_5g"] = True
        elif tm:
            put("network_technology", tm.group(1).upper().replace("  ", " "), tm.group(0))
            plan["has_5g"] = tm.group(1).upper().startswith("5G")

        # --- calling / travel --------------------------------------
        if re.search(r"unlimited\s+calling[^.]*?\bCanada\b", card_text, re.I):
            put("canada_wide_calling", True, "‘unlimited calling … in Canada’")
            put("unlimited_text", True, "‘unlimited … texting … in Canada’")
        if re.search(r"in\s+the\s+U\.?S\.?\b", card_text, re.I) or re.search(r"and\s+in\s+the\s+U\.S\.", card_text, re.I):
            put("includes_us", True, re.search(r"[^.]*U\.?S\.?[^.]*", card_text).group(0)[:120])
        if re.search(r"\bMexico\b", card_text, re.I):
            put("includes_mexico", True, re.search(r"[^.]*Mexico[^.]*", card_text).group(0)[:120])
        introam = re.search(
            r"data roaming in (\d+)\s+(?:other\s+)?countries|international roaming", card_text, re.I
        )
        if introam:
            put("international_roaming", True, introam.group(0)[:140])
        roam = _ROAM.search(card_text)
        if roam:
            gb_day, where = roam.group(1), roam.group(2)
            tm2 = _ROAM_THROTTLE.search(card_text)
            parts = [f"{gb_day} GB/day of data roaming"]
            if where:
                parts.append(f"in {where.strip().rstrip(',')}")
            if tm2:
                parts.append(f"then unlimited at {tm2.group(1)} Kbps")
            put("international_roaming_note", "; ".join(parts)[:200], roam.group(0)[:200])

        # --- features / conditions -------------------------------
        if re.search(r"Hotspot capabilities|hotspot", card_text, re.I):
            put("hotspot", True, "‘Hotspot capabilities’")
        hs = _HOTSPOT_GB.search(card_text)
        if hs:
            g = hs.group(1) or hs.group(2)
            if g:
                put("hotspot_data_gb", float(g), hs.group(0).strip())
        pg = _PRICE_GUARANTEE.search(card_text)
        conditions = []
        if pg:
            conditions.append(f"Price guaranteed for {pg.group(1)} years")
        sv = re.search(r"(SD|HD)\s+video streaming", card_text, re.I)
        if sv:
            conditions.append(f"{sv.group(1).upper()} video streaming")
        calls = re.search(r"[Uu]nlimited minutes for calls from Canada to (\d+)\s+countries", card_text)
        if calls:
            conditions.append(f"unlimited calls from Canada to {calls.group(1)} countries")
        if conditions:
            put("conditions", "; ".join(conditions), " / ".join(conditions))

        important_nulls = [
            f for f in (
                "regular_price_cad", "autopay_price_cad", "bundle_price_cad",
                "promo_price_cad", "promo_ends_at", "promo_expiry_known",
                "autopay_note", "activation_fee_cad", "contract_required",
                "throttle_speed", "data_full_speed_gb", "data_unlimited",
                "includes_us", "available_regions", "student_offer",
            ) if plan.get(f) in (None,) and f not in plan
        ]

        plan["_review"] = {
            "status": "draft-unreviewed",
            "confidence": "low" if not any_tier else "medium",
            "auto_extracted": sorted(set(auto)),
            "check_these_nulls_against_the_page": important_nulls,
            "source_text": review_src,
            "price_notes": price_notes,
            "card_excerpt": card_text[:500],
            "warnings": [
                "PRICE TIERS. regular_price_cad is the UNCONDITIONAL price a neutral "
                "ranking uses -- read from the struck-through figure (identical on "
                "both Bell tabs). The Mobility-only big price combines an AutoPay "
                "credit AND a promotional / new-activation credit that Bell does not "
                "itemise -> stored as promo_price_cad (conditional), NOT "
                "autopay_price_cad. bundle_price_cad = the With-Streaming big price. "
                "Verify every figure against the captures.",
                "promo_expiry_known is set to false (no verified current expiry). If "
                "a Bell footnote states a real end date, add promo_ends_at + set "
                "promo_expiry_known=true.",
                "If a capture ever contains an Exclusive Partner Offer / Lite / "
                "employee plan, it must carry eligibility_restricted=true so the "
                "default ranking excludes it.",
                "Confirm this pricing is for British Columbia and bring-your-own-phone "
                "/ SIM-only.",
            ],
        }
        drafts.append(plan)

    # plans that appear only in the With-Streaming capture (bundle price but no
    # Mobility-only row) -- surface them so the operator doesn't miss a plan.
    for sname, s in streaming.items():
        if sname in streaming_matched:
            continue
        ext = slugify(f"bell-{sname}") or f"bell-plan-{len(drafts) + 1}"
        if ext in seen:
            continue
        drafts.append({
            "external_id": ext,
            "plan_name": sname,
            "plan_type": "postpaid",
            "price_period": "monthly",
            "byod": True,
            "availability": "online",
            "regular_price_cad": s.get("struck"),
            "bundle_price_cad": s.get("bundle_price_cad"),
            "bundle_conditions": s.get("bundle_conditions"),
            "_review": {
                "status": "draft-unreviewed",
                "confidence": "low",
                "auto_extracted": ["plan_name", "regular_price_cad", "bundle_price_cad"],
                "check_these_nulls_against_the_page": ["everything"],
                "source_text": {},
                "price_notes": [
                    "this plan was found ONLY in the With-Streaming capture -- it has "
                    "no Mobility-only row. Re-capture the Mobility-only tab and confirm "
                    "the unconditional price, data and features before import."
                ],
                "card_excerpt": "",
                "warnings": ["incomplete -- only the bundle capture had this plan"],
            },
        })

    if not drafts:
        raise DraftError("plan cards were found but none had a usable name -- fill the template by hand.")
    return {"plans": drafts, "page_warnings": _page_warnings(soup, raw_html=html)}


# ===========================================================================
#  Koodo Mobile (TELUS network) -- official_manual BYOP page
# ===========================================================================
_KOODO_DATA = re.compile(r"(\d+(?:\.\d+)?)\s*(GB|MB)\s+at\s+(\dG\+?)\s+Speed", re.I)
_KOODO_MBPS = re.compile(r"up to\s+(\d+(?:\.\d+)?)\s*Mbps", re.I)
_KOODO_INTL_CALL = re.compile(
    r"(\d+)\s+years?\s+of\s+unlimited international calling to (\d+)\s+countries", re.I
)


def _koodo_cards(soup: BeautifulSoup) -> list:
    """Koodo renders each plan inside a `CardContent__CardContentContainer`
    (styled-components), with an eyebrow tag ('Promotion' / 'Student deal' /
    'Canada-US-Mexico roaming') and section header ('Mobility Plans' /
    'Starter Plans') outside it."""
    return [
        c for c in soup.select("[class*='CardContent__CardContentContainer']")
        if "per month" in c.get_text()
    ]


def _koodo_card_context(card) -> tuple[str, str | None]:
    """(wrapper_text, eyebrow_tag) -- climb to the smallest ancestor holding
    exactly one 'per month' so the eyebrow tag comes with it."""
    tags = ("Canada-US-Mexico roaming", "Canada-US roaming", "Student deal",
            "Exclusive offer", "Partner offer", "Promotion")
    node = card
    wrap = card
    for _ in range(6):
        if node.parent is None:
            break
        node = node.parent
        if len(re.findall(r"per month", node.get_text())) == 1:
            wrap = node
        else:
            break
    wtext = re.sub(r"\s+", " ", wrap.get_text(" ", strip=True))
    tag = next((t for t in tags if t.lower() in wtext[:40].lower()), None)
    return wtext, tag


def _koodo_struck_price(card) -> float | None:
    for el in card.find_all("div"):
        if "line-through" in (el.get("style") or ""):
            m = re.search(r"\$\s?(\d+(?:\.\d+)?)", el.get_text())
            if m:
                return float(m.group(1))
    return None


def _koodo_current_price(card) -> float | None:
    pl = card.select_one("[class*='PriceLockup__PriceLockupContainer']")
    text = re.sub(r"\s+", " ", (pl or card).get_text(" ", strip=True))
    m = re.search(r"\$\s?(\d+)(?:\s*\.\s*(\d+))?\s*per month", text)
    if not m:
        return None
    return float(m.group(1) + ("." + m.group(2) if m.group(2) else ""))


def extract_koodo_plans(html: str) -> dict:
    soup = _clean_soup(html)
    cards = _koodo_cards(soup)
    if not cards:
        raise DraftError(
            "no Koodo plan cards ('per month' + a data spec) in the capture -- the "
            "rate-plan grid may not have rendered before saving (scroll the whole "
            "grid, wait, then re-save), or Koodo changed its markup."
        )

    seen: set[str] = set()
    drafts: list[dict] = []
    for card in cards:
        wtext, tag = _koodo_card_context(card)
        review_src: dict[str, str] = {}
        auto: list[str] = []
        plan: dict = {
            "external_id": "",
            "plan_type": "postpaid",  # this is the postpaid BYOP page
            "price_period": "monthly",
            "byod": True,
            "availability": "online",
        }

        def put(field, value, snippet=None):
            plan[field] = value
            auto.append(field)
            if snippet:
                review_src[field] = snippet

        # --- data / network -> also the plan identity -----------------
        dm = _KOODO_DATA.search(wtext)
        ppu = bool(re.search(r"pay-per-use data", wtext, re.I))
        gb = tech = None
        if dm:
            amount = float(dm.group(1))
            gb = amount / 1000 if dm.group(2).upper() == "MB" else amount
            tech = dm.group(3).upper()
            put("data_base_gb", gb, dm.group(0))
            put("data_full_speed_gb", gb, dm.group(0))
            # Koodo "Shock-Free" data stops at the cap (no overage) -> a hard cap
            put("data_total_gb", gb, dm.group(0))
            plan["data_hard_cap"] = True
            plan["data_unlimited"] = False
            if re.search(r"Shock-?Free", wtext, re.I):
                put("overage_note",
                    "Shock-Free data: data stops at the cap, no overage charges",
                    "Shock-Free® Data")
            put("network_technology", tech, f"{dm.group(0)}")
            plan["has_5g"] = tech.startswith("5G")
        elif ppu:
            put("overage_note", "pay-per-use data (no monthly data allowance)", "Pay-per-use data")
            plan["data_unlimited"] = False
        mb = _KOODO_MBPS.search(wtext)
        if mb:
            put("max_download_mbps", float(mb.group(1)), mb.group(0))

        # --- name (Koodo cards have no plan name -- build a stable one) --
        if gb is not None:
            core = (f"{gb:g}GB" if gb >= 1 else f"{dm.group(1)}MB")
        elif ppu:
            core = "Pay-per-use"
        else:
            core = "plan"
        quals = []
        if tech:
            quals.append(tech)
        if tag and tag != "Promotion":
            quals.append(tag)
        name = f"Koodo {core}" + (f" ({', '.join(quals)})" if quals else "")
        put("plan_name", name, wtext[:80])
        ext = slugify(name)
        if ext in seen:
            continue
        seen.add(ext)
        plan["external_id"] = ext or f"koodo-plan-{len(drafts) + 1}"

        # --- price: struck = unconditional regular; current = discounted -
        struck = _koodo_struck_price(card)
        current = _koodo_current_price(card)
        disc = re.search(
            r"total discounts of \$(\d+)/mo,?\s*including the ([^.]+?)\.", wtext, re.I
        )
        if struck is not None and current is not None and struck != current:
            put("regular_price_cad", struck, "struck-through price on the card")
            put("promo_price_cad", current, disc.group(0) if disc else "current price on the card")
            cond = (
                "the discounted price reflects "
                + (f"${disc.group(1)}/mo in total discounts, including {disc.group(2).strip()}"
                   if disc else "on-card discounts")
                + ". Koodo does not itemise the promotional vs auto-pay share on the "
                "page, so no standalone autopay_price_cad is recorded."
            )
            put("promo_conditions", cond)
            if disc and re.search(r"auto-?pay|pre-?authorized", disc.group(2), re.I):
                put("promo_stacks_conditions", "requires auto-pay by bank account")
                put("autopay_required", True, disc.group(0))
            plan["promo_expiry_known"] = False  # no end date shown
        elif current is not None:
            put("regular_price_cad", current,
                "the only price shown (no struck-through / discount)")
        # note the exact figures for the reviewer
        notes = []
        if struck is not None or current is not None:
            notes.append(
                f"card prices: regular ${struck if struck is not None else current:g}"
                + (f", discounted ${current:g}" if struck is not None and current != struck else "")
            )

        # --- calling / messaging -------------------------------------
        if re.search(r"[Uu]nlimited Canada-wide minutes", wtext):
            put("canada_wide_calling", True, "Unlimited Canada-wide minutes")
        elif re.search(r"\d+ Canada-wide minutes", wtext):
            put("canada_wide_calling", False, re.search(r"\d+ Canada-wide minutes[^.]*", wtext).group(0)[:80])
        if re.search(r"[Uu]nlimited (?:Canada-wide|International) (?:messaging|SMS|text)", wtext):
            put("unlimited_text", True, "unlimited messaging / SMS")
        if re.search(r"[Uu]nlimited International SMS", wtext):
            put("international_text", True, "Unlimited International SMS")

        # --- Canada-US / roaming (ONLY when explicit) ----------------
        if re.search(r"Canada-US(?:-Mexico)? roaming with data, talk", wtext, re.I) or \
           (tag and "canada-us" in tag.lower()):
            put("includes_us", True, "Canada-US roaming with data, talk and texts")
            if re.search(r"Mexico", wtext):
                put("includes_mexico", True, "Canada-US-Mexico roaming")
        ic = _KOODO_INTL_CALL.search(wtext)

        # --- conditions / perks -------------------------------------
        conds = []
        if re.search(r"Pick 1 FREE Perk", wtext, re.I):
            conds.append("includes 1 free perk (customer-selected, e.g. 3-Day Easy Roam International)")
        if ic:
            conds.append(f"{ic.group(1)} years of unlimited international calling to {ic.group(2)} countries (promo perk)")
        if conds:
            put("conditions", "; ".join(conds), " / ".join(conds))

        # --- restricted eligibility --------------------------------
        if tag and re.search(r"student", tag, re.I):
            put("eligibility_restricted", True, tag)
            put("eligibility_conditions",
                "Koodo 'Student deal' -- requires verified student eligibility. "
                "Confirm the exact condition from the capture / Koodo's student page.")
        elif re.search(r"exclusive|partner|invite[- ]only|targeted", (tag or "") + " " + wtext[:60], re.I):
            put("eligibility_restricted", True, (tag or "restricted offer"))
            put("eligibility_conditions", "restricted / targeted offer -- verify eligibility from the capture")

        important_nulls = [
            f for f in (
                "regular_price_cad", "promo_price_cad", "promo_ends_at", "promo_expiry_known",
                "autopay_note", "activation_fee_cad", "contract_required",
                "data_bonus_gb", "data_promo_gb", "includes_us", "student_offer",
                "available_regions",
            ) if plan.get(f) in (None,) and f not in plan
        ]
        plan["_review"] = {
            "status": "draft-unreviewed",
            "confidence": "medium" if plan.get("regular_price_cad") is not None else "low",
            "auto_extracted": sorted(set(auto)),
            "check_these_nulls_against_the_page": important_nulls,
            "source_text": review_src,
            "price_notes": notes,
            "card_excerpt": wtext[:500],
            "warnings": [
                "PRICE. regular_price_cad = the struck-through figure (unconditional). "
                "The bigger current price is promo_price_cad -- it bundles a "
                "promotional discount AND an auto-pay-by-bank-account discount that "
                "Koodo does not itemise, so autopay_price_cad stays null. If Koodo's "
                "'See details' shows a real end date, set promo_ends_at + "
                "promo_expiry_known=true.",
                "DATA. Koodo 'Shock-Free' plans are a HARD CAP (data stops, no "
                "overage) -- data_hard_cap=true, data_unlimited=false. There is no "
                "bonus-data split on this capture; if a card shows 'X GB + Y GB "
                "bonus', put the base in data_base_gb and the bonus in data_bonus_gb.",
                "Confirm British Columbia pricing and bring-your-own-phone / SIM-only.",
                "includes_us is set ONLY for an explicit Canada-US(-Mexico) roaming "
                "plan; 'Unlimited International SMS' alone does NOT qualify.",
                "A 'Student deal' / exclusive / targeted plan is marked "
                "eligibility_restricted -- it stays in the catalogue but out of the "
                "default ranking.",
            ],
        }
        drafts.append(plan)

    if not drafts:
        raise DraftError("Koodo cards found but none yielded a usable plan -- fill the template by hand.")
    return {"plans": drafts, "page_warnings": _page_warnings(soup, raw_html=html)}


# ===========================================================================
#  Freedom Mobile (Videotron / Quebecor network) -- official_manual BYOP page
# ===========================================================================
_FM_NAME = re.compile(r"(\d+)\s*GB\s*(5G\+?|4G(?:\s*LTE)?|LTE)", re.I)
_FM_DOMESTIC = re.compile(r"(\d+(?:\.\d+)?)\s*GB\s+data\s+in\s+Canada-U\.?S\.?-Mexico", re.I)
_FM_ROAM = re.compile(
    r"(\d+(?:\.\d+)?)\s*GB\s+data\s+in\s+(\d+\+?)\s+Roam Beyond global destinations", re.I
)
_FM_THROTTLE = re.compile(r"[Uu]nlimited data at reduced speeds thereafter", re.I)
_FM_DIGITAL_DISCOUNT = 5.0  # Freedom footnote 2: "$5 monthly discount"

# Freedom's "Unlimited Plans Data Policy" footnote states network-DEPENDENT
# throttled speeds -- never a single number. Parsed once per capture.
_FM_THROTTLE_POLICY = re.compile(
    r"up to (\d+)\s*kilobits per second \(for downloads\) and (\d+)\s*kilobits per "
    r"second \(for uploads\) on the Freedom Network,?\s*and up to (\d+)\s*kilobits per "
    r"second \(for downloads\) and (\d+)\s*kilobits per second \(for uploads\) on "
    r"partner networks",
    re.I,
)

# Freedom's restricted post-secondary student offer footnote: "$45/mo. is based on a
# $50/mo. plan after Digital Discount, less a $5/mo. student offer credit for 18
# months ... eligible plan (in-market Total Freedom 175GB + Roam Beyond 10GB and up
# plans ...)". Parsed once per capture; matched to the card it applies to by GB.
_FM_STUDENT = re.compile(
    r"Student Offer\b.*?\$(\d+)/mo\.\s*is based on a \$(\d+)/mo\.\s*plan after Digital "
    r"Discount,\s*less a \$(\d+)/mo\.\s*student offer credit for (\d+)\s*months"
    r".*?eligible plan \(in-market ([^)]+?)\s+and up plans",
    re.I | re.S,
)
_FM_STUDENT_PLAN_GB = re.compile(r"(\d+)\s*GB\s*\+\s*Roam Beyond\s*(\d+)\s*GB", re.I)
_FM_STUDENT_FULL = re.compile(r"Student Offer\b.{0,700}", re.I | re.S)


def _fm_cards(soup: BeautifulSoup) -> list:
    return [
        c for c in soup.select("[data-testid='plan-card']")
        if c.select_one("[data-testid='plan-monthly-price']")
        and (c.select_one("[data-testid='plan-card-v2-plan-name-row']")
             or "Total Freedom" in c.get_text())
    ]


def _fm_ribbon(card) -> str | None:
    wrap = card
    for _ in range(3):
        wrap = wrap.parent
        if wrap is None:
            break
        # the ribbon must live in a wrapper holding EXACTLY this one plan-card
        if len(wrap.select("[data-testid='plan-card']")) != 1:
            break
        sp = wrap.find(string=re.compile(
            r"OFFER!|BACK TO SCHOOL|Exclusive|\bStudent\b|Limited[- ]time", re.I))
        if sp:
            return re.sub(r"\s+", " ", sp.strip())
    return None


def extract_freedom_plans(html: str) -> dict:
    soup = _clean_soup(html)
    cards = _fm_cards(soup)
    if not cards:
        raise DraftError(
            "no Freedom 'plan-card' elements with a price in the capture -- the plan "
            "grid may not have rendered before saving (scroll it, wait, then re-save), "
            "or Freedom changed its markup."
        )

    full_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    # page-level (not per-card) throttle policy: network-dependent, never one number
    policy_m = _FM_THROTTLE_POLICY.search(full_text)
    throttle_policy = None
    throttle_speed_str = None
    if policy_m:
        fn_down, fn_up, pn_down, pn_up = policy_m.groups()
        throttle_policy = {
            "freedom_network": {"down_kbps": int(fn_down), "up_kbps": int(fn_up)},
            "partner_nationwide_us_mexico": {"down_kbps": int(pn_down), "up_kbps": int(pn_up)},
            "overage_fees": False,
            "resets": "end of current billing cycle",
            "source": "Freedom Mobile Unlimited Plans Data Policy (plan-page footnote)",
        }
        throttle_speed_str = (
            f"{fn_down} Kbps down / {fn_up} Kbps up on the Freedom network; "
            f"{pn_down} Kbps down / {pn_up} Kbps up on partner networks "
            f"(Nationwide, U.S. & Mexico)"
        )

    # page-level restricted student offer footnote, matched to its plan by GB
    student_m = _FM_STUDENT.search(full_text)
    student_info = None
    if student_m:
        s_price, s_base, s_credit, s_months, s_elig_plan = student_m.groups()
        gb_m = _FM_STUDENT_PLAN_GB.search(s_elig_plan)
        full_note_m = _FM_STUDENT_FULL.search(full_text)
        student_info = {
            "student_price": float(s_price),
            "base_after_dd": float(s_base),
            "credit": float(s_credit),
            "months": int(s_months),
            "dom_gb": float(gb_m.group(1)) if gb_m else None,
            "roam_gb": float(gb_m.group(2)) if gb_m else None,
            "full_text": re.sub(r"\s+", " ", full_note_m.group(0))[:700] if full_note_m else "",
        }

    seen: set[str] = set()
    drafts: list[dict] = []
    for card in cards:
        ctext = re.sub(r"\s+", " ", card.get_text(" ", strip=True))
        name_row = card.select_one("[data-testid='plan-card-v2-plan-name-row']")
        name_row_t = re.sub(r"\s+", " ", name_row.get_text(" ", strip=True)) if name_row else ""
        price_el = card.select_one("[data-testid='plan-monthly-price']")
        shown = _price_num("$" + price_el.get_text(strip=True)) if price_el else None
        ribbon = _fm_ribbon(card)

        review_src: dict[str, str] = {}
        auto: list[str] = []
        notes: list[str] = []
        plan: dict = {
            "external_id": "",
            "plan_type": "postpaid",
            "price_period": "monthly",
            "byod": True,
            "availability": "online",
        }

        def put(field, value, snippet=None):
            plan[field] = value
            auto.append(field)
            if snippet:
                review_src[field] = snippet

        # --- data: domestic (Canada-U.S.-Mexico) vs Roam Beyond, kept apart --
        dom = _FM_DOMESTIC.search(ctext)
        roam = _FM_ROAM.search(ctext)
        nm = _FM_NAME.search(name_row_t) or _FM_NAME.search(ctext)
        dom_gb = float(dom.group(1)) if dom else (float(nm.group(1)) if nm else None)
        if dom_gb is not None:
            put("data_base_gb", dom_gb, dom.group(0) if dom else name_row_t)
            put("data_full_speed_gb", dom_gb, dom.group(0) if dom else name_row_t)
            put("includes_us", True, "N GB data in Canada-U.S.-Mexico")
            put("includes_mexico", True, "N GB data in Canada-U.S.-Mexico")
            put("can_us_mex_note", "plan data is usable in Canada, the U.S. and Mexico", dom.group(0) if dom else None)
        if _FM_THROTTLE.search(ctext):
            put("data_unlimited", True, "Unlimited data at reduced speeds thereafter")
            plan["data_unlimited_is_full_speed"] = False
            plan["data_hard_cap"] = False
            if throttle_policy:
                # network-dependent -- a single number would misrepresent it, so the
                # summary string names both, and the exact figures live in attributes.
                put("throttle_speed", throttle_speed_str,
                    "Freedom Mobile Unlimited Plans Data Policy footnote")
                put("throttled_after_note",
                    "After the full-speed allowance: no overage fees, but reduced speed "
                    "until the end of the billing cycle -- up to 256 Kbps down / 128 Kbps "
                    "up on the Freedom network, or 128 Kbps down / 64 Kbps up on partner "
                    "networks (Nationwide, U.S. & Mexico).")
                plan.setdefault("attributes", {})["throttle_policy"] = throttle_policy
                put("overage_note",
                    "no overage fees (Freedom Unlimited Plans Data Policy) -- see "
                    "throttle_speed / attributes.throttle_policy for the exact "
                    "network-dependent reduced speeds")
            else:
                put("overage_note", "no hard cap: unlimited data at a reduced speed after the "
                    "full-speed allowance (speed not stated on the card)")
                notes.append(
                    "Freedom's 'Unlimited Plans Data Policy' footnote (with the exact "
                    "throttled Kbps by network) was not found on this capture -- "
                    "throttle_speed left null rather than guessing a single number."
                )
        roam_gb = None
        if roam:
            roam_gb = float(roam.group(1))
            put("international_roaming", True, roam.group(0))
            put("international_roaming_note",
                f"Roam Beyond: {roam.group(1)} GB/mo of data in {roam.group(2)} global "
                f"destinations -- a SEPARATE allowance from the "
                f"{dom_gb:g} GB Canada-U.S.-Mexico data" if dom_gb is not None else
                f"Roam Beyond: {roam.group(1)} GB/mo of data in {roam.group(2)} global destinations",
                roam.group(0))
            plan.setdefault("attributes", {})["roam_beyond_data_gb"] = roam_gb

        # --- network -------------------------------------------------
        # longest-first so "5G+" wins over "5G"; no trailing \b (Freedom follows it
        # with a superscript footnote char, which is not a word boundary)
        tech_m = re.search(r"(5G\+|5G|4G\s*LTE|LTE|4G)(?![A-Za-z])", name_row_t + " " + ctext, re.I)
        if tech_m:
            tech = re.sub(r"\s+", " ", tech_m.group(1)).upper()
            put("network_technology", tech, tech_m.group(0))
            plan["has_5g"] = tech.startswith("5G")

        # --- name (build the real Freedom style) --------------------
        if dom_gb is not None and roam_gb is not None:
            name = f"Total Freedom {dom_gb:g}GB + Roam Beyond {roam_gb:g}GB"
        elif dom_gb is not None:
            name = f"Total Freedom {dom_gb:g}GB"
        else:
            name = f"Total Freedom plan ({name_row_t})"
        put("plan_name", name, name_row_t or ctext[:80])
        ext = slugify(name)
        if ext in seen:
            continue
        seen.add(ext)
        plan["external_id"] = ext or f"freedom-plan-{len(drafts) + 1}"

        # --- price: shown = "with Digital Discount" (conditional) ---
        has_dd = bool(re.search(r"with Digital Discount", ctext, re.I))
        if shown is not None:
            if has_dd:
                put("autopay_price_cad", shown, "'$X /mo. with Digital Discount' on the card")
                put("autopay_discount_cad", _FM_DIGITAL_DISCOUNT, "Freedom footnote: '$5 monthly discount'")
                put("autopay_conditions",
                    "$5/mo Digital Discount -- requires Auto Pay (pre-authorized payments) "
                    "with a valid payment method on file AND redeeming the 'Digital "
                    "Discount' promo code via My Account. Not applied automatically.")
                put("autopay_required", True, "headline price is 'with Digital Discount'")
                # the discount is a stated flat $5 -> the unconditional price is shown + $5
                put("regular_price_cad", round(shown + _FM_DIGITAL_DISCOUNT, 2),
                    "card price + the stated $5 Digital Discount (Freedom does not print "
                    "the pre-discount number on the card -- verify against the footnotes)")
                plan.setdefault("attributes", {})["regular_price_basis"] = (
                    f"Derived, not printed on the card: the displayed 'with Digital "
                    f"Discount' price (${shown:g}/mo) plus Freedom's officially stated "
                    f"$5/mo Digital Discount (see the Digital Discount terms footnote). "
                    f"Freedom does not print the pre-discount price directly."
                )
                notes.append(
                    f"card shows ${shown:g}/mo 'with Digital Discount'; regular_price_cad "
                    f"set to ${shown + _FM_DIGITAL_DISCOUNT:g} (= shown + the stated $5 "
                    f"discount, see attributes.regular_price_basis). Confirm from Freedom's "
                    f"footnotes / a Digital-Discount-off view."
                )
            else:
                put("regular_price_cad", shown, "the only price shown on the card")

        # --- Back to School / offer ribbon -------------------------
        if ribbon and re.search(r"student", ribbon, re.I):
            put("eligibility_restricted", True, ribbon)
            put("eligibility_conditions",
                f"Freedom '{ribbon}' -- requires verified student eligibility. Confirm the "
                f"exact condition and any separate student price from the footnotes.")
        elif ribbon and re.search(r"exclusive|partner|invite|targeted|existing customer", ribbon, re.I):
            put("eligibility_restricted", True, ribbon)
            put("eligibility_conditions", f"Freedom restricted offer: '{ribbon}' -- verify eligibility.")
        elif ribbon:
            put("promo_name", ribbon, ribbon)
            plan["promo_expiry_known"] = False
            notes.append(
                f"card carries a '{ribbon}' ribbon but shows no separate regular price "
                f"and no end date -- verify from Freedom's footnotes whether this is a "
                f"time-limited promo price (set promo_price_cad + promo_ends_at) or just "
                f"a seasonal badge on the current price."
            )

        # --- calling / messaging ----------------------------------
        tt = re.search(r"[Uu]nlimited talk (?:&|and) text in ([^?.]+?)(?:\s*\?|\s*Plan price|$)", ctext)
        if tt:
            put("canada_wide_calling", True, "Unlimited talk & text in " + tt.group(1).strip())
            put("unlimited_text", True, "Unlimited talk & text in " + tt.group(1).strip())
            if re.search(r"global destinations", tt.group(1)):
                put("international_text", True, tt.group(1).strip())

        # --- Price Freeze Promise ---------------------------------
        conds = []
        if re.search(r"Price Freeze Promise", ctext):
            conds.append("Price Freeze Promise: Freedom will not raise the plan price")
        if conds:
            put("conditions", "; ".join(conds), " / ".join(conds))

        important_nulls = [
            f for f in (
                "regular_price_cad", "promo_price_cad", "promo_ends_at", "promo_expiry_known",
                "autopay_note", "activation_fee_cad", "contract_required", "throttle_speed",
                "data_bonus_gb", "data_promo_gb", "hotspot", "student_offer", "available_regions",
            ) if plan.get(f) in (None,) and f not in plan
        ]
        plan["_review"] = {
            "status": "draft-unreviewed",
            "confidence": "medium" if plan.get("regular_price_cad") is not None else "low",
            "auto_extracted": sorted(set(auto)),
            "check_these_nulls_against_the_page": important_nulls,
            "source_text": review_src,
            "price_notes": notes,
            "card_excerpt": ctext[:500],
            "warnings": [
                "REGION. Freedom shows regional pricing and defaults to Ontario. "
                "Confirm this capture was taken with British Columbia / a Metro "
                "Vancouver postal code selected -- see the page-level warnings.",
                "PRICE. The card price is 'with Digital Discount' (-$5/mo, requires "
                "Auto Pay + promo-code redemption) -> stored in autopay_price_cad. "
                "regular_price_cad = card price + $5 (the discount is a stated flat "
                "$5). If a card also has an 'OFFER' ribbon, check the footnotes for a "
                "separate promo price / end date.",
                "DATA. Domestic data (works in Canada-U.S.-Mexico) and the Roam Beyond "
                "allowance (120+ other countries) are SEPARATE -- never added. "
                "includes_us / includes_mexico are set because the card explicitly "
                "says 'data in Canada-U.S.-Mexico'. After the full-speed allowance, data "
                "continues at a reduced, NETWORK-DEPENDENT speed (data_unlimited=true, "
                "data_hard_cap=false) -- throttle_speed / attributes.throttle_policy hold "
                "both the Freedom-network and partner-network Kbps from Freedom's "
                "Unlimited Plans Data Policy footnote; never treat it as one flat number.",
                "A 'Student' / exclusive / targeted ribbon marks the plan "
                "eligibility_restricted -- kept in the catalogue, out of the default "
                "ranking.",
            ],
        }
        drafts.append(plan)

        # --- restricted post-secondary student variant (distinct plan, not a
        # replacement) -- only emitted when the footnote's GB matches this card ---
        if (
            student_info
            and dom_gb == student_info["dom_gb"]
            and roam_gb == student_info["roam_gb"]
            and plan.get("autopay_price_cad") == student_info["base_after_dd"]
        ):
            student_name = f"{name} (Post-Secondary Student Offer)"
            student_plan = {k: v for k, v in plan.items() if k != "_review"}
            student_plan["attributes"] = dict(plan.get("attributes") or {})
            student_plan["plan_name"] = student_name
            s_ext = slugify(student_name) or f"{plan['external_id']}-student"
            if s_ext in seen:
                s_ext = f"{plan['external_id']}-student"
            seen.add(s_ext)
            student_plan["external_id"] = s_ext
            student_plan["promo_price_cad"] = student_info["student_price"]
            student_plan["promo_name"] = "Post-Secondary Student Offer"
            student_plan["promo_duration_months"] = student_info["months"]
            student_plan["promo_expiry_known"] = False
            student_plan["promo_conditions"] = (
                f"Student price ${student_info['student_price']:g}/mo = the "
                f"${student_info['base_after_dd']:g}/mo Digital-Discount price less a "
                f"${student_info['credit']:g}/mo student offer credit for "
                f"{student_info['months']} months."
            )
            student_plan["promo_stacks_conditions"] = (
                "requires the Digital Discount (Auto Pay) AND verified post-secondary "
                "student eligibility"
            )
            student_plan["eligibility_restricted"] = True
            student_plan["eligibility_conditions"] = "Post-secondary student offer -- " + (
                student_info["full_text"] or "requires verified post-secondary student status"
            )
            student_plan["student_offer"] = True
            student_plan["attributes"]["student_offer_details"] = {
                "student_effective_price_cad": student_info["student_price"],
                "base_price_with_digital_discount_cad": student_info["base_after_dd"],
                "student_credit_cad": student_info["credit"],
                "duration_months": student_info["months"],
                "underlying_plan_external_id": plan["external_id"],
                "source": "Freedom Mobile plan-page footnote (Student Offer)",
            }
            student_plan["_review"] = {
                "status": "draft-unreviewed",
                "confidence": "medium",
                "auto_extracted": [
                    "promo_price_cad", "promo_duration_months", "promo_conditions",
                    "eligibility_restricted", "eligibility_conditions", "student_offer",
                ],
                "check_these_nulls_against_the_page": [],
                "source_text": {"eligibility_conditions": student_info["full_text"]},
                "price_notes": [
                    f"derived from the underlying '{name}' plan "
                    f"[{plan['external_id']}] -- this is a DISTINCT eligibility-gated "
                    f"variant; it does not replace or duplicate the ordinary plan."
                ],
                "card_excerpt": student_info["full_text"],
                "warnings": [
                    "RESTRICTED STUDENT VARIANT. eligibility_restricted=true -> excluded "
                    "from the default ranking. Preserves the full 175GB plan data, the "
                    "$45/mo student effective price (promo_price_cad), the 18-month "
                    "duration (promo_duration_months), and the eligibility conditions. "
                    "A future 'Best for Students' mode may include it once the user "
                    "confirms eligibility. Verify the full eligibility text against "
                    "Freedom's footnote before import.",
                ],
            }
            drafts.append(student_plan)

    if not drafts:
        raise DraftError("Freedom plan cards found but none yielded a usable plan.")
    return {"plans": drafts, "page_warnings": _page_warnings(soup, raw_html=html)}


# ---------------------------------------------------------------------------
_PROVIDER_BLOCK = {
    "bell": {
        "provider": {
            "slug": "bell", "display_name": "Bell", "network": "Bell",
            "plan_model": "postpaid", "homepage_url": "https://www.bell.ca/Mobility",
        },
        "source": {
            "url": "https://www.bell.ca/Mobility/Bring-Your-Own-Phone", "kind": "capture",
            "description": (
                "Bell official Bring-Your-Own-Phone plans page, captured by an operator "
                "for British Columbia. Primary capture = the 'Mobility only' tab "
                "(unconditional pricing); optional second capture = the 'With Streaming' "
                "tab (bundle pricing)."
            ),
        },
        "extractor": extract_bell_plans,
    },
    "koodo": {
        "provider": {
            "slug": "koodo", "display_name": "Koodo Mobile", "network": "TELUS",
            "plan_model": "postpaid", "homepage_url": "https://www.koodomobile.com/",
        },
        "source": {
            "url": "https://www.koodomobile.com/en/shop/mobility/plans/bring-your-own-phone",
            "kind": "capture",
            "description": (
                "Koodo Mobile official Bring-Your-Own-Phone plans page, captured by an "
                "operator for British Columbia."
            ),
        },
        "extractor": extract_koodo_plans,
    },
    "freedom-mobile": {
        "provider": {
            "slug": "freedom-mobile", "display_name": "Freedom Mobile",
            "network": "Freedom (Videotron)", "plan_model": "postpaid",
            "homepage_url": "https://www.freedommobile.ca/",
        },
        "source": {
            "url": "https://shop.freedommobile.ca/en-CA/plans",
            "kind": "capture",
            "description": (
                "Freedom Mobile official plans page (BYOP pricing), captured by an "
                "operator for British Columbia. The deeper /plans/bring-your-own-phone "
                "route is not a reliable public landing page; the stable top-level "
                "plans page is used as the official source."
            ),
        },
        "extractor": extract_freedom_plans,
    },
}


def build_draft_manifest(
    provider: str,
    capture_path: str | Path,
    *,
    streaming_capture_path: str | Path | None = None,
) -> dict:
    if provider not in _PROVIDER_BLOCK:
        raise DraftError(f"draft-manifest is only implemented for: {', '.join(_PROVIDER_BLOCK)}")
    spec = _PROVIDER_BLOCK[provider]
    p = Path(capture_path)
    if not p.exists():
        raise DraftError(f"capture not found: {p}")

    html = capture_to_html(p.read_bytes(), suffix=p.suffix)
    kwargs: dict = {}
    streaming_name = None
    if streaming_capture_path is not None:
        sp = Path(streaming_capture_path)
        if not sp.exists():
            raise DraftError(f"streaming capture not found: {sp}")
        kwargs["streaming_html"] = capture_to_html(sp.read_bytes(), suffix=sp.suffix)
        streaming_name = sp.name
    result = spec["extractor"](html, **kwargs)
    plans = result["plans"]

    return {
        "_draft": {
            "reviewed": False,
            "generated_by": DRAFT_TOOL_VERSION,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "capture_file": p.name,
            "secondary_capture_file": streaming_name,
            "plan_count": len(plans),
            "page_warnings": result.get("page_warnings", []),
            "instructions": (
                "AUTO-EXTRACTED DRAFT. The official capture is the source of truth. "
                "Open the page / the capture, check every plan and every value, fix "
                "anything wrong (price fields especially), fill nulls where the page "
                "is clear, then set \"reviewed\": true (or delete this _draft block). "
                "`metromobile import` refuses this file until then."
            ),
        },
        "provider": spec["provider"],
        "source": spec["source"],
        "plans": plans,
    }
