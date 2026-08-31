# Payments: wiring, testing, going live

The shape: Stripe hosts checkout and the account portal; six small Pages
Functions (in `functions/`) connect them to the site; Workers KV remembers
who subscribes; the full CSVs sit behind `/pro/*` and are served only to a
live subscription. Cancel a subscription and the gate closes at the next
click, not at cookie expiry.

## One-time wiring (~20 minutes, all in TEST mode first)

1. **KV namespace** (remembers subscribers):
   `wrangler kv namespace create fle-subs`
   Then bind it: dashboard -> Workers & Pages -> founderledequities ->
   Settings -> Bindings -> Add -> KV namespace ->
   variable name `SUBS`, namespace `fle-subs`. (Both Production and Preview.)

2. **Secrets** (each command prompts for the value; nothing lands in a file):
   ```
   wrangler pages secret put STRIPE_SECRET_KEY   --project-name founderledequities   # sk_test_... for now
   wrangler pages secret put SESSION_SECRET      --project-name founderledequities   # output of: openssl rand -hex 32
   wrangler pages secret put PRICE_ID            --project-name founderledequities   # price_... (TEST-mode price!)
   wrangler pages secret put SITE_URL            --project-name founderledequities   # https://founderledequities.com
   ```
   (STRIPE_WEBHOOK_SECRET comes in step 4; RESEND_API_KEY is optional, step 6.)

3. **Deploy** so the functions exist: `./ops/deploy.sh`

4. **Webhook** (Stripe -> Developers -> Webhooks -> Add endpoint, in TEST mode):
   - URL: `https://founderledequities.com/api/webhook`
   - Events: `checkout.session.completed`,
     `customer.subscription.updated`, `customer.subscription.deleted`
   - Copy the signing secret (`whsec_...`) and:
     `wrangler pages secret put STRIPE_WEBHOOK_SECRET --project-name founderledequities`
   - Redeploy: `./ops/deploy.sh` (secrets apply to new deployments)

5. **Customer portal** (Stripe -> Settings -> Billing -> Customer portal):
   activate; allow customers to cancel subscriptions.

6. **Sign-in email, optional but recommended** (for subscribers on a second
   device): create a free resend.com account, verify the domain (it gives
   you DNS records; add them in Cloudflare DNS), then
   `wrangler pages secret put RESEND_API_KEY --project-name founderledequities`
   and redeploy. Until this is set, sign-in shows a "write to hello@" notice;
   purchases themselves need no email service.

## The test-mode dress rehearsal

In a private browser window on the live domain:

1. Go Pro -> checkout opens on Stripe. Card `4242 4242 4242 4242`,
   any future expiry, any CVC, any ZIP.
2. Land back on the site with the welcome toast; locks gone; nav says
   Account; `/pro/events.csv` loads (Network tab: 200).
3. Account -> portal opens -> cancel the subscription.
4. Reload the site: locks back, filters gated, `/pro/events.csv` 401.
5. Buy again (test money is free); sign out isn't a thing -- clear cookies
   and use the sign-in link instead if RESEND is configured.

If all five hold, the machine works.

## Going live (~10 minutes)

1. Stripe: flip to LIVE mode. Create the same product/price (live objects
   are separate); enable the customer portal in live mode; create the same
   webhook endpoint in live mode.
2. Rotate the three Stripe-side secrets to their live values:
   `STRIPE_SECRET_KEY` (sk_live_...), `PRICE_ID` (the live price_...),
   `STRIPE_WEBHOOK_SECRET` (the live whsec_...).
3. `./ops/deploy.sh`
4. Buy a real subscription yourself with a real card -- customer #1 proves
   the live loop -- then refund yourself from the Stripe dashboard if you
   like (or don't: $5/month to your own project is a fine tradition).

## Day-2 notes

- **Refunds**: Stripe dashboard -> Payments -> refund. The 7-day promise is
  on terms.html; honour it fast and unprompted.
- **Who subscribes**: Stripe -> Customers is the truth; KV mirrors it.
- **If the webhook ever misses** (outage): the activate step already covers
  purchases; for cancellations, Stripe retries webhooks for days. A manual
  fix is: delete the `sub:<email>` key in KV, or re-send the event from the
  Stripe dashboard.
- **Never** commit or paste sk_/whsec_ values anywhere; rotate them in the
  Stripe dashboard if one ever leaks.
