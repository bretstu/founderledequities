// Shared plumbing for the site's small API: the watch confirmations, the
// letter signup, and the view beacon. No dependencies. (The payment and
// session machinery that lived here left with the paid tier, 2026-09-23.)

export const json = (obj, status = 200, headers = {}) =>
  new Response(JSON.stringify(obj), {
    status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...headers },
  });

export const redirect = (url, headers = {}) =>
  new Response(null, { status: 302, headers: { Location: url, ...headers } });

export const site = (env) => (env.SITE_URL || "https://founderledequities.com").replace(/\/$/, "");
