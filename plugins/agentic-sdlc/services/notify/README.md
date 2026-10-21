# Notification service

One Telegram bot for every pipeline project. It only notifies; you act in GitHub through the link. Optional: a project
without it works the same, and a missing URL or key skips notifying silently.

- `needs-you` and `critical` are sent at once. `idea` and `info` wait for one morning digest (05:00 UTC).
- The same dedupe key inside 24 hours collapses into one message.
- Each project has its own key, and a key can only speak for its own project.

Runs on Cloudflare's free plan (Workers 100,000 requests/day, KV 1,000 writes/day, one cron trigger). A Telegram bot costs nothing.

## Set it up (you do this once; the tokens are yours, so keep them out of chats and files)

1. In Telegram, talk to **@BotFather**, send `/newbot`, and keep the token. Send your new bot any message, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and note `message.chat.id`.
2. In this folder:
   ```bash
   npx wrangler kv namespace create STATE     # paste the printed id into wrangler.toml
   npx wrangler secret put TELEGRAM_BOT_TOKEN
   npx wrangler secret put TELEGRAM_CHAT_ID
   npx wrangler secret put PROJECT_KEYS       # JSON: {"my-app":"<key>","other-app":"<key>"}  (key: openssl rand -hex 24)
   npx wrangler deploy                        # prints the service URL
   ```
3. For each project, set `notify.url` in `.sdlc/config.yml` (through a PR) and the key as a repo secret:
   ```bash
   gh secret set SDLC_NOTIFY_KEY --repo <owner>/<repo>
   ```
   The project name in `PROJECT_KEYS` must equal `project:` in that repo's `.sdlc/config.yml`.
4. Try it:
   ```bash
   curl -s -X POST "$URL/v1/events" -H "authorization: Bearer $KEY" -H "content-type: application/json" \
     -d '{"project":"my-app","kind":"needs-you","title":"Test","dedupe":"test-1"}'
   ```

Tests: `node --test services/notify/test.js` (no dependencies; Telegram and KV are faked).
