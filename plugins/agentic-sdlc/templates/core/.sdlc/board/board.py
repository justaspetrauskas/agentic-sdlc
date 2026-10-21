"""Build the metrics board: one static HTML file from the run ledger and the repo's PRs. Runs on your machine.

Usage: python3 .sdlc/board/board.py [--open] [--out FILE]   (run inside the project repo; needs gh)
       python3 .sdlc/board/board.py --test
The data stays in GitHub; the file is written locally and never deployed.
"""
import collections
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
CI_CHECKS = ("checks", "scope", "secrets")


def day_of(ts, tz):
    from zoneinfo import ZoneInfo
    return datetime.datetime.fromisoformat(ts).astimezone(ZoneInfo(tz)).date().isoformat()


def rollup(rows, prs, blocked, cap, tz, now=None):
    """rows: ledger rows. prs: [{headRefName, mergedAt, labels:[names], checks:{name: conclusion}}]. Pure, so it can be tested."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    today = day_of(now.isoformat(), tz)
    add = lambda a, r: a.update(runs=a["runs"] + 1, cost=a["cost"] + r["cost"], turns=a["turns"] + r["turns"],
                                tokens=a["tokens"] + r["output_tokens"], ms=a["ms"] + r["duration_ms"])
    new = lambda: dict(runs=0, cost=0.0, turns=0, tokens=0, ms=0)
    total, days, stages, issues = new(), collections.defaultdict(new), collections.defaultdict(new), collections.defaultdict(new)
    for r in rows:
        add(total, r)
        add(days[day_of(r["ts"], tz)], r)
        add(stages[r["stage"]], r)
        add(issues[r["issue"]], r)
        issues[r["issue"]].setdefault("stages", collections.Counter())[r["stage"]] += 1
    retried = [i for i, v in issues.items() if v["stages"]["build"] > 1 or v["stages"]["revise"] > 0]
    task_prs = [p for p in prs if p["headRefName"].startswith(("fix/", "update/"))]
    return {
        "generated": now.isoformat(timespec="seconds"), "tz": tz,
        "cap": {"used": days[today]["runs"] if today in days else 0, "limit": cap, "day": today},
        "total": total,
        "days": [{"day": d, **v} for d, v in sorted(days.items())],
        "stages": [{"stage": s, **v} for s, v in sorted(stages.items(), key=lambda x: -x[1]["cost"])],
        "issues": [{"issue": i, "retried": i in retried, "stages": dict(v.pop("stages")), **v}
                   for i, v in sorted(issues.items(), key=lambda x: -x[1]["cost"])],
        "runs": sorted(rows, key=lambda r: r["ts"], reverse=True),
        "outcomes": {
            "run_ok": sum(r["outcome"] == "ok" for r in rows), "run_error": sum(r["outcome"] == "error" for r in rows),
            "run_rate_limited": sum(r["outcome"] == "rate_limited" for r in rows),
            "task_prs": len(task_prs),
            "ci_passed": sum(all(p["checks"].get(c) == "SUCCESS" for c in CI_CHECKS if c in p["checks"] or c != "secrets") for p in task_prs),
            "merged": sum(bool(p["mergedAt"]) for p in task_prs),
            "auto_merged": sum("auto-merged" in p["labels"] for p in task_prs),
            "retried_issues": len(retried), "blocked_issues": blocked,
        },
    }


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def collect():
    repo = json.loads(gh("repo", "view", "--json", "nameWithOwner"))["nameWithOwner"]
    os.environ["GH_REPO"] = repo
    import ledger
    rows, _ = ledger.read_rows()
    prs = []
    for p in json.loads(gh("pr", "list", "--state", "all", "--limit", "300", "--json",
                           "headRefName,mergedAt,labels,statusCheckRollup")):
        checks = {c.get("name"): (c.get("conclusion") or "").upper() for c in p["statusCheckRollup"] or []}
        prs.append({"headRefName": p["headRefName"], "mergedAt": p["mergedAt"],
                    "labels": [l["name"] for l in p["labels"]], "checks": checks})
    blocked = len(json.loads(gh("issue", "list", "--label", "state:blocked", "--state", "all", "--json", "number")))
    cfg = open(os.path.join(HERE, "..", "config.yml")).read()
    cap = int((re.search(r"daily_runs:\s*(\d+)", cfg) or [0, 20])[1])
    tz = (re.search(r"^timezone:\s*(\S+)", cfg, re.M) or [0, "UTC"])[1]
    return repo, rollup(rows, prs, blocked, cap, tz)


def render(repo, data):
    page = open(os.path.join(HERE, "board.html")).read()
    blob = json.dumps({"repo": repo, **data}).replace("</", "<\\/")
    return page.replace("__DATA__", blob)


def test():
    now = datetime.datetime(2026, 10, 20, 12, 0, tzinfo=datetime.timezone.utc)
    row = lambda ts, stage, issue, cost, outcome="ok": dict(ts=ts, stage=stage, issue=issue, cost=cost, turns=10,
                                                             output_tokens=100, duration_ms=1000, outcome=outcome)
    rows = [row("2026-10-20T10:00:00+00:00", "build", 5, 0.5), row("2026-10-20T11:00:00+00:00", "build", 5, 0.25, "error"),
            row("2026-10-20T11:30:00+00:00", "review", 6, 0.125), row("2026-10-19T09:00:00+00:00", "spec", 5, 1.0),
            row("2026-10-19T09:30:00+00:00", "revise", 6, 0.125)]
    pr = lambda branch, merged, labels, **c: dict(headRefName=branch, mergedAt=merged, labels=labels,
                                                  checks={"checks": "SUCCESS", "scope": "SUCCESS", "secrets": "SUCCESS", **c})
    old_pr = pr("fix/technical/4-w", "2026-10-18", []); del old_pr["checks"]["secrets"]  # before the secrets job existed
    prs = [pr("fix/technical/6-x", "2026-10-20", ["auto-merged"]), pr("update/technical/5-y", None, [], scope="FAILURE"),
           old_pr, pr("chore/docs/5-spec-z", "2026-10-19", [])]  # last one is not a task PR
    d = rollup(rows, prs, 1, 20, "Europe/Copenhagen", now)
    assert d["cap"] == {"used": 3, "limit": 20, "day": "2026-10-20"}, d["cap"]
    assert round(d["total"]["cost"], 3) == 2.0 and d["total"]["runs"] == 5
    assert [x["day"] for x in d["days"]] == ["2026-10-19", "2026-10-20"] and d["days"][1]["runs"] == 3
    assert d["stages"][0]["stage"] == "spec"  # most expensive first
    o = d["outcomes"]
    assert (o["task_prs"], o["ci_passed"], o["merged"], o["auto_merged"]) == (3, 2, 2, 1), o
    assert o["retried_issues"] == 2 and o["blocked_issues"] == 1 and o["run_error"] == 1, o
    assert "</script>" not in render("a/b", d).split('id="data"')[1].split("</script>")[0]
    print("ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--test"]:
        test()
    else:
        repo, data = collect()
        out = a[a.index("--out") + 1] if "--out" in a else os.path.join(os.environ.get("TMPDIR", "/tmp"), "sdlc-board.html")
        open(out, "w").write(render(repo, data))
        print(out)
        if "--open" in a:
            subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", out])
