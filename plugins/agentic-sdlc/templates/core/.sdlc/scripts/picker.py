"""Pick the next task to build. A plain script, not an agent: at most one active item per repo.

Usage: python3 .sdlc/scripts/picker.py [--dry-run]
       python3 .sdlc/scripts/picker.py --test
"""
import json
import re
import subprocess
import sys

TASK_TITLE = re.compile(r"^Task (\d+) of (\d+): .* \(#(\d+)\)$")
RANK = ["critical", "type:fix", "type:ux", "type:design", "type:idea"]
STOP = {"needs-you", "state:blocked"}


def labels(issue):
    return {l["name"] for l in issue.get("labels", [])}


def rank(parent):
    names = labels(parent)
    return next((i for i, l in enumerate(RANK) if l in names), len(RANK))


def choose(parents, tasks):
    """Return (done_parents, next_task_or_None). Parents are state:planned issues, tasks are type:task issues."""
    by_parent = {}
    for t in tasks:
        m = TASK_TITLE.match(t["title"])
        if m:
            by_parent.setdefault(int(m.group(3)), []).append((int(m.group(1)), t))
    done, pick = [], None
    for p in sorted(parents, key=lambda p: (rank(p), p["createdAt"])):
        mine = sorted(by_parent.get(p["number"], []), key=lambda x: x[0])
        open_tasks = [t for _, t in mine if t["state"] == "OPEN"]
        if mine and not open_tasks:
            done.append(p)
        elif pick is None and open_tasks and not (labels(open_tasks[0]) & STOP):
            pick = open_tasks[0]
    return done, pick


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout.strip()


def main(dry):
    prs = json.loads(gh("pr", "list", "--state", "open", "--json", "number,headRefName"))
    busy = [p for p in prs if p["headRefName"].startswith(("fix/", "update/"))]
    building = json.loads(gh("issue", "list", "--label", "state:building", "--state", "open", "--json", "number"))
    parents = json.loads(gh("issue", "list", "--label", "state:planned", "--state", "open", "--limit", "100",
                            "--json", "number,title,labels,createdAt"))
    tasks = json.loads(gh("issue", "list", "--label", "type:task", "--state", "all", "--limit", "500",
                          "--json", "number,title,state,labels"))
    done, pick = choose(parents, tasks)

    for p in done:
        print(f"done  #{p['number']} {p['title']}")
        if not dry:
            gh("issue", "edit", str(p["number"]), "--add-label", "state:done", "--remove-label", "state:planned")
            gh("issue", "comment", str(p["number"]), "--body",
               "All tasks are merged. The app deploys from main after CI passes.")

    if busy or building:
        print("busy: " + ", ".join([f"PR #{p['number']}" for p in busy] + [f"#{i['number']}" for i in building]))
        return
    if not pick:
        print("Nothing to build.")
        return
    print(f"build #{pick['number']} {pick['title']}")
    if not dry:
        # Label first, so a second picker run sees this task as active before the build run starts.
        gh("issue", "edit", str(pick["number"]), "--add-label", "state:building")
        gh("workflow", "run", "sdlc-build.yml", "-f", f"task={pick['number']}")


def test():
    lab = lambda *n: [{"name": x} for x in n]
    parents = [
        {"number": 13, "title": "Dark mode", "labels": lab("type:idea", "state:planned"), "createdAt": "2026-10-18"},
        {"number": 7, "title": "Todo list", "labels": lab("type:idea", "state:planned"), "createdAt": "2026-10-17"},
    ]
    t = lambda n, i, of, parent, state="OPEN", *l: {"number": n, "title": f"Task {i} of {of}: x (#{parent})",
                                                   "state": state, "labels": lab("type:task", *l)}
    tasks = [t(24, 1, 2, 7, "CLOSED"), t(25, 2, 2, 7), t(18, 1, 1, 13)]
    done, pick = choose(parents, tasks)
    assert done == [] and pick["number"] == 25, pick  # oldest parent first, next open task

    tasks = [t(24, 1, 2, 7, "CLOSED"), t(25, 2, 2, 7, "OPEN", "needs-you"), t(18, 1, 1, 13)]
    assert choose(parents, tasks)[1]["number"] == 18  # a parent waiting for you is skipped

    tasks = [t(24, 1, 1, 7, "CLOSED"), t(18, 1, 1, 13)]
    done, pick = choose(parents, tasks)
    assert [p["number"] for p in done] == [7] and pick["number"] == 18

    fix = {"number": 40, "title": "Fix", "labels": lab("type:fix", "state:planned"), "createdAt": "2026-10-19"}
    assert choose(parents + [fix], tasks + [t(41, 1, 1, 40)])[1]["number"] == 41  # fix beats older ideas
    print("ok")


if __name__ == "__main__":
    test() if sys.argv[1:] == ["--test"] else main("--dry-run" in sys.argv)
