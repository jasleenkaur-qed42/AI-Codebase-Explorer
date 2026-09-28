from explorer import config


def test_prefers_process_environment_over_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text("GITHUB_TOKEN=from-file\n")
    monkeypatch.setenv("GITHUB_TOKEN", "from-env")

    creds = config.load_tracker_credentials()

    assert creds["GITHUB_TOKEN"] == "from-env"


def test_falls_back_to_env_file_when_process_environment_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text("GITHUB_TOKEN=from-file\n")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    creds = config.load_tracker_credentials()

    assert creds["GITHUB_TOKEN"] == "from-file"


def test_returns_none_when_credential_missing_everywhere(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

    creds = config.load_tracker_credentials()

    assert creds["JIRA_API_TOKEN"] is None


def test_returns_all_four_credential_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)

    creds = config.load_tracker_credentials()

    assert set(creds.keys()) == {"GITHUB_TOKEN", "JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"}
