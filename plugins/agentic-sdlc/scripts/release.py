"""Release helper for the plugin: version, changelog and tags. Never pushes anything.

Usage: python3 release.py bump <new-version> "<one-line summary>"   set plugin.json, add the CHANGELOG.md entry (commit it yourself)
       python3 release.py tag [--all]                              tag HEAD v<version> locally (--all: every past release commit)
       python3 release.py since <version>                          print the changelog entries newer than <version>
       python3 release.py backfill                                 rebuild CHANGELOG.md from the git history (one-time)
       python3 release.py --test
Pushing a tag is yours to do: git push origin v<version>
"""
import datetime
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PLUGIN = os.path.join(ROOT, ".claude-plugin", "plugin.json")
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")
HEAD = "# Changelog\n\nPlugin releases, newest first. A project changes only when you run `/sdlc-upgrade`.\n"
ENTRY = re.compile(r"^## (\d+\.\d+\.\d+) .*$", re.M)


def ver(v):
    return tuple(int(x) for x in v.split("."))


def entry(version, date, lines):
    return f"## {version} - {date}\n" + "".join(f"- {l}\n" for l in lines)


def prepend(text, new):
    head, _, rest = text.partition("\n## ")
    return head.rstrip("\n") + "\n\n" + new + ("\n## " + rest if rest else "")


def since(text, version):
    parts = re.split(r"(?m)^(?=## )", text)
    return "".join(p for p in parts if (m := ENTRY.match(p)) and ver(m.group(1)) > ver(version)).strip()


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def releases():
    """(version, date, subjects, last commit) for each version, from the commits that touched plugin.json."""
    out = {}
    for line in git("log", "--reverse", "--format=%H|%ad|%s", "--date=short", "--", PLUGIN).splitlines():
        sha, date, subject = line.split("|", 2)
        v = json.loads(git("show", f"{sha}:{os.path.relpath(PLUGIN, git('rev-parse', '--show-toplevel'))}"))["version"]
        d = out.setdefault(v, [v, date, [], sha])
        subj = re.sub(r"\s*[;,(]?\s*(part of )?version \d+\.\d+\.\d+\)?$|\s*\(part of \d+\.\d+\.\d+\)$", "", subject).strip()
        d[2].append(subj); d[3] = sha
    return sorted(out.values(), key=lambda r: ver(r[0]), reverse=True)


def backfill():
    text = HEAD
    for v, date, subjects, _ in releases():
        text += "\n" + entry(v, date, list(dict.fromkeys(subjects)))
    open(CHANGELOG, "w").write(text)


def bump(new, summary):
    cur = json.load(open(PLUGIN))
    if ver(new) <= ver(cur["version"]):
        sys.exit(f"{new} is not newer than {cur['version']}")
    cur["version"] = new
    open(PLUGIN, "w").write(json.dumps(cur, indent=2) + "\n")
    old = open(CHANGELOG).read() if os.path.exists(CHANGELOG) else HEAD
    open(CHANGELOG, "w").write(prepend(old, entry(new, datetime.date.today().isoformat(), [summary])))


def tag(all_):
    pairs = [(v, sha) for v, _, _, sha in releases()] if all_ else [(json.load(open(PLUGIN))["version"], "HEAD")]
    made = []
    for v, sha in pairs:
        if subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/v{v}"], cwd=ROOT, capture_output=True).returncode:
            git("tag", "-a", f"v{v}", sha, "-m", f"agentic-sdlc {v}"); made.append(f"v{v}")
    print(f"tagged locally: {', '.join(made) or 'nothing new'}\nto publish: git push origin " + (" ".join(made[:1]) if len(made) == 1 else "--tags"))


def test():
    e = entry("0.2.0", "2026-10-25", ["Adds profiles", "Fixes x"])
    assert e == "## 0.2.0 - 2026-10-25\n- Adds profiles\n- Fixes x\n"
    base = HEAD + "\n" + entry("0.1.1", "2026-10-17", ["old"])
    out = prepend(base, e)
    assert out.index("## 0.2.0") < out.index("## 0.1.1") and out.startswith("# Changelog")
    assert [m for m in ENTRY.findall(out)] == ["0.2.0", "0.1.1"]
    assert since(out, "0.1.1") == e.strip() and since(out, "0.2.0") == "" and since(out, "0.0.9").count("## ") == 2
    assert ver("0.1.10") > ver("0.1.9")  # numeric, not alphabetical
    print("ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--test"]:
        test()
    elif a[:1] == ["bump"]:
        bump(a[1], a[2]); print("bumped to", a[1])
    elif a[:1] == ["tag"]:
        tag("--all" in a)
    elif a[:1] == ["since"]:
        print(since(open(CHANGELOG).read(), a[1]))
    elif a == ["backfill"]:
        backfill(); print("wrote", CHANGELOG)
    else:
        sys.exit(__doc__)
