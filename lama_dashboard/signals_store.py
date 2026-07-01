import json
import os
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SIGNALS_FILE = os.path.join(DATA_DIR, "signals.json")

PRIORITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2}

_EMPTY = {
    "last_run": None,
    "next_run": None,
    "run_status": "idle",
    "run_log": [],
    "signals": [],
    "watchlist": [],
    "dismissed": [],
    "action_taken": [],
}


def load_signals():
    if not os.path.exists(SIGNALS_FILE):
        return dict(_EMPTY)
    try:
        with open(SIGNALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in _EMPTY:
            if key not in data:
                data[key] = _EMPTY[key] if isinstance(_EMPTY[key], list) else _EMPTY[key]
        return data
    except Exception as e:
        print(f"[signals_store] load error: {e}")
        return dict(_EMPTY)


def save_signals(data):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SIGNALS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[signals_store] save error: {e}")


def add_signals(signal_list):
    data = load_signals()
    existing_ids = {s["id"] for s in data["signals"]}
    existing_ids |= {s["id"] for s in data["watchlist"]}
    existing_ids |= {s["id"] for s in data.get("dismissed", [])}
    existing_ids |= {s["id"] for s in data.get("action_taken", [])}

    dismissed_ids = {s["id"] for s in data.get("dismissed", [])}

    added = 0
    for sig in signal_list:
        if sig["id"] in existing_ids or sig["id"] in dismissed_ids:
            continue
        sig["status"] = "active"
        data["signals"].append(sig)
        existing_ids.add(sig["id"])
        added += 1

    save_signals(data)
    return added


def dismiss_signal(signal_id):
    data = load_signals()
    sig = _pop_from_active(data, signal_id)
    if sig:
        sig["status"] = "dismissed"
        data["dismissed"].append(sig)
    save_signals(data)


def save_signal(signal_id):
    data = load_signals()
    sig = _pop_from_active(data, signal_id)
    if sig:
        sig["status"] = "saved"
        sig["saved_at"] = _now()
        data["watchlist"].append(sig)
    save_signals(data)


def unsave_signal(signal_id):
    data = load_signals()
    sig = next((s for s in data["watchlist"] if s["id"] == signal_id), None)
    if sig:
        data["watchlist"] = [s for s in data["watchlist"] if s["id"] != signal_id]
        sig["status"] = "active"
        data["signals"].append(sig)
    save_signals(data)


def mark_action_taken(signal_id, note=""):
    data = load_signals()
    sig = _pop_from_active(data, signal_id)
    if not sig:
        sig = next((s for s in data["watchlist"] if s["id"] == signal_id), None)
        if sig:
            data["watchlist"] = [s for s in data["watchlist"] if s["id"] != signal_id]
    if sig:
        sig["status"] = "action_taken"
        sig["action_note"] = note
        sig["actioned_at"] = _now()
        data["action_taken"].append(sig)
    save_signals(data)


def get_active_signals():
    data = load_signals()
    active = [s for s in data["signals"] if s.get("status") == "active"]
    active.sort(key=lambda s: (
        PRIORITY_ORDER.get(s.get("priority", "Medium"), 2),
        0 if s.get("portfolio_relevant") else 1,
        -(s.get("detected_at") or ""),
    ))
    return active


def get_watchlist():
    data = load_signals()
    return data.get("watchlist", [])


def get_stats():
    data = load_signals()
    active = [s for s in data["signals"] if s.get("status") == "active"]
    by_priority = {"Critical": 0, "High": 0, "Medium": 0}
    by_category = {}
    for s in active:
        p = s.get("priority", "Medium")
        by_priority[p] = by_priority.get(p, 0) + 1
        cat = s.get("category", "Market")
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "critical": by_priority.get("Critical", 0),
        "high": by_priority.get("High", 0),
        "medium": by_priority.get("Medium", 0),
        "watchlist": len(data.get("watchlist", [])),
        "action_taken": len(data.get("action_taken", [])),
        "by_category": by_category,
        "total_active": len(active),
    }


def get_run_status():
    data = load_signals()
    return {
        "last_run": data.get("last_run"),
        "next_run": data.get("next_run"),
        "run_status": data.get("run_status", "idle"),
        "run_log": data.get("run_log", []),
    }


def set_run_status(status, log_lines=None, last_run=None, next_run=None):
    data = load_signals()
    data["run_status"] = status
    if log_lines is not None:
        data["run_log"] = log_lines
    if last_run:
        data["last_run"] = last_run
    if next_run:
        data["next_run"] = next_run
    save_signals(data)


def _pop_from_active(data, signal_id):
    sig = next((s for s in data["signals"] if s["id"] == signal_id), None)
    if sig:
        data["signals"] = [s for s in data["signals"] if s["id"] != signal_id]
    return sig


def _now():
    return datetime.now(timezone.utc).isoformat()
