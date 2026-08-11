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
logging.getLogger("httpx").setLevel(logging.WARNING)


def fetch_config(concat_url):
    """Fetch ConCat's /api/config.

    Hosts behind Cloudflare that block the runner's IP are handled two ways:

    - CONCAT_RATELIMIT_KEY: sent as an `x-ratelimit-key` header (works for cons
      on the shared ConCat platform). Scoped to the ConCat host -- redirects are
      followed manually and the header is dropped if a redirect leaves that
      host, so it can never leak to a third party.
    - CONCAT_PROXY: for hosts listed in CONCAT_PROXY_HOSTS (e.g. cons on their
      own Cloudflare zone, where the platform key doesn't apply), the
      /api/config request is routed through a Cloudflare Worker whose egress IP
      isn't blocked, authenticated with CONCAT_PROXY_SECRET.

    Both are request-only -- never logged or written to the imported data.
    """
    base_host = urllib.parse.urlparse(concat_url).netloc

    proxy = os.environ.get("CONCAT_PROXY")
    proxy_hosts = {
        h.strip()
        for h in os.environ.get("CONCAT_PROXY_HOSTS", "").split(",")
        if h.strip()
    }
    if proxy and base_host in proxy_hosts:
        return httpx.get(
            proxy,
            params={"url": f"{concat_url}/api/config"},
            headers={"x-proxy-secret": os.environ.get("CONCAT_PROXY_SECRET", "")},
            timeout=30,
        )

    key = os.environ.get("CONCAT_RATELIMIT_KEY")
    url = f"{concat_url}/api/config"
    with httpx.Client() as client:
        resp = None
        for _ in range(5):
            headers = {}
            if key and urllib.parse.urlparse(url).netloc == base_host:
                headers["x-ratelimit-key"] = key
            resp = client.get(url, headers=headers)
            if resp.is_redirect and resp.next_request is not None:
                url = str(resp.next_request.url)
                continue
            break
        return resp


# Whole-string match only: a venue genuinely named "Coming Soon Hall" is a real
# place, and matching it as a prefix would silently drop a valid convention.
PLACEHOLDER_VENUE_RE = re.compile(
    r"(venue |location )?"
    r"(coming soon|tba|tbd|to be announced|to be determined|to be confirmed"
    r"|unknown|none|n/?a)",
    re.IGNORECASE,
)


# The longest venue in the live dataset is 72 characters; anything past this is
# not a venue name, and the bracket substitution below is quadratic on input an
# upstream host controls.
MAX_VENUE_LENGTH = 200


# Long enough for the skip reasons below once their upstream parts are bounded.
MAX_WARNING_LENGTH = 500


def warn_skip(message):
    """Log a skip, annotated so it shows up in the GitHub Actions run summary.

    `::warning::` makes the line a workflow command Actions parses, so upstream
    text reaching it must not carry newlines: a `longName` containing
    `\\n::stop-commands::x` would suppress every later annotation in the job,
    including the `::error::` report of failed sources.
    """
    message = re.sub(r"[\r\n]+", " ", message)
    prefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") else ""
    # Bound the whole line, prefix included: truncating the message first would
    # put the annotation over the limit only under Actions, where nobody runs
    # the tests locally to notice.
    logging.warning(f"{prefix}{message}"[:MAX_WARNING_LENGTH])


def normalize_venue(venue):
    """ConCat's venue string reduced to the words worth matching on."""
    venue = re.sub(r"[(\[][^)\]]*[)\]]", " ", venue)
    venue = venue.replace(".", "")
    venue = re.sub(r"\s+", " ", venue)
    return venue.strip(" -–—*!?:,;")


def is_placeholder_venue(venue):
    """True if ConCat's venue is a placeholder rather than a real place."""
    if venue is None:
        return True
    if len(venue) > MAX_VENUE_LENGTH:
        warn_skip(f"venue is {len(venue)} characters, too long to be a real one")
        return True
    venue = normalize_venue(venue)
    return not venue or PLACEHOLDER_VENUE_RE.fullmatch(venue) is not None


