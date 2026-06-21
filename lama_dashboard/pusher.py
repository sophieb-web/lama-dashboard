import os
from datetime import date


def push_to_github(summary=None):
    """
    Stage deals.csv, staging.json, commit, and push to origin main.
    Requires GITHUB_TOKEN env var for Railway authentication.
    Returns dict: {success: bool, message: str}
    """
    try:
        import git
    except ImportError:
        return {"success": False, "message": "gitpython not installed. Run: pip install gitpython"}

    token = os.environ.get("GITHUB_TOKEN", "")
    repo_name = os.environ.get("GITHUB_REPO", "sophieb-web/lama-dashboard")

    # Repo root is two levels up from lama_dashboard/
    lama_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(lama_dir)

    try:
        repo = git.Repo(repo_root)
    except git.InvalidGitRepositoryError:
        return {"success": False, "message": f"No git repo found at {repo_root}"}

    # Files to stage
    files_to_add = [
        os.path.join("lama_dashboard", "data", "deals.csv"),
        os.path.join("lama_dashboard", "data", "taxonomy.csv"),
        os.path.join("lama_dashboard", "data", "staging.json"),
    ]
    # Only add files that exist and have changes
    to_add = [f for f in files_to_add if os.path.exists(os.path.join(repo_root, f))]
    if not to_add:
        return {"success": False, "message": "No files to commit"}

    repo.index.add(to_add)

    # Check if there's actually anything staged
    if not repo.index.diff("HEAD") and not repo.untracked_files:
        return {"success": True, "message": "Nothing to commit — database already up to date"}

    # Build commit message
    if summary:
        msg = (f"auto-update: {summary.get('new_rounds', 0)} new rounds, "
               f"{summary.get('new_companies', 0)} new companies — {date.today()}")
    else:
        msg = f"auto-update: database sync — {date.today()}"

    repo.index.commit(msg)

    # Set authenticated remote URL if token available
    origin = repo.remote(name="origin")
    if token:
        remote_url = f"https://{token}@github.com/{repo_name}.git"
        origin.set_url(remote_url)

    try:
        origin.push()
        return {"success": True, "message": f"Pushed: {msg}"}
    except Exception as e:
        return {"success": False, "message": f"Push failed: {e}. Check GITHUB_TOKEN in Railway Variables."}
