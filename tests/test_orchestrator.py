from pathlib import Path

from orchestrator import write_files


def test_writes_nested_file(tmp_path: Path):
    reply = "FILE: src/app/main.py\n```python\nprint('hello')\n```"

    written = write_files(reply, tmp_path)

    assert written == ["src/app/main.py"]
    assert (tmp_path / "src/app/main.py").read_text(encoding="utf-8") == "print('hello')\n"


def test_rejects_parent_directory_traversal(tmp_path: Path):
    reply = "FILE: ../outside.py\n```python\nprint('bad')\n```"

    assert write_files(reply, tmp_path) == []
    assert not (tmp_path.parent / "outside.py").exists()


def test_rejects_absolute_paths(tmp_path: Path):
    outside = (tmp_path.parent / "outside.py").resolve()
    reply = f"FILE: {outside}\n```python\nprint('bad')\n```"

    assert write_files(reply, tmp_path) == []
    assert not outside.exists()


def test_accepts_multiple_files(tmp_path: Path):
    reply = (
        "FILE: src/main.py\n```python\nprint('main')\n```\n\n"
        "FILE: tests/test_main.py\n```python\ndef test_main():\n    assert True\n```"
    )

    written = write_files(reply, tmp_path)

    assert written == ["src/main.py", "tests/test_main.py"]
    assert (tmp_path / "src/main.py").exists()
    assert (tmp_path / "tests/test_main.py").exists()


def test_ignores_text_without_file_blocks(tmp_path: Path):
    assert write_files("No file block here.", tmp_path) == []


def test_enforces_allowed_output_directory(tmp_path: Path):
    reply = (
        "FILE: src/app.py\n```python\nprint('ok')\n```\n\n"
        "FILE: plan.md\n```text\nreplace the plan\n```"
    )

    assert write_files(reply, tmp_path, "src") == ["src/app.py"]
    assert not (tmp_path / "plan.md").exists()
