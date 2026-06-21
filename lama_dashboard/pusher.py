import os
from datetime import date


def _log(msg):
    print(f"[pusher] {msg}", flush=True)


def push_to_github(summary=None):
    """
    Stage deals.csv, staging.json, commit, and push to origin main.
    Requires GITHUB_TOKEN env var for Railway authentication.
    Returns dict: {success: bool, message: str}
    """
    try:
        import git
    except ImportError:
        msg = "gitpython not installed. Run: pip install gitpython"
        _log(msg)
        return {"success": False, "message": msg}

    token = os.environ.get("GITHUB_TOKEN", "")
    repo_name = os.environ.get("GITHUB_REPO", "sophieb-web/lama-dashboard")

    # Repo root is two levels up from lama_dashboard/
    lama_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(lama_dir)
    _log(f"lama_dir: {lama_dir}")
    _log(f"repo_root: {repo_root}")

    try:
        repo = git.Repo(repo_root)
        _log(f"Git repo: {repo.working_dir} | branch: {repo.active_branch.name}")
    except git.InvalidGitRepositoryError:
        msg = f"No git repo found at {repo_root}"
        _log(msg)
        return {"success": False, "message": msg}

    # Always use forward slashes — git/gitpython require POSIX paths
    files_to_add = [
        "lama_dashboard/data/deals.csv",
        "lama_dashboard/data/taxonomy.csv",
        "lama_dashboard/data/staging.json",
    ]

    # Only add files that exist on disk
    existing = [f for f in files_to_add
                if os.path.exists(os.path.join(repo_root, f.replace("/", os.sep)))]
    _log(f"Files to stage: {existing}")

    if not existing:
        msg = "No data files found to commit"
        _log(msg)
        return {"success": False, "message": msg}

    repo.index.add(existing)
    _log(f"Staged {len(existing)} file(s)")

    # Check if anything actually changed vs HEAD
    staged_diff = repo.index.diff("HEAD")
    _log(f"Staged diff count: {len(staged_diff)}")
    if not staged_diff:
        msg = "Nothing to commit — database already up to date"
        _log(msg)
        return {"success": True, "message": msg}

    # Build commit message
    if summary:
        msg = (f"auto-update: {summary.get('new_rounds', 0)} new rounds, "
               f"{summary.get('new_companies', 0)} new companies — {date.today()}")
    else:
        msg = f"auto-update: database sync — {date.today()}"

    _log(f"Committing: {msg}")
    repo.index.commit(msg)

    # Set authenticated remote URL
    origin = repo.remote(name="origin")
    _log(f"Remote origin: {origin.url if not token else '<token-auth>'}")
    if token:
        remote_url = f"https://{token}@github.com/{repo_name}.git"
        origin.set_url(remote_url)
        _log(f"Set remote URL: https://***@github.com/{repo_name}.git")

    try:
        _log("Pushing to origin...")
        origin.push()
        result = {"success": True, "message": f"Pushed: {msg}"}
        _log(f"Push successful")
        return result
    except Exception as e:
        msg = f"Push failed: {e}. Check GITHUB_TOKEN in Railway Variables."
        _log(msg)
        return {"success": False, "message": msg}
