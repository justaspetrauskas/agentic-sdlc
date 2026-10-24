# Profile: mobile app

- Checks: `typecheck`, `lint`, `test` npm scripts (unit and integration with a JS test runner). CI does not build the app.
- Release: building a binary is allowed (for example `npx expo export`); uploading to a store is never done by an agent, it is always the owner.
  Signing keys and store credentials are secrets: never read, print or commit them.
- Screens follow `docs/design.md`. Check phone sizes first, then tablet. Touch targets of at least 44px.
