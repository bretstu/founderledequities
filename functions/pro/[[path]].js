// The gate. /pro/* holds the full data files as ordinary static assets, and
// this function stands in front of every request to them: a live signed
// cookie AND a live subscription in KV, or a 401. ASSETS.fetch serves the
// underlying file without re-entering this function.
import { isPro, json } from "../_shared.js";

export async function onRequest({ request, env }) {
  // THE PLAN PAGE IS NOT BEHIND ITS OWN PAYWALL. /pro/ (and /pro/index.html)
  // is the page that sells the subscription; only the data files under
  // the prefix are gated.
  const path = new URL(request.url).pathname;
  if (path === "/pro" || path === "/pro/" || path === "/pro/index.html") return env.ASSETS.fetch(request);
  const s = await isPro(env, request);
  if (!s.pro) return json({ error: "subscription required" }, 401);
  return env.ASSETS.fetch(request);
}
