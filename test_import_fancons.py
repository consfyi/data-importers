#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "pytest",
#   "eviltransform",
#   "httpx",
#   "icalendar",
#   "googlemaps",
#   "PyICU==2.16.2",
#   "regex==2025.7.34",
# ]
# ///

"""Tests for import_fancons' ICU-based series IDs.

Run with `./test_import_fancons.py`.

PyICU and regex are pinned to the versions in import_fancons.py.lock, since
slugify runs through both. PyICU ships only as an sdist, so this test is also
the build check: when the runner image moves to an ICU release the pinned
PyICU doesn't support, this fails on the PR instead of the hourly import
failing on main.
"""

import os
import sys

import pytest

os.environ.setdefault("GOOGLE_MAPS_API_KEY", "unused")

import import_fancons


# Series IDs already in the data repo. The importer matches FanCons entries to
# existing series by slug, so a slug that drifts creates a duplicate series.
# The region is what the importer derives the transliteration language from.
@pytest.mark.parametrize(
    "name, region, expected",
    [
        ("Rügen Furcon", "DE", "ruegen-furcon"),
        ("Futrołajki", "PL", "futrolajki"),
        ("Pörröcon", "FI", "porrocon"),
        ("ČeSFuR", "CZ", "cesfur"),
        ("Ainmhícon", "IE", "ainmhicon"),
        ("Fur-Eh!", "CA", "fur-eh"),
    ],
)
def test_series_id_matches_existing_data(name, region, expected):
    locale = import_fancons.guess_language_for_region(region)
    assert import_fancons.slugify(name, locale) == expected


def test_ampersand_becomes_and():
    locale = import_fancons.guess_language_for_region("US")
    assert import_fancons.slugify("Fur & Loathing", locale) == "fur-and-loathing"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", *sys.argv[1:]]))
