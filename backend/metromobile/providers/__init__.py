"""Provider registry. Add a carrier by dropping an adapter here."""

from __future__ import annotations

from .base import NormalizedPlan, ParseError, SecondaryAdapter, SourceUnavailable
from .chatr import ChatrAdapter
from .freedom_mobile import FreedomMobileAdapter
from .public_mobile import PublicMobileAdapter
from .whistleout import WhistleOutAdapter

_ADAPTERS = [ChatrAdapter, PublicMobileAdapter, FreedomMobileAdapter, WhistleOutAdapter]

REGISTRY = {cls.slug: cls for cls in _ADAPTERS}

# adapters wired to a working source, and which pipeline entrypoint they use
IMPLEMENTED = {"chatr", "whistleout"}
SECONDARY = {slug for slug, cls in REGISTRY.items() if issubclass(cls, SecondaryAdapter)}

__all__ = [
    "REGISTRY",
    "IMPLEMENTED",
    "SECONDARY",
    "NormalizedPlan",
    "ParseError",
    "SourceUnavailable",
    "get_adapter",
]


def get_adapter(slug: str):
    try:
        return REGISTRY[slug]()
    except KeyError:
        raise KeyError(
            f"Unknown provider {slug!r}. Known: {', '.join(sorted(REGISTRY))}"
        ) from None
