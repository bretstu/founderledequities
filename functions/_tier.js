// The subscriber's first paint, shared by the home page and the company
// pages: read the signed session, and if the reader is a subscriber,
// rewrite the parts of the static page that say otherwise, in the stream.
// Anonymous readers get the static file untouched. No cookie is set.
import { isPro } from "./_shared.js";

export async function proPage(request, env, { hero = false } = {}) {
  const page = await env.ASSETS.fetch(request);
  let s = { pro: false };
  try { s = await isPro(env, request); } catch (e) { /* the free page is always right to show */ }
  if (!s.pro) return page;
  let rw = new HTMLRewriter()
    .on(".topnav button.gopro", { element(e) { e.setInnerContent("Account"); } })
    .on(".topnav a.gopro", { element(e) { e.setInnerContent("Account"); } });
  if (hero) {
    // the headline is the same sentence for everyone; the strip beneath it
    // carries the Pro numbers, stamped beside the free ones, and the
    // "N of them are sealed" note is not true for a subscriber
    rw = rw.on("div#herostats", { element(e) {
        const p = e.getAttribute("data-pro");
        if (p) e.setInnerContent(p, { html: true });
      } })
      .on("p#herosub span.sealnote", { element(e) { e.remove(); } });
  }
  const out = rw.transform(page);
  const h = new Headers(out.headers);
  h.set("Cache-Control", "private, no-store");
  return new Response(out.body, { status: out.status, headers: h });
}
