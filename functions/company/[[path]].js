// GET /company/* -> the static company page, with "Account" in the nav
// for a subscriber from the first byte instead of after /api/me answers.
import { proPage } from "../_tier.js";

export async function onRequestGet({ request, env }) {
  return proPage(request, env);
}
