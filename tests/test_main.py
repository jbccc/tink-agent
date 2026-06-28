import subprocess
import sys


def test_module_version_flag_exits_without_starting_app():
    res = subprocess.run(
        [sys.executable, "-m", "tink_agent", "--version"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert res.returncode == 0
    assert res.stdout.strip().startswith("tink-agent ")
