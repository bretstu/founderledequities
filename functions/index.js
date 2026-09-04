// GET / -> index.html, with the Pro hero already in it for a subscriber.
//
// THE FIRST PAINT IS THE RIGHT PAINT. index.html is stamped at deploy with
// the free numbers (19 of 500) for everyone and search engines, and carries
// the Pro numbers (199 of 2,135) in data-pro attributes beside them. A
// subscriber used to see the free hero for seconds, then watch it change,
// because the page could not know who was reading until /api/me and a
// 1.3MB universe file had come back. This function knows: it reads the same
// signed session the /pro/* gate reads, and if the reader is a subscriber
// it rewrites the hero, the stat strip and the nav button in the stream.
// Anonymous readers get the static file untouched, and no cookie is ever
// set here -- the page's own privacy rule (no cookie for the counter)
// holds. The rewritten response is private and uncached.
import { isPro } from "./_shared.js";

const SENTENCE = (n, of) =>
  `<b>${n}</b> of ${of} chief executives own more than 5% of the company they run.`;

export async function onRequestGet({ request, env }) {
  const page = await env.ASSETS.fetch(request);
  let s = { pro: false };
  try { s = await isPro(env, request); } catch (e) { /* the free page is always right to show */ }
  if (!s.pro) return page;
  const out = new HTMLRewriter()
    .on("h1#thesis", { element(e) {
      const p = (e.getAttribute("data-pro") || "").split("|");
      if (p.length === 2 && p[0] && p[1]) e.setInnerContent(SENTENCE(p[0], p[1]), { html: true });
    } })
    .on("div#herostats", { element(e) {
      const p = e.getAttribute("data-pro");
      if (p) e.setInnerContent(p, { html: true });
    } })
    .on(".topnav button.gopro", { element(e) { e.setInnerContent("Account"); } })
    .transform(page);
  const h = new Headers(out.headers);
  h.set("Cache-Control", "private, no-store");
  return new Response(out.body, { status: out.status, headers: h });
}
