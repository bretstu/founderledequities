// GET /api/checkout -> a fresh Stripe Checkout session, then off to Stripe.
// Stripe hosts the payment page; card numbers never touch this site.
import { stripe, site, redirect, json } from "../_shared.js";

export async function onRequestGet({ request, env }) {
  // THE PLAN (PLAN.md section 2): $15 a month or $150 a year, a card-backed
  // 14-day trial. ?plan=yearly picks the yearly price; anything else is
  // monthly. No fallback: a missing price is refused, not replaced.
  const plan = new URL(request.url).searchParams.get("plan") === "yearly" ? "yearly" : "monthly";
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
