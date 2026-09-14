// WATCHES (PLAN.md sections 2 and 5): "email me if this founder buys on the
// open market or makes a discretionary sale." One watch is free; a list is
// Pro. The watches live in the D1 database bound as HITS (a `watches` table,
// created on first use); the pipeline never holds an address.
//
//   POST /api/watch        {tk, email?}   a free reader gives an email and
//                                          confirms by one click; a signed-in
//                                          Pro reader is watching at once
//   GET  /api/watch?confirm=<token>        the click: the watch is on
//   GET  /api/watch?stop=<token>           the link in every alert: off
//   GET  /api/watch?tk=NVDA                the signed-in reader's watches
//   POST /api/watch/run    {key, events}   THE NIGHTLY: today's open-market buys
//                                          and discretionary sales; one alert
//                                          per watcher, each filing sent once
import { isPro, readCookie, site, json, redirect, PRO_STATUSES } from "../_shared.js";

const FROM = "Founder Led Equities <tape@founderledequities.com>";
const RESEND = (env) => env.RESEND_API_BASE || "https://api.resend.com";
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

async function ensure(env) {
  await env.HITS.batch([
    env.HITS.prepare("CREATE TABLE IF NOT EXISTS watches (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL, tk TEXT NOT NULL, ceo TEXT, confirmed INTEGER NOT NULL DEFAULT 0, token TEXT NOT NULL, created TEXT NOT NULL, UNIQUE(email, tk))"),
    env.HITS.prepare("CREATE TABLE IF NOT EXISTS alerts_sent (watch_id INTEGER NOT NULL, accession TEXT NOT NULL, sent TEXT NOT NULL, PRIMARY KEY (watch_id, accession))"),
  ]);
}

const token = () => [...crypto.getRandomValues(new Uint8Array(24))].map((b) => b.toString(16).padStart(2, "0")).join("");
const clean = (s, n) => (s == null ? "" : String(s)).slice(0, n);

async function send(env, to, subject, text, html) {
  return fetch(`${RESEND(env)}/emails`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from: FROM, to: [to], subject, text, html }),
  });
}

// the site's look, in mail: paper, ink, a serif headline, one button
const shell = (title, body, footer) => `<!doctype html><html><body style="margin:0;padding:0;background:#ECE9E2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ECE9E2;"><tr><td align="center" style="padding:20px 10px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#F7F4EE;font-family:Helvetica,Arial,sans-serif;color:#1A1A1A;">
<tr><td style="padding:28px;">
<div style="font-family:Menlo,Consolas,monospace;font-size:10px;letter-spacing:.14em;color:#8C8880;">FOUNDER LED EQUITIES</div>
<h1 style="font-family:Georgia,'Times New Roman',serif;font-weight:normal;font-size:28px;line-height:1.15;margin:18px 0 10px;">${title}</h1>
${body}
<div style="border-top:1px solid #D6D1C7;margin:22px 0 12px;"></div>
<p style="font-size:11px;line-height:1.5;color:#8C8880;margin:0;">${footer}</p>
</td></tr></table></td></tr></table></body></html>`;

const button = (href, label) => `<table role="presentation" cellpadding="0" cellspacing="0" style="margin:16px 0 6px;"><tr><td style="background:#1A1A1A;"><a href="${href}" style="display:inline-block;padding:11px 22px;color:#F7F4EE;font-size:14px;font-weight:bold;text-decoration:none;">${label}</a></td></tr></table>`;

