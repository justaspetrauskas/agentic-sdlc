# Changelog

Plugin releases, newest first. A project changes only when you run `/sdlc-upgrade`.

## 0.1.38 - 2026-10-24
- S3: profiles (web, mobile, claude-plugin, chrome-ext) read by CI and the prompts; upgrade.py installs and upgrades by profile; sdlc-init uses it

## 0.1.37 - 2026-10-24
- S2: CHANGELOG.md (backfilled), release.py (bump, tag, since), upgrade PRs list release notes, plugin author

## 0.1.36 - 2026-10-24
- S1: upgrade.py classifies and applies upgrades; the skill drives it (renders placeholders, merges config keys, keeps edits)

## 0.1.35 - 2026-10-24
- notify.py sends its own User-Agent (Cloudflare blocks the urllib default with 403/1010); service folder lives in Development

## 0.1.34 - 2026-10-22
- Notifications are an optional function: /sdlc-notify-setup skill, hashed per-project keys in KV, add-project.sh, sdlc-notify-test

## 0.1.33 - 2026-10-21
- M5: notification service (Worker + Telegram), notify.py client, wired into escalation points

## 0.1.32 - 2026-10-21
- M4: metrics board (board.py + static board.html) and /sdlc-board

## 0.1.31 - 2026-10-20
- Planner adds a task to adopt docs/design.md when the app does not follow it

## 0.1.30 - 2026-10-20
- M3: needs step decides stack, hosting, auth, testing and docs/design.md before the first plan

## 0.1.29 - 2026-10-20
- M2c: gitleaks scan in CI gates merge and deploy; /sdlc-stop-all

## 0.1.28 - 2026-10-20
- Revise accepts dispatches from github-actions (ci-fix)

## 0.1.27 - 2026-10-20
- ledger: send the request body (gh api needs --input -)

## 0.1.26 - 2026-10-20
- M2b: run ledger, daily cap, night window, retries, rate-limit pause

## 0.1.25 - 2026-10-19
- merge.py reads check runs via REST (checks:read only)

## 0.1.24 - 2026-10-19
- sdlc-merge can read checks; tolerate pending checks

## 0.1.23 - 2026-10-19
- sdlc-merge triggers on the review comment, not workflow_run

## 0.1.22 - 2026-10-19
- Fix and UX issues are their own task: picker builds them directly

## 0.1.21 - 2026-10-19
- M2a: auto-merge script and workflow with GitHub App token

## 0.1.20 - 2026-10-19
- Revise mode: /build comments on a task PR

## 0.1.19 - 2026-10-19
- Review allows runs started by the Claude app

## 0.1.18 - 2026-10-19
- Build allows picker dispatch, picker stops at a blocked item, quiet wrangler

## 0.1.17 - 2026-10-19
- Deploy provider setting; Cloudflare Pages deploy from CI after checks

## 0.1.16 - 2026-10-19
- M1.7: picker, CI on push for Railway Wait for CI, health monitor

## 0.1.15 - 2026-10-19
- CI uses current Node LTS

## 0.1.14 - 2026-10-19
- M1.6: build, CI with tripwire, advisory review

## 0.1.13 - 2026-10-18
- M1.5: plan and tasks from an approved spec

## 0.1.12 - 2026-10-18
- Per-issue job-level concurrency so queued runs are not dropped

## 0.1.11 - 2026-10-18
- Product lead after answers, usage per step

## 0.1.10 - 2026-10-18
- Product lead decides non-critical questions

## 0.1.9 - 2026-10-18
- M1.4b: live spec, answers, approval

## 0.1.8 - 2026-10-17
- Add sdlc-upgrade, init writes manifest

## 0.1.7 - 2026-10-17
- Ask for stack from a fixed list

## 0.1.6 - 2026-10-17
- M1.4: spec writer

## 0.1.5 - 2026-10-17
- M1.3b: watchdog on pushes to main

## 0.1.4 - 2026-10-17
- M1.3: kill switch guard

## 0.1.3 - 2026-10-17
- Merge ux and ui into one area

## 0.1.2 - 2026-10-17
- Branch naming convention

## 0.1.1 - 2026-10-17
- M1.2: sdlc-init skill

## 0.1.0 - 2026-10-17
- M0: plugin skeleton
