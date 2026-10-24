# agentic-sdlc

A Claude Code plugin that turns a GitHub repo into a small, self-running software pipeline.

You file an idea, a bug or a UX request as an issue. Agents write the spec and the plan, build the tasks, and review the PRs. You merge what matters and answer the questions only you can. Small fixes and UX tweaks can merge themselves; anything that touches workflows, dependencies or the constitution always waits for you.

It's built for hobby budgets. Everything runs on free tiers (GitHub Actions, Cloudflare Pages and Workers) plus your own Claude subscription.

## What you get

- **A real flow, not a chatbot.** Idea, spec, a stack-and-design proposal, plan, task issues, build PRs, review, deploy. Bugs and UX fixes skip straight to a build.
- **Limits that hold.** A `PAUSE` label stops everything, there's a daily cap on agent runs, retries are capped, and a tripwire stops a PR that grows past its task. Agents can't change their own rules.
- **Four project types.** Web, mobile, Claude plugin and Chrome extension. The pipeline is the same; the type decides what CI checks and how a release works.
- **Upgrades you review.** Projects get pinned copies of the workflows. `/sdlc-upgrade` opens a PR with the diff and the release notes, and never overwrites a file you edited.
- **Optional extras.** A local metrics board (`/sdlc-board`) and Telegram notifications (`/sdlc-notify-setup`).

## Try it

```
/plugin marketplace add justaspetrauskas/agentic-sdlc
/plugin install agentic-sdlc@agentic-sdlc-marketplace
```

Then, inside a repo you own:

```
/agentic-sdlc:sdlc-init
```

It asks for a project name and type, and opens a PR with the pipeline files. It starts in dry-run, so agents only write down what they would do. You'll also need a `CLAUDE_CODE_OAUTH_TOKEN` repo secret.

## Status

All the planned milestones are built and tested end to end on two projects: a todo app (web) and a small demo plugin. Two things haven't run live yet: the rate-limit pause and the night window.

Releases are in [CHANGELOG.md](plugins/agentic-sdlc/CHANGELOG.md). Each script has a `--test` self-check.
