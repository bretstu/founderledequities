// GET /api/activate?session_id=... -- Stripe sends the buyer here after a
// successful checkout. Trust nothing in the URL: fetch the session from
// Stripe, confirm it is paid, and only then record the subscription and set
// the signed cookie. This also covers the race where the buyer arrives
// before the webhook does.
import { stripe, recordSub, makeCookie, site, redirect } from "../_shared.js";

export async function onRequestGet({ request, env }) {
  const id = new URL(request.url).searchParams.get("session_id") || "";
  if (!/^cs_[A-Za-z0-9_]+$/.test(id)) return redirect(`${site(env)}/`);
  try {
    const s = await stripe(env, "GET", `/v1/checkout/sessions/${id}`);
    const email = s?.customer_details?.email;
    if (s?.mode === "subscription" && s?.payment_status === "paid" && email && s?.customer) {
      await recordSub(env, { email, customer: s.customer, status: "active",
                             subscription: s.subscription });
      return redirect(`${site(env)}/?welcome=1`,
        { "Set-Cookie": await makeCookie(env, email) });
    }
  } catch (e) { /* fall through to the plain redirect */ }
  return redirect(`${site(env)}/`);
}
