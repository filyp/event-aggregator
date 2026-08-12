#!/usr/bin/env python3
"""Generate data/browse.html — a self-contained event browser.

Reads data/events/*.json, drops events outside the location_filter.json
radius (if that file exists), embeds the rest as JSON in a single HTML page
with a date picker (default today). Rerun after scraping.
"""

import json
from pathlib import Path

from scrape import EVENTS_DIR, DATA, load_location_filter, event_in_area

OUT = DATA / "site" / "index.html"

TEMPLATE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>events</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; background: #fafafa; color: #222; }
  .bar { display: flex; gap: .5rem; align-items: center; margin-bottom: 1.5rem; }
  .bar input { font-size: 1.1rem; padding: .3rem; }
  .bar button { font-size: 1.1rem; padding: .3rem .7rem; cursor: pointer; }
  .ev { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: .8rem 1rem; margin-bottom: .8rem; cursor: pointer; }
  .ev a { color: inherit; text-decoration: none; font-weight: 600; font-size: 1.05rem; }
  .ev a:hover { text-decoration: underline; }
  .meta { color: #666; font-size: .9rem; margin-top: .3rem; }
  .hosts { color: #888; font-size: .85rem; margin-top: .2rem; }
  .tickets { font-size: .85rem; margin-top: .3rem; }
  details summary { cursor: pointer; color: #888; font-size: .85rem; margin-top: .4rem; list-style: none; }
  details summary::before { content: '▸ '; }
  details[open] summary::before { content: '▾ '; }
  .desc { white-space: pre-wrap; font-size: .95rem; margin-top: .6rem; line-height: 1.45; }
  .photo { max-width: 100%; border-radius: 6px; margin-top: .6rem; display: block; }
  #none { color: #888; text-align: center; margin-top: 3rem; }
  @media (prefers-color-scheme: dark) {
    body { background: #1a1a1a; color: #ddd; }
    .ev { background: #242424; border-color: #3a3a3a; }
    .meta { color: #999; } .hosts { color: #777; }
  }
</style>
<div class="bar">
  <button id="prev">&larr;</button>
  <input type="date" id="day">
  <button id="next">&rarr;</button>
  <span id="count"></span>
</div>
<div id="list"></div>
<p id="none" hidden>no events this day</p>
<script>
const EVENTS = __EVENTS__;

const day = document.getElementById('day');
const esc = s => s.replace(/[&<>"']/g, c => '&#' + c.charCodeAt(0) + ';');
const fmtTime = ts => new Date(ts * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
const localDate = ts => {
  const d = new Date(ts * 1000);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
};

function render() {
  const sel = day.value;
  const evs = EVENTS.filter(e => localDate(e.start) === sel).sort((a, b) => a.start - b.start);
  document.getElementById('list').innerHTML = evs.map(e => `
    <div class="ev">
      <a href="${esc(e.url)}" target="_blank">${esc(e.name)}</a>
      <div class="meta">${fmtTime(e.start)}${e.venue ? ' · ' + esc(e.venue) : ''}</div>
      ${e.hosts.length ? `<div class="hosts">by ${esc(e.hosts.join(', '))}</div>` : ''}
      ${e.ticketUrl ? `<div class="tickets"><a href="${esc(e.ticketUrl)}" target="_blank">tickets</a></div>` : ''}
      ${e.photo || e.desc ? `<details><summary>details</summary>
        ${e.photo ? `<img class="photo" loading="lazy" src="${esc(e.photo)}">` : ''}
        ${e.desc ? `<div class="desc">${esc(e.desc)}</div>` : ''}
      </details>` : ''}
    </div>`).join('');
  document.getElementById('none').hidden = evs.length > 0;
  document.getElementById('count').textContent = evs.length ? evs.length + ' events' : '';
}

function shift(days) {
  const d = new Date(day.value + 'T12:00');
  d.setDate(d.getDate() + days);
  day.value = localDate(d.getTime() / 1000);
  render();
}

document.getElementById('list').addEventListener('click', ev => {
  if (ev.target.closest('a, summary, details[open]')) return;
  const det = ev.target.closest('.ev')?.querySelector('details');
  if (det) det.open = !det.open;
});

day.value = localDate(Date.now() / 1000);
day.onchange = render;
document.getElementById('prev').onclick = () => shift(-1);
document.getElementById('next').onclick = () => shift(1);
render();
</script>
"""


def main():
    geo = load_location_filter()
    events = []
    seen = set()
    for f in sorted(EVENTS_DIR.glob("*.json")):
        e = json.loads(f.read_text())
        if not event_in_area(e, geo):
            continue
        if not e.get("startTimestamp") or e.get("isCanceled"):
            continue
        # dedupe: recurring events are saved under both the series id and the
        # occurrence id, and venues sometimes double-post identical events
        keys = {e["id"], (e["name"].strip(), e["startTimestamp"])}
        if keys & seen:
            continue
        seen |= keys
        events.append({
            "name": e["name"],
            "start": e["startTimestamp"],
            "url": e["url"],
            "venue": ((e.get("location") or {}).get("name")) or "",
            "hosts": [h["name"] for h in e.get("hosts") or []],
            "ticketUrl": e.get("ticketUrl") or "",
            "desc": e.get("description") or "",
            "photo": ((e.get("photo") or {}).get("imageUri")) or "",
        })
    page = TEMPLATE.replace("__EVENTS__", json.dumps(events, ensure_ascii=False)
                            .replace("</", "<\\/"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page)
    print(f"{len(events)} events -> {OUT}")


if __name__ == "__main__":
    main()
