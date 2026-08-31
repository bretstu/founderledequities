// GET /api/me -> { pro: bool }. The one question the frontend asks on load.
import { isPro, json } from "../_shared.js";

export async function onRequestGet({ request, env }) {
  const s = await isPro(env, request);
  return json(s.pro ? { pro: true, email: s.email } : { pro: false });
}
