"""Application tracker — logs applied jobs to avoid duplicates and enable resume."""
import json
from pathlib import Path
from datetime import datetime

TRACKER_FILE = Path(__file__).parent / "applied_jobs.json"


def load_tracker() -> list:
    if TRACKER_FILE.exists():
        return json.loads(TRACKER_FILE.read_text())
    return []


def save_tracker(data: list):
    TRACKER_FILE.write_text(json.dumps(data, indent=2))


def is_already_applied(url: str) -> bool:
    tracker = load_tracker()
    return any(entry["url"] == url for entry in tracker)


def log_application(job: dict, status: str = "submitted"):
    tracker = load_tracker()
    tracker.append({
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "url": job.get("url", ""),
        "source": job.get("source", ""),
        "score": job.get("score", 0),
        "status": status,
        "applied_at": datetime.now().isoformat(),
    })
    save_tracker(tracker)
