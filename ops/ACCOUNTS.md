# Accounts & recovery

Every account the business stands on, how to get in, and what to do when
a login or reset email never arrives. Written for a future person who has
forgotten how all of this is wired. Keep this file boring and current.

The one rule: every account here uses authenticator-app 2FA, and the
backup codes live in the password manager. Backup codes are the recovery
path that works when everything else is broken.

---

## How email works here (read this first)

Addresses at founderledequities.com are NOT mailboxes. They forward:

    anything@founderledequities.com
      -> Cloudflare Email Routing (dash -> founderledequities.com -> Email)
      -> bret.1.stuart@gmail.com

So "the email never arrived" almost always means one of:
1. It's in Gmail spam (search: to:hello@founderledequities.com)
2. The Cloudflare route was deleted/disabled, or the destination
   address became unverified (Cloudflare dash -> Email -> Email Routing)
3. The domain lapsed (renews Aug 2027 -- auto-renew must stay ON)

Quick test: send a mail to hello@founderledequities.com from anywhere.
If it lands in Gmail, the chain is fine; retry whatever you were doing.

Outbound mail (sign-in links to subscribers) is separate: Resend, from
signin@founderledequities.com. Routing being broken does not affect it,
and vice versa.

---

## X / Twitter (@founderledequities)

- Login: hello@founderledequities.com + password (in password manager)
- 2FA: authenticator app. Backup codes: in password manager.
- Email is only needed for resets and notifications, never for daily login.

Reset email never arrives:
1. Gmail spam
2. Cloudflare Email Routing check (above)
3. Still stuck: log in with a 2FA backup code -- works with email dead.

## Cloudflare (account f5a0a1e71ccbe577c214af474c43063c)

Holds: the domain, DNS, Pages (the site), KV (subscriptions),
Email Routing, secrets. This is the load-bearing account.

- Login: bret.1.stuart@gmail.com
- 2FA: authenticator app. Backup codes: in password manager.
- Domain founderledequities.com: auto-renew ON, renews 2027-08.

## Stripe (live payments)

- Login: bret.1.stuart@gmail.com
- 2FA + backup codes: password manager.
- Webhook + API keys are set as Pages secrets; rotating them is in
  ops/PAYMENTS.md.

## Resend (sign-in emails)

- Login: bret.1.stuart@gmail.com
- Sends as signin@founderledequities.com (DKIM on the root domain).
- If sign-in emails stop: Resend dash -> Logs says why in one line.

## Google (bret.1.stuart@gmail.com)

The end of every chain above. If this is lost, everything is hard.
- 2FA: authenticator app. Backup codes: in password manager.
- Recovery phone/email: keep current -- check once a year.

---

## When adding any new account

1. Register with hello@founderledequities.com if it's a brand asset,
   the Gmail if it's infrastructure.
2. Authenticator-app 2FA, never SMS.
3. Save backup codes to the password manager immediately.
4. Add a section here before closing the tab.
