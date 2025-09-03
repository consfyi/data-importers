#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "httpx",
#   "googlemaps",
#   "whenever",
# ]
# ///

import sys
import json
import logging
import googlemaps
import httpx
import re
import os
import uuid
import urllib.parse
import whenever

logging.basicConfig(level=logging.INFO)


def main():
    gmaps = googlemaps.Client(key=os.environ["GOOGLE_MAPS_API_KEY"])

    _, fn, concat_url = sys.argv
    parsed_url = urllib.parse.urlparse(concat_url)

    series_id, _ = os.path.splitext(fn)

    with open(fn) as f:
        series = json.load(f)

    venue_details = {
        event["venue"]: {k: v for k, v in event.items() if k in {"address", "latLng"}}
        for event in series["events"]
    }

    resp = httpx.get(f"{concat_url}/api/config")
    resp.raise_for_status()
    config = resp.json()

    for convention in config["conventions"]:
        if not convention["domain"].endswith(parsed_url.netloc):
            continue

        start_date = whenever.OffsetDateTime.parse_common_iso(
            convention["startAt"]
        ).date()
        end_date = whenever.OffsetDateTime.parse_common_iso(convention["endAt"]).date()

        suffix = str(start_date.year)
        _, _, name_suffix = convention["longName"].rpartition(" ")
        if name_suffix.isdigit():
            suffix = name_suffix

        id = f"{series_id}-{suffix}"

        events = series["events"]
        for i, e in enumerate(events):
            if whenever.Date.parse_common_iso(e["startDate"]).year <= start_date.year:
                break
        else:
            i = len(events)

        previous_event = None
        if i < len(events):
            previous_event = events[i]
            if previous_event["id"] == id:
                sources = previous_event.get("sources", [])
                if sources != ["fancons.com"] and sources != ["guessed"]:
                    if (
                        whenever.Date.parse_common_iso(previous_event["startDate"]).year
                        == start_date.year
                        and whenever.Date.parse_common_iso(
                            previous_event["endDate"]
                        ).year
                        == end_date.year
                    ):
                        previous_event["startDate"] = start_date.format_common_iso()
                        previous_event["endDate"] = end_date.format_common_iso()
                        continue

                del events[i]

        venue = convention["venue"]

        country = config["organization"]["country"]

        if venue not in venue_details:
            logging.info(f"geocoding required for: {venue}")
            address = None
            lat_lng = None

            session_token = str(uuid.uuid4())

            predictions = gmaps.places_autocomplete(
                f"{venue}, {country}", session_token=session_token
            )

            if predictions:
                prediction, *_ = predictions

                place = gmaps.place(
                    prediction["place_id"],
                    session_token=session_token,
                    fields=["geometry/location", "name", "formatted_address"],
                )["result"]
                address = place["formatted_address"]
                l = place["geometry"]["location"]
                lat_lng = [l["lat"], l["lng"]]

            venue_details[venue] = {
                "address": address,
                "latLng": lat_lng,
            }

        details = venue_details[venue]
        address = details["address"]
        lat_lng = details["latLng"]

        if previous_event is not None:
            url = previous_event["url"]
        else:
            url = re.sub(r"^https://reg.", "https://", concat_url)

        event = {
            "id": id,
            "name": f"{series['name']} {suffix}",
            "url": url,
            "startDate": start_date.format_common_iso(),
            "endDate": end_date.format_common_iso(),
            "venue": venue,
            "address": address,
            "locale": f"en_{country}",  # Probably don't hardcode this...
            "latLng": lat_lng,
        }
        logging.info(f"imported: {event}")
        events.insert(i, {k: v for k, v in event.items() if v is not None})

    with open(fn, "w") as f:
        json.dump(series, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    main()
