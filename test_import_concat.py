#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "pytest",
#   "httpx",
#   "googlemaps",
#   "whenever==0.8.8",
# ]
# ///

"""Tests for import_concat's dedup and placeholder handling.

Run with `./test_import_concat.py`.

whenever is pinned to the version in import_concat.py.lock: later versions
drop `OffsetDateTime.parse_common_iso`, so an unpinned test would exercise an
API the importer never runs against.
"""

import copy
import sys

import pytest
import whenever

import import_concat

TODAY = whenever.Date(2026, 8, 10)


def convention(
    long_name,
    start,
    end,
    venue="Durham Convention Center",
    domain="reg.bewhiskeredcon.org",
):
    """A ConCat /api/config convention entry, in the shape the importer reads."""
    return {
        "longName": long_name,
        "domain": domain,
        "startAt": f"{start}T04:00:00.000Z",
        "endAt": f"{end}T04:00:00.000Z",
        "venue": venue,
    }


# The two conventions reg.bewhiskeredcon.org actually served on 2026-08-10.
# The 2027 entry carries the 2026 edition's dates and a placeholder venue
# because its real dates aren't announced yet.
BEWHISKERED_CONVENTIONS = [
    convention("Bewhiskered 2027", "2026-04-02", "2026-04-05", venue="Coming Soon"),
    convention(
        "Bewhiskered 2026",
        "2026-04-02",
        "2026-04-05",
        domain="2026.reg.bewhiskeredcon.org",
    ),
]

BEWHISKERED_SERIES = {
    "name": "Bewhiskered",
    "events": [
        {
            "id": "bewhiskered-2026",
            "name": "Bewhiskered 2026",
            "url": "https://bewhiskeredcon.org",
            "startDate": "2026-04-02",
            "endDate": "2026-04-05",
            "venue": "Durham Convention Center",
            "address": "301 W Morgan St, Durham, NC 27701, United States",
            "locale": "en-US",
            "latLng": [35.9975142, -78.90234679999999],
        },
        {
            "id": "bewhiskered-2025",
            "name": "Bewhiskered 2025",
            "url": "https://bewhiskeredcon.org",
            "startDate": "2025-04-03",
            "endDate": "2025-04-06",
            "venue": "Durham Convention Center",
            "address": "301 W Morgan St, Durham, NC 27701, United States",
            "locale": "en-US",
            "latLng": [35.9975142, -78.90234679999999],
        },
    ],
}


def series_with_2027(start="2027-04-01", end="2027-04-04"):
    """BEWHISKERED_SERIES with a stored 2027 edition in front."""
    series = copy.deepcopy(BEWHISKERED_SERIES)
    series["events"].insert(
        0,
        {
            **BEWHISKERED_SERIES["events"][0],
            "id": "bewhiskered-2027",
            "name": "Bewhiskered 2027",
            "startDate": start,
            "endDate": end,
        },
    )
    return series


def run(series, conventions, geocode=None, series_id="bewhiskered"):
    """Import `conventions` into a copy of `series`, returning the copy."""
    series = copy.deepcopy(series)
    venue_details = {
        e["venue"]: {k: v for k, v in e.items() if k in {"address", "latLng"}}
        for e in series["events"]
    }

    def unexpected_geocode(venue, country):
        raise AssertionError(f"geocoded unexpectedly: {venue!r}")

    for c in conventions:
        import_concat.apply_convention(
            series,
            series_id,
            c,
            "US",
            "https://bewhiskeredcon.org",
            venue_details,
            geocode or unexpected_geocode,
            TODAY,
        )
    return series


def test_bewhiskered_import_is_idempotent():
    """The regression: this run produced [2026, 2027, 2026, 2025] on main."""
    result = run(BEWHISKERED_SERIES, BEWHISKERED_CONVENTIONS)

    assert [e["id"] for e in result["events"]] == [
        "bewhiskered-2026",
        "bewhiskered-2025",
    ]
    assert result["events"] == BEWHISKERED_SERIES["events"]


