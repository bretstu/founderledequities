// Shared plumbing for the payment functions. No dependencies: Stripe is a
// REST API and cookies are HMAC -- both within reach of fetch and WebCrypto,
// and a paywall this small should not carry a node_modules.

const enc = new TextEncoder();

export const b64u = (buf) =>
  btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

export const b64uDecode = (s) => {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  return atob(s + "=".repeat((4 - (s.length % 4)) % 4));
};

async function hmacKey(secret) {
  return crypto.subtle.importKey("raw", enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

export async function hmacHex(secret, msg) {
  const sig = await crypto.subtle.sign("HMAC", await hmacKey(secret), enc.encode(msg));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// ---- the session cookie: v1.<b64 email>.<expiry>.<hmac> -------------------
// The cookie says who you are; whether you are STILL a subscriber is asked
// of KV on every request, so a cancellation takes effect at the next click,
// not at cookie expiry.

const COOKIE = "fle_s";

export async function makeCookie(env, email, days = 30) {
  const exp = Math.floor(Date.now() / 1000) + days * 86400;
  const body = `${b64u(enc.encode(email.toLowerCase()))}.${exp}`;
  const sig = await hmacHex(env.SESSION_SECRET, body);
  return `${COOKIE}=v1.${body}.${sig}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=${days * 86400}`;
}

export const clearCookie = () =>
  `${COOKIE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0`;

export async function readCookie(env, request) {
  const raw = (request.headers.get("Cookie") || "")
    .split(/;\s*/).find((c) => c.startsWith(COOKIE + "="));
  if (!raw) return null;
  const parts = raw.slice(COOKIE.length + 1).split(".");
  if (parts.length !== 4 || parts[0] !== "v1") return null;
  const [, emailB64, expStr, sig] = parts;
  const body = `${emailB64}.${expStr}`;
  if (sig !== (await hmacHex(env.SESSION_SECRET, body))) return null;
  if (Number(expStr) < Date.now() / 1000) return null;
  try { return b64uDecode(emailB64).toLowerCase(); } catch { return null; }
}

// ---- subscription state ---------------------------------------------------
// past_due counts as subscribed: Stripe retries a failed card for days, and
// cutting someone off on the first retry punishes an expired card like a
// cancellation. unpaid / canceled are the real exits.

export const PRO_STATUSES = new Set(["active", "trialing", "past_due"]);

export async function subFor(env, email) {
  if (!email) return null;
  const raw = await env.SUBS.get(`sub:${email.toLowerCase()}`);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export async function isPro(env, request) {
  const email = await readCookie(env, request);
  if (!email) return { pro: false };
  const sub = await subFor(env, email);
  return { pro: !!sub && PRO_STATUSES.has(sub.status), email, sub };
}

export async function recordSub(env, { email, customer, status, subscription }) {
  email = email.toLowerCase();
  await env.SUBS.put(`cust:${customer}`, email);
  // keep a subscription id we already knew: subscription.updated carries one,
  // checkout.session.completed carries one, but neither is guaranteed
  const prev = await subFor(env, email);
  const sub = subscription || prev?.subscription;
  await env.SUBS.put(`sub:${email}`,
    JSON.stringify(sub ? { customer, status, subscription: sub }
                       : { customer, status }));
}

// ---- Stripe over plain REST ----------------------------------------------

export function stripeBase(env) {
  return env.STRIPE_API_BASE || "https://api.stripe.com";
}

export async function stripe(env, method, path, params) {
  const init = {
    method,
    headers: { Authorization: `Bearer ${env.STRIPE_SECRET_KEY}` },
  };
  if (params) {
    init.headers["Content-Type"] = "application/x-www-form-urlencoded";
    init.body = new URLSearchParams(params).toString();
  }
  const r = await fetch(`${stripeBase(env)}${path}`, init);
  const j = await r.json();
  if (!r.ok) throw new Error(j?.error?.message || `stripe ${r.status}`);
  return j;
}

// ---- webhook signature ----------------------------------------------------
// stripe-signature: t=<unix>,v1=<hex hmac of "<t>.<raw body>">

export async function verifyStripeSig(env, request, rawBody, toleranceSec = 300) {
  const header = request.headers.get("stripe-signature") || "";
  const kv = Object.fromEntries(header.split(",").map((p) => p.split("=")));
  const t = kv.t, v1 = kv.v1;
  if (!t || !v1) return false;
  if (Math.abs(Date.now() / 1000 - Number(t)) > toleranceSec) return false;
  const expected = await hmacHex(env.STRIPE_WEBHOOK_SECRET, `${t}.${rawBody}`);
  // constant-time-ish compare
  if (expected.length !== v1.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ v1.charCodeAt(i);
  return diff === 0;
}

export const json = (obj, status = 200, headers = {}) =>
  new Response(JSON.stringify(obj), {
    status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...headers },
  });

export const redirect = (url, headers = {}) =>
  new Response(null, { status: 302, headers: { Location: url, ...headers } });

export const site = (env) => (env.SITE_URL || "https://founderledequities.com").replace(/\/$/, "");
