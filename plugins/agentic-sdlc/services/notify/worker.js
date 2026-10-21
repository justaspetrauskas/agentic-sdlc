// Notification service: one Telegram bot for every pipeline project. One-way: it only notifies.
// POST /v1/events  Authorization: Bearer <project key>  {project, kind, title, link, dedupe}
// needs-you and critical go out at once; idea and info wait for the morning digest (cron).
const KINDS = ["needs-you", "idea", "critical", "info"];
const NOW = new Set(["needs-you", "critical"]);
const LABEL = { "needs-you": "needs you", critical: "CRITICAL", idea: "idea", info: "info" };
const DEDUPE_TTL = 86400; // one day: the same event inside it collapses into one message
const clean = (s, max) => String(s).replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, max);
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

async function digest256(s) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)));
}
// Constant-time comparison of two keys (hash first, so the lengths match).
async function sameKey(a, b) {
  const [x, y] = await Promise.all([digest256(a), digest256(b)]);
  let d = 0;
  for (let i = 0; i < x.length; i++) d |= x[i] ^ y[i];
  return d === 0;
}

export async function projectFor(env, key) {
  const keys = JSON.parse(env.PROJECT_KEYS || "{}");
  let found = null;
  for (const [project, k] of Object.entries(keys)) if (await sameKey(k, key)) found = project;
  return found;
}

export function validate(b) {
  if (!b || typeof b !== "object") return "body must be a JSON object";
  if (!KINDS.includes(b.kind)) return `kind must be one of ${KINDS.join(", ")}`;
  for (const f of ["project", "title", "dedupe"]) if (typeof b[f] !== "string" || !b[f].trim()) return `${f} is required`;
  if (b.link !== undefined && !/^https:\/\/\S+$/.test(b.link)) return "link must be an https URL";
  return null;
}

async function telegram(env, text) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text, disable_web_page_preview: true }),
  });
  return r.ok;
}
const line = (e) => `[${e.project}] ${LABEL[e.kind]}: ${e.title}${e.link ? "\n" + e.link : ""}`;

export async function handleEvent(request, env) {
  if (request.method !== "POST" || new URL(request.url).pathname !== "/v1/events") return json(404, { error: "not found" });
  const key = (request.headers.get("authorization") || "").replace(/^Bearer /, "");
  const project = key ? await projectFor(env, key) : null;
  if (!project) return json(401, { error: "bad key" });
  const text = await request.text();
  if (text.length > 4096) return json(413, { error: "body too large" });
  let b;
  try { b = JSON.parse(text); } catch { return json(400, { error: "invalid JSON" }); }
  const bad = validate(b);
  if (bad) return json(400, { error: bad });
  // A key speaks only for its own project, so one leaked key cannot impersonate another project.
  if (b.project !== project) return json(401, { error: "key does not belong to this project" });
  const e = { project, kind: b.kind, title: clean(b.title, 200), link: b.link ? clean(b.link, 300) : "" };
  const dedupe = `d:${project}:${clean(b.dedupe, 100)}`;
  if (await env.STATE.get(dedupe)) return json(200, { status: "duplicate" });
  if (NOW.has(e.kind)) {
    // Mark it as seen only after Telegram accepted it, so a failed send can be retried.
    if (!(await telegram(env, line(e)))) return json(502, { error: "telegram refused the message" });
    await env.STATE.put(dedupe, "1", { expirationTtl: DEDUPE_TTL });
    return json(200, { status: "sent" });
  }
  await env.STATE.put(`q:${Date.now()}:${crypto.randomUUID()}`, JSON.stringify(e));
  await env.STATE.put(dedupe, "1", { expirationTtl: DEDUPE_TTL });
  return json(200, { status: "queued" });
}

// Morning digest: one message per ~3800 characters, grouped by project. Queued events are deleted only after a send.
export async function sendDigest(env) {
  const keys = [];
  let cursor;
  do {
    const page = await env.STATE.list({ prefix: "q:", cursor });
    keys.push(...page.keys.map((k) => k.name));
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  if (!keys.length) return 0;
  const events = [];
  for (const k of keys) events.push(JSON.parse(await env.STATE.get(k)));
  const byProject = {};
  for (const e of events) (byProject[e.project] ||= []).push(e);
  // Split by line, so even one busy project stays under the Telegram limit (an entry is at most ~520 characters).
  const messages = [];
  let cur = "Morning digest";
  const add = (s) => {
    if ((cur + "\n" + s).length > 3800) { messages.push(cur); cur = "Morning digest (cont.)"; }
    cur += "\n" + s;
  };
  for (const [p, es] of Object.entries(byProject).sort()) {
    add(`\n${p} (${es.length})`);
    for (const e of es) add(`- ${LABEL[e.kind]}: ${e.title}${e.link ? "\n  " + e.link : ""}`);
  }
  messages.push(cur);
  for (const m of messages) if (!(await telegram(env, m))) throw new Error("telegram refused the digest");
  for (const k of keys) await env.STATE.delete(k);
  return events.length;
}

export default {
  fetch: (request, env) => handleEvent(request, env),
  scheduled: (_event, env, ctx) => ctx.waitUntil(sendDigest(env)),
};
