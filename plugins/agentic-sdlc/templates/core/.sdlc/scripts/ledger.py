"""Run ledger: one JSON row per agent run, in runs.jsonl on the orphan `sdlc-metrics` branch.

Usage: python3 .sdlc/scripts/ledger.py append <stage> <issue> <model> <usage.json>   (prints the outcome)
       python3 .sdlc/scripts/ledger.py count [--today TZ] [--issue N] [--stage S]
       python3 .sdlc/scripts/ledger.py --test
Needs GH_TOKEN and GH_REPO. Reading needs contents:read, appending needs contents:write.
"""
import base64
import datetime
import json
import os
import re
import subprocess
import sys

BRANCH, FILE = "sdlc-metrics", "runs.jsonl"
RATE_LIMIT = re.compile(r"rate.?limit|usage limit|limit reached|too many requests", re.I)


def api(*args, body=None):
    """Return (ok, parsed json or raw text). A failed call is a value, so callers can retry or treat 404 as empty."""
    p = subprocess.run(["gh", "api", *args, *(["--input", "-"] if body is not None else [])], input=json.dumps(body) if body is not None else None,
                       capture_output=True, text=True)
    if p.returncode:
        return False, p.stderr
    try:
        return True, json.loads(p.stdout)
    except ValueError:
        return True, p.stdout


def read_rows():
    ok, res = api(f"repos/{os.environ['GH_REPO']}/contents/{FILE}?ref={BRANCH}")
    if not ok:
        if "404" in res or "Not Found" in res:
            return [], None
        raise RuntimeError(res)
    text = base64.b64decode(res["content"]).decode()
    return [json.loads(l) for l in text.splitlines() if l.strip()], res["sha"]


def outcome(results):
    r = results[-1] if results else None
    if r is None:
        return "error"
    if RATE_LIMIT.search(str(r.get("result", ""))) and r.get("is_error"):
        return "rate_limited"
    return "error" if r.get("is_error") or r.get("subtype", "success") != "success" else "ok"


def row(stage, issue, model, results):
    r = results[-1] if results else {}
    u = r.get("usage") or {}
    return {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "run": os.environ.get("GITHUB_RUN_ID", ""), "workflow": os.environ.get("GITHUB_WORKFLOW", ""),
            "stage": stage, "issue": int(issue) if str(issue).isdigit() else None, "model": model,
            "cost": r.get("total_cost_usd", 0), "turns": r.get("num_turns", 0),
            "input_tokens": u.get("input_tokens", 0), "output_tokens": u.get("output_tokens", 0),
            "cache_read_tokens": u.get("cache_read_input_tokens", 0), "duration_ms": r.get("duration_ms", 0),
            "outcome": outcome(results)}


def append(new, tries=5):
    repo = os.environ["GH_REPO"]
    err = ""
    for _ in range(tries):
        rows, sha = read_rows()
        text = "".join(json.dumps(r) + "\n" for r in rows + [new])
        if sha:
            # The Contents API rejects a stale sha, so a concurrent append makes this attempt fail and re-read.
            ok, err = api("-X", "PUT", f"repos/{repo}/contents/{FILE}", body={
                "message": "ledger: " + new["stage"], "branch": BRANCH, "sha": sha,
                "content": base64.b64encode(text.encode()).decode()})
        else:
            ok, err = create_branch(repo, text)
        if ok:
            return
    raise RuntimeError("could not append to the ledger: " + str(err))


def create_branch(repo, text):
    ok, tree = api("-X", "POST", f"repos/{repo}/git/trees", body={
        "tree": [{"path": FILE, "mode": "100644", "type": "blob", "content": text}]})
    if not ok:
        return False, tree
    ok, commit = api("-X", "POST", f"repos/{repo}/git/commits", body={"message": "ledger: start", "tree": tree["sha"]})
    if not ok:
        return False, commit
    return api("-X", "POST", f"repos/{repo}/git/refs", body={"ref": f"refs/heads/{BRANCH}", "sha": commit["sha"]})


def count(rows, today=None, issue=None, stage=None, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if today:
        from zoneinfo import ZoneInfo
        day = now.astimezone(ZoneInfo(today)).date()
    def keep(r):
        if issue is not None and r.get("issue") != issue:
            return False
        if stage and r.get("stage") != stage:
            return False
        return not today or datetime.datetime.fromisoformat(r["ts"]).astimezone(ZoneInfo(today)).date() == day
    return sum(1 for r in rows if keep(r))


def test():
    ok = {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.2, "num_turns": 11,
          "usage": {"output_tokens": 3400}}
    assert outcome([ok]) == "ok" and outcome([]) == "error"
    assert outcome([{**ok, "is_error": True, "result": "Claude usage limit reached"}]) == "rate_limited"
    assert outcome([{**ok, "is_error": True, "subtype": "error_max_turns"}]) == "error"
    r = row("build", "7", "sonnet", [ok])
    assert r["issue"] == 7 and r["cost"] == 0.2 and r["output_tokens"] == 3400 and r["outcome"] == "ok"
    now = datetime.datetime(2026, 10, 20, 12, 0, tzinfo=datetime.timezone.utc)
    rows = [{**r, "ts": "2026-10-20T10:00:00+00:00"}, {**r, "ts": "2026-10-19T10:00:00+00:00", "issue": 8},
            {**r, "ts": "2026-10-19T23:30:00+00:00", "stage": "revise"}]  # 23:30Z is already the 20th in Copenhagen
    assert count(rows, "Europe/Copenhagen", now=now) == 2 and count(rows) == 3
    assert count(rows, issue=7, stage="build") == 1
    print("ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--test"]:
        test()
    elif a[:1] == ["append"]:
        _, stage, issue, model, path = a
        try:
            results = [x for x in json.load(open(path)) if x.get("type") == "result"]
        except (OSError, ValueError):
            results = []
        new = row(stage, issue, model, results)
        append(new)
        print(new["outcome"])
    elif a[:1] == ["count"]:
        opt = dict(zip(a[1::2], a[2::2]))
        n = count(read_rows()[0], opt.get("--today"), int(opt["--issue"]) if "--issue" in opt else None, opt.get("--stage"))
        print(n)
    else:
        sys.exit(__doc__)
