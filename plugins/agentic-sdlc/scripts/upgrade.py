"""Upgrade a project's pinned pipeline files to the plugin's templates. A plain script, so every upgrade classifies the same way.

Usage: python3 upgrade.py plan  <repo> [--owner NAME] [--templates DIR ...]        print the plan as JSON, change nothing
       python3 upgrade.py apply <repo> [--owner NAME] [--templates DIR ...] [--take PATH,PATH]   write files and the manifest
       python3 upgrade.py --test
Later --templates dirs override earlier ones (core first, then a profile). Git, the branch and the PR are the caller's job.
Classes: new | same | update (repo file untouched since install) | edited (you changed it: kept unless in --take)
         | config (.sdlc/config.yml: only missing keys are added) | owned (the constitution is never touched).
"""
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile

OWNED = {"docs/constitution.md"}
CONFIG = ".sdlc/config.yml"
MANIFEST = ".sdlc/manifest.json"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def render(data, project, owner):
    return data.replace(b"{{PROJECT_NAME}}", project.encode()).replace(b"{{GITHUB_USER}}", owner.encode())


def template_files(roots):
    files = {}
    for root in roots:
        for d, _, fs in os.walk(root):
            for f in fs:
                p = os.path.join(d, f)
                files[os.path.relpath(p, root)] = p
    return files


def blocks(text):
    """Split YAML text into (top-level key, lines) blocks; a block runs to the next unindented key. Comments stay with the block above."""
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):", line)
        if m:
            cur = (m.group(1), [line]); out.append(cur)
        elif cur:
            cur[1].append(line)
    return out


def children(lines):
    """Group a block's indented lines into (child key, lines) by the two-space keys under the header."""
    out = []
    for l in lines[1:]:
        m = re.match(r"^  ([A-Za-z_][\w-]*):", l)
        if m:
            out.append((m.group(1), [l]))
        elif out:
            out[-1][1].append(l)
    return out


def merge_config(repo_text, tmpl_text):
    """Add keys the template has and the repo lacks (top level, and one level down in a block); every existing value stays as it is."""
    pre, mine = [], []
    for line in repo_text.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):", line)
        if m:
            mine.append((m.group(1), [line]))
        elif mine:
            mine[-1][1].append(line)
        else:
            pre.append(line)
    have, added = dict(mine), []
    for key, lines in blocks(tmpl_text):
        if key not in have:
            mine.append((key, list(lines))); have[key] = mine[-1][1]; added.append(key)
            continue
        if lines[0].split(":", 1)[1].split("#")[0].strip() or have[key][0].split(":", 1)[1].split("#")[0].strip():
            continue  # a scalar or an inline { } value: leave it alone
        known = {k for k, _ in children(have[key])}
        for ck, cl in children(lines):
            if ck not in known:
                n = len(have[key])
                while n > 1 and not have[key][n - 1].strip():
                    n -= 1
                have[key][n:n] = cl; added.append(f"{key}.{ck}")
    return "\n".join(pre + [l for _, ls in mine for l in ls]).rstrip("\n") + "\n", added


def plan(repo, owner, roots, version="?"):
    cfg = open(os.path.join(repo, CONFIG)).read()
    project = (re.search(r'^project:\s*"?([^"\n#]*[^"\s#])', cfg, re.M) or [0, os.path.basename(repo)])[1]
    mpath = os.path.join(repo, MANIFEST)
    manifest = json.load(open(mpath)) if os.path.exists(mpath) else {"version": None, "files": {}}
    files, out = template_files(roots), {"new": [], "update": [], "same": [], "edited": [], "owned": [], "config": [], "removed": []}
    rendered = {}
    for rel, src in sorted(files.items()):
        want = rendered[rel] = render(open(src, "rb").read(), project, owner)
        dst = os.path.join(repo, rel)
        if rel == CONFIG:
            text, added = merge_config(cfg, want.decode()); out["config"] = added; rendered[rel] = text.encode()
        elif rel in OWNED:
            out["owned"].append(rel)
        elif not os.path.exists(dst):
            out["new"].append(rel)
        else:
            have = open(dst, "rb").read()
            if have == want:
                out["same"].append(rel)
            elif sha(have) == manifest["files"].get(rel):
                out["update"].append(rel)
            else:
                diff = "".join(difflib.unified_diff(have.decode(errors="replace").splitlines(True), want.decode(errors="replace").splitlines(True), "yours", "new", n=1))
                out["edited"].append({"path": rel, "diff": diff})
    out["removed"] = sorted(set(manifest["files"]) - set(files))
    return {"project": project, "owner": owner, "from": manifest.get("version"), "to": version, **out}, rendered, files, manifest


def apply(repo, owner, roots, version, take=()):
    p, rendered, files, manifest = plan(repo, owner, roots, version)
    mf = dict(manifest["files"])
    for rel in p["new"] + p["update"] + p["same"] + [e["path"] for e in p["edited"] if e["path"] in take]:
        dst = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        open(dst, "wb").write(rendered[rel]); shutil.copymode(files[rel], dst)
        mf[rel] = sha(rendered[rel])
    if p["config"]:
        open(os.path.join(repo, CONFIG), "wb").write(rendered[CONFIG])
    for rel in p["owned"] + [CONFIG]:
        mf.setdefault(rel, sha(open(os.path.join(repo, rel), "rb").read()))
    for rel in p["removed"]:
        mf.pop(rel, None)
    json.dump({"version": version, "files": dict(sorted(mf.items()))}, open(os.path.join(repo, MANIFEST), "w"), indent=2)
    open(os.path.join(repo, MANIFEST), "a").write("\n")
    return p


