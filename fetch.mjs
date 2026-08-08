// Thin CLI wrapper around facebook-event-scraper.
// Usage:
//   node fetch.mjs list <page-or-profile-url> [upcoming|past]
//   node fetch.mjs event <event-id-or-url>
// Prints JSON to stdout; errors as {"error": ...} with exit code 1.
import {
  scrapeFbEvent,
  scrapeFbEventFromFbid,
  scrapeFbEventList,
  EventType,
} from 'facebook-event-scraper';

const [cmd, arg, sub] = process.argv.slice(2);

try {
  let result;
  if (cmd === 'list') {
    const type = sub === 'past' ? EventType.Past : EventType.Upcoming;
    result = await scrapeFbEventList(arg.replace(/\/+$/, ''), type);
  } else if (cmd === 'event') {
    result = arg.startsWith('http')
      ? await scrapeFbEvent(arg)
      : await scrapeFbEventFromFbid(arg);
  } else {
    throw new Error(`unknown command: ${cmd}`);
  }
  console.log(JSON.stringify(result));
} catch (err) {
  console.log(JSON.stringify({ error: String(err.message || err) }));
  process.exit(1);
}
