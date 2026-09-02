// POST /api/hit -> 204. The page's own count of real visits and clicks.
//
// WHY NOT THE HOST'S ANALYTICS. Cloudflare's dashboard counts every request
// for the HTML -- crawlers, scanners, link unfurlers -- and reported
// thousands of "unique visitors" for a site with no customers. Nothing here
// fires unless a browser ran the page's script, which is very nearly the
// definition of a person. No cookie, no email, no IP address is stored: a
// random visitor id the browser keeps for itself, a session id per tab, the
// country Cloudflare attaches, and what was looked at and clicked.
//
// Binding: a D1 database bound as HITS (Settings -> Bindings -> D1). Without
// it this function is a no-op, so the site never depends on it.

const BOT = /bot|crawl|spider|slurp|preview|fetch|curl|wget|python|httpclient|headless|lighthouse|monitor|scan|facebookexternalhit|twitterbot|discordbot|whatsapp|telegram/i;
const KINDS = new Set(["view", "section", "open", "click", "sort", "day", "window", "table", "switch"]);
const clip = (v, n) => (v === undefined || v === null ? "" : String(v)).slice(0, n);

export async function onRequestPost({ request, env }) {
  const ok = new Response(null, { status: 204 });
  if (!env.HITS) return ok;
  const ua = request.headers.get("User-Agent") || "";
  if (!ua || BOT.test(ua)) return ok;
  let body;
  try { body = await request.json(); } catch { return new Response("bad json", { status: 400 }); }
  const events = Array.isArray(body.events) ? body.events.slice(0, 60) : [];
  if (!events.length) return ok;
  const vid = clip(body.vid, 32), sid = clip(body.sid, 32);
  if (!vid || !sid) return ok;
  const pro = body.pro ? 1 : 0;
  const device = clip(body.device, 8) || "desktop";
  const country = clip(request.cf && request.cf.country, 2);
  const now = new Date();
  const ts = now.toISOString(), day = ts.slice(0, 10);
  const stmt = env.HITS.prepare(
    "INSERT INTO hits (ts, day, vid, sid, kind, name, detail, path, ref, country, pro, device) " +
    "VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)");
  const rows = [];
  for (const e of events) {
    const kind = clip(e.kind, 12);
    if (!KINDS.has(kind)) continue;
    rows.push(stmt.bind(ts, day, vid, sid, kind, clip(e.name, 40), clip(e.detail, 80),
                        clip(e.path, 120), clip(e.ref, 200), country, pro, device));
  }
  if (!rows.length) return ok;
  try { await env.HITS.batch(rows); } catch (err) {
    // a full or missing table must never surface to the reader
    console.log("hits: " + (err && err.message));
  }
  return ok;
}

export async function onRequestGet() {
  return new Response("POST only", { status: 405 });
}
