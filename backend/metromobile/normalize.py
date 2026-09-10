"""Pure helpers for turning provider strings into normalized values.

These never invent data: an unparseable input returns ``None`` (or ``unlimited``
only when the text literally says so).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUM_UNIT_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>gb|mb|tb|g|m)\b",
    re.IGNORECASE,
)
_UNLIMITED_RE = re.compile(r"\bunlimited\b", re.IGNORECASE)


@dataclass(frozen=True)
class DataAmount:
    gb: float | None
    unlimited: bool | None  # True/False when known, None when the source is silent


def parse_data_amount(text: str | None) -> DataAmount:
    """'10 GB' -> 10.0 ; '512 MB' / '512MB' -> 0.5 ; 'Unlimited' -> unlimited ;
    '' / None / junk -> unknown (all None)."""
    if text is None:
        return DataAmount(None, None)
    s = text.strip()
    if not s:
        return DataAmount(None, None)
    if _UNLIMITED_RE.search(s):
        return DataAmount(None, True)
    m = _NUM_UNIT_RE.search(s)
    if not m:
        return DataAmount(None, None)
    num = float(m.group("num"))
    unit = m.group("unit").lower()
    if unit in ("mb", "m"):
        gb = num / 1024.0
    elif unit in ("tb",):
        gb = num * 1024.0
    else:  # gb, g
        gb = num
    # round to a sane precision (0.5 GB stays 0.5, 512 MB -> 0.5)
    return DataAmount(round(gb, 4), False)


def parse_price(value: object) -> float | None:
    """Accepts a number or a string like '$35', '35.00', '35/mo'. Returns a
    non-negative float, or None if it can't be read as a price."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if value >= 0 else None
    if isinstance(value, str):
        m = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
        if m:
            f = float(m.group(0))
            return f if f >= 0 else None
    return None


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    s = " ".join(value.split()).strip()
    return s or None


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
