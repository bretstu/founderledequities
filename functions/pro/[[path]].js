// The gate. /pro/* holds the full data files as ordinary static assets, and
// this function stands in front of every request to them: a live signed
// cookie AND a live subscription in KV, or a 401. ASSETS.fetch serves the
// underlying file without re-entering this function.
import { isPro, json } from "../_shared.js";

export async function onRequest({ request, env }) {
  const s = await isPro(env, request);
  if (!s.pro) return json({ error: "subscription required" }, 401);
  return env.ASSETS.fetch(request);
}
