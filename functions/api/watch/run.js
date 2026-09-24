// THE ALERTS (PLAN.md section 5a): automatic, one fixed template, sent by the
// nightly. The pipeline posts the day's stake-moving decisions (open-market
// buys and discretionary sales, every CEO) with the shared secret; this
// function matches them against the confirmed watches, sends one email per
// watcher with everything of theirs that moved, and records each (watch,
// filing) so a filing is never sent twice. A plan or a compensation filing
// never reaches here: the pipeline does not post them.
import { site, json } from "../../_shared.js";

const FROM = "Founder Led Equities <tape@founderledequities.com>";
const RESEND = (env) => env.RESEND_API_BASE || "https://api.resend.com";

const money = (v) => {
  if (!v) return "";
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toFixed(1).replace(/\.0$/, "")}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(1).replace(/\.0$/, "")}M`;
  if (a >= 1e3) return `$${Math.round(v / 1e3)}K`;
  return `$${Math.round(v).toLocaleString()}`;
};
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
function longDay(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  if (!m) return iso || "";
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return `${DAYS[d.getUTCDay()]}, ${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
}
const num = (v) => (v === "" || v == null || isNaN(Number(v)) ? null : Number(v));
function dayLine(e) {
  const when = longDay(e.traded || e.filed);
  const sh = num(e.shares), mv = num(e.move);
  const bits = [];
  if (sh) bits.push(`${Math.round(Math.abs(sh)).toLocaleString("en-US")} shares`);
  if (mv != null && mv !== 0) bits.push(`${Math.abs(mv).toFixed(1)}% of their holding`);
  return bits.length ? `${when} \u00b7 ${bits.join(", ")}.` : `${when}.`;
}
function stakeLine(e) {
  const a = num(e.pct_after), bf = num(e.pct_before);
  const f = (x) => `${x.toFixed(x < 1 ? 3 : 2)}%`;
  if (a == null) return "";
  return bf != null && Math.abs(bf - a) > 0.0005 ? `They now own ${f(a)}, from ${f(bf)}.` : `They now own ${f(a)}.`;
}

