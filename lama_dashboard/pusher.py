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
    target_branch = os.environ.get("GITHUB_BRANCH", "main")

    # Repo root is two levels up from lama_dashboard/
    lama_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(lama_dir)
    _log(f"lama_dir: {lama_dir}")
    _log(f"repo_root: {repo_root}")

    try:
        repo = git.Repo(repo_root)
    except git.InvalidGitRepositoryError:
        msg = f"No git repo found at {repo_root}"
        _log(msg)
        return {"success": False, "message": msg}

    # Log HEAD state — Railway often deploys in detached HEAD
    try:
        branch_name = repo.active_branch.name
        _log(f"Git branch: {branch_name}")
    except TypeError:
        branch_name = None
        head_sha = repo.head.commit.hexsha[:8]
        _log(f"Git HEAD: detached at {head_sha} — will push to {target_branch}")

    # Ensure git user is configured (required for commit on Railway)
    with repo.config_writer() as cw:
        try:
            cw.get_value("user", "name")
        except Exception:
            cw.set_value("user", "name", "Lama Dashboard Bot")
            _log("Set git user.name = Lama Dashboard Bot")
        try:
            cw.get_value("user", "email")
        except Exception:
            cw.set_value("user", "email", "bot@lama.vc")
            _log("Set git user.email = bot@lama.vc")

    # Always use forward slashes — git/gitpython require POSIX paths
    files_to_add = [
        "lama_dashboard/data/deals.csv",
        "lama_dashboard/data/taxonomy.csv",
        "lama_dashboard/data/staging.json",
    ]

    existing = [f for f in files_to_add
                if os.path.exists(os.path.join(repo_root, f.replace("/", os.sep)))]
    _log(f"Files to stage: {existing}")

    if not existing:
        msg = "No data files found to commit"
        _log(msg)
        return {"success": False, "message": msg}

    repo.index.add(existing)
    _log(f"Staged {len(existing)} file(s)")

    staged_diff = repo.index.diff("HEAD")
    _log(f"Staged diff count: {len(staged_diff)}")
    if not staged_diff:
        msg = "Nothing to commit — database already up to date"
        _log(msg)
        return {"success": True, "message": msg}

    # Build commit message
    if summary and summary.get("merged", 0) > 0:
        msg = (f"auto-update: {summary.get('new_rounds', 0)} new rounds, "
               f"{summary.get('new_companies', 0)} new companies — {date.today()}")
    else:
        msg = f"auto-update: database sync — {date.today()}"

    _log(f"Committing: {msg}")
    repo.index.commit(msg)

    # Set authenticated remote URL
    origin = repo.remote(name="origin")
    if token:
        remote_url = f"https://{token}@github.com/{repo_name}.git"
        origin.set_url(remote_url)
        _log(f"Set remote URL with token: https://***@github.com/{repo_name}.git")
    else:
        _log(f"WARNING: GITHUB_TOKEN not set — push may fail. Remote: {origin.url}")

    # Push with explicit refspec so detached HEAD works
    refspec = f"HEAD:{target_branch}"
    _log(f"Pushing with refspec: {refspec}")
    try:
        push_info = origin.push(refspec=refspec)
        # Check for errors in push_info flags
        for info in push_info:
            _log(f"Push info: {info.summary.strip()} (flags={info.flags})")
            if info.flags & info.ERROR:
                msg = f"Push error: {info.summary.strip()}"
                _log(msg)
                return {"success": False, "message": msg}
        result = {"success": True, "message": f"Pushed: {msg}"}
        _log("Push successful")
        return result
    except Exception as e:
        msg = f"Push failed: {e}. Check GITHUB_TOKEN in Railway Variables."
        _log(msg)
        return {"success": False, "message": msg}