def test():
    d = tempfile.mkdtemp()
    w = lambda *a: (os.makedirs(os.path.dirname(os.path.join(d, *a[:-1])), exist_ok=True), open(os.path.join(d, *a[:-1]), "w").write(a[-1]))
    t, r = os.path.join(d, "t"), os.path.join(d, "r")
    W = lambda base, rel, text: (os.makedirs(os.path.dirname(os.path.join(base, rel)), exist_ok=True), open(os.path.join(base, rel), "w").write(text))
    # templates (new version)
    W(t, ".github/CODEOWNERS", "/.sdlc/ @{{GITHUB_USER}}\n")
    W(t, "a.txt", "A2\n"); W(t, "b.txt", "B2\n"); W(t, "c.txt", "C2\n"); W(t, "same.txt", "S\n"); W(t, "new.txt", "N\n")
    W(t, "docs/constitution.md", "# {{PROJECT_NAME}}\n")
    W(t, CONFIG, 'project: "{{PROJECT_NAME}}"\ndry_run: true\nlimits:\n  daily_runs: 20\n  retries: 2\n  extra: 1\nneeds:\n  enabled: true  # c\n')
    # repo as installed by the old version
    W(r, ".github/CODEOWNERS", "/.sdlc/ @justas\n"); W(r, "a.txt", "A1\n"); W(r, "b.txt", "B-mine\n"); W(r, "c.txt", "C1\n")
    W(r, "same.txt", "S\n"); W(r, "docs/constitution.md", "# mine\n")
    W(r, CONFIG, 'project: "demo"\ndry_run: false\nlimits:\n  daily_runs: 40\n  retries: 2\n')
    old = {".github/CODEOWNERS": sha(b"/.sdlc/ @{{x}}\n"), "a.txt": sha(b"A1\n"), "b.txt": sha(b"B1\n"), "c.txt": sha(b"C1\n"), "gone.txt": "x"}
    W(r, MANIFEST, json.dumps({"version": "1", "files": old}))
    p, *_ = plan(r, "justas", [t], "2")
    assert p["new"] == ["new.txt"], p["new"]
    assert p["same"] == [".github/CODEOWNERS", "same.txt"] and p["owned"] == ["docs/constitution.md"], p["same"]
    assert set(p["update"]) == {"a.txt", "c.txt"}, p["update"]
    assert [e["path"] for e in p["edited"]] == ["b.txt"], p["edited"]
    assert p["removed"] == ["gone.txt"] and set(p["config"]) == {"needs", "limits.extra"}, p["config"]
    assert "-B-mine" in [e for e in p["edited"] if e["path"] == "b.txt"][0]["diff"]
    apply(r, "justas", [t], "2", take=["b.txt"])
    rd = lambda *a: open(os.path.join(r, *a)).read()
    assert rd("a.txt") == "A2\n" and rd("b.txt") == "B2\n" and rd("new.txt") == "N\n"
    assert rd(".github/CODEOWNERS") == "/.sdlc/ @justas\n" and rd("docs/constitution.md") == "# mine\n"
    cfg = rd(CONFIG)
    assert "dry_run: false" in cfg and "daily_runs: 40" in cfg and "  extra: 1" in cfg and "needs:\n  enabled: true" in cfg, cfg
    m = json.load(open(os.path.join(r, MANIFEST)))
    assert m["version"] == "2" and "gone.txt" not in m["files"] and m["files"]["a.txt"] == sha(b"A2\n"), m
    W(r, "b.txt", "B-mine-again\n")  # an edit you keep: the manifest entry must not move, so it is flagged again next time
    keep = json.load(open(os.path.join(r, MANIFEST)))["files"]["b.txt"]
    apply(r, "justas", [t], "2")
    assert json.load(open(os.path.join(r, MANIFEST)))["files"]["b.txt"] == keep and rd("b.txt") == "B-mine-again\n"
    p2, *_ = plan(r, "justas", [t], "2")
    assert p2["new"] == p2["update"] == [] and p2["config"] == [], p2
    # a placeholder in a NEW file is rendered, never copied raw (the bug a hand-made upgrade once shipped)
    W(t, "more/OWNERS", "@{{GITHUB_USER}} {{PROJECT_NAME}}\n")
    apply(r, "justas", [t], "3")
    assert rd("more/OWNERS") == "@justas demo\n"
    # the real incident: a hand-made upgrade left a raw placeholder in the repo AND in the manifest; the next upgrade must repair it
    W(r, ".github/CODEOWNERS", "/.sdlc/ @{{GITHUB_USER}}\n")
    mm = json.load(open(os.path.join(r, MANIFEST))); mm["files"][".github/CODEOWNERS"] = sha(b"/.sdlc/ @{{GITHUB_USER}}\n")
    json.dump(mm, open(os.path.join(r, MANIFEST), "w"))
    assert plan(r, "justas", [t], "3")[0]["update"] == [".github/CODEOWNERS"]
    apply(r, "justas", [t], "3")
    assert rd(".github/CODEOWNERS") == "/.sdlc/ @justas\n"
    print("ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--test"]:
        test()
    else:
        mode, repo = a[0], os.path.abspath(a[1])
        opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
        roots = [a[i + 1] for i, x in enumerate(a) if x == "--templates"] or [os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "core")]
        pj = os.path.join(roots[0], "..", "..", ".claude-plugin", "plugin.json")
        version = json.load(open(pj))["version"] if os.path.exists(pj) else "?"
        if mode == "plan":
            print(json.dumps(plan(repo, opt("--owner", ""), roots, version)[0], indent=2))
        else:
            print(json.dumps(apply(repo, opt("--owner", ""), roots, version, (opt("--take") or "").split(",")), indent=2))
