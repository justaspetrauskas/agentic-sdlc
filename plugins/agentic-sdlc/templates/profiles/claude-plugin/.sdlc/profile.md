# Profile: Claude plugin

- Checks: `claude plugin validate .` must pass (CI installs the free Claude CLI for it). Unit tests run when `package.json` has a `test` script.
- Layout: `.claude-plugin/plugin.json`, then `skills/<name>/SKILL.md`, `agents/`, `hooks/`, `.mcp.json` as needed. Follow the Claude Code plugin docs.
- Release: tag a version and push it; users update through the marketplace. Bump `version` in `plugin.json` for every release.
- `claude plugin validate` may warn about a missing icon and a missing marketplace install line in the README. Both are optional for
  a private plugin and do not fail CI; add them when you publish (`claude plugin install <name>@<marketplace>`).
- There is no UI, so there is no `docs/design.md`. A skill's text is code: keep it short, plain and testable.