def name_suffix(long_name):
    """The trailing digits in ConCat's longName, or None if it has none.

    Not necessarily a year: ordinal-numbered cons ("Furvester 7") carry their
    edition number here. ASCII digits only -- other Nd digits build an id the
    schema rejects.
    """
    _, _, suffix = long_name.strip().rpartition(" ")
    return suffix if re.fullmatch(r"[0-9]{1,4}", suffix) else None


def name_year(long_name):
    """The trailing year in ConCat's longName, or None if it has no year."""
    suffix = name_suffix(long_name)
    if suffix is None or len(suffix) != 4:
        return None
    year = int(suffix)
    return year if 1900 <= year <= 2999 else None


def has_placeholder_dates(long_name, start_year, end_year):
    """True if the name's year disagrees with the years the dates fall in.

    A year-spanning con is named for either the year it starts in or the year
    it ends in, so matching either is enough.
    """
    year = name_year(long_name)
    return year is not None and year != start_year and year != end_year


def find_event_indexes(events, id):
    """Indexes of every event with this id, in order."""
    return [i for i, e in enumerate(events) if e["id"] == id]


# Fields the importer does not own: hand-curated or written by other tools, and
# not re-derivable if lost. `sources` is deliberately absent -- dropping it is
# how a fancons.com/guessed row is upgraded to a ConCat one.
CURATED_FIELDS = ("keyDates", "translations", "canceled", "attendance")


def curated_fields(event):
    """The curated fields present on an event."""
    return {k: event[k] for k in CURATED_FIELDS if k in event}


def derive_url(concat_url):
    """The convention's own site: ConCat's reg endpoint minus the `reg.` host."""
    return re.sub(r"^https://reg\.", "https://", concat_url)


def insertion_index(events, start_year):
    """Where an event starting in `start_year` belongs in descending order."""
    for i, e in enumerate(events):
        if whenever.Date.parse_common_iso(e["startDate"]).year <= start_year:
            return i
    return len(events)


