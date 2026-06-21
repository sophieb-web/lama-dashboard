import json
import os

STAGING_FILE = os.path.join(os.path.dirname(__file__), "data", "staging.json")

_EMPTY = {
    "last_scraped": None,
    "next_scheduled": None,
    "scrape_status": "idle",
    "scrape_log": [],
    "pending": [],
    "approved": [],
    "rejected": [],
    "pushed": [],
}


def load_staging():
    if not os.path.exists(STAGING_FILE):
        save_staging(_EMPTY.copy())
        return _EMPTY.copy()
    with open(STAGING_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_staging(data):
    with open(STAGING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_findings(findings_list):
    data = load_staging()
    existing_ids = {f["id"] for f in data["pending"] + data["approved"] + data["rejected"] + data["pushed"]}
    added = 0
    for f in findings_list:
        if f["id"] not in existing_ids:
            data["pending"].append(f)
            existing_ids.add(f["id"])
            added += 1
    save_staging(data)
    return added


def approve_finding(finding_id):
    data = load_staging()
    for i, f in enumerate(data["pending"]):
        if f["id"] == finding_id:
            f["status"] = "approved"
            data["approved"].append(f)
            data["pending"].pop(i)
            break
    save_staging(data)


def reject_finding(finding_id):
    data = load_staging()
    for i, f in enumerate(data["pending"]):
        if f["id"] == finding_id:
            f["status"] = "rejected"
            data["rejected"].append(f)
            data["pending"].pop(i)
            break
    save_staging(data)


def approve_all():
    data = load_staging()
    for f in data["pending"]:
        f["status"] = "approved"
        data["approved"].append(f)
    data["pending"] = []
    save_staging(data)


def reject_all():
    data = load_staging()
    for f in data["pending"]:
        f["status"] = "rejected"
        data["rejected"].append(f)
    data["pending"] = []
    save_staging(data)


def update_finding(finding_id, field_updates):
    """Update data fields of a pending finding."""
    data = load_staging()
    for f in data["pending"]:
        if f["id"] == finding_id:
            f["data"].update(field_updates)
            break
    save_staging(data)


def get_approved():
    return load_staging()["approved"]


def clear_pushed(finding_ids):
    ids = set(finding_ids)
    data = load_staging()
    to_push = [f for f in data["approved"] if f["id"] in ids]
    for f in to_push:
        f["status"] = "pushed"
        data["pushed"].append(f)
    data["approved"] = [f for f in data["approved"] if f["id"] not in ids]
    save_staging(data)


def get_stats():
    data = load_staging()
    return {
        "pending": len(data["pending"]),
        "approved": len(data["approved"]),
        "rejected": len(data["rejected"]),
        "pushed": len(data["pushed"]),
        "last_scraped": data.get("last_scraped"),
        "next_scheduled": data.get("next_scheduled"),
        "scrape_status": data.get("scrape_status", "idle"),
        "scrape_log": data.get("scrape_log", []),
    }
