// Run: node --test services/notify/test.js   (no dependencies; Telegram and KV are faked)
import test from "node:test";
import assert from "node:assert/strict";
import worker, { sendDigest } from "./worker.js";

const kv = () => {
  const m = new Map();
  return {
    m, get: async (k) => m.get(k) ?? null, put: async (k, v) => void m.set(k, v), delete: async (k) => void m.delete(k),
    list: async ({ prefix }) => ({ keys: [...m.keys()].filter((k) => k.startsWith(prefix)).sort().map((name) => ({ name })), list_complete: true }),
  };
};
const setup = (ok = true) => {
  const sent = [];
  globalThis.fetch = async (_url, init) => { sent.push(JSON.parse(init.body).text); return { ok }; };
  const env = { STATE: kv(), TELEGRAM_BOT_TOKEN: "t", TELEGRAM_CHAT_ID: "1", PROJECT_KEYS: JSON.stringify({ alpha: "key-a", beta: "key-b" }) };
  return { sent, env };
};
const post = (env, key, body) => worker.fetch(new Request("https://x/v1/events", {
  method: "POST", headers: { authorization: `Bearer ${key}` }, body: typeof body === "string" ? body : JSON.stringify(body) }), env);
const ev = (o = {}) => ({ project: "alpha", kind: "needs-you", title: "Plan ready", link: "https://github.com/o/r/pull/1", dedupe: "plan-1", ...o });

test("needs-you is sent at once, tagged with the project", async () => {
  const { sent, env } = setup();
  const r = await post(env, "key-a", ev());
  assert.equal((await r.json()).status, "sent");
  assert.equal(sent[0], "[alpha] needs you: Plan ready\nhttps://github.com/o/r/pull/1");
});
test("the same dedupe key collapses into one message", async () => {
  const { sent, env } = setup();
  await post(env, "key-a", ev());
  assert.equal((await (await post(env, "key-a", ev())).json()).status, "duplicate");
  assert.equal(sent.length, 1);
  assert.equal((await (await post(env, "key-a", ev({ dedupe: "other" }))).json()).status, "sent");
});
test("a bad or foreign key is refused", async () => {
  const { sent, env } = setup();
  assert.equal((await post(env, "nope", ev())).status, 401);
  assert.equal((await post(env, "key-b", ev())).status, 401); // beta's key cannot speak for alpha
  assert.equal(sent.length, 0);
});
test("bad input is refused", async () => {
  const { env } = setup();
  assert.equal((await post(env, "key-a", "{nope")).status, 400);
  assert.equal((await post(env, "key-a", ev({ kind: "spam" }))).status, 400);
  assert.equal((await post(env, "key-a", ev({ link: "http://x" }))).status, 400);
  assert.equal((await post(env, "key-a", ev({ title: " " }))).status, 400);
  assert.equal((await post(env, "key-a", "x".repeat(5000))).status, 413);
});
test("a failed Telegram send is not marked as seen, so a retry goes out", async () => {
  const bad = setup(false);
  assert.equal((await post(bad.env, "key-a", ev())).status, 502);
  const good = setup(true);
  good.env.STATE = bad.env.STATE;
  assert.equal((await (await post(good.env, "key-a", ev())).json()).status, "sent");
});
test("idea and info wait for the digest, which groups by project and clears the queue", async () => {
  const { sent, env } = setup();
  await post(env, "key-a", ev({ kind: "idea", title: "Dark mode", dedupe: "i1" }));
  await post(env, "key-a", ev({ kind: "info", title: "Auto-merged #5", dedupe: "i2" }));
  await post(env, "key-b", ev({ project: "beta", kind: "info", title: "Spec ready", dedupe: "i3" }));
  assert.equal(sent.length, 0);
  assert.equal(await sendDigest(env), 3);
  assert.equal(sent.length, 1);
  assert.match(sent[0], /alpha \(2\)/); assert.match(sent[0], /beta \(1\)/);
  for (const t of ["Dark mode", "Auto-merged #5", "Spec ready"]) assert.ok(sent[0].includes(t), t);
  assert.ok(sent[0].indexOf("alpha") < sent[0].indexOf("beta"));
  assert.equal(await sendDigest(env), 0); // nothing left, nothing sent
  assert.equal(sent.length, 1);
});
test("a long digest is split under the Telegram limit", async () => {
  const { sent, env } = setup();
  for (let i = 0; i < 60; i++) await post(env, "key-a", ev({ kind: "info", title: "x".repeat(150), dedupe: `d${i}` }));
  await sendDigest(env);
  assert.ok(sent.length > 1 && sent.every((m) => m.length <= 4096));
});