export async function onRequestPost({ request, env }) {
  if (!env.HITS) return json({ ok: false, message: "Watches aren't available yet." }, 503);
  await ensure(env);
  let body = {};
  try { body = await request.json(); } catch {}
  const tk = clean(body.tk, 12).toUpperCase().replace(/[^A-Z0-9.\-]/g, "");
  const ceo = clean(body.ceo, 80);
  if (!tk) return json({ ok: false, message: "Which company?" }, 400);
  const s = await isPro(env, request);
  const email = (s.email || clean(body.email, 120)).trim().toLowerCase();
  if (!EMAIL.test(email)) return json({ ok: false, message: "An email address is needed." }, 400);
  const now = new Date().toISOString();

  // ONE WATCH IS FREE (PLAN.md section 3, moment four): a second confirmed
  // watch on another name is where the list becomes Pro
  if (!s.pro) {
    const have = await env.HITS.prepare("SELECT tk, ceo FROM watches WHERE email = ?1 AND confirmed = 1 AND tk != ?2 LIMIT 1").bind(email, tk).first();
    if (have) {
      return json({ ok: false, pro: true,
        message: `You're watching ${have.ceo || have.tk}. A list of names is Pro.` });
    }
  }
  const existing = await env.HITS.prepare("SELECT id, confirmed, token FROM watches WHERE email = ?1 AND tk = ?2").bind(email, tk).first();
  if (existing && existing.confirmed) return json({ ok: true, watching: true, message: `You're watching ${ceo || tk}.` });
  const t = existing ? existing.token : token();
  if (!existing) {
    await env.HITS.prepare("INSERT INTO watches (email, tk, ceo, confirmed, token, created) VALUES (?1, ?2, ?3, ?4, ?5, ?6)")
      .bind(email, tk, ceo, s.pro ? 1 : 0, t, now).run();
  }
  if (s.pro) {
    if (existing) await env.HITS.prepare("UPDATE watches SET confirmed = 1 WHERE id = ?1").bind(existing.id).run();
    return json({ ok: true, watching: true, message: `You're watching ${ceo || tk}.` });
  }
  // a free reader confirms by one click, like the letter
  const link = `${site(env)}/api/watch?confirm=${t}`;
  await send(env, email, `Confirm: watch ${ceo || tk}`,
    `One click and you're watching ${ceo || tk} (${tk}): an email when they buy on the open market or make a discretionary sale.\n\n${link}\n\nIf you didn't ask for this, ignore it and nothing happens.`,
    shell(`One click and you're watching ${ceo || tk}.`,
      `<p style="font-size:14px;line-height:1.5;color:#5F5B55;margin:0;">An email when they buy on the open market or make a discretionary sale. Never for a plan or compensation.</p>${button(link, "Confirm &rarr;")}`,
      "If you didn't ask for this, ignore it and nothing happens."));
  return json({ ok: true, watching: false, message: "Check your inbox: one click confirms it." });
}

export async function onRequestGet({ request, env }) {
  if (!env.HITS) return json({ ok: false }, 503);
  await ensure(env);
  const u = new URL(request.url);
  const confirm = u.searchParams.get("confirm"), stop = u.searchParams.get("stop"), tk = u.searchParams.get("tk");
  if (confirm && /^[0-9a-f]{48}$/.test(confirm)) {
    const w = await env.HITS.prepare("SELECT id, tk, email FROM watches WHERE token = ?1").bind(confirm).first();
    if (!w) return redirect(`${site(env)}/?watch=expired`);
    // the free cap holds at the click too: a confirmation link for a second
    // name, opened by someone who is not Pro, lands on the plan
    const other = await env.HITS.prepare("SELECT tk FROM watches WHERE email = ?1 AND confirmed = 1 AND tk != ?2 LIMIT 1").bind(w.email, w.tk).first();
    if (other) {
      const sub = await env.SUBS.get(`sub:${w.email}`, "json");
      if (!sub || !PRO_STATUSES.has(sub.status)) return redirect(`${site(env)}/pro/?watch=second`);
    }
    await env.HITS.prepare("UPDATE watches SET confirmed = 1 WHERE id = ?1").bind(w.id).run();
    return redirect(`${site(env)}/company/${w.tk}/?watch=on`);
  }
  if (stop && /^[0-9a-f]{48}$/.test(stop)) {
    const w = await env.HITS.prepare("SELECT id, tk FROM watches WHERE token = ?1").bind(stop).first();
    if (w) await env.HITS.prepare("DELETE FROM watches WHERE id = ?1").bind(w.id).run();
    return redirect(`${site(env)}/company/${w ? w.tk : ""}${w ? "/" : ""}?watch=off`);
  }
  // the signed-in reader's watches (the box says "Watching" without asking)
  const email = await readCookie(env, request);
  if (!email) return json({ watches: [] });
  const rows = await env.HITS.prepare("SELECT tk, ceo FROM watches WHERE email = ?1 AND confirmed = 1 ORDER BY created").bind(email.toLowerCase()).all();
  const list = (rows.results || []).map((r) => ({ tk: r.tk, ceo: r.ceo }));
  return json({ watches: tk ? list.filter((w) => w.tk === tk.toUpperCase()) : list });
}
