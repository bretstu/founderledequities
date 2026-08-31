# Going live, and staying live

The shape: **the mini PC builds, Cloudflare serves.** The box runs the
nightly pipeline and pushes static files to Cloudflare Pages; the site is
on a CDN with your domain in front of it. If the box dies, the site stays
up with yesterday's data -- staleness, never downtime.

## One-time setup (roughly an hour)

1. On the mini PC: clone/copy this folder, `pip install -r requirements.txt`,
   set a real contact address in `ops/fle-refresh.service` (EDGAR requires it).
2. `npm install -g wrangler && wrangler login`
   `wrangler pages project create founderledequities`
3. Run it once by hand, end to end:
   `python3 -m fle.cli refresh --dir . && ops/deploy.sh`
   You should get a *.pages.dev URL with the live site.
4. Cloudflare dashboard -> Pages -> founderledequities -> Custom domains
   -> add founderledequities.com (DNS is already there; it wires itself).
5. Install the schedule:
   `sudo cp ops/fle-refresh.{service,timer} /etc/systemd/system/`
   `sudo systemctl daemon-reload && sudo systemctl enable --now fle-refresh.timer`
6. Cloudflare Email Routing (free): create corrections@ and hello@
   forwarding to your real inbox. Two clicks; the site already links them.
7. Optional but worth it: a free healthchecks.io check, its URL in
   FLE_HEARTBEAT_URL, expected daily. It emails you when a night fails.
8. Optional: Cloudflare Web Analytics (free, no cookies) -- one script tag,
   and you can see whether anyone is coming.

## The guarantees you already have

- The refresh publishes atomically and refuses to publish if a verified
  holding moves (`refresh.log` says why). Yesterday's site stays live.
- `--force` overrides the gate once you've checked a change by hand.
- Serving is decoupled from building: a dead box costs freshness only.

## What this does NOT cover yet

- Payments and accounts (Stripe) -- see the plan in the project notes.
- Real gating: today every CSV is public and ?pro=1 unlocks the preview.
  Fine for the validation phase; must change the day money changes hands.
