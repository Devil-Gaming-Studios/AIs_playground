from pathlib import Path
import io
import subprocess
from types import SimpleNamespace

import pytest

from orchestrator import MAX_TEST_OUTPUT_BYTES, build_docker_command, run, run_pytest, write_files

FENCE = chr(96) * 3


def test_writes_nested_file(tmp_path: Path):
    reply = f"FILE: src/app/main.py\n{FENCE}python\nprint('hello')\n{FENCE}"

    written = write_files(reply, tmp_path)

    assert written == ["src/app/main.py"]
    assert (tmp_path / "src/app/main.py").read_text(encoding="utf-8") == "print('hello')\n"


def test_rejects_parent_directory_traversal(tmp_path: Path):
    reply = f"FILE: ../outside.py\n{FENCE}python\nprint('bad')\n{FENCE}"

    assert write_files(reply, tmp_path) == []
    assert not (tmp_path.parent / "outside.py").exists()


def test_rejects_absolute_paths(tmp_path: Path):
    outside = (tmp_path.parent / "outside.py").resolve()
    reply = f"FILE: {outside}\n{FENCE}python\nprint('bad')\n{FENCE}"

    assert write_files(reply, tmp_path) == []
    assert not outside.exists()


def test_accepts_multiple_files(tmp_path: Path):
    reply = (
        f"FILE: src/main.py\n{FENCE}python\nprint('main')\n{FENCE}\n\n"
        f"FILE: tests/test_main.py\n{FENCE}python\ndef test_main():\n    assert True\n{FENCE}"
    )

    written = write_files(reply, tmp_path)

    assert written == ["src/main.py", "tests/test_main.py"]
    assert (tmp_path / "src/main.py").exists()
    assert (tmp_path / "tests/test_main.py").exists()


def test_ignores_text_without_file_blocks(tmp_path: Path):
    assert write_files("No file block here.", tmp_path) == []


def test_enforces_allowed_output_directory(tmp_path: Path):
    reply = (
        f"FILE: src/app.py\n{FENCE}python\nprint('ok')\n{FENCE}\n\n"
        f"FILE: plan.md\n{FENCE}text\nreplace the plan\n{FENCE}"
    )

    assert write_files(reply, tmp_path, "src") == ["src/app.py"]
    assert not (tmp_path / "plan.md").exists()


def test_docker_command_enables_sandbox_restrictions(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    command = build_docker_command(tmp_path, "sandbox:test", "round-table-test")
    joined = " ".join(command)

    assert "--network=none" in command
    assert "--ipc=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges:true" in command
    assert "--pids-limit=64" in command
    assert "--memory=512m" in command
    assert "--cpus=1" in command
    assert "--user=65532:65532" in command
    assert f"type=bind,source={(tmp_path / 'src').resolve()},target=/workspace/src,readonly" in joined
    assert f"type=bind,source={(tmp_path / 'tests').resolve()},target=/workspace/tests,readonly" in joined
    assert f"type=bind,source={tmp_path.resolve()},target=/workspace,readonly" not in joined
    assert command[command.index("--entrypoint") + 1] == "python"
    assert command[-6:] == ["-m", "pytest", "-p", "no:cacheprovider", "tests", "-q"]


def test_run_pytest_uses_docker(monkeypatch, tmp_path: Path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    calls = []

    class FakeProcess:
        stdout = io.BytesIO(b"1 passed")

        def wait(self, timeout=None):
            return 0

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    result = run_pytest(tmp_path)

    assert result == "Exit code: 0\n1 passed"
    assert len(calls) == 1
    assert calls[0][:3] == ["docker", "image", "inspect"]


def test_run_pytest_does_not_run_when_image_is_missing(monkeypatch, tmp_path: Path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="No such image")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_pytest(tmp_path)

    assert "docker build -f Dockerfile.sandbox" in result
    assert len(calls) == 1


def test_run_pytest_stops_container_after_timeout(monkeypatch, tmp_path: Path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    calls = []

    class FakeProcess:
        stdout = io.BytesIO(b"")

        def wait(self, timeout=None):
            if timeout == 1:
                raise subprocess.TimeoutExpired("docker run", 1)
            return -9

        def kill(self):
            pass

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    result = run_pytest(tmp_path, timeout=1)

    assert "timed out after 1 seconds" in result
    assert calls[1][0:3] == ["docker", "stop", "--time"]
    assert calls[2][0:3] == ["docker", "rm", "--force"]


def test_run_checks_docker_before_building_providers(monkeypatch, tmp_path: Path):
    import orchestrator

    def fail_if_called():
        pytest.fail("providers must not be initialized when Docker preflight fails")

    monkeypatch.setattr(orchestrator, "check_docker_image", lambda image: "sandbox image missing")
    monkeypatch.setattr(orchestrator, "build_providers", fail_if_called)

    with pytest.raises(RuntimeError, match="sandbox image missing"):
        run("example task", execute_tests=True)


def test_run_pytest_caps_retained_output(monkeypatch, tmp_path: Path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    class FakeProcess:
        stdout = io.BytesIO(b"x" * (MAX_TEST_OUTPUT_BYTES + 100))

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(
        subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    result = run_pytest(tmp_path)

    assert len(result.encode("utf-8")) < MAX_TEST_OUTPUT_BYTES + 200
    assert "[pytest output truncated after 100000 bytes]" in result
