# agentic-sdlc

Vault project folder: ~/Documents/IdeaVault/skylab/projects/agentic-sdlc/

The plan, the status log and the backlog live in the vault, not in this repo. Read `plan.md` there before starting work
(its Progress section says what is done), and add a `status-log.md` entry when a phase ends.

In this repo: the plugin is `plugins/agentic-sdlc/`. Install and upgrade projects through
`plugins/agentic-sdlc/scripts/upgrade.py`, never by copying templates by hand. Release with `scripts/release.py`
(bump, tag); never push tags without asking. Run every `--test` self-check before a release.