def test_repeated_imports_do_not_accumulate():
    result = run(BEWHISKERED_SERIES, BEWHISKERED_CONVENTIONS * 3)

    ids = [e["id"] for e in result["events"]]
    assert len(ids) == len(set(ids)), ids


def test_live_2027_entry_is_never_geocoded():
    """The live 2027 entry is rejected by the dates guard, before its venue.

    Pins the whole live payload, not the venue guard on its own -- that guard
    is isolated by test_placeholder_venue_skips_a_convention_whose_dates_agree.
    """
    run(BEWHISKERED_SERIES, [BEWHISKERED_CONVENTIONS[0]])


def test_dedups_when_id_year_disagrees_with_start_date_year():
    """The dedup must not depend on ids being ordered by startDate.

    The stored bewhiskered-2027 sits where the ordering scan lands for 2026
    dates, so a probe of that one slot finds the wrong event and writes a
    third: the buggy code yields [2026, 2027, 2026] here.
    """
    series = {
        "name": "Bewhiskered",
        "events": [
            {
                **BEWHISKERED_SERIES["events"][0],
                "id": "bewhiskered-2027",
                "name": "Bewhiskered 2027",
            },
            BEWHISKERED_SERIES["events"][0],
        ],
    }

    result = run(series, [convention("Bewhiskered 2026", "2026-04-02", "2026-04-05")])

    assert [e["id"] for e in result["events"]] == [
        "bewhiskered-2027",
        "bewhiskered-2026",
    ]


def test_duplicate_ids_already_in_the_file_are_healed():
    """Ids are unique per the schema, so every copy an earlier run wrote goes."""
    series = {
        "name": "Bewhiskered",
        "events": [
            BEWHISKERED_SERIES["events"][0],
            copy.deepcopy(BEWHISKERED_SERIES["events"][0]),
            BEWHISKERED_SERIES["events"][1],
        ],
    }

    result = run(series, [convention("Bewhiskered 2026", "2026-04-02", "2026-04-05")])

    assert [e["id"] for e in result["events"]] == [
        "bewhiskered-2026",
        "bewhiskered-2025",
    ]


def test_healing_duplicates_keeps_curated_fields():
    """The copy an earlier run wrote comes first; the curated one carries keyDates.

    Collapsing to the first copy on its own would drop keyDates permanently:
    it feeds the keydates worker and is not re-derivable.
    """
    curated = {
        **BEWHISKERED_SERIES["events"][0],
        "keyDates": {"registration": "2025-11-01"},
        "canceled": True,
    }
    series = {
        "name": "Bewhiskered",
        "events": [
            copy.deepcopy(BEWHISKERED_SERIES["events"][0]),
            {
                **BEWHISKERED_SERIES["events"][0],
                "id": "bewhiskered-2027",
                "name": "Bewhiskered 2027",
            },
            curated,
            BEWHISKERED_SERIES["events"][1],
        ],
    }

    result = run(series, [convention("Bewhiskered 2026", "2026-04-02", "2026-04-05")])

    assert [e["id"] for e in result["events"]] == [
        "bewhiskered-2026",
        "bewhiskered-2027",
        "bewhiskered-2025",
    ]
    survivor = result["events"][0]
    assert survivor["keyDates"] == {"registration": "2025-11-01"}
    assert survivor["canceled"] is True


def test_healing_three_copies_collapses_them_all():
    """Deleting forward would remove shifted indexes and eat other editions."""
    curated = {
        **BEWHISKERED_SERIES["events"][0],
        "keyDates": {"registration": "2025-11-01"},
    }
    series = {
        "name": "Bewhiskered",
        "events": [
            copy.deepcopy(BEWHISKERED_SERIES["events"][0]),
            {
                **BEWHISKERED_SERIES["events"][0],
                "id": "bewhiskered-2027",
                "name": "Bewhiskered 2027",
            },
            copy.deepcopy(BEWHISKERED_SERIES["events"][0]),
            BEWHISKERED_SERIES["events"][1],
            curated,
        ],
    }

    result = run(series, [convention("Bewhiskered 2026", "2026-04-02", "2026-04-05")])

    assert [e["id"] for e in result["events"]] == [
        "bewhiskered-2026",
        "bewhiskered-2027",
        "bewhiskered-2025",
    ]
    # The third copy is the curated one, so stopping after the second loses it.
    assert result["events"][0]["keyDates"] == {"registration": "2025-11-01"}


