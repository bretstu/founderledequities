// The Monday tape's signup (PLAN.md section 5a): double opt-in.
// POST {email} -> a confirmation link is mailed; nothing is added yet.
// GET ?token=... -> the click adds the address to the Resend audience.
// The response to POST is the same whatever the address, so the endpoint
// cannot be used to test which addresses are on the list.
import { site, redirect, json } from "../_shared.js";

const RESEND = (env) => env.RESEND_API_BASE || "https://api.resend.com";

export async function onRequestPost({ request, env }) {
  let email = "";
  try { email = ((await request.json()).email || "").trim().toLowerCase(); } catch {}
  const generic = json({ ok: true, message: "Check your inbox: one click confirms it." });
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return generic;
  if (!env.RESEND_API_KEY) {
    return json({ ok: false, message: "The list isn't open yet; write to hello@founderledequities.com and I'll add you." }, 503);
  }
  // ONE CONFIRMATION PER ADDRESS PER TEN MINUTES. Five clicks, a reload, a
  // second tab: the first sends, the rest get the same reply and no mail.
  const seen = `subreq:${email}`;
  if (await env.SUBS.get(seen)) return generic;
  await env.SUBS.put(seen, "1", { expirationTtl: 600 });
  const token = [...crypto.getRandomValues(new Uint8Array(24))].map((b) => b.toString(16).padStart(2, "0")).join("");
  await env.SUBS.put(`sub:${token}`, email, { expirationTtl: 86400 });
  const link = `${site(env)}/api/subscribe?token=${token}`;
  await fetch(`${RESEND(env)}/emails`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: "Founder Led Equities <tape@founderledequities.com>",
      to: [email],
      subject: "Confirm: the Monday tape",
      text: `One click and you're on the list for the Monday tape: who bought, who cut a stake, who sold on a plan, founders first.\n\n${link}\n\nThe link works once and expires in a day. If you didn't ask for this, ignore it and nothing happens.`,
    }),
  });
  return generic;
}

export async function onRequestGet({ request, env }) {
  const token = new URL(request.url).searchParams.get("token") || "";
  if (!/^[0-9a-f]{48}$/.test(token)) return redirect(`${site(env)}/tape/`);
  const email = await env.SUBS.get(`sub:${token}`);
  if (!email) return redirect(`${site(env)}/tape/?subscribed=expired`);
  await env.SUBS.delete(`sub:${token}`);
  // Resend's audience is account-level now: one list, no audience id.
  // (RESEND_AUDIENCE_ID, if ever set, selects the older per-audience path.)
  const path = env.RESEND_AUDIENCE_ID ? `/audiences/${env.RESEND_AUDIENCE_ID}/contacts` : "/contacts";
  const r = await fetch(`${RESEND(env)}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ email, unsubscribed: false }),
  });
  // A REFUSED ADD IS NOT A SUCCESS. A sending-access key can mail the
  // confirmation and still be refused by the contacts endpoint; saying
  // "you're on the list" then would be false. The page says so instead,
  // and the token is kept for a day so a fixed key can retry the click.
  if (!r.ok) {
    await env.SUBS.put(`sub:${token}`, email, { expirationTtl: 86400 });
    return redirect(`${site(env)}/tape/?subscribed=error`);
  }
  return redirect(`${site(env)}/tape/?subscribed=1`);
}
