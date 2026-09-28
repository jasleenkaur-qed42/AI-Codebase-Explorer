from dataclasses import dataclass, field
from itertools import combinations

import git


@dataclass
class HistoryResult:
    commits: list = field(default_factory=list)
    authors: list = field(default_factory=list)
    edges: list = field(default_factory=list)


def _edge(src_id, dst_id, type, attrs=None):
    return {"src_id": src_id, "dst_id": dst_id, "type": type, "attrs": attrs or {}}


def mine(repo_path: str, since_commit: str | None = None) -> HistoryResult:
    repo = git.Repo(repo_path)
    result = HistoryResult()
    seen_authors = {}
    co_change_counts = {}

    rev_range = "HEAD"
    if since_commit:
        rev_range = f"{since_commit}..HEAD"

    commits = list(repo.iter_commits(rev_range))
    for commit in reversed(commits):  # oldest first
        author_email = commit.author.email
        author_id = f"author:{author_email}"
        if author_email not in seen_authors:
            seen_authors[author_email] = {
                "id": author_id,
                "email": author_email,
                "name": commit.author.name,
            }

        files_changed = sorted(commit.stats.files.keys())
        result.commits.append({
            "id": f"commit:{commit.hexsha}",
            "hash": commit.hexsha,
            "author_id": author_id,
            "timestamp": commit.committed_date,
            "message": commit.message.strip(),
            "files_changed": files_changed,
        })

        result.edges.append(_edge(f"commit:{commit.hexsha}", author_id, "authored_by"))
        for path in files_changed:
            result.edges.append(_edge(f"commit:{commit.hexsha}", f"file:{path}", "modifies"))

        for path_a, path_b in combinations(files_changed, 2):
            key = tuple(sorted((path_a, path_b)))
            co_change_counts[key] = co_change_counts.get(key, 0) + 1

    for (path_a, path_b), count in co_change_counts.items():
        result.edges.append(
            _edge(f"file:{path_a}", f"file:{path_b}", "co_changed_with", {"count": count})
        )

    result.authors = list(seen_authors.values())
    return result
