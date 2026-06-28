from tink_agent import launchagent


def test_launchagent_label_uses_public_github_namespace():
    assert launchagent.LABEL == "io.github.tajchert.tinkagent"


def test_plist_contents_has_python_module_and_runatload():
    p = launchagent.plist_contents("/venv/bin/python", "/repo")
    assert "/venv/bin/python" in p
    assert "<string>-m</string>" in p
    assert "<string>tink_agent</string>" in p
    assert "/repo" in p
    assert "RunAtLoad" in p
    assert launchagent.LABEL in p


def test_set_run_at_login_writes_and_removes(tmp_path):
    plist = tmp_path / "agent.plist"
    assert launchagent.is_enabled(plist) is False

    launchagent.set_run_at_login(True, "/venv/bin/python", "/repo", plist)
    assert plist.exists()
    assert launchagent.is_enabled(plist) is True
    assert "/venv/bin/python" in plist.read_text()

    launchagent.set_run_at_login(False, "", "", plist)
    assert not plist.exists()
    assert launchagent.is_enabled(plist) is False


def test_set_run_at_login_false_when_absent_is_noop(tmp_path):
    plist = tmp_path / "agent.plist"
    launchagent.set_run_at_login(False, "", "", plist)  # should not raise
    assert not plist.exists()


def test_install_writes_plist_and_bootstraps(tmp_path):
    plist = tmp_path / "agent.plist"
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        class R:
            returncode = 0; stdout = ""; stderr = ""
        return R()

    launchagent.install_and_start("/venv/bin/python", "/repo", plist, runner=runner)
    assert plist.exists()
    subcmds = [c[1] for c in calls]  # launchctl <sub> ...
    assert "bootout" in subcmds
    assert "bootstrap" in subcmds
    assert any(str(plist) in c for c in calls)
