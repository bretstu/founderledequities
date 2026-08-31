// GET /api/checkout -> a fresh Stripe Checkout session, then off to Stripe.
// Stripe hosts the payment page; card numbers never touch this site.
import { stripe, site, redirect, json } from "../_shared.js";

export async function onRequestGet({ env }) {
  try {
    const session = await stripe(env, "POST", "/v1/checkout/sessions", {
      mode: "subscription",
      "line_items[0][price]": env.PRICE_ID,
      "line_items[0][quantity]": "1",
      allow_promotion_codes: "true",
      // the activate step verifies payment server-side and sets the cookie,
      // so a fabricated ?welcome=1 unlocks nothing
      success_url: `${site(env)}/api/activate?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${site(env)}/`,
    });
    return redirect(session.url);
  } catch (e) {
    return json({ error: "checkout unavailable — please try again shortly" }, 502);
  }
}
