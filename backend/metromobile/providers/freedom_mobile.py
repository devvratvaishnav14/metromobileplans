"""Freedom Mobile adapter -- intentionally not implemented (yet).

The plans page (shop.freedommobile.ca/en-CA/plans) is a client-rendered SPA; the
curated plan list is not in the server HTML. Freedom's only public data source is
the DSL API its own page config points at:

    GET  https://api.freedommobile.ca/api/v1/plans          (200, no auth)
    POST https://api.freedommobile.ca/api/v1/shop/plans     (200, no auth)

Both return an unfiltered ~415-entry internal ratebook: discontinued plans, dozens
of near-duplicate internal variants (Care / Prime / Choice / Select / Limited),
one row literally named "...Talk incorrect", an unreliable data field, and
contradictory availability flags. The logic that picks the ~10 currently-marketed
consumer plans out of that runs client-side and is not publicly exposed.

Extracting "current plans" from the ratebook would require guessing which internal
variant is live -- i.e. fabrication by selection -- so this adapter stays a stub
until we do Freedom properly (browser capture, or a deeper integration).
"""

from __future__ import annotations

from .base import NormalizedPlan, SourceUnavailable

PARSER_VERSION = "freedom-mobile-deferred"


class FreedomMobileAdapter:
    slug = "freedom-mobile"
    display_name = "Freedom Mobile"
    network = "Freedom (Videotron/Quebecor)"
    plan_model = "mixed"
    homepage_url = "https://www.freedommobile.ca/"
    source_url = "https://shop.freedommobile.ca/en-CA/plans"
    # No automated path to the curated list -> eligible only via official_manual import.
    source_mode = "official_manual"
    verification_method = "operator_manual_review"
    source_kind = "capture"
    source_description = (
        "Official plans page. Public data is only an unfiltered internal ratebook API; "
        "the curated consumer list is eligible only via a controlled official_manual import."
    )
    parser_version = PARSER_VERSION

    def fetch(self):  # pragma: no cover - not runnable by design
        raise SourceUnavailable(
            "Freedom Mobile's only public data is an unfiltered internal ratebook "
            "(~415 rows incl. discontinued/duplicate variants). No safe public path "
            "to the current consumer plan list. Deferred."
        )

    def parse(self, content: bytes) -> list[NormalizedPlan]:  # pragma: no cover
        raise SourceUnavailable("Freedom Mobile source is unavailable (see fetch()).")
