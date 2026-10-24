"""Check a Chrome extension's manifest.json: Manifest V3, required fields, no remote code.

Usage: python3 .sdlc/scripts/check_manifest.py [path ...]   (default: manifest.json, then public/manifest.json, then src/manifest.json)
       python3 .sdlc/scripts/check_manifest.py --test
Exit 1 with one line per problem. A project that has no manifest yet passes: the scaffold task creates it.
"""
import json
import os
import re
import sys

REQUIRED = ["manifest_version", "name", "version", "description"]
BROAD = {"<all_urls>", "*://*/*", "http://*/*", "https://*/*"}


def problems(m):
    p = [f"missing {k}" for k in REQUIRED if not m.get(k)]
    if m.get("manifest_version") != 3:
        p.append("manifest_version must be 3")
    if m.get("version") and not re.fullmatch(r"\d+(\.\d+){0,3}", str(m["version"])):
        p.append("version must be 1 to 4 dot-separated integers")
    csp = m.get("content_security_policy", {})
    csp = " ".join(csp.values()) if isinstance(csp, dict) else str(csp)
    if re.search(r"unsafe-eval|https?://", csp):
        p.append("content_security_policy allows eval or remote code")
    if BROAD & set(m.get("host_permissions", []) + m.get("permissions", [])):
        p.append("broad host permission (<all_urls> or a wildcard host): ask for specific sites")
    return p


def main(paths):
    paths = paths or [x for x in ("manifest.json", "public/manifest.json", "src/manifest.json") if os.path.exists(x)]
    if not paths:
        print("No manifest.json yet. Nothing to check."); return 0
    bad = 0
    for path in paths:
        try:
            found = problems(json.load(open(path)))
        except ValueError as e:
            found = [f"not valid JSON: {e}"]
        for f in found:
            print(f"{path}: {f}"); bad += 1
    return 1 if bad else 0


def test():
    ok = {"manifest_version": 3, "name": "x", "version": "1.2.3", "description": "d", "permissions": ["storage"]}
    assert problems(ok) == []
    assert problems({**ok, "manifest_version": 2}) == ["manifest_version must be 3"]
    assert "missing description" in problems({k: v for k, v in ok.items() if k != "description"})
    assert any("version must" in x for x in problems({**ok, "version": "1.0-beta"}))
    assert any("remote code" in x for x in problems({**ok, "content_security_policy": {"extension_pages": "script-src 'self' 'unsafe-eval'"}}))
    assert any("remote code" in x for x in problems({**ok, "content_security_policy": {"extension_pages": "script-src https://cdn.x.com"}}))
    assert any("broad host" in x for x in problems({**ok, "host_permissions": ["<all_urls>"]}))
    assert problems({**ok, "host_permissions": ["https://example.com/*"]}) == []
    print("ok")


if __name__ == "__main__":
    test() if sys.argv[1:] == ["--test"] else sys.exit(main(sys.argv[1:]))
