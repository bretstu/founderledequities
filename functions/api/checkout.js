// GET /api/checkout -> a fresh Stripe Checkout session, then off to Stripe.
// Stripe hosts the payment page; card numbers never touch this site.
import { stripe, site, redirect, json } from "../_shared.js";

export async function onRequestGet({ request, env }) {
  // THE PLAN (2026-09-18): $8 a month or $69 a year (PRICE_ID_MONTHLY / PRICE_ID_YEARLY in the environment), a card-backed
  // 14-day trial. ?plan=yearly picks the yearly price; anything else is
  // monthly. No fallback: a missing price is refused, not replaced.
  const url = new URL(request.url);
  const plan = url.searchParams.get("plan") === "yearly" ? "yearly" : "monthly";
  // the address, when the caller knows it (a signed-in reader, a link from the
  // letter), pre-fills Stripe's form: one click fewer between wanting and having
  const email = (url.searchParams.get("email") || "").trim().toLowerCase();
  const knows = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) && email.length < 200;
  const price = plan === "yearly" ? env.PRICE_ID_YEARLY : env.PRICE_ID_MONTHLY;
  if (!price) return json({ error: `the ${plan} price is not configured` }, 503);
  try {
    const session = await stripe(env, "POST", "/v1/checkout/sessions", {
      mode: "subscription",
      "line_items[0][price]": price,
      "line_items[0][quantity]": "1",
      "subscription_data[trial_period_days]": "14",
      payment_method_collection: "always",
      allow_promotion_codes: "true",
      ...(knows ? { customer_email: email } : {}),
      // the activate step verifies payment server-side and sets the cookie,
      // so a fabricated ?welcome=1 unlocks nothing
      success_url: `${site(env)}/api/activate?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${site(env)}/pro/`,
    });
    return redirect(session.url);
  } catch (e) {
    return json({ error: "checkout unavailable — please try again shortly" }, 502);
  }
}