def test_healing_keeps_falsy_curated_fields():
    """`canceled: false` and `attendance: 0` must survive the collapse too."""
    series = {
        "name": "Bewhiskered",
        "events": [
            copy.deepcopy(BEWHISKERED_SERIES["events"][0]),
            {
                **BEWHISKERED_SERIES["events"][0],
                "canceled": False,
                "attendance": 0,
                "translations": {"ja": "ビウィスカード"},
            },
        ],
    }

    result = run(series, [convention("Bewhiskered 2026", "2026-04-02", "2026-04-05")])

    survivor = result["events"][0]
    assert survivor["canceled"] is False
    assert survivor["attendance"] == 0
    assert survivor["translations"] == {"ja": "ビウィスカード"}


def test_healing_keeps_the_survivors_value_and_warns_on_a_conflict(caplog):
    """Two copies can't be merged, so the discard has to be visible in the log."""
    series = {
        "name": "Bewhiskered",
        "events": [
            {**BEWHISKERED_SERIES["events"][0], "attendance": 1200},
            {**BEWHISKERED_SERIES["events"][0], "attendance": 50},
        ],
    }

    with caplog.at_level("WARNING"):
        result = run(
            series, [convention("Bewhiskered 2026", "2026-04-02", "2026-04-05")]
        )

    assert result["events"][0]["attendance"] == 1200
    assert [m for m in caplog.messages if "disagree on attendance" in m]


def stub_geocode(venue, country):
    """The Durham Armory result, for tests that only care that a venue moved."""
    return {
        "address": "220 Foster St, Durham, NC 27701, United States",
        "latLng": [35.9960153, -78.9006756],
    }


def test_replaced_event_keeps_curated_fields():
    """Hand-curated fields must survive the delete-and-recreate path.

    `canceled` is the exception, covered by
    test_canceled_is_dropped_when_a_guessed_row_is_upgraded.
    """
    series = copy.deepcopy(BEWHISKERED_SERIES)
    series["events"][0] = {
        **series["events"][0],
        "sources": ["guessed"],
        "keyDates": {"registration": "2025-11-01"},
        "attendance": 1200,
        "translations": {"ja": "ビウィスカード"},
    }

    result = run(
        series,
        [
            convention(
                "Bewhiskered 2026", "2026-04-02", "2026-04-05", venue="Durham Armory"
            )
        ],
        geocode=stub_geocode,
    )

    new = result["events"][0]
    assert new["venue"] == "Durham Armory"
    assert new["keyDates"] == {"registration": "2025-11-01"}
    assert new["attendance"] == 1200
    assert new["translations"] == {"ja": "ビウィスカード"}
    # The fancons.com -> ConCat upgrade drops `sources` deliberately.
    assert "sources" not in new


def test_a_non_first_event_is_recreated_in_place():
    """The replacement goes back where it was, not to the front of the list."""
    series = copy.deepcopy(BEWHISKERED_SERIES)
    series["events"][1] = {**series["events"][1], "sources": ["guessed"]}

    result = run(
        series,
        [
            convention(
                "Bewhiskered 2025", "2025-04-03", "2025-04-06", venue="Durham Armory"
            )
        ],
        geocode=stub_geocode,
    )

    assert [e["id"] for e in result["events"]] == [
        "bewhiskered-2026",
        "bewhiskered-2025",
    ]
    assert result["events"][1]["venue"] == "Durham Armory"


