import base64
import os
from datetime import date

import requests

LAMA_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(LAMA_DIR)


def _log(msg):
    print(f"[pusher] {msg}", flush=True)


def _github_api(method, path, token, **kwargs):
    """Call the GitHub Contents API."""
    url = f"https://api.github.com/repos/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    r = requests.request(method, url, headers=headers, timeout=20, **kwargs)
    return r


def _push_file(token, repo_name, branch, repo_path, local_path, commit_msg):
    """
    Push a single file to GitHub via Contents API.
    repo_path: path inside the repo, e.g. "lama_dashboard/data/deals.csv"
    local_path: absolute path on disk
    Returns (success, message)
    """
    # Read local file as base64
    with open(local_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("ascii")

    api_path = f"{repo_name}/contents/{repo_path}"

    # Get current SHA (needed for update)
    get_r = _github_api("GET", api_path, token, params={"ref": branch})
    if get_r.status_code == 200:
        sha = get_r.json().get("sha", "")
        _log(f"  {repo_path}: current SHA={sha[:8]}")
    elif get_r.status_code == 404:
        sha = None
        _log(f"  {repo_path}: new file (404 on GET)")
    else:
        return False, f"GET {repo_path} failed: {get_r.status_code} {get_r.text[:200]}"

    # Build PUT body
    body = {
        "message": commit_msg,
        "content": content_b64,
        "branch": branch,
    }
    if sha:
        body["sha"] = sha

    put_r = _github_api("PUT", api_path, token, json=body)
    if put_r.status_code in (200, 201):
        _log(f"  {repo_path}: pushed OK")
        return True, None
    else:
        return False, f"PUT {repo_path} failed: {put_r.status_code} {put_r.text[:300]}"


def push_to_github(summary=None):
    """
    Push data files to GitHub via REST API — no git binary required.
    Requires GITHUB_TOKEN env var.
    Returns dict: {success: bool, message: str}
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        msg = "GITHUB_TOKEN not set. Add it in Railway > Variables."
        _log(msg)
        return {"success": False, "message": msg}

    repo_name = os.environ.get("GITHUB_REPO", "sophieb-web/lama-dashboard")
    branch = os.environ.get("GITHUB_BRANCH", "main")

    # Build commit message
    if summary and summary.get("merged", 0) > 0:
        commit_msg = (f"auto-update: {summary.get('new_rounds', 0)} new rounds, "
                      f"{summary.get('new_companies', 0)} new companies — {date.today()}")
    else:
        commit_msg = f"auto-update: database sync — {date.today()}"

    _log(f"Pushing to {repo_name}@{branch}: {commit_msg}")

    # Files to push
    files = [
        ("lama_dashboard/data/deals.csv",    os.path.join(REPO_ROOT, "lama_dashboard", "data", "deals.csv")),
        ("lama_dashboard/data/staging.json", os.path.join(REPO_ROOT, "lama_dashboard", "data", "staging.json")),
    ]

    errors = []
    pushed = []
    for repo_path, local_path in files:
        if not os.path.exists(local_path):
            _log(f"  SKIP {repo_path}: not found on disk")
            continue
        ok, err = _push_file(token, repo_name, branch, repo_path, local_path, commit_msg)
        if ok:
            pushed.append(repo_path)
        else:
            _log(f"  ERROR: {err}")
            errors.append(err)

    if errors:
        return {"success": False, "message": " | ".join(errors)}
    if not pushed:
        return {"success": False, "message": "No files pushed"}

    result_msg = f"Pushed {len(pushed)} file(s): {commit_msg}"
    _log(result_msg)
    return {"success": True, "message": result_msg}
