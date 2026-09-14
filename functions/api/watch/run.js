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

function line(e) {
  const what = e.code === "P" ? "bought" : "sold";
  const amt = e.value ? ` ${money(e.value)} of` : "";
  const how = e.code === "P" ? "on the open market" : "at their own discretion";
  const stake = e.pct_after != null && e.pct_after !== "" ? ` They now own ${Number(e.pct_after).toFixed(Number(e.pct_after) < 1 ? 3 : 2)}%.` : "";
  return `${e.ceo} ${what}${amt} ${e.tk} ${how} on ${e.traded || e.filed}.${stake}`;
}

export async function onRequestPost({ request, env }) {
  if (!env.HITS || !env.ALERTS_KEY) return json({ error: "not configured" }, 503);
  let body = {};
  try { body = await request.json(); } catch { return json({ error: "bad json" }, 400); }
  if (!body.key || body.key !== env.ALERTS_KEY) return json({ error: "refused" }, 401);
  const events = (Array.isArray(body.events) ? body.events : []).filter((e) => e && e.tk && e.accession && (e.code === "P" || e.code === "S"));
  if (!events.length) return json({ ok: true, sent: 0, watchers: 0 });
  const tks = [...new Set(events.map((e) => String(e.tk).toUpperCase()))];
  const marks = tks.map((_, i) => `?${i + 1}`).join(",");
  const rows = await env.HITS.prepare(`SELECT id, email, tk, ceo, token FROM watches WHERE confirmed = 1 AND tk IN (${marks})`).bind(...tks).all();
  const watches = rows.results || [];
  if (!watches.length) return json({ ok: true, sent: 0, watchers: 0 });

  // what each watcher has not yet been told
  const byEmail = new Map();
  for (const w of watches) {
    const mine = events.filter((e) => String(e.tk).toUpperCase() === w.tk);
    for (const e of mine) {
      const seen = await env.HITS.prepare("SELECT 1 FROM alerts_sent WHERE watch_id = ?1 AND accession = ?2").bind(w.id, e.accession).first();
      if (seen) continue;
      if (!byEmail.has(w.email)) byEmail.set(w.email, { items: [], watches: new Map() });
      const b = byEmail.get(w.email);
      b.items.push({ e, w });
      b.watches.set(w.id, w);
    }
  }
  let sent = 0;
  for (const [email, b] of byEmail) {
    b.items.sort((x, y) => (y.e.value || 0) - (x.e.value || 0));
    const first = b.items[0].e;
    const subject = b.items.length === 1
      ? `${first.ceo} ${first.code === "P" ? "bought" : "sold"} ${first.tk}`
      : `${first.ceo} ${first.code === "P" ? "bought" : "sold"} ${first.tk}, and ${b.items.length - 1} more`;
    const stopLinks = [...b.watches.values()].map((w) => `<a href="${site(env)}/api/watch?stop=${w.token}" style="color:#8C8880;">stop watching ${esc(w.ceo || w.tk)}</a>`).join(" &middot; ");
    const paras = b.items.map(({ e }) => `<p style="font-size:15px;line-height:1.5;margin:0 0 12px;">${esc(line(e))}${e.url ? ` <a href="${esc(e.url)}" style="color:#1A1A1A;">The filing.</a>` : ""} <a href="${site(env)}/company/${esc(e.tk)}/" style="color:#1A1A1A;">The record.</a></p>`).join("");
    const html = `<!doctype html><html><body style="margin:0;padding:0;background:#ECE9E2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ECE9E2;"><tr><td align="center" style="padding:20px 10px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#F7F4EE;font-family:Helvetica,Arial,sans-serif;color:#1A1A1A;">
<tr><td style="padding:28px;">
<div style="font-family:Menlo,Consolas,monospace;font-size:10px;letter-spacing:.14em;color:#8C8880;">FOUNDER LED EQUITIES &middot; WATCH</div>
<h1 style="font-family:Georgia,'Times New Roman',serif;font-weight:normal;font-size:28px;line-height:1.15;margin:18px 0 14px;">${esc(subject)}.</h1>
${paras}
<div style="border-top:1px solid #D6D1C7;margin:22px 0 12px;"></div>
<p style="font-size:11px;line-height:1.5;color:#8C8880;margin:0;">You asked to be told when this person buys on the open market or sells at discretion; plans and compensation never come this way. ${stopLinks}. Nothing here is investment advice.</p>
</td></tr></table></td></tr></table></body></html>`;
    const text = b.items.map(({ e }) => line(e) + (e.url ? ` ${e.url}` : "") + ` ${site(env)}/company/${e.tk}/`).join("\n\n")
      + `\n\nYou asked to be told when this person buys on the open market or sells at discretion. Stop watching: `
      + [...b.watches.values()].map((w) => `${site(env)}/api/watch?stop=${w.token}`).join(" ");
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
