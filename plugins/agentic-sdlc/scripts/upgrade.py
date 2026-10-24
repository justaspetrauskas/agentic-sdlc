"""Upgrade a project's pinned pipeline files to the plugin's templates. A plain script, so every upgrade classifies the same way.

Usage: python3 upgrade.py plan  <repo> [--owner NAME] [--templates DIR ...]        print the plan as JSON, change nothing
       python3 upgrade.py apply <repo> [--owner NAME] [--templates DIR ...] [--take PATH,PATH]   write files and the manifest
       python3 upgrade.py apply <repo> --init --project NAME --type web|mobile|claude-plugin|chrome-ext --owner NAME   first install
       python3 upgrade.py --test
Templates are core plus the profile of the repo's `type:` (templates/profiles/<type>); later directories override earlier ones.
Git, the branch and the PR are the caller's job.
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


PROFILES = ("web", "mobile", "claude-plugin", "chrome-ext")


def set_type(cfg, type_):
    """The chosen type goes into the config; types that do not deploy to a web host switch the deploy off, and a project with no UI skips the needs step."""
    cfg = re.sub(r"^type:.*$", f"type: {type_}            # web | mobile | claude-plugin | chrome-ext", cfg, count=1, flags=re.M)
    if type_ != "web":
        cfg = cfg.replace("provider: cloudflare-pages", "provider: none", 1)
    if type_ == "claude-plugin":
        cfg = re.sub(r"(?m)^(needs:\n  enabled:) true", r"\1 false", cfg, count=1)
    return cfg


def init_config(repo, owner, templates_core, project, type_):
    dst = os.path.join(repo, CONFIG)
    if os.path.exists(dst):
        sys.exit(f"{CONFIG} already exists: this repo is installed. Use plan/apply without --init.")
    cfg = render(open(os.path.join(templates_core, CONFIG), "rb").read(), project, owner).decode()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "w").write(set_type(cfg, type_))


def roots_for(repo, templates_base):
    """core, plus the profile of the type named in the repo's config."""
    cfg = open(os.path.join(repo, CONFIG)).read()
    t = (re.search(r"^type:\s*([\w-]+)", cfg, re.M) or [0, "web"])[1]
    prof = os.path.join(templates_base, "profiles", t)
    return [os.path.join(templates_base, "core")] + ([prof] if os.path.isdir(prof) else [])


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
        elif not os.path.exists(dst):
            out["new"].append(rel)  # even an owned file is installed the first time; it is never touched after that
        elif rel in OWNED:
            out["owned"].append(rel)
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
    # profiles: a later root overrides an earlier one, and adds its own files
    prof = os.path.join(d, "prof")
    W(prof, "a.txt", "A-profile\n"); W(prof, ".sdlc/profile.yml", "type: chrome-ext\n")
    p3, rendered3, *_ = plan(r, "justas", [t, prof], "3")
    assert rendered3["a.txt"] == b"A-profile\n" and ".sdlc/profile.yml" in p3["new"], p3
    # init: the config is created from the template with the project and the type; a non-web type turns deploy off
    base = os.path.join(d, "base"); W(os.path.join(base, "core"), CONFIG, 'project: "{{PROJECT_NAME}}"\ntype: web            # x\nneeds:\n  enabled: true\ndeploy:\n  provider: cloudflare-pages\n')
    W(os.path.join(base, "core"), "n.txt", "n\n"); W(os.path.join(base, "profiles", "claude-plugin"), ".sdlc/profile.yml", "type: claude-plugin\n")
    fresh = os.path.join(d, "fresh"); os.makedirs(fresh)
    init_config(fresh, "justas", os.path.join(base, "core"), "plug", "claude-plugin")
    c = open(os.path.join(fresh, CONFIG)).read()
    assert 'project: "plug"' in c and "type: claude-plugin" in c and "provider: none" in c and "enabled: false" in c, c
    assert roots_for(fresh, base) == [os.path.join(base, "core"), os.path.join(base, "profiles", "claude-plugin")]
    apply(fresh, "justas", roots_for(fresh, base), "1")
    assert os.path.exists(os.path.join(fresh, ".sdlc/profile.yml")) and os.path.exists(os.path.join(fresh, "n.txt"))
    W(os.path.join(base, "core"), "docs/constitution.md", "# {{PROJECT_NAME}}\n")
    apply(fresh, "justas", roots_for(fresh, base), "1")
    assert open(os.path.join(fresh, "docs/constitution.md")).read() == "# plug\n"  # installed on a first run...
    open(os.path.join(fresh, "docs/constitution.md"), "w").write("# mine\n")
    apply(fresh, "justas", roots_for(fresh, base), "2")
    assert open(os.path.join(fresh, "docs/constitution.md")).read() == "# mine\n"  # ...and never overwritten after that
    assert set_type('type: web\nprovider: cloudflare-pages\n', "web") == 'type: web            # web | mobile | claude-plugin | chrome-ext\nprovider: cloudflare-pages\n'
    print("ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--test"]:
        test()
    else:
        mode, repo = a[0], os.path.abspath(a[1])
        opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")
        if "--init" in a:
            if opt("--type") not in PROFILES:
                sys.exit(f"--type must be one of {', '.join(PROFILES)}")
            init_config(repo, opt("--owner", ""), os.path.join(base, "core"), opt("--project") or os.path.basename(repo), opt("--type"))
        roots = [a[i + 1] for i, x in enumerate(a) if x == "--templates"] or roots_for(repo, base)
        pj = os.path.join(roots[0], "..", "..", ".claude-plugin", "plugin.json")
        version = json.load(open(pj))["version"] if os.path.exists(pj) else "?"
        if mode == "plan":
            print(json.dumps(plan(repo, opt("--owner", ""), roots, version)[0], indent=2))
        else:
            print(json.dumps(apply(repo, opt("--owner", ""), roots, version, (opt("--take") or "").split(",")), indent=2))
