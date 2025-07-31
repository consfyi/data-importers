#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "eviltransform",
#   "httpx",
#   "googlemaps",
#   "whenever",
# ]
# ///

import sys
import json
import logging
import eviltransform
import googlemaps
import httpx
import re
import os
import uuid
import whenever

logging.basicConfig(level=logging.INFO)


def main():
    gmaps = googlemaps.Client(key=os.environ["GOOGLE_MAPS_API_KEY"])

    _, fn, concat_url = sys.argv

    series_id, ext = os.path.splitext(fn)

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
        start_date = whenever.OffsetDateTime.parse_common_iso(
            convention["startAt"]
        ).date()
        end_date = whenever.OffsetDateTime.parse_common_iso(convention["endAt"]).date()

        id = f"{series_id}-{start_date.year}"

        for i, e in enumerate(series["events"]):
            if whenever.Date.parse_common_iso(e["startDate"]) <= start_date:
                break
        else:
            i = len(series["events"])

        previous_event = None
        if i < len(series["events"]):
            previous_event = series["events"][i]
            if previous_event["id"] == id:
                continue

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
                st = prediction["structured_formatting"]
                if "secondary_text" in st:
                    address = st["secondary_text"]

                place = gmaps.place(
                    prediction["place_id"],
                    session_token=session_token,
                    fields=["geometry/location"],
                )
                l = place["result"]["geometry"]["location"]
                lat_lng = [l["lat"], l["lng"]]
                if country == "CN":
                    lat, lng = lat_lng
                    lat_lng = eviltransform.gcj2wgs(lat, lng)

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
            "name": f"{series['name']} {start_date.year}",
            "url": url,
            "startDate": start_date.format_common_iso(),
            "endDate": end_date.format_common_iso(),
            "venue": venue,
            "address": address,
            "country": country,
            "latLng": lat_lng,
        }
        logging.info(f"imported: {event}")
        series["events"].insert(i, {k: v for k, v in event.items() if v is not None})

    with open(fn, "w") as f:
        json.dump(series, f, indent=2, ensure_ascii=False)
        f.write("\n")


main()
