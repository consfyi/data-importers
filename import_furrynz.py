#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "httpx",
#   "whenever",
# ]
# ///
#
# Imports event dates from furry.nz (the anthro.nz regional hub), which
# publishes each event as schema.org JSON-LD on its page. Used for the NZ/AU
# cons that previously came from EventDrake (furconz, FurDU, Tails of Terror,
# aurawra) — furry.nz is a stable, standards-based source that doesn't depend
# on per-con AppSync API keys.
#
# Usage: import_furrynz.py <series.json> <group> [slug_prefix]
#   group       furry.nz group slug, e.g. "furconz", "furdu", "aurawra"
#   slug_prefix optional event-slug filter, needed when one group runs several
#               cons (e.g. group "furdu" hosts both "furdu-*" and
#               "tails-of-terror-*").
#
# Like import_eventdrake, this uses the source ONLY for dates: existing
# same-year events have their dates refreshed, and new years are inserted
# carrying url/venue/address/locale/latLng forward from the previous event
# (furry.nz has no coordinates, and the existing entries are already geocoded).
import dataclasses
import json
import logging
import os
import re
import sys

import httpx
import whenever

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

BASE = "https://furry.nz"

EVENT_HREF = re.compile(r'href="(/events/\d+/[^"/]+/)"')
JSON_LD = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S
)


@dataclasses.dataclass
class ImportedEvent:
    start_date: whenever.Date
    end_date: whenever.Date


def list_event_paths(group):
    resp = httpx.get(f"{BASE}/groups/{group}/", follow_redirects=True)
    resp.raise_for_status()
    paths = []
    for match in EVENT_HREF.finditer(resp.text):
        path = match.group(1)
        if path not in paths:
            paths.append(path)
    return paths


def fetch_event(path):
    resp = httpx.get(f"{BASE}{path}", follow_redirects=True)
    resp.raise_for_status()
    for match in JSON_LD.finditer(resp.text):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Event":
            return data
    return None


def list_all_events(group, prefix):
    for path in list_event_paths(group):
        slug = path.rstrip("/").rsplit("/", 1)[-1]
        if prefix and not slug.startswith(prefix):
            continue
        data = fetch_event(path)
        if data is None:
            continue
        start = data.get("startDate")
        end = data.get("endDate")
        if not start or not end:
            continue
        yield ImportedEvent(
            start_date=whenever.Date.parse_iso(start),
            end_date=whenever.Date.parse_iso(end),
        )


def main():
    _, fn, group, *rest = sys.argv
    prefix = rest[0] if rest else ""

    series_id, _ = os.path.splitext(fn)

    with open(fn, "r") as f:
        series = json.load(f)

    events = series["events"]

    for imported in list_all_events(group, prefix):
        for i, e in enumerate(events):
            if (
                whenever.Date.parse_iso(e["startDate"]).year
                <= imported.start_date.year
            ):
                break
        else:
            i = len(events)

        if i < len(events):
            previous_event = events[i]

            if (
                whenever.Date.parse_iso(previous_event["startDate"]).year
                == imported.start_date.year
                and whenever.Date.parse_iso(previous_event["endDate"]).year
                == imported.end_date.year
            ):
                previous_event["startDate"] = imported.start_date.format_iso()
                previous_event["endDate"] = imported.end_date.format_iso()
                continue
        else:
            previous_event = events[-1]

        event = {
            "id": f"{series_id}-{imported.start_date.year}",
            "name": f"{series['name']} {imported.start_date.year}",
            "url": previous_event["url"],
            "startDate": imported.start_date.format_iso(),
            "endDate": imported.end_date.format_iso(),
            **{
                k: v
                for k, v in previous_event.items()
                if k in {"venue", "address", "locale", "ageRestriction", "latLng"}
            },
        }
        logging.info(f"imported: {event}")
        events.insert(i, {k: v for k, v in event.items() if v is not None})

    with open(fn, "w") as f:
        json.dump(series, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    main()
