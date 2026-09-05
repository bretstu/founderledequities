// GET / -> index.html, with the Pro hero already in it for a subscriber.
//
// THE FIRST PAINT IS THE RIGHT PAINT. index.html is stamped at deploy with
// the free numbers (19 of 500) for everyone and search engines, and carries
// the Pro numbers (199 of 2,100) in data-pro attributes beside them. A
// subscriber used to see the free hero for seconds, then watch it change,
// because the page could not know who was reading until /api/me and a
// 1.3MB universe file had come back. The rewrite in _tier.js knows.
import { proPage } from "./_tier.js";

export async function onRequestGet({ request, env }) {
  return proPage(request, env, { hero: true });
}
