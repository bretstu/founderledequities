// Sign out: the cookie is cleared; the subscription is untouched.
import { clearCookie, site, redirect } from "../_shared.js";

export async function onRequestGet({ env }) {
  return redirect(`${site(env)}/`, { "Set-Cookie": clearCookie() });
}
