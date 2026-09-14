// The Monday tape's signup (PLAN.md section 5a): double opt-in.
// POST {email} -> a confirmation link is mailed; nothing is added yet.
// GET ?token=... -> the click adds the address to the Resend audience.
// The response to POST is the same whatever the address, so the endpoint
// cannot be used to test which addresses are on the list.
import { site, redirect, json } from "../_shared.js";

const RESEND = (env) => env.RESEND_API_BASE || "https://api.resend.com";

// the site's look, in mail: paper, ink, a serif headline, one button
const confirmHtml = (link) => `<!doctype html><html><body style="margin:0;padding:0;background:#ECE9E2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ECE9E2;"><tr><td align="center" style="padding:20px 10px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#F7F4EE;font-family:Helvetica,Arial,sans-serif;color:#1A1A1A;">
<tr><td style="padding:28px;">
<div style="font-family:Menlo,Consolas,monospace;font-size:10px;letter-spacing:.14em;color:#8C8880;">FOUNDER LED EQUITIES</div>
<h1 style="font-family:Georgia,'Times New Roman',serif;font-weight:normal;font-size:30px;line-height:1.1;margin:18px 0 6px;">One click and you're on the list.</h1>
<p style="font-size:14px;line-height:1.5;color:#5F5B55;margin:0 0 18px;">The Monday tape: who bought, who cut a stake, who sold on a plan. Founders first. Every Monday.</p>
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 22px;"><tr><td style="background:#1A1A1A;"><a href="${link}" style="display:inline-block;padding:11px 22px;color:#F7F4EE;font-size:14px;font-weight:bold;text-decoration:none;">Confirm &rarr;</a></td></tr></table>
<p style="font-size:11px;line-height:1.5;color:#8C8880;margin:0;">The link works once and expires in a day. If you didn't ask for this, ignore it and nothing happens.</p>
</td></tr></table></td></tr></table></body></html>`;

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
      html: confirmHtml(link),
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
