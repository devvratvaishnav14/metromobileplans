"""Public Mobile adapter -- intentionally not implemented.

publicmobile.ca sits entirely behind a Cloudflare "Just a moment..." anti-bot JS
challenge: every URL (home, /en/plans, /en/bc/plans, sitemap.xml) returns HTTP 403
`cf-mitigated: challenge`, including for the Googlebot UA. Retrieving it would mean
solving / bypassing an anti-bot protection or driving a headless browser -- both
explicitly out of scope for this project. The Internet Archive shows no recent
successful snapshots of the plan pages either (its crawler is blocked too).

Left here so the provider registry documents *why* it is absent.
"""

from __future__ import annotations

from .base import NormalizedPlan, SourceUnavailable

PARSER_VERSION = "public-mobile-unavailable"


class PublicMobileAdapter:
    slug = "public-mobile"
    display_name = "Public Mobile"
    network = "TELUS"
    plan_model = "prepaid"
    homepage_url = "https://www.publicmobile.ca/"
    source_url = "https://www.publicmobile.ca/en/plans"
    # Cloudflare blocks automated retrieval -> the realistic path is a controlled
    # official_manual import (a person views the page, captures it, transcribes it).
    source_mode = "official_manual"
    verification_method = "operator_manual_review"
    source_kind = "capture"
    source_description = (
        "Official plans page -- blocked by a Cloudflare anti-bot challenge; "
        "eligible only via a controlled official_manual import."
    )
    parser_version = PARSER_VERSION

    def fetch(self):  # pragma: no cover - not runnable by design
        raise SourceUnavailable(
            "Public Mobile is behind a Cloudflare anti-bot challenge; no legitimate "
            "public path to its current plan data. Not retrievable without bypassing "
            "anti-bot protection or using browser automation."
        )

    def parse(self, content: bytes) -> list[NormalizedPlan]:  # pragma: no cover
        raise SourceUnavailable("Public Mobile source is unavailable (see fetch()).")
