// THE SITE-WIDE SIGNUP (2026-09-24; PLAN.md section 5a): double opt-in,
// one address, one promise. POST {email} -> a confirmation link is
// mailed; nothing is added yet. GET ?token=... -> the click writes a
// confirmed FOUNDERS watch, which is the alert. The weekly letter left
// on 2026-09-29: the click no longer adds the address to a Resend
// segment; the contact is still created at the account level (harmless,
// and a list should a broadcast ever be wanted), but it is not what
// confirms. The response to POST is the same whatever the address, so
// the endpoint cannot be used to test which addresses are on the list.
import { site, redirect, json } from "../_shared.js";

const RESEND = (env) => env.RESEND_API_BASE || "https://api.resend.com";

// the site's look, in mail (design b, 2026-09-29): a grey panel on a near-white
// ground, a bold sans headline, one indigo button
const confirmHtml = (link) => `<!doctype html><html><body style="margin:0;padding:0;background:#FCFCFD;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#FCFCFD;"><tr><td align="center" style="padding:24px 10px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#E9EDF3;border:1px solid #D9DFE8;border-radius:12px;font-family:Inter,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;color:#0F172A;">
<tr><td style="padding:28px;">
<div style="font-size:10px;font-weight:600;letter-spacing:.06em;color:#94A3B8;">FOUNDER LED EQUITIES</div>
<h1 style="font-weight:700;letter-spacing:-.02em;font-size:26px;line-height:1.15;margin:16px 0 8px;">One click and you're on the list.</h1>
<p style="font-size:14px;line-height:1.55;color:#64748B;margin:0 0 20px;">One email: an alert when any founder&rsquo;s stake moves 1% or more, usually within minutes of the SEC filing. Every email carries its own one-click stop.</p>
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 22px;"><tr><td style="background:#4F46E5;border-radius:8px;"><a href="${link}" style="display:inline-block;padding:11px 22px;color:#FFFFFF;font-size:14px;font-weight:600;text-decoration:none;">Confirm &rarr;</a></td></tr></table>
<p style="font-size:11px;line-height:1.5;color:#94A3B8;margin:0;">The link works once and expires in a day. If you didn't ask for this, ignore it and nothing happens.</p>
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
      subject: `Confirm: founder moves, as they file (${new Date().toISOString().slice(0, 10)})`,
      text: `One click and you're on the list: an alert when any founder's stake moves 1% or more, usually within minutes of the SEC filing. Every email carries its own one-click stop. Confirm: ${link}

The link works once and expires in a day. If you didn't ask for this, ignore it and nothing happens.`,
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
  // THE WATCH IS THE SUBSCRIPTION (2026-09-29): the confirmed click writes a
  // confirmed FOUNDERS watch, and that write is what succeeds or fails. A
  // refused write is not a success: the page says so, and the token is
  // kept for a day so a fixed setting can retry the click.
  let ok = false;
  if (env.HITS) {
    try {
      await env.HITS.prepare("CREATE TABLE IF NOT EXISTS watches (id INTEGER PRIMARY KEY, email TEXT NOT NULL, tk TEXT NOT NULL, ceo TEXT, confirmed INTEGER DEFAULT 0, token TEXT, created TEXT, UNIQUE(email, tk))").run();
      const t = [...crypto.getRandomValues(new Uint8Array(24))].map((b) => b.toString(16).padStart(2, "0")).join("");
      await env.HITS.prepare("INSERT INTO watches (email, tk, ceo, confirmed, token, created) VALUES (?1, 'FOUNDERS', 'every founder', 1, ?2, ?3) ON CONFLICT(email, tk) DO UPDATE SET confirmed = 1")
        .bind(email, t, new Date().toISOString()).run();
      ok = true;
    } catch { ok = false; }
  }
  if (!ok) {
    await env.SUBS.put(`sub:${token}`, email, { expirationTtl: 86400 });
    return redirect(`${site(env)}/tape/?subscribed=error`);
  }
  // the Resend contact, best effort: a list at the account level, no segment
  // (the letter's segment add left with the letter). A failure here changes
  // nothing the reader was promised.
  if (env.RESEND_API_KEY) {
    try {
      await fetch(`${RESEND(env)}/contacts`, {
        method: "POST",
        headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({ email, unsubscribed: false }),
      });
    } catch { /* the watch stands */ }
  }
  return redirect(`${site(env)}/tape/?subscribed=1`);
}