def test_recreated_event_does_not_jump_an_earlier_edition_of_the_same_year():
    """Two editions in one calendar year exist; a rewrite keeps its own slot."""
    series = {
        "name": "Bewhiskered",
        "events": [
            {
                **BEWHISKERED_SERIES["events"][0],
                "id": "bewhiskered-2027",
                "name": "Bewhiskered 2027",
                "startDate": "2026-12-28",
                "endDate": "2026-12-30",
            },
            {
                **BEWHISKERED_SERIES["events"][0],
                "startDate": "2026-05-01",
                "endDate": "2026-05-03",
                "sources": ["guessed"],
            },
        ],
    }

    result = run(
        series,
        [
            convention(
                "Bewhiskered 2026", "2026-05-01", "2026-05-03", venue="Durham Armory"
            )
        ],
        geocode=stub_geocode,
    )

    assert [e["id"] for e in result["events"]] == [
        "bewhiskered-2027",
        "bewhiskered-2026",
    ]
    assert result["events"][1]["venue"] == "Durham Armory"


def test_canceled_is_dropped_when_a_guessed_row_is_upgraded():
    """`canceled` comes from fancons.com's iCal STATUS, not from a human.

    Keeping it across the upgrade leaves the con cancelled while ConCat is
    listing registration, with `sources` stripped and no way to clear it.
    """
    for sources in (["guessed"], ["fancons.com"]):
        series = copy.deepcopy(BEWHISKERED_SERIES)
        series["events"][0] = {
            **series["events"][0],
            "sources": sources,
            "canceled": True,
            "keyDates": {"registration": "2025-11-01"},
        }

        result = run(
            series,
            [
                convention(
                    "Bewhiskered 2026",
                    "2026-04-02",
                    "2026-04-05",
                    venue="Durham Armory",
                )
            ],
            geocode=stub_geocode,
        )

        new = result["events"][0]
        assert "canceled" not in new, sources
        # The genuinely curated fields are untouched by that.
        assert new["keyDates"] == {"registration": "2025-11-01"}


def test_falsy_curated_fields_survive_the_recreate_path():
    """`canceled: false` and `attendance: 0` are values, not absences.

    Dropping them is schema-valid, so only an identity assert catches it.
    """
    series = series_with_2027(start="2026-12-30", end="2026-12-31")
    series["events"][0] = {
        **series["events"][0],
        "id": "bewhiskered-2026",
        "name": "Bewhiskered 2026",
        "canceled": False,
        "attendance": 0,
    }
    del series["events"][1]

    result = run(
        series,
        [
            convention(
                "Bewhiskered 2026", "2026-12-30", "2027-01-02", venue="Durham Armory"
            )
        ],
        geocode=stub_geocode,
    )

    new = result["events"][0]
    assert new["venue"] == "Durham Armory"
    assert new["canceled"] is False
    assert new["attendance"] == 0


def test_new_edition_is_inserted_in_descending_date_order():
    result = run(
        BEWHISKERED_SERIES,
        [convention("Bewhiskered 2027", "2027-04-01", "2027-04-04")],
    )

    assert [e["id"] for e in result["events"]] == [
        "bewhiskered-2027",
        "bewhiskered-2026",
        "bewhiskered-2025",
    ]
    new = result["events"][0]
    assert new["venue"] == "Durham Convention Center"


def test_older_edition_is_inserted_last():
    """The insertion point is scanned for, not assumed to be the front."""
    result = run(
        BEWHISKERED_SERIES,
        [convention("Bewhiskered 2024", "2024-04-05", "2024-04-08")],
    )

    assert [e["id"] for e in result["events"]] == [
        "bewhiskered-2026",
        "bewhiskered-2025",
        "bewhiskered-2024",
    ]


def test_new_edition_inherits_url_and_age_restriction_from_its_neighbour():
    """A new edition takes the series' real url, not the derived default."""
    series = copy.deepcopy(BEWHISKERED_SERIES)
    for e in series["events"]:
        e["url"] = "https://bewhiskeredcon.com"
    series["events"][0]["ageRestriction"] = "18+"

    result = run(series, [convention("Bewhiskered 2027", "2027-04-01", "2027-04-04")])

    new = result["events"][0]
    assert new["url"] == "https://bewhiskeredcon.com"
    assert new["ageRestriction"] == "18+"


