#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "bs4",
#   "eviltransform",
#   "httpx",
#   "googlemaps",
#   "PyICU",
#   "regex",
# ]
# ///
import asyncio
from bs4 import BeautifulSoup
import dataclasses
import datetime
import eviltransform
import html
import httpx
import googlemaps
import uuid
import json
import icu
import logging
import pathlib
import regex
import os
import typing
import unicodedata
import xml.etree.ElementTree as ET


logging.basicConfig(level=logging.INFO)


def guess_language_for_region(region_code: str) -> icu.Locale:
    return icu.Locale.createFromName(f"und_{region_code}").addLikelySubtags()


def slugify(s: str, langid: icu.Locale) -> str:
    try:
        trans = icu.Transliterator.createInstance(f"{langid.getLanguage()}-ASCII")
    except:
        trans = icu.Transliterator.createInstance("ASCII")

    return "-".join(
        regex.sub(
            r"[^a-z0-9\s-]+",
            "",
            trans.transliterate(
                icu.CaseMap.toLower(
                    langid, unicodedata.normalize("NFKC", s.replace("&", "and"))
                )
            ),
        ).split()
    )


async def fetch_bytes(client: httpx.AsyncClient, url: str) -> bytes:
    resp = await client.get(url)
    resp.raise_for_status()
    return resp.content


with open(os.path.join(os.path.dirname(__file__), "fancons_ignore"), "r") as f:
    IGNORE = {line.strip() for line in f}


with open(os.path.join(os.path.dirname(__file__), "countries.json"), "r") as f:
    COUNTRIES = json.load(f)


OUTPUT_DIR = pathlib.Path(os.environ.get("OUTPUT_DIR", "."))
CALENDAR_URL = os.environ.get(
    "CALENDAR_URL", "https://furrycons.com/calendar/calendar.php"
)
MAP_URL = os.environ.get(
    "MAP_URL", "https://furrycons.com/calendar/map/yc-maps/map-upcoming.xml"
)
GOOGLE_MAPS_API_KEY = os.environ["GOOGLE_MAPS_API_KEY"]


async def fetch_map(
    client: httpx.AsyncClient, url: str
) -> dict[str, tuple[float, float]]:
    resp = await client.get(url)
    resp.raise_for_status()

    markers = {}
    for marker in ET.fromstring(resp.content).findall("marker"):
        markers[marker.attrib["id"]] = (
            float(marker.attrib["lat"]),
            float(marker.attrib["lng"]),
        )
    return markers


async def fetch_calendar(
    client: httpx.AsyncClient, url: str
) -> list[dict[str, typing.Any]]:
    events = []

    resp = await client.get(url)
    resp.raise_for_status()

    for script in BeautifulSoup(resp.content, "html.parser").find_all(
        "script", {"type": "application/ld+json"}
    ):
        entries = json.loads(html.unescape(script.string or "").replace("\n", " "))
        if not isinstance(entries, list):
            entries = [entries]

        for entry in entries:
            if (
                entry.get("@context") != "http://schema.org"
                or entry.get("@type") != "Event"
            ):
                continue
            events.append(entry)

    return events


@dataclasses.dataclass
class Event:
    series_id: str
    series_name: str
    id: str
    name: str
    url: str
    start_date: datetime.date
    end_date: datetime.date
    venue: str
    address: str | None
    locale: icu.Locale
    translations: typing.Dict[str, typing.Dict[str, str]]
    lat_lng: tuple[float, float] | None
    canceled: bool
    sources: typing.List[str] | None

    def update_via_geocode(self, gmaps: googlemaps.Client):
        session_token = str(uuid.uuid4())

        predictions = gmaps.places_autocomplete(
            ", ".join(part for part in [self.venue, self.address] if part is not None),
            session_token=session_token,
        )

        if predictions:
            prediction, *_ = predictions

            place = gmaps.place(
                prediction["place_id"],
                session_token=session_token,
                fields=[
                    "name",
                    "formatted_address",
                    "geometry/location",
                    "address_component",
                ],
                language=str(self.locale),
            )["result"]

            self.venue = place["name"]
            self.address = place["formatted_address"]

            l = place["geometry"]["location"]
            self.lat_lng = (l["lat"], l["lng"])
            country = next(
                component["short_name"]
                for component in place["address_components"]
                if "country" in component["types"]
            )
            self.locale = guess_language_for_region(country)

            if self.locale.getLanguage() != "en":
                enPlace = gmaps.place(
                    prediction["place_id"],
                    session_token=session_token,
                    fields=[
                        "name",
                        "formatted_address",
                    ],
                    language="en",
                )["result"]

                enTranslations = self.translations.setdefault("en", {})
                enTranslations["venue"] = enPlace["name"]
                enTranslations["address"] = enPlace["formatted_address"]

            if self.locale.getCountry() == "CN":
                lat, lng = self.lat_lng
                self.lat_lng = eviltransform.gcj2wgs(lat, lng)

    def materialize_entry(self, gmaps: googlemaps.Client):
        self.update_via_geocode(gmaps)
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "startDate": self.start_date.isoformat(),
            "endDate": self.end_date.isoformat(),
            "venue": self.venue,
            **({"address": self.address} if self.address is not None else {}),
            "locale": f"{self.locale.getLanguage()}-{self.locale.getCountry()}",
            **({"translations": self.translations} if self.translations else {}),
            **({"latLng": self.lat_lng} if self.lat_lng is not None else {}),
            **({"canceled": True} if self.canceled else {}),
            **({"sources": self.sources} if self.sources is not None else {}),
        }


