#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "httpx",
#   "whenever",
# ]
# ///
import dataclasses
import whenever
import httpx
import json
import os
import sys


@dataclasses.dataclass
class ImportedEvent:
    title: str
    start_date: whenever.Date
    end_date: whenever.Date


GQL_QUERY = """
query listAllEvents($nextToken: String) {
  listAllEvents(nextToken: $nextToken) {
    items {
      title
      title_short
      date_event_start
      date_event_end
    }
    nextToken
  }
}
"""

_, fn, endpoint, api_key = sys.argv


def list_all_events():
    next_token = None
    while True:
        resp = httpx.post(
            f"{endpoint}/graphql",
            json={
                "operationName": "listAllEvents",
                "variables": {"nextToken": next_token},
                "query": GQL_QUERY,
            },
            headers={"authorization": api_key},
        )
        resp.raise_for_status()
        body = resp.json()["data"]["listAllEvents"]
        for item in body["items"]:
            yield ImportedEvent(
                title=item["title"],
                start_date=whenever.Instant.from_timestamp(item["date_event_start"])
                .to_tz("UTC")
                .date(),
                end_date=whenever.Instant.from_timestamp(item["date_event_end"])
                .to_tz("UTC")
                .date(),
            )
        next_token = body["nextToken"]
        if next_token is None:
            break


def main():
    events = list(list_all_events())
    import pprint

    pprint.pprint(events)


if __name__ == "__main__":
    main()