def test_guessed_event_is_replaced_with_geocoded_details():
    """A placeholder row from another importer gets real details, same url."""
    series = copy.deepcopy(BEWHISKERED_SERIES)
    series["events"][0] = {
        **series["events"][0],
        "sources": ["guessed"],
        "url": "https://bewhiskeredcon.com",
        "ageRestriction": "18+",
        "venue": "Somewhere In Durham",
        "address": "Durham, NC, United States",
        "latLng": [36.0, -78.9],
    }

    def geocode(venue, country):
        assert venue == "Durham Armory"
        return {
            "address": "220 Foster St, Durham, NC 27701, United States",
            "latLng": [35.9960153, -78.9006756],
        }

    result = run(
        series,
        [
            convention(
                "Bewhiskered 2026", "2026-04-02", "2026-04-05", venue="Durham Armory"
            )
        ],
        geocode=geocode,
    )

    # The full list: replacing must delete the old row, not just insert a new one.
    assert [e["id"] for e in result["events"]] == [
        "bewhiskered-2026",
        "bewhiskered-2025",
    ]
    new = result["events"][0]
    assert new["venue"] == "Durham Armory"
    assert new["address"] == "220 Foster St, Durham, NC 27701, United States"
    assert new["latLng"] == [35.9960153, -78.9006756]
    assert new["url"] == "https://bewhiskeredcon.com"
    assert new["ageRestriction"] == "18+"
    assert "sources" not in new


def test_announced_dates_update_an_existing_future_event():
    result = run(
        series_with_2027(),
        [convention("Bewhiskered 2027", "2027-04-08", "2027-04-11")],
    )

    assert result["events"][0]["startDate"] == "2027-04-08"
    assert result["events"][0]["endDate"] == "2027-04-11"


def test_announced_dates_update_an_event_whose_venue_is_still_a_placeholder():
    """New dates land before the venue is announced -- keep them, not the venue."""
    result = run(
        series_with_2027(),
        [
            convention(
                "Bewhiskered 2027", "2027-05-06", "2027-05-09", venue="Coming Soon"
            )
        ],
    )

    assert result["events"][0]["startDate"] == "2027-05-06"
    assert result["events"][0]["endDate"] == "2027-05-09"
    assert result["events"][0]["venue"] == "Durham Convention Center"


def test_announced_dates_update_an_event_whose_year_moved_but_venue_has_not():
    """The year-changed path must publish dates too, not stall on the venue.

    ConCat announces "2026-12-30 - 2027-01-02, venue TBA" while the stored
    event still carries the April dates it was guessed with.
    """
    result = run(
        BEWHISKERED_SERIES,
        [convention("Bewhiskered 2026", "2026-12-30", "2027-01-02", venue="TBA")],
    )

    assert [e["id"] for e in result["events"]] == [
        "bewhiskered-2026",
        "bewhiskered-2025",
    ]
    assert result["events"][0]["startDate"] == "2026-12-30"
    assert result["events"][0]["endDate"] == "2027-01-02"
    # The last known real venue stays: only the dates were announced.
    assert result["events"][0]["venue"] == "Durham Convention Center"


def test_past_dates_do_not_rewrite_an_event_whose_year_moved():
    """Same path, but the dates already happened, so they are not news."""
    result = run(
        BEWHISKERED_SERIES,
        [convention("Bewhiskered 2025", "2024-12-30", "2025-01-02", venue="TBA")],
    )

    assert result["events"][1]["startDate"] == "2025-04-03"
    assert result["events"][1]["endDate"] == "2025-04-06"


def test_past_event_dates_are_not_rewritten():
    """A con that already happened keeps the dates it actually ran on."""
    result = run(
        BEWHISKERED_SERIES,
        [convention("Bewhiskered 2026", "2026-04-09", "2026-04-12")],
    )

    assert result["events"][0]["startDate"] == "2026-04-02"
    assert result["events"][0]["endDate"] == "2026-04-05"