export async function onRequestPost({ request, env }) {
  if (!env.HITS || !env.ALERTS_KEY) return json({ error: "not configured" }, 503);
  let body = {};
  try { body = await request.json(); } catch { return json({ error: "bad json" }, 400); }
  if (!body.key || body.key !== env.ALERTS_KEY) return json({ error: "refused" }, 401);
  const events = (Array.isArray(body.events) ? body.events : []).filter((e) => e && e.tk && e.accession && (e.sentence || e.code === "P" || e.code === "S"));
  if (!events.length) return json({ ok: true, sent: 0, watchers: 0 });
  const tks = [...new Set(events.map((e) => String(e.tk).toUpperCase()))];
  const marks = tks.map((_, i) => `?${i + 1}`).join(",");
  // LIVE FOUNDER ALERTS (2026-09-17): the reserved name FOUNDERS is a watch on
  // every founder; it matches every event the tape marks as a founder's
  const rows = await env.HITS.prepare(`SELECT id, email, tk, ceo, token FROM watches WHERE confirmed = 1 AND (tk IN (${marks}) OR tk = 'FOUNDERS')`).bind(...tks).all();
  const watches = rows.results || [];
  if (!watches.length) return json({ ok: true, sent: 0, watchers: 0 });

  // what each watcher has not yet been told; ONE EMAIL PER EVENT PER ADDRESS,
  // however many of a reader's watches it matches (a name and FOUNDERS both)
  const byEmail = new Map();
  for (const w of watches) {
    // TWO PROMISES (2026-09-24): a per-company watch takes every event of its
    // ticker; the site-wide FOUNDERS stream promises "moves the stake 1% or
    // more" and takes only events that clear that bar (move1 from the
    // pipeline; older posts without it fall back to the move field).
    const clears1 = (e) => (e.move1 != null ? !!Number(e.move1) : Math.abs(Number(e.move) || 0) >= 1);
    const mine = w.tk === "FOUNDERS" ? events.filter((e) => e.founder && clears1(e)) : events.filter((e) => String(e.tk).toUpperCase() === w.tk);
    for (const e of mine) {
      const seen = await env.HITS.prepare("SELECT 1 FROM alerts_sent WHERE watch_id = ?1 AND accession = ?2").bind(w.id, e.accession).first();
      if (seen) continue;
      if (!byEmail.has(w.email)) byEmail.set(w.email, { items: [], watches: new Map(), accs: new Set() });
      const b = byEmail.get(w.email);
      b.watches.set(w.id, w);
      if (b.accs.has(e.accession)) continue;
      b.accs.add(e.accession);
      b.items.push({ e, w });
    }
  }
  let sent = 0;
  for (const [email, b] of byEmail) {
    b.items.sort((x, y) => (y.e.value || 0) - (x.e.value || 0));
    const first = b.items[0].e;
    const short = (e) => (e.sentence || `${e.ceo} ${e.code === "P" ? "bought" : "sold"} ${e.tk}.`).replace(/ on \d{4}-\d{2}-\d{2}\.$/, ".").replace(/\.$/, "");
    // THE SUBJECT LEADS WITH THE TICKER (2026-09-18): alerts line up and sort in an inbox
    const shortNoCo = (e) => short(e).replace(new RegExp(` of ${(e.company || e.tk).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`), "");
    const subject = b.items.length === 1 ? `${first.tk} \u00b7 ${shortNoCo(first)}` : `${first.tk} \u00b7 ${shortNoCo(first)}, and ${b.items.length - 1} more`;
    const anyToken = [...b.watches.values()][0].token;
    // THE MAIL (2026-09-17): the headline, the day and the size of the move in
    // the person's own terms, the stake after and before, one link to the
    // page. The footer names the alert it came from and how to stop it.
    const ws = [...b.watches.values()];
    const liveW = ws.find((w) => w.tk === "FOUNDERS");
    const from = liveW && ws.length === 1 ? "Live founder alerts: every founder\u2019s move, as it is filed."
      : `Your watch on ${ws.filter((w) => w.tk !== "FOUNDERS").map((w) => esc(w.ceo || w.tk)).join(", ")}${liveW ? ", and live founder alerts" : ""}.`;
    const stopThese = ws.length === 1 ? `<a href="${site(env)}/api/watch?stop=${ws[0].token}" style="color:#8C8880;">Stop these</a>`
      : ws.map((w) => `<a href="${site(env)}/api/watch?stop=${w.token}" style="color:#8C8880;">stop ${w.tk === "FOUNDERS" ? "live founder alerts" : "watching " + esc(w.ceo || w.tk)}</a>`).join(" &middot; ");
    const blocks = b.items.map(({ e }) => `
<h1 style="font-family:Georgia,'Times New Roman',serif;font-weight:normal;font-size:26px;line-height:1.2;margin:16px 0 14px;">${esc(short(e))}.</h1>
${Array.isArray(e.facts) && e.facts.length
  ? `<table role="presentation" cellpadding="0" cellspacing="0" style="font-size:14px;line-height:1.5;margin:0 0 16px;border-collapse:collapse;">${e.facts.map(([k, v]) => `<tr><td style="padding:2px 18px 2px 0;color:#8C8880;white-space:nowrap;vertical-align:top;">${esc(k)}</td><td style="padding:2px 0;color:#1A1A1A;">${esc(v)}</td></tr>`).join("")}</table>`
  : `<p style="font-size:15px;line-height:1.6;margin:0 0 16px;">${esc(e.body || `${dayLine(e)} ${stakeLine(e)}`.trim())}</p>`}
<p style="font-size:15px;line-height:1.5;margin:0 0 22px;"><a href="${site(env)}/company/${esc(e.tk)}/" style="color:#1A1A1A;font-weight:bold;text-decoration:none;">${esc(e.company || e.tk)} on Founder Led Equities &rarr;</a></p>`).join("");
    const html = `<!doctype html><html><body style="margin:0;padding:0;background:#ECE9E2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ECE9E2;"><tr><td align="center" style="padding:20px 10px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#F7F4EE;font-family:Helvetica,Arial,sans-serif;color:#1A1A1A;">
<tr><td style="padding:26px 28px 22px;">
<div style="font-family:Menlo,Consolas,monospace;font-size:10px;letter-spacing:.14em;color:#8C8880;">FOUNDER LED EQUITIES</div>
${blocks}
<div style="border-top:1px solid #D6D1C7;margin:4px 0 12px;"></div>
<p style="font-size:11px;line-height:1.6;color:#8C8880;margin:0;">${from}<br>${stopThese} &middot; <a href="${site(env)}/api/watch?stopall=${anyToken}" style="color:#8C8880;">Stop everything</a> &middot; Nothing here is investment advice.</p>
</td></tr></table></td></tr></table></body></html>`;
    const text = b.items.map(({ e }) => `${short(e)}.\n${Array.isArray(e.facts) && e.facts.length ? e.facts.map(([k, v]) => `${k}: ${v}`).join("\n") : (e.body || `${dayLine(e)} ${stakeLine(e)}`.trim())}\n${site(env)}/company/${e.tk}/`).join("\n\n")
      + `\n\n${from.replace(/<[^>]+>/g, "")}\nStop these: ` + ws.map((w) => `${site(env)}/api/watch?stop=${w.token}`).join(" ")
      + `\nStop everything: ${site(env)}/api/watch?stopall=${anyToken}`;
    const r = await fetch(`${RESEND(env)}/emails`, {
      method: "POST",
      headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from: FROM, to: [email], subject, text, html }),
    });
    if (!r.ok) continue;
    sent++;
    const now = new Date().toISOString();
    await env.HITS.batch(b.items.map(({ e, w }) =>
      env.HITS.prepare("INSERT OR IGNORE INTO alerts_sent (watch_id, accession, sent) VALUES (?1, ?2, ?3)").bind(w.id, e.accession, now)));
  }
  return json({ ok: true, sent, watchers: byEmail.size, events: events.length });
}
