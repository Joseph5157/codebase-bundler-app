import re
import os
import tempfile
import requests

GITHUB_URL_REGEX = re.compile(
    r'(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)'
)

def extract_github_repo_info(url_or_text: str):
    """
    Extracts (owner, repo) from a GitHub URL string.
    """
    match = GITHUB_URL_REGEX.search(url_or_text)
    if not match:
        return None, None
    owner = match.group(1)
    repo = match.group(2)
    if repo.endswith('.git'):
        repo = repo[:-4]
    return owner, repo

def download_github_repo_zip(url_or_text: str):
    owner, repo = extract_github_repo_info(url_or_text)
    if not owner or not repo:
        raise ValueError("Invalid GitHub URL format. Example: https://github.com/owner/repo")

    headers = {
        'User-Agent': 'Codebase-Bundler-Bot/1.0'
    }

    # Try main.zip first
    main_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip"
    resp = requests.get(main_url, headers=headers, stream=True)
    
    if resp.status_code != 200:
        # Fallback to master.zip
        master_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/master.zip"
        resp = requests.get(master_url, headers=headers, stream=True)

    if resp.status_code != 200:
        # Query GitHub API for exact default branch
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        api_resp = requests.get(api_url, headers=headers)
        if api_resp.status_code == 200:
            default_branch = api_resp.json().get('default_branch', 'main')
            branch_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{default_branch}.zip"
            resp = requests.get(branch_url, headers=headers, stream=True)

    if resp.status_code != 200:
        raise ValueError(f"Could not download repository '{owner}/{repo}'. Ensure it is public and valid.")

    # Save to temp zip file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip', prefix=f"{repo}_")
    for chunk in resp.iter_content(chunk_size=8192):
        if chunk:
            tmp.write(chunk)
    tmp.close()

    return tmp.name, f"{owner}_{repo}.zip"