def test_dates_of_a_con_in_progress_are_not_rewritten():
    """Both ends must be in the future: a con already under way keeps its dates."""
    series = series_with_2027(start="2026-08-01", end="2026-08-04")
    series["events"][0]["id"] = "bewhiskered-2026"
    series["events"][0]["name"] = "Bewhiskered 2026"
    del series["events"][1]

    result = run(
        series,
        [convention("Bewhiskered 2026", "2026-08-09", "2026-08-12")],
    )

    assert result["events"][0]["startDate"] == "2026-08-01"
    assert result["events"][0]["endDate"] == "2026-08-04"


def test_a_new_end_year_recreates_the_event():
    """The stored end year is checked too, not just the start year."""
    series = series_with_2027(start="2026-12-30", end="2026-12-31")
    series["events"][0]["id"] = "bewhiskered-2026"
    series["events"][0]["name"] = "Bewhiskered 2026"
    del series["events"][1]

    result = run(
        series,
        [
            convention(
                "Bewhiskered 2026", "2026-12-30", "2027-01-02", venue="Durham Armory"
            )
        ],
        geocode=lambda venue, country: {
            "address": "220 Foster St, Durham, NC 27701, United States",
            "latLng": [35.9960153, -78.9006756],
        },
    )

    assert result["events"][0]["id"] == "bewhiskered-2026"
    assert result["events"][0]["endDate"] == "2027-01-02"
    # Recreated, not just date-updated in place: the venue moved too.
    assert result["events"][0]["venue"] == "Durham Armory"


def test_placeholder_venue_skips_a_convention_whose_dates_agree():
    """Isolates the venue guard: only it rejects this new, unstored edition."""
    result = run(
        BEWHISKERED_SERIES,
        [
            convention(
                "Bewhiskered 2027", "2027-04-01", "2027-04-04", venue="Coming Soon"
            )
        ],
    )

    assert result["events"] == BEWHISKERED_SERIES["events"]


def test_disagreeing_year_skips_a_convention_with_a_real_venue():
    """Isolates the dates guard: the venue here is a real, geocodable place."""
    result = run(
        BEWHISKERED_SERIES,
        [convention("Bewhiskered 2027", "2026-04-02", "2026-04-05")],
    )

    assert result["events"] == BEWHISKERED_SERIES["events"]


@pytest.mark.parametrize(
    "venue",
    [
        "Coming Soon",
        "  coming soon  ",
        "TBA",
        "tbd",
        "To Be Announced",
        "To Be Determined",
        "To Be Confirmed",
        "None",
        "Unknown",
        "N/A",
        "T.B.A.",
        "Coming  Soon",
        "TBA (venue)",
        "Venue TBD",
        "-",
        "",
        None,
    ],
)
def test_placeholder_venues(venue):
    assert import_concat.is_placeholder_venue(venue)


@pytest.mark.parametrize(
    "venue",
    [
        "Durham Convention Center",
        "Tbilisi Convention Hall",
        "NA Center",
        "Coming Soon Hall",
        "Unknown Fields Pavilion",
    ],
)
def test_real_venues(venue):
    assert not import_concat.is_placeholder_venue(venue)


