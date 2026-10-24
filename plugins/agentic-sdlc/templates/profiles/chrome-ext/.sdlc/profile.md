# Profile: Chrome extension

- Checks: `lint` and `test` npm scripts, plus `.sdlc/scripts/check_manifest.py` (Manifest V3, required fields, no remote code).
- Release: CI zips `package_dir` (default `dist`) as a build artifact. Uploading to the Chrome Web Store is always the owner.
- Ask for the fewest permissions that work, and never `<all_urls>` unless the spec says so. No remote code: no `eval`, no scripts loaded from a URL.
- Popup and options pages follow `docs/design.md`.
