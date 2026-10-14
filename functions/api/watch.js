// POST /api/watch {tk, ceo, email} -> a watch: an email when that chief
// executive's stake moves. Everything is free (2026-09-23; the paid tier is
// gone): any number of names, each confirmed by one click from the inbox,
// stopped by one click from any alert. The reserved name FOUNDERS is the
// live stream: every founder's move, within minutes of the filing, on the
// same confirm/stop machinery as any other watch.
// GET  /api/watch?confirm=<token> | ?stop=<token> | ?stopall=<token> | ?mine=<token>
// POST /api/watch {tk, ceo, t}      -> a watch from a signed-in browser: on at once
// POST /api/watch {signin: email}   -> a six-digit code mailed (and a link that signs a device in)
// POST /api/watch {code, email}     -> the code checked; the reader's token returned
//
// THE EMAIL IS THE ACCOUNT (2026-10-14). The site has no passwords. A reader
// is an address plus one sign-in token (the `readers` table); a browser
// that holds the token is signed in, and holds it only because something
// arrived in that inbox: the confirm click on a first watch, the "Your
// watches" link in any alert, or the six-digit code the sign-in page mails.
// Signed in, a watch is one click and no email field; the list at ?mine=
// shows every watch of the address, each with its own stop token (the
// per-watch tokens the alert footers carry are unchanged). A token never
// travels in the reply to a typed address: a typed address is not proof of
// owning it. ?mine= accepts a watch token too, so a browser that kept one
// from an alert's link is upgraded to the reader's.
import { site, json, redirect, readerToken } from "../_shared.js";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const TOKEN = /^[0-9a-f]{48}$/;
const clean = (s, n) => String(s || "").replace(/[\r\n]/g, " ").slice(0, n).trim();
const token = () => [...crypto.getRandomValues(new Uint8Array(24))].map(b => b.toString(16).padStart(2, "0")).join("");

async function ensure(env) {
  await env.HITS.prepare("CREATE TABLE IF NOT EXISTS watches (id INTEGER PRIMARY KEY, email TEXT NOT NULL, tk TEXT NOT NULL, ceo TEXT, confirmed INTEGER DEFAULT 0, token TEXT, created TEXT, UNIQUE(email, tk))").run();
  await env.HITS.prepare("CREATE TABLE IF NOT EXISTS readers (email TEXT PRIMARY KEY, token TEXT UNIQUE, created TEXT)").run();
}

