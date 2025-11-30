#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "httpx",
#   "whenever",
# ]
# ///
import dataclasses
import logging
import whenever
import httpx
import json
import os
import sys


logging.basicConfig(level=logging.INFO)


@dataclasses.dataclass
class ImportedEvent:
    title: str
    start_date: whenever.Date
    end_date: whenever.Date


GQL_QUERY = """
query listAllEvents($nextToken: String) {
  listAllEvents(nextToken: $nextToken) {
    items {
      id
      visible
      enabled
      title
      title_short
      date_event_start
      date_event_end
      url_key
    }
    nextToken
  }
}
"""

_, fn, endpoint, prefix = sys.argv


def get_config():
    resp = httpx.get(f"{endpoint}/_config/system.json")
    resp.raise_for_status()
    return resp.json()


CONFIG = get_config()


def get_event_config(event_id):
    resp = httpx.get(f"{endpoint}/_config/app/{event_id}.json")
    resp.raise_for_status()
    return resp.json()


def list_all_events():
    next_token = None
    while True:
        resp = httpx.post(
            CONFIG["graphql"]["endpoint"],
            json={
                "operationName": "listAllEvents",
                "variables": {"nextToken": next_token},
                "query": GQL_QUERY,
            },
            headers={"authorization": CONFIG["graphql"]["api_key"]},
        )
        resp.raise_for_status()
        json = resp.json()
        if "errors" in json:
            raise Exception(json["errors"])
        body = json["data"]["listAllEvents"]
        for item in body["items"]:
            if not item["visible"] or not item["enabled"]:
                continue
            if item["url_key"] == "default" or not item["url_key"].startswith(prefix):
                continue
            if item["date_event_start"] == 0 or item["date_event_end"] == 0:
                continue
            event_config = get_event_config(item["id"])
            tz = event_config["core"]["locale"]["timezone"]
            yield ImportedEvent(
                title=item["title"],
                start_date=whenever.Instant.from_timestamp(item["date_event_start"])
                .to_tz(tz)
                .date(),
                end_date=whenever.Instant.from_timestamp(item["date_event_end"])
                .to_tz(tz)
                .date(),
            )
        next_token = body["nextToken"]
        if next_token is None:
            break


def main():
    series_id, _ = os.path.splitext(fn)

    with open(fn, "r") as f:
        series = json.load(f)

    events = series["events"]

    for imported in list_all_events():
        for i, e in enumerate(events):
            if (
                whenever.Date.parse_common_iso(e["startDate"]).year
                <= imported.start_date.year
            ):
                break
        else:
            i = len(events)

        if i < len(events):
            previous_event = events[i]

            if (
                whenever.Date.parse_common_iso(previous_event["startDate"]).year
                == imported.start_date.year
                and whenever.Date.parse_common_iso(previous_event["endDate"]).year
                == imported.end_date.year
            ):
                previous_event["startDate"] = imported.start_date.format_common_iso()
                previous_event["endDate"] = imported.end_date.format_common_iso()
                continue
        else:
            previous_event = events[-1]

        event = {
            "id": f"{series_id}-{imported.start_date.year}",
            "name": f"{series['name']} {imported.start_date.year}",
            "url": previous_event["url"],
            "startDate": imported.start_date.format_common_iso(),
            "endDate": imported.end_date.format_common_iso(),
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
