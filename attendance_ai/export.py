import csv
import json
import urllib.request


def _final_status(s, unresolved):
    if s.status != "review":
        return s.status
    if unresolved == "error":
        raise ValueError(f"{s.roll} still needs teacher review (orange). Resolve before saving.")
    return unresolved   # 'absent' or 'present'


def to_payload(result, unresolved="error", teacher_id=""):
    return {
        "date": result.date, "section": result.section, "teacher_id": teacher_id,
        "records": [{"roll": s.roll, "name": s.name,
                     "status": _final_status(s, unresolved),
                     "similarity": round(s.similarity, 3), "source": s.source}
                    for s in result.students],
    }


def to_csv(result, path, unresolved="error"):
    p = to_payload(result, unresolved)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "section", "roll", "name", "status", "similarity", "source"])
        for r in p["records"]:
            w.writerow([p["date"], p["section"], r["roll"], r["name"],
                        r["status"], r["similarity"], r["source"]])
    return path


class CollegeClient:
    """One-click upload. ADAPT the URL / auth / JSON shape to your college's attendance API."""

    def __init__(self, url, token=None, timeout=30):
        self.url, self.token, self.timeout = url, token, timeout

    def push(self, payload):
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {self.token}"} if self.token else {})})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return r.status, r.read().decode()