// whose token is this: a reader's, or a confirmed watch's (an alert's link)
async function whose(env, t) {
  if (!TOKEN.test(t || "")) return "";
  const r = await env.HITS.prepare("SELECT email FROM readers WHERE token = ?1").bind(t).first();
  if (r) return r.email;
  const w = await env.HITS.prepare("SELECT email FROM watches WHERE token = ?1 AND confirmed = 1").bind(t).first();
  return w ? w.email : "";
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

// design b (2026-09-29): the confirm and stop pages in the site's look
function shell(title, body, fine) {
  return `<div style="font-family:Inter,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;max-width:520px;margin:32px auto;padding:28px;background:#E9EDF3;border:1px solid #D9DFE8;border-radius:12px;color:#0F172A"><p style="font-size:18px;font-weight:600;letter-spacing:-.01em;line-height:1.4;margin:0 0 12px">${title}</p>${body}<p style="font-size:12px;line-height:1.5;color:#94A3B8;margin:18px 0 0">${fine}</p></div>`;
}
function button(link, label) {
  return `<p style="margin:18px 0"><a href="${link}" style="display:inline-block;background:#4F46E5;color:#FFFFFF;padding:10px 18px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600">${label}</a></p>`;
}

export async function onRequestPost({ request, env }) {
  if (!env.HITS) return json({ ok: false, message: "Not configured." }, 503);
  await ensure(env);
  let body = {};
  try { body = await request.json(); } catch (e) { /* empty */ }

  // SIGN IN, STEP ONE: a six-digit code to the address, ten minutes, one
  // code a minute per address; the same reply whatever the address. The
  // mail also carries a link that signs in whichever browser opens it, for
  // a reader at a desk; the code is for the browser the reader is in,
  // which a link opened from a phone's mail app often is not.
  if (body.signin !== undefined) {
    const generic = json({ ok: true, message: "Check your inbox for a six-digit code." });
    const email = clean(body.signin, 120).toLowerCase();
    if (!EMAIL.test(email)) return json({ ok: false, message: "An email address is needed." }, 400);
    if (!env.SUBS) return json({ ok: false, message: "Not configured." }, 503);
    if (await env.SUBS.get(`codereq:${email}`)) return generic;
    await env.SUBS.put(`codereq:${email}`, "1", { expirationTtl: 60 });
    const code = String(crypto.getRandomValues(new Uint32Array(1))[0] % 1000000).padStart(6, "0");
    await env.SUBS.put(`code:${email}`, JSON.stringify({ code, tries: 0 }), { expirationTtl: 600 });
    const t = await readerToken(env, email);
    const link = `${site(env)}/alerts/?t=${t}`;
    await send(env, email, `${code} is your sign-in code`,
      `Your sign-in code for Founder Led Equities: ${code}\n\nIt works for ten minutes. Or open this link on the device you want signed in:\n${link}\n\nIf you didn't ask for this, ignore it and nothing happens.`,
      shell("Your sign-in code.",
        `<p style="font-family:'IBM Plex Mono',Menlo,Consolas,monospace;font-size:32px;font-weight:600;letter-spacing:.18em;margin:6px 0 10px;">${code}</p><p style="font-size:14px;line-height:1.5;color:#64748B;margin:0;">It works for ten minutes. Or open the link below on the device you want signed in.</p>${button(link, "Sign this device in &rarr;")}`,
        "If you didn't ask for this, ignore it and nothing happens."));
    return generic;
  }
  // SIGN IN, STEP TWO: the code, checked; five tries, then it is spent
  if (body.code !== undefined) {
    const email = clean(body.email, 120).toLowerCase();
    const code = clean(body.code, 12).replace(/\D/g, "");
    if (!EMAIL.test(email) || !env.SUBS) return json({ ok: false, message: "Start again." }, 400);
    const raw = await env.SUBS.get(`code:${email}`);
    const rec = raw ? JSON.parse(raw) : null;
    if (!rec) return json({ ok: false, message: "That code expired; ask for a new one." });
    if (rec.code !== code) {
      rec.tries = (rec.tries || 0) + 1;
      if (rec.tries >= 5) { await env.SUBS.delete(`code:${email}`); return json({ ok: false, message: "Five tries; ask for a new code." }); }
      await env.SUBS.put(`code:${email}`, JSON.stringify(rec), { expirationTtl: 600 });
      return json({ ok: false, message: "That isn't the code." });
    }
    await env.SUBS.delete(`code:${email}`);
    return json({ ok: true, email, token: await readerToken(env, email) });
  }

  const tk = clean(body.tk, 12).toUpperCase();
  const ceo = clean(body.ceo, 80);
  if (!tk) return json({ ok: false, message: "Which company?" }, 400);
  const now = new Date().toISOString();

  // A SIGNED-IN WATCH: the browser's token names the address; on at once
  if (body.t !== undefined) {
    const email = await whose(env, clean(body.t, 48));
    if (!email) return json({ ok: false, signedout: true, message: "Sign in again." }, 401);
    const existing = await env.HITS.prepare("SELECT id, confirmed FROM watches WHERE email = ?1 AND tk = ?2").bind(email, tk).first();
    if (existing) await env.HITS.prepare("UPDATE watches SET confirmed = 1 WHERE id = ?1").bind(existing.id).run();
    else await env.HITS.prepare("INSERT INTO watches (email, tk, ceo, confirmed, token, created) VALUES (?1, ?2, ?3, 1, ?4, ?5)").bind(email, tk, ceo, token(), now).run();
    return json({ ok: true, watching: true, message: `You're watching ${ceo || tk}.` });
  }

  const email = clean(body.email, 120).toLowerCase();
  if (!EMAIL.test(email)) return json({ ok: false, message: "An email address is needed." }, 400);
  const existing = await env.HITS.prepare("SELECT id, confirmed, token FROM watches WHERE email = ?1 AND tk = ?2").bind(email, tk).first();
  // THE TOKEN NEVER TRAVELS IN A POST REPLY (2026-10-14, same day). A known
  // address's watch is on at once, but whoever typed the address is not
  // necessarily its owner: the reply that carried the token handed the
  // address's whole list, and every stop, to anyone who knew the address.
  // A browser earns the token one way only, by opening a link that arrived
  // in the address's own inbox (the confirm click, "Your watches" in any
  // alert, or the sign-in code).
  if (existing && existing.confirmed) return json({ ok: true, watching: true, message: `You're watching ${ceo || tk}.` });
  const t = existing ? existing.token : token();
  // ONE CONFIRMATION PER ADDRESS (2026-10-14). The first stranger to want
  // alerts watched three companies in three minutes, got three emails each
  // asking for a click, and confirmed none. An address that has confirmed
  // any watch is known: its later watches are on at once, and every alert
  // carries its own stop link. The confirm click below also confirms every
  // watch the address had pending, so one click covers whatever they asked.
  const known = await env.HITS.prepare("SELECT 1 AS k FROM watches WHERE email = ?1 AND confirmed = 1 LIMIT 1").bind(email).first();
  if (known) {
    if (existing) await env.HITS.prepare("UPDATE watches SET confirmed = 1 WHERE id = ?1").bind(existing.id).run();
    else await env.HITS.prepare("INSERT INTO watches (email, tk, ceo, confirmed, token, created) VALUES (?1, ?2, ?3, 1, ?4, ?5)")
      .bind(email, tk, ceo, t, now).run();
    return json({ ok: true, watching: true, message: `You're watching ${ceo || tk}. Every alert has a stop link.` });
  }
  if (!existing) {
    await env.HITS.prepare("INSERT INTO watches (email, tk, ceo, confirmed, token, created) VALUES (?1, ?2, ?3, 0, ?4, ?5)")
      .bind(email, tk, ceo, t, now).run();
  }
  // the first watch from an address confirms by one click; the click
  // confirms everything pending for the address
  const link = `${site(env)}/api/watch?confirm=${t}`;
  const what = tk === "FOUNDERS"
    ? "an email when any founder's stake moves 1% or more, usually within minutes of the SEC filing"
    : `an email for any discretionary buy/sell, or any filing that moves their stake 1% or more`;
  await send(env, email, `Confirm: watch ${ceo || tk}`,
    `One click and you're watching ${ceo || tk}${tk === "FOUNDERS" ? "" : ` (${tk})`}: ${what}.\n\n${link}\n\nIf you didn't ask for this, ignore it and nothing happens.`,
    shell(`One click and you're watching ${ceo || tk}.`,
      `<p style="font-size:14px;line-height:1.5;color:#64748B;margin:0;">${(what.charAt(0).toUpperCase() + what.slice(1)).replace(", or any filing", ",<br>or any filing")}.</p>${button(link, "Confirm &rarr;")}`,
      "If you didn't ask for this, ignore it and nothing happens."));
  return json({ ok: true, watching: false, message: "Check your inbox: one click confirms it." });
}

export async function onRequestGet({ request, env }) {
  if (!env.HITS) return json({ ok: false }, 503);
  await ensure(env);
  const u = new URL(request.url);
  const confirm = u.searchParams.get("confirm"), stop = u.searchParams.get("stop");
  const asJson = u.searchParams.get("json") === "1";   // the watches page stops from a fetch, not a click
  if (confirm && TOKEN.test(confirm)) {
    const w = await env.HITS.prepare("SELECT id, tk, email FROM watches WHERE token = ?1").bind(confirm).first();
    if (!w) return redirect(`${site(env)}/?watch=expired`);
    // one click confirms this watch and every other the address had pending (2026-10-14)
    await env.HITS.prepare("UPDATE watches SET confirmed = 1 WHERE email = ?1 AND confirmed = 0").bind(w.email).run();
    // the landing carries the reader's token: the click came from the inbox, so the browser is signed in
    const t = await readerToken(env, w.email);
    return redirect(w.tk === "FOUNDERS" ? `${site(env)}/alerts/?watch=on&t=${t}` : `${site(env)}/company/${w.tk}/?watch=on&t=${t}`);
  }
  // YOUR WATCHES: every confirmed watch of the address this token belongs
  // to, with the address and the reader's own token (a browser that holds
  // a watch token from an alert's link is upgraded to it)
  const mine = u.searchParams.get("mine");
  if (mine && TOKEN.test(mine)) {
    const email = await whose(env, mine);
    if (!email) return json({ watches: [] });
    const rows = await env.HITS.prepare("SELECT tk, ceo, token, created FROM watches WHERE email = ?1 AND confirmed = 1 ORDER BY created").bind(email).all();
    return json({ email, token: await readerToken(env, email),
      watches: (rows.results || []).map((r) => ({ tk: r.tk, ceo: r.ceo || "", token: r.token, since: String(r.created || "").slice(0, 10) })) });
  }
  if (stop && TOKEN.test(stop)) {
    const w = await env.HITS.prepare("SELECT id, tk FROM watches WHERE token = ?1").bind(stop).first();
    if (w) await env.HITS.prepare("DELETE FROM watches WHERE id = ?1").bind(w.id).run();
    if (asJson) return json({ ok: true, stopped: w ? w.tk : null });
    // the founder stream has no company page: its stop lands on the alerts page (2026-10-14)
    if (w && w.tk === "FOUNDERS") return redirect(`${site(env)}/alerts/?watch=off`);
    return redirect(`${site(env)}/company/${w ? w.tk : ""}${w ? "/" : ""}?watch=off`);
  }
  // STOP EVERYTHING, one click from any alert, no sign-in: the token names
  // the person; every watch of theirs goes (a reader's token works too)
  const stopall = u.searchParams.get("stopall");
  if (stopall && TOKEN.test(stopall)) {
    const w = await env.HITS.prepare("SELECT email, tk FROM watches WHERE token = ?1").bind(stopall).first();
    const email = w ? w.email : await whose(env, stopall);
    if (email) await env.HITS.prepare("DELETE FROM watches WHERE email = ?1").bind(email).run();
    if (asJson) return json({ ok: true, stopped: "all" });
    if (!w || w.tk === "FOUNDERS") return redirect(`${site(env)}/alerts/?watch=alloff`);
    return redirect(`${site(env)}/company/${w.tk}/?watch=alloff`);
  }
  return json({ watches: [] });
}
