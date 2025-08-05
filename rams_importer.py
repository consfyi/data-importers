#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "bs4",
#   "httpx",
#   "whenever",
# ]
# ///
from bs4 import BeautifulSoup
import datetime
import httpx
import json
import logging
import re
import whenever

fn = "midwest-furfest.json"

logging.basicConfig(level=logging.INFO)

LOCATION = {
    "venue": "Donald E. Stephens Convention Center",
    "address": "North River Road, Rosemont, IL, USA",
    "country": "US",
    "latLng": [41.9792232, -87.861987],
}

MONTHS = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def main():
    with open(fn, "r") as f:
        series = json.load(f)

    resp = httpx.get("https://reg.furfest.org/landing/index")
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "html.parser")
    (title,) = soup.select("#mainContainer .landing-title")
    (dates,) = soup.select("#mff_read_more > strong")

    title = title.text
    dates = dates.text

    match = re.match(r"Midwest FurFest (\d+) Registration", title)
    assert match is not None
    year = int(match.group(1))

    id = f"midwest-furfest-{year}"
    if any(event["id"] == id for event in series["events"]):
        return

    name = f"Midwest FurFest {year}"

    # https://github.com/MidwestFurryFandom/rams/blob/fc845002466b91fe443158eb4923901c14010b4f/uber/custom_tags.py#L131-L138
    if " - " in dates:
        epoch, eschaton = dates.split(" - ", 1)
        epoch_month, epoch_day = epoch.split(" ", 1)
        eschaton_month, eschaton_day = epoch.split(" ", 1)
    elif "-" in dates:
        month, rest = dates.split(" ", 1)
        epoch_month = eschaton_month = month
        epoch_day, eschaton_day = rest.split("-")
    else:
        month, day = dates.split(" ", 1)
        epoch_month = eschaton_month = month
        epoch_day = eschaton_day = day

    epoch_month = MONTHS.index(epoch_month)
    epoch_day = int(epoch_day)

    eschaton_month = MONTHS.index(eschaton_month)
    eschaton_day = int(eschaton_day)

    epoch = whenever.Date(year, epoch_month, epoch_day)
    eschaton = whenever.Date(year, eschaton_month, eschaton_day)

    events = series["events"]
    for i, e in enumerate(events):
        if whenever.Date.parse_common_iso(e["startDate"]) <= epoch:
            break
    else:
        i = len(events)

    events.insert(
        i,
        {
            "id": id,
            "name": name,
            "url": "https://www.furfest.org",
            "startDate": epoch.format_common_iso(),
            "endDate": eschaton.format_common_iso(),
            **LOCATION,
        },
    )

    with open(fn, "w") as f:
        json.dump(series, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    main()
