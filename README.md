# event-aggregator

Scrapes **public** Facebook events from a seed list of organisers and recursively
expands the organiser graph via event co-hosts. Anonymous (logged-off) scraping
only — no login, no private events.

## How it works

- `fetch.mjs` — thin Node CLI over the
  [facebook-event-scraper](https://github.com/francescov1/facebook-event-scraper)
  npm library. `node fetch.mjs list <host-url> [upcoming|past]` lists a
  page/profile's hosted events; `node fetch.mjs event <id>` fetches full event
  details. JSON to stdout.
- `scrape.py` — all orchestration. Maintains a host graph where each host has a
  `distance` from the seed set (seeds = 0). Scraping a host lists its events,
  fetches each event's details, and registers every co-host of an (in-area)
  event at `distance + 1`. New hosts are never scraped until you raise
  `--max-distance`.

## Setup

```sh
sudo pacman -S nodejs npm   # or equivalent
npm install
```

Requires Python ≥ 3.10 (stdlib only).

## Input files (gitignored)

- `seed_hosts.txt` — one Facebook page/profile URL per line (tab-separated
  numbering allowed; the URL is taken from the last tab-separated column).
- `location_filter.json` *(optional)* — if present, co-hosts are only
  registered from events within `radius_km` of the point; events without
  coordinates don't expand the graph. Seeds are always scraped regardless.

  ```json
  { "latitude": 50.06097, "longitude": 19.94154, "radius_km": 10 }
  ```

## Usage

```sh
python3 scrape.py scrape                  # scrape seed (distance-0) hosts
python3 scrape.py scrape --max-distance 1 # also scrape discovered hosts
python3 scrape.py scrape --past           # include past events
python3 scrape.py scrape --rescrape       # re-scrape already-scraped hosts
python3 scrape.py status                  # host/event counts per distance
```

Discovered hosts are fetched via their numeric `profile.php?id=` URL (works
for both Pages and Users, and avoids the library's strict vanity-URL regex);
seeds use the URL from `seed_hosts.txt` directly.

## Browsing

```sh
python3 browse.py    # writes data/browse.html
```

Generates a self-contained event browser (no server needed) — open
`data/site/index.html` in a browser. Shows one day at a time (date picker +
prev/next, defaults to today); events outside the `location_filter.json`
radius and cancelled events are omitted. Rerun after each scrape.

### Hosting (Cloudflare Pages)

One-time: `npx wrangler login`. Then after each `browse.py` run:

```sh
npm run deploy    # -> https://<project-name>.pages.dev
```

The project name (and thus the URL) is set in the `deploy` script in
`package.json` — change `--project-name=krk-events` to your own; the
project is created automatically on first deploy.

Only `data/site/` (the single generated HTML file) is uploaded — never the
raw scraped data.

## Output (`data/`, gitignored)

- `data/hosts.json` — host graph: url, name, distance, scraped_at, event_ids.
- `data/events/<id>.json` — full event data (name, description, location with
  coordinates, timestamps, hosts, ticketUrl, …). Cached: an event on disk is
  never re-fetched, but its co-hosts are still (re-)registered each run.

## Notes & limits

- Logged-off Facebook only exposes ~8 upcoming events per page (the soonest
  ones) — fine for "what's on soon", not for archival.
- 0.5-second delay between requests (`DELAY` in `scrape.py`), with 15 s/60 s
  retry backoff on transient errors. If you hit persistent "temporarily
  blocked" errors, raise `DELAY` or configure a proxy (the underlying library
  supports Axios-style proxy options via `fetch.mjs`).
- Public events only; scraping private events or logging in violates Meta ToS
  and is out of scope.
