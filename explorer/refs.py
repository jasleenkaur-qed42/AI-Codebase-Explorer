import re

_PR_MERGE_RE = re.compile(r"Merge pull request #(\d+)")
_PR_SQUASH_RE = re.compile(r"\(#(\d+)\)")
_ISSUE_KEYWORD_RE = re.compile(r"\b(?:fixes|closes)\s+#(\d+)", re.IGNORECASE)
_BARE_ISSUE_RE = re.compile(r"#(\d+)")
_JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


def extract_pr_refs(message: str) -> list[int]:
    numbers = _PR_MERGE_RE.findall(message) + _PR_SQUASH_RE.findall(message)
    return [int(n) for n in numbers]


def extract_bare_issue_refs(message: str) -> list[int]:
    pr_numbers = set(extract_pr_refs(message))
    numbers = []
    for n in _ISSUE_KEYWORD_RE.findall(message) + _BARE_ISSUE_RE.findall(message):
        num = int(n)
        if num not in pr_numbers and num not in numbers:
            numbers.append(num)
    return numbers


def extract_jira_keys(message: str) -> list[str]:
    return _JIRA_KEY_RE.findall(message)
