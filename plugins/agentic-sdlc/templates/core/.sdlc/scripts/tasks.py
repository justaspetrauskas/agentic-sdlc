"""Turn the tasks in an approved plan into GitHub issues, one per task, as sub-issues of the parent issue.

Usage: python3 .sdlc/scripts/tasks.py <parent-issue-number> <plan-file>
       python3 .sdlc/scripts/tasks.py --test
Safe to rerun: a task whose issue already exists is skipped.
"""
import json
import re
import subprocess
import sys

TASK = re.compile(r"^### (T-\d+): (.+)$", re.M)


def parse(plan):
    heads = list(TASK.finditer(plan))
    tasks = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(plan)
        body = plan[m.end():end]
        body = re.split(r"^## ", body, maxsplit=1, flags=re.M)[0].strip()
        tasks.append({"id": m.group(1), "title": m.group(2).strip(), "body": body})
    return tasks


def title(task, n, total, parent):
    return f"Task {n} of {total}: {task['title']} (#{parent})"


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout.strip()


def main(parent, path):
    tasks = parse(open(path).read())
    if not tasks:
        sys.exit(f"No tasks found in {path}")
    existing = {i["title"] for i in json.loads(
        gh("issue", "list", "--label", "type:task", "--state", "all", "--limit", "500", "--json", "title"))}
    for n, task in enumerate(tasks, 1):
        t = title(task, n, len(tasks), parent)
        if t in existing:
            print(f"skip  {t}")
            continue
        body = f"{task['id']} from `{path}`. Parent: #{parent}.\n\n{task['body']}"
        url = gh("issue", "create", "--title", t, "--body", body, "--label", "type:task")
        print(f"made  {t} {url}")
        num = url.rsplit("/", 1)[1]
        try:
            child = gh("api", f"repos/{{owner}}/{{repo}}/issues/{num}", "--jq", ".id")
            gh("api", "-X", "POST", f"repos/{{owner}}/{{repo}}/issues/{parent}/sub_issues", "-F", f"sub_issue_id={child}")
        except subprocess.CalledProcessError as e:
            print(f"      not linked as sub-issue ({e.stderr.strip()}); the body names the parent")


def test():
    plan = """# Plan
## Tasks
### T-1: Scaffold the app
- Covers: AC-1
- Done when: build passes

### T-2: Add the toggle
- Covers: AC-2, AC-3

## Gates
- More than 5 tasks: no
"""
    tasks = parse(plan)
    assert [t["id"] for t in tasks] == ["T-1", "T-2"], tasks
    assert tasks[0]["body"] == "- Covers: AC-1\n- Done when: build passes", tasks[0]
    assert "Gates" not in tasks[1]["body"], tasks[1]
    assert title(tasks[1], 2, 2, 13) == "Task 2 of 2: Add the toggle (#13)"
    print("ok")


if __name__ == "__main__":
    test() if sys.argv[1:] == ["--test"] else main(int(sys.argv[1]), sys.argv[2])
