// GET /api/portal -> the Stripe customer portal: cancellation, card changes,
// invoices -- the entire account-management system, hosted by Stripe.
//
// OPEN ON THE SUBSCRIPTION, NOT THE LOBBY.
// The portal's home page is an overview -- plan summary, card, billing
// address, invoice history -- and "Cancel plan" sits one click deeper, on
// the subscription's own page. Someone who clicked "Account" meaning to
// cancel lands somewhere that does not obviously let them, and a
// cancellation a subscriber cannot find is a support email at best and a
// card dispute at worst. Stripe lets a session name its landing page, so
// this one opens where the buttons are. If the deep link is ever refused
// (an older portal configuration, a subscription we no longer hold), the
// plain portal is still better than an error.
import { isPro, stripe, site, redirect, json } from "../_shared.js";

export async function onRequestGet({ request, env }) {
  const s = await isPro(env, request);
  if (!s.email || !s.sub?.customer) return redirect(`${site(env)}/`);

  const base = { customer: s.sub.customer, return_url: `${site(env)}/` };
  let sub = s.sub.subscription;

  // subscribers recorded before this shipped have no subscription id stored;
  // ask Stripe once rather than making them find the deep page by hand
  if (!sub) {
    try {
      const list = await stripe(env, "GET",
        `/v1/subscriptions?customer=${encodeURIComponent(s.sub.customer)}&status=all&limit=1`);
      sub = list?.data?.[0]?.id;
    } catch (e) { /* fall through */ }
  }

  if (sub) {
    try {
      const deep = await stripe(env, "POST", "/v1/billing_portal/sessions", {
        ...base,
        "flow_data[type]": "subscription_update",
        "flow_data[subscription_update][subscription]": sub,
      });
      return redirect(deep.url);
    } catch (e) { /* fall back to the portal home */ }
  }
  try {
    const portal = await stripe(env, "POST", "/v1/billing_portal/sessions", base);
    return redirect(portal.url);
  } catch (e) {
    return json({ error: "portal unavailable — please try again shortly" }, 502);
  }
}
