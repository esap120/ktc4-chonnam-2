from daesingo.common.env import load_env_file


def test_no_argument_loader_ignores_shell_env_file(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("KEY=cwd\n", encoding="utf-8")
    override = tmp_path / "override.env"
    override.write_text("KEY=override\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DAESINGO_ENV_FILE", str(override))
    assert load_env_file() == {"KEY": "cwd"}
    assert load_env_file(str(override)) == {"KEY": "override"}
    assert load_env_file(str(tmp_path / "missing")) == {}
