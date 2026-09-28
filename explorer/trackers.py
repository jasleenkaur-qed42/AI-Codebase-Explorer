"""GitHub/Jira issue-tracker linking.

READ-ONLY BY DESIGN: every function in this module must only ever issue
HTTP GET requests to the GitHub/Jira APIs. Never add POST/PUT/PATCH/DELETE
calls here — this project must never comment on, edit, or otherwise write
to an external issue tracker, only read from it.
"""

import re

import requests
from git import InvalidGitRepositoryError, Repo

from explorer import config, refs, store

GITHUB_API = "https://api.github.com"
_REMOTE_RE = re.compile(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?$")


def github_owner_repo(repo_path: str):
    try:
        url = Repo(repo_path).remotes.origin.url
    except (InvalidGitRepositoryError, AttributeError, ValueError):
        return None
    match = _REMOTE_RE.search(url)
    if not match:
        return None
    return match.group(1), match.group(2)


def fetch_github_pr(owner, repo, number, token):
    return _github_get(f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}", token)


def fetch_github_issue(owner, repo, number, token):
    return _github_get(f"{GITHUB_API}/repos/{owner}/{repo}/issues/{number}", token)


def _github_get(url, token):
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=10,
        )
    except requests.exceptions.RequestException:
        return None
    if response.status_code != 200:
        return None
    return response.json()


def fetch_jira_issue(base_url, email, api_token, key):
    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/rest/api/3/issue/{key}",
            auth=(email, api_token),
            timeout=10,
        )
    except requests.exceptions.RequestException:
        return None
    if response.status_code != 200:
        return None
    return response.json()


def _upsert_pr_node(conn, owner, repo, number, data):
    node_id = f"pr:{owner}/{repo}:{number}"
    title = data.get("title", "")
    body = data.get("body") or ""
    store.upsert_node(conn, id=node_id, type="pr", name=title, attrs={
        "number": number,
        "state": data.get("state"),
        "url": data.get("html_url"),
        "merged_at": data.get("merged_at"),
        "assignee": (data.get("assignee") or {}).get("login"),
    })
    store.index_text(conn, "trackers", node_id=node_id, text=f"{title}\n{body}")
    return store.get_node(conn, node_id)


def _upsert_issue_node(conn, owner, repo, number, data):
    node_id = f"issue:{owner}/{repo}:{number}"
    title = data.get("title", "")
    body = data.get("body") or ""
    store.upsert_node(conn, id=node_id, type="issue", name=title, attrs={
        "number": number,
        "state": data.get("state"),
        "url": data.get("html_url"),
        "closed_at": data.get("closed_at"),
        "assignee": (data.get("assignee") or {}).get("login"),
    })
    store.index_text(conn, "trackers", node_id=node_id, text=f"{title}\n{body}")
    return store.get_node(conn, node_id)


def _upsert_ticket_node(conn, base_url, key, data):
    node_id = f"ticket:{key}"
    fields = data.get("fields", {})
    title = fields.get("summary", "")
    description = fields.get("description")
    description_text = description if isinstance(description, str) else ""
    store.upsert_node(conn, id=node_id, type="ticket", name=title, attrs={
        "key": key,
        "status": (fields.get("status") or {}).get("name"),
        "url": f"{base_url.rstrip('/')}/browse/{key}",
        "assignee": (fields.get("assignee") or {}).get("displayName"),
    })
    store.index_text(conn, "trackers", node_id=node_id, text=f"{title}\n{description_text}")
    return store.get_node(conn, node_id)


def _resolve_github_ref(conn, owner, repo, number, token, is_pr_ref):
    pr_id = f"pr:{owner}/{repo}:{number}"
    issue_id = f"issue:{owner}/{repo}:{number}"
    existing = store.get_node(conn, pr_id) or store.get_node(conn, issue_id)
    if existing:
        return existing

    if is_pr_ref:
        data = fetch_github_pr(owner, repo, number, token)
        if data:
            return _upsert_pr_node(conn, owner, repo, number, data)
        return None

    data = fetch_github_issue(owner, repo, number, token)
    if data is None:
        return None
    if data.get("pull_request"):
        pr_data = fetch_github_pr(owner, repo, number, token)
        if pr_data:
            return _upsert_pr_node(conn, owner, repo, number, pr_data)
        return None
    return _upsert_issue_node(conn, owner, repo, number, data)


def _resolve_jira_ref(conn, base_url, email, api_token, key):
    node_id = f"ticket:{key}"
    existing = store.get_node(conn, node_id)
    if existing:
        return existing
    data = fetch_jira_issue(base_url, email, api_token, key)
    if data is None:
        return None
    return _upsert_ticket_node(conn, base_url, key, data)


def link_commits_to_trackers(conn, commits, repo_path):
    credentials = config.load_tracker_credentials()
    github_token = credentials.get("GITHUB_TOKEN")
    owner_repo = github_owner_repo(repo_path) if github_token else None

    jira_base_url = credentials.get("JIRA_BASE_URL")
    jira_email = credentials.get("JIRA_EMAIL")
    jira_api_token = credentials.get("JIRA_API_TOKEN")
    jira_configured = bool(jira_base_url and jira_email and jira_api_token)

    if not owner_repo and not jira_configured:
        return

    for commit in commits:
        message = commit["message"]
        commit_id = f"commit:{commit['hash']}"

        if owner_repo:
            owner, repo = owner_repo
            for number in refs.extract_pr_refs(message):
                node = _resolve_github_ref(conn, owner, repo, number, github_token, is_pr_ref=True)
                if node:
                    store.upsert_edge(conn, src_id=commit_id, dst_id=node["id"], type="references")
            for number in refs.extract_bare_issue_refs(message):
                node = _resolve_github_ref(conn, owner, repo, number, github_token, is_pr_ref=False)
                if node:
                    store.upsert_edge(conn, src_id=commit_id, dst_id=node["id"], type="references")

        if jira_configured:
            for key in refs.extract_jira_keys(message):
                node = _resolve_jira_ref(conn, jira_base_url, jira_email, jira_api_token, key)
                if node:
                    store.upsert_edge(conn, src_id=commit_id, dst_id=node["id"], type="references")
