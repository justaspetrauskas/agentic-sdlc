# Notification service

One Telegram bot for every pipeline project. It only notifies; you act in GitHub through the link. Optional: a project
without it works the same, and a missing URL or key skips notifying silently.

- `needs-you` and `critical` are sent at once. `idea` and `info` wait for one morning digest (05:00 UTC).
- The same dedupe key inside 24 hours collapses into one message.
- Each project has its own key, and a key can only speak for its own project.

Runs on Cloudflare's free plan (Workers 100,000 requests/day, KV 1,000 writes/day, one cron trigger). A Telegram bot costs nothing.

## Set it up

Use the guided skill: run **`/sdlc-notify-setup`** in Claude Code. It deploys the service once, then adds each project.
The Telegram bot token and chat id are secrets you type into wrangler yourself; the skill never sees them.

By hand, in a copy of this folder:
1. Bot: in Telegram talk to **@BotFather**, `/newbot`, keep the token. Message your bot, then read `message.chat.id` from
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.
2. `npx wrangler@4 login`, then `npx wrangler@4 kv namespace create STATE` and paste the id into `wrangler.toml`.
3. `npx wrangler@4 secret put TELEGRAM_BOT_TOKEN` and `npx wrangler@4 secret put TELEGRAM_CHAT_ID`, then `npx wrangler@4 deploy`.
4. For each project: `./add-project.sh <project-name> <owner/repo>` (stores a hash of a new key in KV, saves the key as the
   repo secret `SDLC_NOTIFY_KEY`; no redeploy). Set `notify.url` in that repo's `.sdlc/config.yml`, then run the
   `sdlc-notify-test` workflow. `<project-name>` must equal `project:` in that config.

Tests: `node --test test.js` (no dependencies; Telegram and KV are faked).
