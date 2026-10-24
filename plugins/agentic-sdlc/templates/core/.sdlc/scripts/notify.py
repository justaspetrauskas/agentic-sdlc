"""Send one event to the notification service. Best effort: it never fails a job, and skips silently when not set up.

Usage: python3 .sdlc/scripts/notify.py <kind> <title> <link> <dedupe>      kind: needs-you | critical | idea | info
       python3 .sdlc/scripts/notify.py --test
Needs `notify.url` in .sdlc/config.yml and the SDLC_NOTIFY_KEY secret (as an env var). Missing either means skip.
"""
import http.server
import json
import os
import re
import sys
import threading
import urllib.request

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.yml")


def settings(cfg):
    url = re.search(r"^notify:\s*\n\s+url:\s*\"?([^\"\s#]*)", cfg, re.M)
    project = re.search(r"^project:\s*\"?([^\"\n#]*[^\"\s#])", cfg, re.M)
    return (url.group(1) if url else ""), (project.group(1) if project else "")


def send(url, key, project, kind, title, link, dedupe):
    body = json.dumps({"project": project, "kind": kind, "title": title, "link": link or None, "dedupe": dedupe}
                      if link else {"project": project, "kind": kind, "title": title, "dedupe": dedupe}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/events", data=body, method="POST",
                                 headers={"authorization": f"Bearer {key}", "content-type": "application/json",
                                          # Cloudflare answers the default Python-urllib agent with error 1010 (HTTP 403).
                                          "user-agent": "agentic-sdlc-notify/1"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r).get("status")


def main(args):
    kind, title, link, dedupe = args
    url, project = settings(open(CONFIG).read())
    key = os.environ.get("SDLC_NOTIFY_KEY", "")
    if not (url and key and project):
        print("Notifications are not set up. Skipped.")
        return
    try:
        print("notify:", send(url, key, project, kind, title, link, dedupe))
    except Exception as e:  # a notification must never fail the job that sends it
        print(f"::warning::notify failed: {e}")


def test():
    cfg = 'project: "my-app"\nnotify:\n  url: "https://n.example.dev"  # the service\n  other: 1\n'
    assert settings(cfg) == ("https://n.example.dev", "my-app"), settings(cfg)
    assert settings('project: x\nnotify:\n  url: ""\n') == ("", "x")
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            got.update(path=self.path, auth=self.headers["authorization"], agent=self.headers["user-agent"], body=json.loads(self.rfile.read(int(self.headers["content-length"]))))
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"sent"}')
        def log_message(self, *a): pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}/"
    assert send(base, "k", "my-app", "needs-you", "Plan ready", "https://x/y", "plan-1") == "sent"
    assert got["path"] == "/v1/events" and got["auth"] == "Bearer k"
    assert not got["agent"].startswith("Python-urllib"), got["agent"]
    assert got["body"] == {"project": "my-app", "kind": "needs-you", "title": "Plan ready", "link": "https://x/y", "dedupe": "plan-1"}
    send(base, "k", "my-app", "info", "t", "", "d")
    assert "link" not in got["body"]
    srv.shutdown()
    print("ok")


if __name__ == "__main__":
    test() if sys.argv[1:] == ["--test"] else main(sys.argv[1:])
