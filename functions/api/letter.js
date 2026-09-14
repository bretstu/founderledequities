// THE LETTER, FROM THE ACCOUNT PAGE: is the signed-in reader on the Monday
// list, and turning it off or on. Resend holds the list; this only asks and
// tells it. A signed-in reader has proved the address, so joining from here
// needs no confirmation click.
//   GET  /api/letter          {on: true|false, email}
//   POST /api/letter {on}     turn it on (create or resubscribe, and join the
//                             segment) or off (unsubscribed: true)
import { readCookie, json } from "../_shared.js";

const RESEND = (env) => env.RESEND_API_BASE || "https://api.resend.com";

async function status(env, email) {
  const r = await fetch(`${RESEND(env)}/contacts/${encodeURIComponent(email)}`, {
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}` },
  });
  if (r.status === 404) return { exists: false, on: false };
  if (!r.ok) return { exists: false, on: false, error: r.status };
  const c = await r.json();
  return { exists: true, on: !c.unsubscribed };
}

export async function onRequestGet({ request, env }) {
  const email = await readCookie(env, request);
  if (!email) return json({ error: "sign in" }, 401);
  if (!env.RESEND_API_KEY) return json({ on: false, email, unavailable: true });
  const s = await status(env, email.toLowerCase());
  return json({ on: s.on, email: email.toLowerCase() });
}

export async function onRequestPost({ request, env }) {
  const email = await readCookie(env, request);
  if (!email) return json({ error: "sign in" }, 401);
  if (!env.RESEND_API_KEY) return json({ ok: false, message: "The list isn't available right now." }, 503);
  let body = {};
  try { body = await request.json(); } catch {}
  const on = !!body.on;
  const headers = { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" };
  const addr = email.toLowerCase();
  const s = await status(env, addr);
  let r;
  if (!s.exists) {
    if (!on) return json({ ok: true, on: false });
    r = await fetch(`${RESEND(env)}/contacts`, { method: "POST", headers, body: JSON.stringify({ email: addr, unsubscribed: false }) });
  } else {
    r = await fetch(`${RESEND(env)}/contacts/${encodeURIComponent(addr)}`, { method: "PATCH", headers, body: JSON.stringify({ unsubscribed: !on }) });
  }
  if (!r.ok) return json({ ok: false, message: "The list refused the change; write to hello@founderledequities.com." }, 502);
  if (on && env.RESEND_SEGMENT_ID) {
    await fetch(`${RESEND(env)}/contacts/${encodeURIComponent(addr)}/segments/${env.RESEND_SEGMENT_ID}`, { method: "POST", headers });
  }
  return json({ ok: true, on });
}
