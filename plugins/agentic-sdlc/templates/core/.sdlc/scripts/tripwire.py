"""Stop a task PR that grew past its task: unplanned protected paths, unplanned dependencies, or too many files.

Usage: python3 .sdlc/scripts/tripwire.py <base-ref> <task-body-file> <plan-file> <protected-json>
       python3 .sdlc/scripts/tripwire.py --test
Prints one reason per line and exits 1 if the tripwire fires.
"""
import fnmatch
import json
import re
import subprocess
import sys

LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}


def field(body, name):
    m = re.search(rf"^- {name}:(.*)$", body, re.M)
    return m.group(1).strip() if m else ""


def ticks(text):
    return re.findall(r"`([^`]+)`", text)


def matches(path, pattern):
    pattern = pattern.rstrip("/")
    return (fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, pattern + "/*")
            or path.startswith(pattern + "/") or fnmatch.fnmatch("/" + path, "/" + pattern))


def deps(pkg):
    return set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))


def check(changed, task_body, plan, protected, old_pkg, new_pkg):
    reasons = []
    allowed_protected = ticks(field(task_body, "Protected paths"))
    task_files = ticks(field(task_body, "Files"))

    for path in changed:
        if any(matches(path, p) for p in protected) and not any(matches(path, a) for a in allowed_protected):
            reasons.append(f"protected path not in the task: {path}")

    planned = plan.split("## New dependencies", 1)[-1].split("\n## ", 1)[0] if "## New dependencies" in plan else ""
    # The scaffold task installs the stack, so its packages count as planned when the task touches package.json.
    scaffold = any(matches("package.json", a) for a in allowed_protected)
    for dep in sorted(deps(new_pkg) - deps(old_pkg)):
        if dep not in planned and not scaffold:
            reasons.append(f"dependency not in the plan: {dep}")

    # ponytail: a file counts as in scope if a listed path matches it or shares its folder; tune the limit if it is noisy.
    folders = {f.rsplit("/", 1)[0] for f in task_files if "/" in f}
    outside = [p for p in changed if p not in LOCKFILES
               and not any(matches(p, f) for f in task_files)
               and not any(p.startswith(d + "/") for d in folders)
               and not any(matches(p, a) for a in allowed_protected)]
    limit = max(3, len(task_files))
    if len(outside) > limit:
        reasons.append(f"{len(outside)} files outside the task's Files (limit {limit}): " + ", ".join(outside[:10]))
    return reasons


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout


def main(base, task_file, plan_file, protected_json):
    changed = git("diff", "--name-only", f"{base}...HEAD").split()
    old = git("show", f"{base}:package.json")
    try:
        new = open("package.json").read()
    except FileNotFoundError:
        new = ""
    reasons = check(changed, open(task_file).read(), open(plan_file).read(), json.loads(protected_json),
                    json.loads(old or "{}"), json.loads(new or "{}"))
    for r in reasons:
        print(r)
    sys.exit(1 if reasons else 0)


def test():
    protected = [".github/**", ".sdlc/**", "docs/constitution.md", "**/migrations/**", "package.json", "package-lock.json"]
    task = "- Covers: AC-2\n- Files: `src/theme/theme.ts`, `src/theme/*.test.ts`\n- Protected paths: none\n"
    plan = "## New dependencies and services\nNone.\n\n## Tasks\n"
    ok = ["src/theme/theme.ts", "src/theme/theme.test.ts", "src/theme/useTheme.ts"]
    assert check(ok, task, plan, protected, {}, {}) == []
    r = check(ok + [".github/workflows/ci.yml"], task, plan, protected, {}, {})
    assert r == ["protected path not in the task: .github/workflows/ci.yml"], r
    r = check(ok + ["db/migrations/001.sql"], task, plan, protected, {}, {})
    assert r == ["protected path not in the task: db/migrations/001.sql"], r
    r = check(ok, task, plan, protected, {"dependencies": {"react": "1"}}, {"dependencies": {"react": "1", "lodash": "4"}})
    assert r == ["dependency not in the plan: lodash"], r
    plan2 = "## New dependencies and services\n- `lodash`: deep clone.\n\n## Tasks\n"
    assert check(ok, task, plan2, protected, {}, {"dependencies": {"lodash": "4"}}) == []
    r = check(ok + ["a.ts", "b.ts", "c.ts", "d.ts"], task, plan, protected, {}, {})
    assert len(r) == 1 and r[0].startswith("4 files outside"), r
    scaffold = "- Files: `src/`, `index.html`\n- Protected paths: `package.json`, `package-lock.json`, `.github/**`\n"
    r = check(["package.json", "package-lock.json", ".github/workflows/x.yml", "src/App.tsx", "index.html", "vite.config.ts"],
              scaffold, plan, protected, {}, {"dependencies": {"react": "18"}})
    assert r == [], r
    print("ok")


if __name__ == "__main__":
    test() if sys.argv[1:] == ["--test"] else main(*sys.argv[1:5])
