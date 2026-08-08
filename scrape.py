#!/usr/bin/env python3
"""Recursive Facebook public-event scraper.

Keeps a host graph in data/hosts.json (each host has a `distance` from the
seed set) and full event data in data/events/<id>.json. Scraping a host lists
its hosted events, fetches each event's details, and registers every co-host
as a new host at distance+1 (never scraped until you raise --max-distance).

Usage:
  python scrape.py scrape                  # scrape distance-0 (seed) hosts
  python scrape.py scrape --max-distance 1 # also scrape distance-1 hosts
  python scrape.py scrape --past           # include past events
  python scrape.py status                  # summary of hosts/events
Seeds are read from seed_hosts.txt (lines: "<n>\t<url>").
"""

import argparse
import json
import math
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
EVENTS_DIR = DATA / "events"
HOSTS_FILE = DATA / "hosts.json"
SEEDS_FILE = ROOT / "seed_hosts.txt"
LOCATION_FILE = ROOT / "location_filter.json"

DELAY = 0.5  # seconds between requests
BACKOFFS = [15, 60]  # retry sleeps after a failed request


def norm_url(url: str) -> str:
    url = url.strip().rstrip("/")
    url = re.sub(r"^https?://(www\.|m\.)?facebook\.com", "https://www.facebook.com", url)
    return url


def fetch(cmd: str, arg: str, sub: str | None = None):
    """Call the Node wrapper; returns parsed JSON or raises RuntimeError.

    Transient-looking failures are retried with backoff; permanent ones
    (invalid URL, no public events) raise immediately.
    """
    argv = ["node", str(ROOT / "fetch.mjs"), cmd, arg] + ([sub] if sub else [])
    for i, backoff in enumerate([*BACKOFFS, None]):
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"bad output: {proc.stdout[:200]!r} {proc.stderr[:200]!r}")
        if isinstance(data, dict) and "error" in data:
            permanent = "Invalid" in data["error"] or "No event data found" in data["error"]
            if permanent or backoff is None:
                raise RuntimeError(data["error"])
            print(f"   retrying in {backoff}s ({data['error']})", file=sys.stderr)
            time.sleep(backoff)
            continue
        return data


def load_location_filter() -> dict | None:
    """Optional geo filter: {"latitude", "longitude", "radius_km"}.

    If location_filter.json exists, co-hosts are only registered from events
    whose coordinates fall within radius_km of the given point. Events
    without coordinates don't expand the host graph.
    """
    if LOCATION_FILE.exists():
        return json.loads(LOCATION_FILE.read_text())
    return None


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))


def event_in_area(event: dict, geo: dict | None) -> bool:
    if geo is None:
        return True
    coords = ((event.get("location") or {}).get("coordinates")) or {}
    lat, lon = coords.get("latitude"), coords.get("longitude")
    if lat is None or lon is None:
        return False
    return haversine_km(lat, lon, geo["latitude"], geo["longitude"]) <= geo["radius_km"]


def load_hosts() -> dict:
    if HOSTS_FILE.exists():
        return json.loads(HOSTS_FILE.read_text())
    return {}


def save_hosts(hosts: dict):
    DATA.mkdir(exist_ok=True)
    HOSTS_FILE.write_text(json.dumps(hosts, indent=2, ensure_ascii=False))


def load_seeds(hosts: dict):
    """Merge seed_hosts.txt into the host store at distance 0."""
    for line in SEEDS_FILE.read_text().splitlines():
        parts = line.strip().split("\t")
        url = norm_url(parts[-1]) if parts else ""
        if not url.startswith("http"):
            continue
        key = url.lower()
        if key not in hosts:
            hosts[key] = {"url": url, "name": None, "distance": 0, "scraped_at": None}
        else:
            hosts[key]["distance"] = 0


