"""Decide whether a task PR may merge itself. A plain script, not an agent. Prints "merge" or one reason per line.

Usage: python3 merge.py <pr> <head-sha> <auto-merge-enabled> <protected-json>   (run from the base branch checkout)
       python3 merge.py --test
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tripwire import matches  # noqa: E402

AUTO_TYPES = {"type:fix", "type:ux"}
GATE_YES = re.compile(r"^- [^:\n]+:\s*\**yes\b", re.I | re.M)
NO_BLOCKING = "Review: no blocking findings."


def gates_fired(plan):
    section = plan.split("## Gates", 1)[-1].split("\n## ", 1)[0] if "## Gates" in plan else ""
    return [line.split(":", 1)[0][2:].strip("* ") for line in GATE_YES.findall(section)]


def decide(f):
    """f: facts about the PR. Returns the reasons it must wait for the owner (empty list means merge)."""
    r = []
    if not f["enabled"]:
        r.append("auto-merge is off (auto_merge.enabled in .sdlc/config.yml)")
    if not (f["parent_labels"] & AUTO_TYPES):
        r.append("only fixes and UX changes merge themselves")
    if f["gates"]:
        r.append("plan gates fired: " + ", ".join(f["gates"]))
    if f["protected"]:
        r.append("protected paths touched: " + ", ".join(f["protected"]))
    for name in ("checks", "scope"):
        if f["checks"].get(name) != "SUCCESS":
            r.append(f"CI {name} is not green")
    if f["review"] != NO_BLOCKING:
        r.append("no non-blocking review for the latest commit")
    if f["blocking_label"]:
        r.append("review:blocking is set")
    if f["needs_you"]:
        r.append("needs-you is set")
    if f["head_moved"]:
        r.append("new commits since the review")
    return r


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def facts(pr, sha, enabled, protected):
    p = json.loads(gh("pr", "view", pr, "--json", "body,labels,files,headRefOid,comments,commits"))
    task = re.search(r"^Closes #(\d+)", p["body"], re.M)
    task_body = gh("issue", "view", task.group(1), "--json", "body", "--jq", ".body") if task else ""
    t_labels = json.loads(gh("issue", "view", task.group(1), "--json", "labels")) if task else {"labels": []}
    parent = re.search(r"Parent: #(\d+)", task_body)
    if parent:
        parent_labels = {l["name"] for l in json.loads(gh("issue", "view", parent.group(1), "--json", "labels"))["labels"]}
    else:  # a fix or UX issue with no plan is its own task
        parent_labels = {l["name"] for l in t_labels["labels"]}
    plan_path = re.search(r"from `([^`]+)`", task_body.splitlines()[0]) if task_body else None
    plan = subprocess.run(["git", "show", f"HEAD:{plan_path.group(1)}"], capture_output=True, text=True).stdout if plan_path else ""
    # Check runs of the head commit via REST: needs only checks:read (gh pr checks also wants actions:read).
    runs = json.loads(gh("api", f"repos/{{owner}}/{{repo}}/commits/{p['headRefOid']}/check-runs?per_page=100",
                         "--jq", "[.check_runs[] | {name, conclusion}]"))
    checks = {c["name"]: (c["conclusion"] or "PENDING").upper() for c in runs}
    last_commit = p["commits"][-1]["committedDate"] if p["commits"] else ""
    reviews = [c for c in p["comments"] if c["body"].startswith("Review:") and c["createdAt"] >= last_commit]
    labels = {l["name"] for l in p["labels"]} | {l["name"] for l in t_labels["labels"]}
    return {
        "enabled": enabled == "true",
        "parent_labels": parent_labels,
        "gates": gates_fired(plan),
        "protected": [x["path"] for x in p["files"] if any(matches(x["path"], g) for g in protected)],
        "checks": checks,
        "review": reviews[-1]["body"].splitlines()[0].strip() if reviews else "",
        "blocking_label": "review:blocking" in labels,
        "needs_you": "needs-you" in labels,
        "head_moved": p["headRefOid"] != sha,
    }


def test():
    plan = "## Gates\n- Clarification needed: no.\n- New dependency or external service: **yes**. React.\n" \
           "  - Question: ok?\n- Data model or API change: yes, a key.\n- More than 5 tasks: no.\n\n## Risks\n- yes: x\n"
    assert gates_fired(plan) == ["New dependency or external service", "Data model or API change"], gates_fired(plan)
    ok = {"enabled": True, "parent_labels": {"type:fix"}, "gates": [], "protected": [],
          "checks": {"checks": "SUCCESS", "scope": "SUCCESS"}, "review": NO_BLOCKING,
          "blocking_label": False, "needs_you": False, "head_moved": False}
    assert decide(ok) == []
    assert decide({**ok, "parent_labels": {"type:idea"}}) == ["only fixes and UX changes merge themselves"]
    assert decide({**ok, "checks": {"checks": "SUCCESS", "scope": "FAILURE"}}) == ["CI scope is not green"]
    assert decide({**ok, "review": "Review: 1 blocking finding(s)."}) == ["no non-blocking review for the latest commit"]
    assert len(decide({**ok, "enabled": False, "protected": ["package.json"]})) == 2
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        test()
    else:
        pr, sha, enabled, protected = sys.argv[1:5]
        reasons = decide(facts(pr, sha, enabled, json.loads(protected)))
        print("\n".join(reasons) if reasons else "merge")
