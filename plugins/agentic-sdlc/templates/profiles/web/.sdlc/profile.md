# Profile: web app

- Checks: `typecheck`, `lint`, `test` npm scripts. CI runs them on every PR.
- Release: CI deploys `main` to the host named in `.sdlc/config.yml` (`deploy:`) after checks pass. A red build never deploys.
- UI work follows `docs/design.md`.
