import os
import subprocess
from datetime import date


def _log(msg):
    print(f"[pusher] {msg}", flush=True)


def _run(cmd, cwd):
    """Run a git command, return (stdout, stderr, returncode)."""
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True
    )
    if result.stdout.strip():
        _log(f"  stdout: {result.stdout.strip()}")
    if result.stderr.strip():
        _log(f"  stderr: {result.stderr.strip()}")
    return result


def push_to_github(summary=None):
    """
    Stage deals.csv, staging.json, commit, and push to origin main.
    Uses subprocess git — no gitpython dependency.
    Requires GITHUB_TOKEN env var for Railway authentication.
    Returns dict: {success: bool, message: str}
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    repo_name = os.environ.get("GITHUB_REPO", "sophieb-web/lama-dashboard")
    target_branch = os.environ.get("GITHUB_BRANCH", "main")

    # Repo root is two levels up from lama_dashboard/
    lama_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(lama_dir)
    _log(f"repo_root: {repo_root}")

    # Verify git is available
    check = _run(["git", "--version"], cwd=repo_root)
    if check.returncode != 0:
        return {"success": False, "message": "git not found on this system"}

    # Set git identity (required for commit if not configured globally)
    _run(["git", "config", "user.email", "bot@lama.vc"], cwd=repo_root)
    _run(["git", "config", "user.name", "Lama Dashboard Bot"], cwd=repo_root)

    # Files to stage — always forward slashes for git
    files_to_add = [
        "lama_dashboard/data/deals.csv",
        "lama_dashboard/data/taxonomy.csv",
        "lama_dashboard/data/staging.json",
    ]
    existing = [f for f in files_to_add
                if os.path.exists(os.path.join(repo_root, f.replace("/", os.sep)))]
    _log(f"Files to stage: {existing}")

    if not existing:
        return {"success": False, "message": "No data files found to commit"}

    # Stage files
    add_result = _run(["git", "add"] + existing, cwd=repo_root)
    if add_result.returncode != 0:
        return {"success": False, "message": f"git add failed: {add_result.stderr}"}

    # Check if anything changed
    status = _run(["git", "diff", "--cached", "--name-only"], cwd=repo_root)
    changed = [l for l in status.stdout.splitlines() if l.strip()]
    _log(f"Changed files: {changed}")
    if not changed:
        return {"success": True, "message": "Nothing to commit — database already up to date"}

    # Build commit message
    if summary and summary.get("merged", 0) > 0:
        msg = (f"auto-update: {summary.get('new_rounds', 0)} new rounds, "
               f"{summary.get('new_companies', 0)} new companies — {date.today()}")
    else:
        msg = f"auto-update: database sync — {date.today()}"

    _log(f"Committing: {msg}")
    commit_result = _run(["git", "commit", "-m", msg], cwd=repo_root)
    if commit_result.returncode != 0:
        return {"success": False, "message": f"git commit failed: {commit_result.stderr}"}

    # Set authenticated remote URL if token is available
    if token:
        remote_url = f"https://{token}@github.com/{repo_name}.git"
        _run(["git", "remote", "set-url", "origin", remote_url], cwd=repo_root)
        _log(f"Set remote URL with token")
    else:
        _log("WARNING: GITHUB_TOKEN not set — push may fail")

    # Push with explicit refspec so detached HEAD works
    refspec = f"HEAD:{target_branch}"
    _log(f"Pushing HEAD to {target_branch}...")
    push_result = _run(["git", "push", "origin", refspec], cwd=repo_root)
    if push_result.returncode != 0:
        return {"success": False,
                "message": f"git push failed: {push_result.stderr.strip()}. Check GITHUB_TOKEN in Railway Variables."}

    _log("Push successful")
    return {"success": True, "message": f"Pushed: {msg}"}
