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

// THE EMAIL IS THE ACCOUNT (2026-10-14): a reader is an address plus one
// sign-in token, made on first need; the watch worker and the founder
// confirm both hand it to the browser that proved it can read the inbox
export const newToken = () => [...crypto.getRandomValues(new Uint8Array(24))].map(b => b.toString(16).padStart(2, "0")).join("");
export async function readerToken(env, email) {
  await env.HITS.prepare("CREATE TABLE IF NOT EXISTS readers (email TEXT PRIMARY KEY, token TEXT UNIQUE, created TEXT)").run();
  const r = await env.HITS.prepare("SELECT token FROM readers WHERE email = ?1").bind(email).first();
  if (r && r.token) return r.token;
  const t = newToken();
  await env.HITS.prepare("INSERT INTO readers (email, token, created) VALUES (?1, ?2, ?3) ON CONFLICT(email) DO NOTHING").bind(email, t, new Date().toISOString()).run();
  const again = await env.HITS.prepare("SELECT token FROM readers WHERE email = ?1").bind(email).first();
  return (again && again.token) || t;
}