def test_skip_warnings_are_annotated_on_github_actions(monkeypatch, caplog):
    """A con that quietly stops importing should surface as a run annotation."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    with caplog.at_level("WARNING"):
        run(BEWHISKERED_SERIES, [BEWHISKERED_CONVENTIONS[0]])

    assert [m for m in caplog.messages if m.startswith("::warning::")]


def test_warn_skip_strips_newlines_and_bounds_the_message(caplog):
    """`::warning::` is parsed by Actions, so upstream text can't carry newlines.

    A `longName` of "Con 2026\\n::stop-commands::x" otherwise suppresses every
    later workflow command in the job, including the failed-source report.
    """
    with caplog.at_level("WARNING"):
        import_concat.warn_skip("skipping\r\n::stop-commands::x " + "y" * 10_000)

    (message,) = caplog.messages
    assert "\n" not in message and "\r" not in message
    assert len(message) <= import_concat.MAX_WARNING_LENGTH


def test_upstream_strings_are_truncated_before_they_are_logged(caplog):
    """An 8 MB venue must not become 8 MB of run log."""
    with caplog.at_level("WARNING"):
        run(
            BEWHISKERED_SERIES,
            [
                convention(
                    "Bewhiskered " + "x" * 100_000,
                    "2027-04-01",
                    "2027-04-04",
                    venue="V" * 100_000,
                )
            ],
        )

    assert caplog.messages
    for message in caplog.messages:
        assert len(message) <= import_concat.MAX_WARNING_LENGTH


@pytest.mark.parametrize("on_actions", [False, True])
def test_the_bound_holds_with_the_actions_prefix(caplog, monkeypatch, on_actions):
    """The prefix counts toward the bound.

    Truncating the message before prefixing puts the line over the limit only
    when GITHUB_ACTIONS is set -- i.e. never on the machine where anyone runs
    the tests, and always in CI.
    """
    if on_actions:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
    else:
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    with caplog.at_level("WARNING"):
        import_concat.warn_skip("y" * 10_000)

    (message,) = caplog.messages
    assert message.startswith("::warning::") is on_actions
    assert len(message) <= import_concat.MAX_WARNING_LENGTH


def test_an_ungeocodable_venue_does_not_crash_the_next_run():
    """A stored event with no address leaves {} in the cache main() rebuilds."""
    series = copy.deepcopy(BEWHISKERED_SERIES)
    # What the None-filter writes when the geocoder returned no prediction.
    for e in series["events"]:
        del e["address"]
        del e["latLng"]

    result = run(
        series,
        [convention("Bewhiskered 2027", "2027-04-01", "2027-04-04")],
    )

    new = result["events"][0]
    assert new["id"] == "bewhiskered-2027"
    assert "address" not in new and "latLng" not in new


def test_a_neighbour_without_a_url_falls_back_to_the_derived_one():
    """One malformed stored row must not abort the rest of the series."""
    series = copy.deepcopy(BEWHISKERED_SERIES)
    del series["events"][0]["url"]

    result = run(series, [convention("Bewhiskered 2027", "2027-04-01", "2027-04-04")])

    assert result["events"][0]["url"] == "https://bewhiskeredcon.org"


def test_sources_survive_a_year_change_but_not_the_guess_upgrade():
    """Only the fancons/guessed upgrade is meant to drop attribution."""
    series = copy.deepcopy(BEWHISKERED_SERIES)
    series["events"][0]["sources"] = ["bsky"]

    moved = run(
        series,
        [convention("Bewhiskered 2026", "2026-12-30", "2027-01-02")],
    )
    assert moved["events"][0]["sources"] == ["bsky"]

    upgraded = run(
        {
            "name": "Bewhiskered",
            "events": [{**BEWHISKERED_SERIES["events"][0], "sources": ["guessed"]}],
        },
        [convention("Bewhiskered 2026", "2026-04-02", "2026-04-05")],
    )
    assert "sources" not in upgraded["events"][0]


def test_over_long_venue_is_a_placeholder_at_the_boundary():
    """Fails in milliseconds if the cap goes, where the input below would hang."""
    over = "x" * (import_concat.MAX_VENUE_LENGTH + 1)
    assert import_concat.is_placeholder_venue(over)
    assert not import_concat.is_placeholder_venue(over[:-1])


def test_pathological_venue_is_a_placeholder():
    """Runs of "(" are quadratic in the bracket substitution, so cap first.

    An upstream host controls this string; unbounded it stalls the whole
    scheduled import. Over the cap it is not a venue name, so it is never
    geocoded either.
    """
    assert import_concat.is_placeholder_venue("(" * 20_000)
    assert import_concat.is_placeholder_venue("Durham Convention Center" * 100)


def test_placeholder_dates_detection():
    assert import_concat.has_placeholder_dates("Bewhiskered 2027", 2026, 2026)
    assert not import_concat.has_placeholder_dates("Bewhiskered 2026", 2026, 2026)
    # No year in the name means nothing to disagree with.
    assert not import_concat.has_placeholder_dates("NCAS", 2026, 2026)
    # Trailing whitespace must not hide the year from the guard.
    assert import_concat.has_placeholder_dates("Bewhiskered 2027 ", 2026, 2026)
    # An ordinal edition number is not a year.
    assert not import_concat.has_placeholder_dates("Furvester 7", 2026, 2026)


def test_year_spanning_con_named_for_the_year_it_ends_in():
    """new-years-furry-ball-2026 runs 2025-12-30 - 2026-01-01 and is real."""
    assert not import_concat.has_placeholder_dates(
        "New Year's Furry Ball 2026", 2025, 2026
    )

    result = run(
        BEWHISKERED_SERIES,
        [convention("Bewhiskered 2027", "2026-12-30", "2027-01-01")],
    )

    assert result["events"][0]["id"] == "bewhiskered-2027"
    assert result["events"][0]["startDate"] == "2026-12-30"


def test_name_suffix_is_kept_for_ordinal_conventions():
    """furvester-7 and friends number editions, not years."""
    assert import_concat.name_suffix("Furvester 7") == "7"
    assert import_concat.name_year("Furvester 7") is None
    assert import_concat.name_year("Bewhiskered 2027") == 2027
    assert import_concat.name_year("Bewhiskered 2027 ") == 2027

    result = run(
        {"name": "Furvester", "events": []},
        [convention("Furvester 7", "2026-11-06", "2026-11-08")],
        geocode=lambda venue, country: {
            "address": "Durham, NC",
            "latLng": [36.0, -78.9],
        },
        series_id="furvester",
    )

    assert result["events"][0]["id"] == "furvester-7"
    assert result["events"][0]["name"] == "Furvester 7"
    # No neighbour to inherit from, so the url is the one derived from the host.
    assert result["events"][0]["url"] == "https://bewhiskeredcon.org"


def test_implausible_year_is_not_a_year():
    """1000 is a suffix like any other, but not a year the guard should trust."""
    assert import_concat.name_suffix("Furvester 1000") == "1000"
    assert import_concat.name_year("Furvester 1000") is None


def test_superscript_digit_suffix_does_not_crash():
    """`"²".isdigit()` is True but `int("²")` raises."""
    assert import_concat.name_suffix("Anthrocon ²") is None
    assert import_concat.name_year("Anthrocon ²") is None


def test_non_ascii_digit_suffix_is_not_a_suffix():
    """Arabic-Indic digits are decimal, but build an id schema.json rejects."""
    assert import_concat.name_suffix("Anthrocon ٢٠٢٦") is None
    assert import_concat.name_year("Anthrocon ٢٠٢٦") is None


def test_absurdly_long_digit_suffix_is_not_a_suffix():
    """The id becomes a filename, so an unbounded run of digits is not one."""
    assert import_concat.name_suffix("Anthrocon " + "0" * 300) is None


def test_name_without_year_falls_back_to_the_start_year():
    result = run(
        BEWHISKERED_SERIES,
        [convention("Bewhiskered", "2027-04-01", "2027-04-04")],
    )

    assert result["events"][0]["id"] == "bewhiskered-2027"


def test_default_url_drops_the_reg_subdomain():
    assert (
        import_concat.derive_url("https://reg.bewhiskeredcon.org")
        == "https://bewhiskeredcon.org"
    )
    # The dot is literal: an unescaped one ate the first label's first char.
    assert (
        import_concat.derive_url("https://regfurrycon.example")
        == "https://regfurrycon.example"
    )
    assert import_concat.derive_url("https://furrycon.example") == (
        "https://furrycon.example"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", *sys.argv[1:]]))
