#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "whenever",
#   "tzfpy[tzdata]",
# ]
# ///

import sys
import json
import logging
import os
import math
import tzfpy
import whenever

logging.basicConfig(level=logging.INFO)


def get_week_of_month(date: whenever.Date) -> int:
    first = whenever.Date(date.year, date.month, 1)
    return int(math.ceil((date.day + first.day_of_week().value) / 7))


def get_weekday_in_nth_week(
    year: int, month: int, weekday: whenever.Weekday, week: int
) -> whenever.Date:
    first = whenever.Date(year, month, 1)
    return first + whenever.days(
        -first.day_of_week().value + weekday.value + (week - 1) * 7
    )


def add_year_same_weekday(date: whenever.Date) -> whenever.Date:
    return get_weekday_in_nth_week(
        date.year + 1,
        date.month,
        date.day_of_week(),
        get_week_of_month(date),
    )


def main():
    _, fn = sys.argv

    series_id, ext = os.path.splitext(fn)
    now = whenever.Instant.now()

    with open(fn) as f:
        series = json.load(f)

    events = series["events"]
    if not events:
        return

    previous_event = events[0]
    previous_start_date = whenever.Date.parse_common_iso(previous_event["startDate"])
    previous_end_date = whenever.Date.parse_common_iso(previous_event["endDate"])

    timezone = "UTC"
    if "latLng" in previous_event:
        lat, lng = previous_event["latLng"]
        timezone = tzfpy.get_tz(lat, lng)

    if previous_end_date >= now.to_tz(timezone).date():
        return

    start_date = add_year_same_weekday(previous_start_date)
    end_date = add_year_same_weekday(previous_end_date)

    suffix = start_date.year
    _, previous_suffix = previous_event["name"].rsplit(" ", 1)
    try:
        previous_suffix = int(previous_suffix)
    except:
        pass
    else:
        suffix = previous_suffix + 1

    events.insert(
        0,
        {
            "id": f"{series_id}-{suffix}",
            "name": f"{series['name']} {suffix}",
            "url": previous_event["url"],
            "startDate": start_date.format_common_iso(),
            "endDate": end_date.format_common_iso(),
            "venue": previous_event["venue"],
            "address": previous_event["address"],
            "country": previous_event["country"],
            "latLng": previous_event["latLng"],
            "sources": ["guessed"],
        },
    )

    with open(fn, "w") as f:
        json.dump(series, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    main()
