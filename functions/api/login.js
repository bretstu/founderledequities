// Sign-in for a subscriber on a new device, by magic link.
// POST {email} -> if that email has a live subscription, a one-time link is
// mailed to it. The response is identical either way: this endpoint must not
// be usable to test which addresses subscribe.
// GET ?token=... -> redeem the link: set the cookie, burn the token.
import { subFor, PRO_STATUSES, makeCookie, site, redirect, json } from "../_shared.js";

export async function onRequestPost({ request, env }) {
  let email = "";
  try { email = ((await request.json()).email || "").trim().toLowerCase(); } catch {}
  const generic = json({ ok: true,
    message: "If that email has an active subscription, a sign-in link is on its way." });
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return generic;

  // configuration is checked BEFORE membership: a "not configured" answer
  // that only subscribers received would itself confirm who subscribes
  if (!env.RESEND_API_KEY) {
    return json({ ok: false,
      message: "Email sign-in isn't configured yet — write to hello@founderledequities.com and I'll sort you out." }, 503);
  }
  const sub = await subFor(env, email);
  if (!sub || !PRO_STATUSES.has(sub.status)) return generic;
  const token = [...crypto.getRandomValues(new Uint8Array(24))]
    .map((b) => b.toString(16).padStart(2, "0")).join("");
  await env.SUBS.put(`tok:${token}`, email, { expirationTtl: 900 });
  const link = `${site(env)}/api/login?token=${token}`;
  await fetch(`${env.RESEND_API_BASE || "https://api.resend.com"}/emails`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: "Founder Led Equities <signin@founderledequities.com>",
      to: [email],
      subject: "Your sign-in link",
      text: `Select this link to sign in — it works once and expires in 15 minutes:\n\n${link}\n\nIf you didn't request this, ignore it.`,
    }),
  });
  return generic;
}

export async function onRequestGet({ request, env }) {
  const token = new URL(request.url).searchParams.get("token") || "";
  if (!/^[0-9a-f]{48}$/.test(token)) return redirect(`${site(env)}/`);
  const email = await env.SUBS.get(`tok:${token}`);
  if (!email) return redirect(`${site(env)}/?signin=expired`);
  await env.SUBS.delete(`tok:${token}`);
  return redirect(`${site(env)}/?welcome=1`,
    { "Set-Cookie": await makeCookie(env, email) });
}
