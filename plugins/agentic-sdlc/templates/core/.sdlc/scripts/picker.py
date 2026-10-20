"""Pick the next task to build. A plain script, not an agent: at most one active item per repo.

Usage: python3 .sdlc/scripts/picker.py [--dry-run] [--window HH:MM-HH:MM --tz ZONE]
       A window keeps non-critical builds to those hours; leave it out to build at any hour.
       python3 .sdlc/scripts/picker.py --test
"""
import datetime
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


def choose(parents, tasks, direct=()):
    """Return (done_parents, next_task_or_None). Parents are state:planned issues, tasks are type:task issues.
    Direct items are fix/UX issues with no state label: the issue is its own task, no spec or plan.
    One active item per repo: if the first item with open tasks waits for the owner, nothing else starts."""
    by_parent = {d["number"]: [(1, {**d, "state": "OPEN"})] for d in direct}
    parents = list(parents) + list(direct)
    for t in tasks:
        m = TASK_TITLE.match(t["title"])
        if m:
            by_parent.setdefault(int(m.group(3)), []).append((int(m.group(1)), t))
    done, pick, started = [], None, False
    for p in sorted(parents, key=lambda p: (rank(p), p["createdAt"])):
        mine = sorted(by_parent.get(p["number"], []), key=lambda x: x[0])
        open_tasks = [t for _, t in mine if t["state"] == "OPEN"]
        if mine and not open_tasks:
            done.append(p)
        elif open_tasks and not started:
            started = True
            if not (labels(open_tasks[0]) & STOP):
                pick = {**open_tasks[0], "critical": "critical" in labels(p)}
    return done, pick


def in_window(window, tz, now=None):
    """True when the local time in tz is inside HH:MM-HH:MM; a window may wrap past midnight."""
    from zoneinfo import ZoneInfo
    now = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(ZoneInfo(tz)).strftime("%H:%M")
    start, end = window.split("-")
    return start <= now < end if start <= end else now >= start or now < end


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout.strip()


def main(dry, window=None, tz="UTC"):
    prs = json.loads(gh("pr", "list", "--state", "open", "--json", "number,headRefName"))
    busy = [p for p in prs if p["headRefName"].startswith(("fix/", "update/"))]
    building = json.loads(gh("issue", "list", "--label", "state:building", "--state", "open", "--json", "number"))
    parents = json.loads(gh("issue", "list", "--label", "state:planned", "--state", "open", "--limit", "100",
                            "--json", "number,title,labels,createdAt"))
    tasks = json.loads(gh("issue", "list", "--label", "type:task", "--state", "all", "--limit", "500",
                          "--json", "number,title,state,labels"))
    direct = [i for kind in ("type:fix", "type:ux")
              for i in json.loads(gh("issue", "list", "--label", kind, "--state", "open", "--limit", "100",
                                     "--json", "number,title,labels,createdAt"))
              if not any(n.startswith("state:") for n in labels(i))]
    done, pick = choose(parents, tasks, direct)

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
    if window and not pick["critical"] and not in_window(window, tz):
        print(f"#{pick['number']} waits for the night window {window} ({tz}).")
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
    assert choose(parents, tasks)[1] is None  # the first item waits for you, so nothing else starts

    tasks = [t(24, 1, 1, 7, "CLOSED"), t(18, 1, 1, 13)]
    done, pick = choose(parents, tasks)
    assert [p["number"] for p in done] == [7] and pick["number"] == 18

    fix = {"number": 40, "title": "Fix", "labels": lab("type:fix", "state:planned"), "createdAt": "2026-10-19"}
    assert choose(parents + [fix], tasks + [t(41, 1, 1, 40)])[1]["number"] == 41  # fix beats older ideas
    bug = {"number": 39, "title": "Fix: x", "labels": lab("type:fix"), "createdAt": "2026-10-19"}
    assert choose(parents, [t(25, 2, 2, 7)], [bug])[1]["number"] == 39  # a direct fix is its own task, ahead of ideas
    blocked = {**bug, "labels": lab("type:fix", "needs-you")}
    assert choose(parents, [t(25, 2, 2, 7)], [blocked])[1] is None  # and blocks like any item when it waits for you
    assert choose(parents, [t(25, 2, 2, 7)])[1]["critical"] is False
    crit = {**parents[0], "labels": lab("type:idea", "state:planned", "critical")}
    assert choose([crit], [t(18, 1, 1, 13)])[1]["critical"] is True  # critical comes from the parent
    from zoneinfo import ZoneInfo
    at = lambda h, m: datetime.datetime(2026, 10, 20, h, m, tzinfo=ZoneInfo("Europe/Copenhagen"))
    assert in_window("01:00-06:00", "Europe/Copenhagen", at(1, 0)) and not in_window("01:00-06:00", "Europe/Copenhagen", at(6, 0))
    assert in_window("22:00-04:00", "Europe/Copenhagen", at(23, 30)) and not in_window("22:00-04:00", "Europe/Copenhagen", at(12, 0))
    print("ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    arg = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    test() if a == ["--test"] else main("--dry-run" in a, arg("--window"), arg("--tz", "UTC"))
