from __future__ import annotations

import pytest

from metromobile.normalize import parse_data_amount, parse_price


@pytest.mark.parametrize(
    "text, gb, unlimited",
    [
        ("10 GB", 10.0, False),
        ("0.5 GB", 0.5, False),
        ("512 MB", 0.5, False),
        ("512MB", 0.5, False),
        ("1 TB", 1024.0, False),
        ("Unlimited", None, True),
        ("unlimited data", None, True),
        ("", None, None),
        (None, None, None),
        ("talk & text", None, None),
    ],
)
def test_parse_data_amount(text, gb, unlimited):
    d = parse_data_amount(text)
    assert d.gb == gb
    assert d.unlimited is unlimited


@pytest.mark.parametrize(
    "value, expected",
    [
        (35, 35.0),
        (35.0, 35.0),
        ("$35", 35.0),
        ("35/mo", 35.0),
        ("1,234.5", 1234.5),
        (-5, None),
        ("free", None),
        (None, None),
        (True, None),
    ],
)
def test_parse_price(value, expected):
    assert parse_price(value) == expected