async def fetch_events():

    async with httpx.AsyncClient() as client:
        calendar, markers = await asyncio.gather(
            fetch_calendar(client, CALENDAR_URL),
            fetch_map(client, MAP_URL),
        )

        for entry in calendar:
            try:
                name = entry["name"]
                prefix, year = entry["name"].rsplit(" ", 1)

                url = entry["url"]
                start_date = datetime.date.fromisoformat(entry["startDate"])
                end_date = datetime.date.fromisoformat(entry["endDate"])
                loc = entry["location"]
                venue = loc["name"]
                address_parts = loc["address"]
                country_name = address_parts["addressCountry"]
                country = COUNTRIES[country_name]
                address = ", ".join(
                    part
                    for part in [
                        address_parts.get("addressLocality", ""),
                        address_parts.get("addressRegion", ""),
                        country_name,
                    ]
                    if part
                )
                canceled = entry["eventStatus"] not in {
                    "https://schema.org/EventScheduled",
                    "https://schema.org/EventRescheduled",
                }

                locale = guess_language_for_region(country)
                series_id = slugify(prefix, locale)

                match = regex.search(r"/event/(\d+)/", url)
                assert match is not None
                fc_id = match.group(1)
                lat_lng = markers.get(fc_id) if fc_id else None

                yield Event(
                    series_id=series_id,
                    series_name=prefix,
                    id=f"{series_id}-{year}",
                    name=name,
                    url=url,
                    start_date=start_date,
                    end_date=end_date,
                    venue=venue,
                    address=address,
                    locale=f"{locale.getLanguage()}-{locale.getCountry()}",
                    translations={},
                    lat_lng=lat_lng,
                    canceled=canceled,
                    sources=["fancons.com"],
                )

            except Exception as e:
                logging.warning(f"Failed to process event: {e}")


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)
    async for event in fetch_events():
        if event.series_id in IGNORE:
            continue

        fn = f"{event.series_id}.json"

        if os.path.exists(fn):
            with open(fn, "r") as f:
                series = json.load(f)
        else:
            fn = os.path.join("import_pending", fn)
            if os.path.exists(fn):
                with open(fn, "r") as f:
                    series = json.load(f)
            else:
                logging.info(f"Adding pending series {event.series_id}")
                series = {"name": event.series_name, "events": []}

        for i, e in enumerate(series["events"]):
            start_date = datetime.date.fromisoformat(e["startDate"])
            if start_date.year <= event.start_date.year:
                break
        else:
            i = len(series["events"])

        if i < len(series["events"]):
            previous_event = series["events"][i]

            event.url = previous_event["url"]
            event.locale = previous_event["locale"]

            # Handle numbered cons.
            previous_prefix, maybe_space, previous_suffix = regex.match(
                r"^(.*?)( ?)(\d+)$", previous_event["name"]
            ).groups()
            previous_start_date = datetime.date.fromisoformat(
                previous_event["startDate"]
            )
            previous_end_date = datetime.date.fromisoformat(previous_event["endDate"])

            if (
                event.start_date.year == previous_start_date.year
                and event.end_date.year == previous_end_date.year
            ):
                continue

            try:
                previous_suffix = int(previous_suffix)
            except:
                pass
            else:
                if (
                    previous_start_date.year != previous_suffix
                    or previous_end_date.year != previous_suffix
                ) and previous_prefix == series["name"]:
                    suffix = previous_suffix + 1
                    event.name = f"{series['name']}{maybe_space}{suffix}"
                    event.id = f"{event.series_id}-{suffix}"

            if previous_event["id"] == event.id:
                continue

        logging.info(f"Adding event {event.id} to {event.series_id}")
        series["events"].insert(i, event.materialize_entry(gmaps))
        with open(fn, "w") as f:
            json.dump(series, f, ensure_ascii=False, indent=2)
            f.write("\n")


if __name__ == "__main__":
    asyncio.run(main())