def register_host(hosts: dict, h: dict, distance: int):
    """Register a co-host discovered on an event; keep the smallest distance."""
    url = norm_url(h.get("url") or "")
    if not url:
        return
    key = url.lower()
    if key in hosts:
        hosts[key]["distance"] = min(hosts[key]["distance"], distance)
        hosts[key].setdefault("name", h.get("name"))
    else:
        hosts[key] = {
            "url": url,
            "name": h.get("name"),
            "fb_id": h.get("id"),
            "distance": distance,
            "scraped_at": None,
        }


def scrape_host(hosts: dict, key: str, include_past: bool, geo: dict | None):
    host = hosts[key]
    print(f"== {host.get('name') or host['url']} (distance {host['distance']})")
    # the numeric profile.php form works for both Pages and Users and never
    # trips the library's URL regex (vanity slugs with hyphens etc. do)
    url = (f"https://www.facebook.com/profile.php?id={host['fb_id']}"
           if host.get("fb_id") else host["url"])
    event_ids = []
    for etype in ["upcoming"] + (["past"] if include_past else []):
        try:
            listing = fetch("list", url, etype)
            event_ids += [e["id"] for e in listing]
            print(f"   {etype}: {len(listing)} events")
        except RuntimeError as e:
            print(f"   {etype}: ERROR {e}", file=sys.stderr)
        time.sleep(DELAY)

    host.setdefault("event_ids", [])
    for eid in event_ids:
        if eid not in host["event_ids"]:
            host["event_ids"].append(eid)
        event_file = EVENTS_DIR / f"{eid}.json"
        if event_file.exists():
            event = json.loads(event_file.read_text())
        else:
            try:
                event = fetch("event", eid)
            except RuntimeError as e:
                print(f"   event {eid}: ERROR {e}", file=sys.stderr)
                time.sleep(DELAY)
                continue
            EVENTS_DIR.mkdir(parents=True, exist_ok=True)
            event_file.write_text(json.dumps(event, indent=2, ensure_ascii=False))
            print(f"   saved event {eid}: {event.get('name')}")
            time.sleep(DELAY)
        if event_in_area(event, geo):
            for h in event.get("hosts") or []:
                register_host(hosts, h, host["distance"] + 1)

    host["scraped_at"] = datetime.now(timezone.utc).isoformat()
    save_hosts(hosts)


def cmd_scrape(args):
    hosts = load_hosts()
    load_seeds(hosts)
    save_hosts(hosts)
    geo = load_location_filter()
    if geo:
        print(f"location filter: {geo['radius_km']} km around "
              f"{geo['latitude']},{geo['longitude']}")
    todo = [
        k for k, h in sorted(hosts.items(), key=lambda kv: kv[1]["distance"])
        if h["distance"] <= args.max_distance
        and (args.rescrape or not h.get("scraped_at"))
    ]
    print(f"{len(todo)} hosts to scrape (max distance {args.max_distance})")
    for key in todo:
        scrape_host(hosts, key, args.past, geo)
    cmd_status(args)


def cmd_status(args):
    hosts = load_hosts()
    n_events = len(list(EVENTS_DIR.glob("*.json"))) if EVENTS_DIR.exists() else 0
    by_dist: dict[int, list] = {}
    for h in hosts.values():
        by_dist.setdefault(h["distance"], []).append(h)
    print(f"\n{len(hosts)} hosts, {n_events} events stored")
    for d in sorted(by_dist):
        group = by_dist[d]
        scraped = sum(1 for h in group if h.get("scraped_at"))
        print(f"  distance {d}: {len(group)} hosts ({scraped} scraped)")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("scrape", help="scrape hosts up to a distance")
    ps.add_argument("--max-distance", type=int, default=0)
    ps.add_argument("--past", action="store_true", help="also scrape past events")
    ps.add_argument("--rescrape", action="store_true", help="re-scrape already-scraped hosts")
    ps.set_defaults(func=cmd_scrape)
    pt = sub.add_parser("status", help="show host/event counts")
    pt.set_defaults(func=cmd_status)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
