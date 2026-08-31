// POST /api/webhook -- Stripe tells us what changed. The signature check is
// the whole security model here: without it, anyone could POST themselves a
// subscription.
import { verifyStripeSig, recordSub, json } from "../_shared.js";

export async function onRequestPost({ request, env }) {
  const raw = await request.text();
  if (!(await verifyStripeSig(env, request, raw))) {
    return json({ error: "bad signature" }, 400);
  }
  let event;
  try { event = JSON.parse(raw); } catch { return json({ error: "bad payload" }, 400); }
  const obj = event?.data?.object || {};

  if (event.type === "checkout.session.completed") {
    const email = obj?.customer_details?.email;
    if (obj.mode === "subscription" && email && obj.customer) {
      await recordSub(env, { email, customer: obj.customer, status: "active",
                             subscription: obj.subscription });
    }
  } else if (event.type === "customer.subscription.updated"
          || event.type === "customer.subscription.deleted") {
    // the subscription object carries no email; the customer id is the join
    const email = await env.SUBS.get(`cust:${obj.customer}`);
    if (email) {
      const status = event.type.endsWith("deleted") ? "canceled" : obj.status;
      await recordSub(env, { email, customer: obj.customer, status,
                             subscription: obj.id });
    }
  }
  return json({ received: true });
}
