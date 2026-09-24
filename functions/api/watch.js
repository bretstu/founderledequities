// POST /api/watch {tk, ceo, email} -> a watch: an email when that chief
// executive's stake moves. Everything is free (2026-09-23; the paid tier is
// gone): any number of names, each confirmed by one click from the inbox,
// stopped by one click from any alert. The reserved name FOUNDERS is the
// live stream: every founder's move, within minutes of the filing, on the
// same confirm/stop machinery as any other watch.
// GET  /api/watch?confirm=<token> | ?stop=<token> | ?stopall=<token>
import { site, json, redirect } from "../_shared.js";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const clean = (s, n) => String(s || "").replace(/[\r\n]/g, " ").slice(0, n).trim();
const token = () => [...crypto.getRandomValues(new Uint8Array(24))].map(b => b.toString(16).padStart(2, "0")).join("");

async function ensure(env) {
  await env.HITS.prepare("CREATE TABLE IF NOT EXISTS watches (id INTEGER PRIMARY KEY, email TEXT NOT NULL, tk TEXT NOT NULL, ceo TEXT, confirmed INTEGER DEFAULT 0, token TEXT, created TEXT, UNIQUE(email, tk))").run();
}

async function send(env, to, subject, text, html) {
  // ONE KEY NAME (2026-09-24): this function alone read RESEND_KEY while
  // subscribe.js and watch/run.js read RESEND_API_KEY. With only the
  // latter configured, every confirmation email silently never sent, no
  // watch could ever confirm, and the whole alert product was dead with
  // no error anywhere. Both names work now.
  const key = env.RESEND_API_KEY || env.RESEND_KEY;
  if (!key) return;
  await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { "Authorization": `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from: env.MAIL_FROM || "Founder Led Equities <tape@founderledequities.com>", to, subject, text, html }),
  });
}

function shell(title, body, fine) {
  return `<div style="font-family:Georgia,serif;max-width:520px;margin:0 auto;padding:24px;color:#141413"><p style="font-size:17px;line-height:1.45;margin:0 0 12px">${title}</p>${body}<p style="font-size:12px;color:#8a8578;margin-top:20px">${fine}</p></div>`;
}
function button(link, label) {
  return `<p style="margin:18px 0"><a href="${link}" style="background:#141413;color:#faf9f5;padding:10px 18px;text-decoration:none;font-size:14px">${label}</a></p>`;
}

export async function onRequestPost({ request, env }) {
  if (!env.HITS) return json({ ok: false, message: "Not configured." }, 503);
  await ensure(env);
  let body = {};
  try { body = await request.json(); } catch (e) { /* empty */ }
  const tk = clean(body.tk, 12).toUpperCase();
  const ceo = clean(body.ceo, 80);
  if (!tk) return json({ ok: false, message: "Which company?" }, 400);
  const email = clean(body.email, 120).toLowerCase();
  if (!EMAIL.test(email)) return json({ ok: false, message: "An email address is needed." }, 400);
  const now = new Date().toISOString();
  const existing = await env.HITS.prepare("SELECT id, confirmed, token FROM watches WHERE email = ?1 AND tk = ?2").bind(email, tk).first();
  if (existing && existing.confirmed) return json({ ok: true, watching: true, message: `You're watching ${ceo || tk}.` });
  const t = existing ? existing.token : token();
  if (!existing) {
    await env.HITS.prepare("INSERT INTO watches (email, tk, ceo, confirmed, token, created) VALUES (?1, ?2, ?3, 0, ?4, ?5)")
      .bind(email, tk, ceo, t, now).run();
  }
  // every watch confirms by one click, like the letter
  const link = `${site(env)}/api/watch?confirm=${t}`;
  const what = tk === "FOUNDERS"
    ? "an email when any founder's stake moves 1% or more, usually within minutes of the SEC filing"
    : `an email when they buy on the open market or make a discretionary sale`;
  await send(env, email, `Confirm: watch ${ceo || tk}`,
    `One click and you're watching ${ceo || tk}${tk === "FOUNDERS" ? "" : ` (${tk})`}: ${what}.\n\n${link}\n\nIf you didn't ask for this, ignore it and nothing happens.`,
    shell(`One click and you're watching ${ceo || tk}.`,
      `<p style="font-size:14px;line-height:1.5;color:#5F5B55;margin:0;">${what.charAt(0).toUpperCase() + what.slice(1)}.</p>${button(link, "Confirm &rarr;")}`,
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
    await env.HITS.prepare("UPDATE watches SET confirmed = 1 WHERE id = ?1").bind(w.id).run();
    return redirect(w.tk === "FOUNDERS" ? `${site(env)}/alerts/?watch=on` : `${site(env)}/company/${w.tk}/?watch=on`);
  }
  if (stop && /^[0-9a-f]{48}$/.test(stop)) {
    const w = await env.HITS.prepare("SELECT id, tk FROM watches WHERE token = ?1").bind(stop).first();
    if (w) await env.HITS.prepare("DELETE FROM watches WHERE id = ?1").bind(w.id).run();
    return redirect(`${site(env)}/company/${w ? w.tk : ""}${w ? "/" : ""}?watch=off`);
  }
  // STOP EVERYTHING, one click from any alert, no sign-in: the token names
  // the person; every watch of theirs goes
  const stopall = u.searchParams.get("stopall");
  if (stopall && /^[0-9a-f]{48}$/.test(stopall)) {
    const w = await env.HITS.prepare("SELECT email, tk FROM watches WHERE token = ?1").bind(stopall).first();
    if (w) await env.HITS.prepare("DELETE FROM watches WHERE email = ?1").bind(w.email).run();
    return redirect(`${site(env)}/company/${w ? w.tk : ""}${w ? "/" : ""}?watch=alloff`);
  }
  // no sessions, no sign-in (2026-09-23): a watch is managed by the links in
  // its own emails, so there is no list to ask for
  return json({ watches: [] });
}
