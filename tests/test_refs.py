from explorer import refs


def test_extracts_pr_ref_from_merge_commit_message():
    message = "Merge pull request #123 from acme/migrate-app-router\n\nMigrate project to app router"
    assert refs.extract_pr_refs(message) == [123]


def test_extracts_pr_ref_from_squash_commit_message():
    message = "Migrate project to app router (#456)"
    assert refs.extract_pr_refs(message) == [456]


def test_extract_pr_refs_returns_empty_when_no_pr_reference():
    assert refs.extract_pr_refs("Fix typo in README") == []


def test_extracts_bare_issue_ref_from_fixes_keyword():
    assert refs.extract_bare_issue_refs("fixes #42: broken auth flow") == [42]


def test_extracts_bare_issue_ref_from_closes_keyword():
    assert refs.extract_bare_issue_refs("closes #99") == [99]


def test_extracts_plain_bare_issue_ref():
    assert refs.extract_bare_issue_refs("Address feedback from #17") == [17]


def test_bare_issue_refs_excludes_refs_already_captured_as_pr_merge():
    message = "Migrate project to app router (#456)"
    assert refs.extract_bare_issue_refs(message) == []


def test_extracts_jira_key_from_commit_message():
    message = "DESIGN-77: update button spacing per design change request"
    assert refs.extract_jira_keys(message) == ["DESIGN-77"]


def test_extracts_multiple_jira_keys_mid_sentence():
    message = "Follow-up to PROJ-12, also fixes AUTH-3 regression"
    assert refs.extract_jira_keys(message) == ["PROJ-12", "AUTH-3"]


def test_jira_keys_returns_empty_when_none_present():
    assert refs.extract_jira_keys("Fix typo in README") == []