def apply_convention(
    series, series_id, convention, country, default_url, venue_details, geocode, today
):
    """Merge one ConCat convention into `series["events"]` in place."""
    start_date = whenever.OffsetDateTime.parse_common_iso(convention["startAt"]).date()
    end_date = whenever.OffsetDateTime.parse_common_iso(convention["endAt"]).date()

    long_name = convention["longName"]
    venue = convention["venue"]

    if has_placeholder_dates(long_name, start_date.year, end_date.year):
        # long_name and venue are upstream-controlled and unbounded: truncate
        # every interpolation of them so one entry can't flood the run log.
        warn_skip(
            f"skipping {long_name[:100]}: dates {start_date} - {end_date} disagree "
            "with the year in its name, so they are the previous edition's"
        )
        return

    suffix = name_suffix(long_name) or str(start_date.year)
    id = f"{series_id}-{suffix}"

    events = series["events"]

    # The id lookup and the date update run before the venue check: an already
    # stored event gets its announced dates even while its venue is still a
    # placeholder upstream, which is exactly when new dates show up first.
    matches = find_event_indexes(events, id)
    # The survivor is whichever copy comes first, which is the stripped one the
    # buggy run inserted, so its curated fields come from the copies it replaces
    # rather than from itself. Deleting tail-first keeps its index put.
    survivor = events[matches[0]] if matches else None
    for i in reversed(matches[1:]):
        for k, v in curated_fields(events[i]).items():
            if k in survivor and survivor[k] != v:
                # No deep merge: the discard is one-way and schema-valid, so
                # the only safe thing is to make it visible.
                warn_skip(
                    f"{id}: duplicate copies disagree on {k}, "
                    f"keeping {survivor[k]!r}"
                )
            survivor.setdefault(k, v)
        del events[i]
    existing = matches[0] if matches else None

    previous_event = None
    replaces_guess = False
    same_years = False
    if existing is not None:
        previous_event = events[existing]
        sources = previous_event.get("sources", [])
        replaces_guess = sources == ["fancons.com"] or sources == ["guessed"]
        same_years = (
            whenever.Date.parse_common_iso(previous_event["startDate"]).year
            == start_date.year
            and whenever.Date.parse_common_iso(previous_event["endDate"]).year
            == end_date.year
        )
        if not replaces_guess and same_years:
            if start_date > today and end_date > today:
                previous_event["startDate"] = start_date.format_common_iso()
                previous_event["endDate"] = end_date.format_common_iso()
            return

    # Anything past here geocodes the venue and writes it into an event, so a
    # placeholder must stop it -- including the delete-and-recreate above.
    if is_placeholder_venue(venue):
        if existing is not None and start_date > today and end_date > today:
            # The year moved, so the early return above didn't run. Publish the
            # announced dates anyway and keep the last known real venue.
            previous_event["startDate"] = start_date.format_common_iso()
            previous_event["endDate"] = end_date.format_common_iso()
        shown = venue if venue is None else venue[:100]
        warn_skip(f"skipping {long_name[:100]}: placeholder venue {shown!r}")
        return

    preserved = {}
    if existing is not None:
        # The rebuilt event is written from a fixed key set, so the curated
        # fields of the event it replaces have to be carried over by hand.
        preserved = curated_fields(previous_event)
        if replaces_guess:
            # `canceled` is derived from fancons.com's iCal STATUS, not curated
            # by hand: carrying it across the upgrade would leave the con
            # cancelled while ConCat is listing registration, with `sources`
            # gone and nothing left to clear it but a hand edit.
            preserved.pop("canceled", None)
        elif previous_event.get("sources") is not None:
            # Only the fancons/guessed upgrade above is meant to drop `sources`.
            # This path also runs when an existing event's dates move into
            # another year, and that is no reason to lose its attribution.
            preserved["sources"] = previous_event["sources"]
        del events[existing]
        # An unchanged year belongs back in the slot it already held: series
        # with two editions in one calendar year exist, and recomputing would
        # hop this one over the earlier of them.
        index = existing if same_years else insertion_index(events, start_date.year)
    else:
        # A brand-new edition inherits url/ageRestriction from the edition it
        # sits next to; only those two fields, never the dates or the dedup.
        index = insertion_index(events, start_date.year)
        if index < len(events):
            previous_event = events[index]

    if venue not in venue_details:
        logging.info(f"geocoding required for: {venue}")
        venue_details[venue] = geocode(venue, country)

    details = venue_details[venue]

    age_restriction = None
    if previous_event is not None:
        # On the new-edition path this is an arbitrary neighbour rather than
        # the same event, so don't let one malformed row abort the series.
        url = previous_event.get("url") or default_url
        age_restriction = previous_event.get("ageRestriction")
    else:
        url = default_url

    event = {
        "id": id,
        "name": f"{series['name']} {suffix}",
        "url": url,
        "startDate": start_date.format_common_iso(),
        "endDate": end_date.format_common_iso(),
        "venue": venue,
        # .get: the None-filter below can store an event with no address, and
        # the cache in main() is rebuilt from stored events, so a venue that
        # once failed to geocode comes back as {} on the next run.
        "address": details.get("address"),
        "locale": f"en-{country}",  # Probably don't hardcode this...
        **({"ageRestriction": age_restriction} if age_restriction is not None else {}),
        "latLng": details.get("latLng"),
        **preserved,
    }
    logging.info(f"imported: {event}")
    events.insert(index, {k: v for k, v in event.items() if v is not None})


def main():
    gmaps = googlemaps.Client(key=os.environ["GOOGLE_MAPS_API_KEY"])
    today = whenever.Instant.now().to_system_tz().date()

    _, fn, concat_url = sys.argv
    parsed_url = urllib.parse.urlparse(concat_url)

    series_id, _ = os.path.splitext(fn)

    with open(fn) as f:
        series = json.load(f)

    venue_details = {
        event["venue"]: {k: v for k, v in event.items() if k in {"address", "latLng"}}
        for event in series["events"]
    }

    resp = fetch_config(concat_url)
    resp.raise_for_status()
    config = resp.json()

    default_url = derive_url(concat_url)

    def geocode(venue, country):
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

        return {"address": address, "latLng": lat_lng}

    for convention in config["conventions"]:
        if not convention["domain"].endswith(parsed_url.netloc):
            continue

        apply_convention(
            series,
            series_id,
            convention,
            config["organization"]["country"],
            default_url,
            venue_details,
            geocode,
            today,
        )

    with open(fn, "w") as f:
        json.dump(series, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    main()
