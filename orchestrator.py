"""Round Table: Planner -> Coder -> Reviewer/Tester -> Judge."""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from providers import build_providers

DEFAULT_DOCKER_IMAGE = "round-table-test-sandbox:latest"
ROLE_PROMPTS = {
    "planner": "Turn the task into a specification, acceptance criteria, and numbered plan.",
    "coder": "Implement the plan. Output each file as FILE: relative/path followed by a fenced code block. Put application code under src/.",
    "reviewer": "Review the actual source files. Report bugs and security issues first, with file paths.",
    "tester": "Write pytest tests for the source. Output each test file as FILE: tests/test_name.py followed by a fenced Python block. Do not claim tests ran unless execution output is supplied.",
    "judge": "Judge the implementation. First non-empty line must be exactly DONE or REVISE, followed by a short reason.",
}
FILE_RE = re.compile(r"(?m)^FILE:\\s*(\\S+)\\s*\\r?\\n\x60\x60\x60[^\\r\\n]*\\r?\\n(.*?)\\r?\\n\x60\x60\x60", re.DOTALL)


def write_files(reply: str, output_dir: Path, allowed_prefix: str | None = None) -> list[str]:
    root = output_dir.resolve()
    written = []
    for relative, body in FILE_RE.findall(reply):
        normalized = relative.replace("\\\\", "/")
        parts = Path(normalized).parts
        if not parts or Path(normalized).is_absolute() or ".." in parts or ":" in parts[0]:
            continue
        if allowed_prefix and parts[0] != allowed_prefix:
            continue
        target = root.joinpath(*parts).resolve()
        if target == root or root not in target.parents:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body.rstrip() + "\\n", encoding="utf-8")
        written.append(Path(*parts).as_posix())
    return written


def collect_source(source_dir: Path) -> str:
    sections = []
    if source_dir.exists():
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                sections.append(f"FILE: {path.relative_to(source_dir.parent).as_posix()}\\n\x60\x60\x60\\n{content}\\n\x60\x60\x60")
    return "\\n\\n".join(sections) or "(No source files have been generated yet.)"


def build_docker_command(run_dir: Path, image: str, container_name: str) -> list[str]:
    """Build a locked-down, read-only Docker invocation for generated tests."""
    workspace = str(run_dir.resolve())
    return [
        "docker", "run", "--rm", "--pull=never", "--init",
        "--name", container_name,
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=64",
        "--memory=512m",
        "--memory-swap=512m",
        "--cpus=1",
        "--user=65532:65532",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m",
        "--mount", f"type=bind,source={workspace},target=/workspace,readonly",
        "--workdir=/workspace",
        "--env=PYTHONPATH=/workspace/src",
        "--env=PYTHONDONTWRITEBYTECODE=1",
        "--env=HOME=/tmp",
        image,
        "python", "-m", "pytest", "-p", "no:cacheprovider", "tests", "-q",
    ]


def run_pytest(run_dir: Path, timeout: int = 60, docker_image: str = DEFAULT_DOCKER_IMAGE) -> str:
    """Run generated tests only inside the prebuilt, network-isolated Docker image."""
    tests_dir = run_dir / "tests"
    if not tests_dir.exists() or not any(tests_dir.rglob("test_*.py")):
        return "No pytest test files were generated."
    if timeout < 1:
        raise ValueError("timeout must be at least 1 second")
    try:
        image_check = subprocess.run(
            ["docker", "image", "inspect", docker_image],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except FileNotFoundError:
        return "Docker CLI was not found. Install Docker and start its daemon before using --run-tests."
    except subprocess.TimeoutExpired:
        return "Timed out while checking Docker. Ensure the Docker daemon is running."
    if image_check.returncode != 0:
        detail = (image_check.stderr or image_check.stdout).strip()
        return (
            f"Docker image '{docker_image}' is unavailable or Docker cannot be reached. "
            "Build it with: docker build -f Dockerfile.sandbox -t "
            f"{docker_image} .\\n{detail}"
        )

    container_name = f"round-table-test-{uuid.uuid4().hex[:12]}"
    command = build_docker_command(run_dir, docker_image, container_name)
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        for cleanup in (
            ["docker", "stop", "--time", "1", container_name],
            ["docker", "rm", "--force", container_name],
        ):
            try:
                subprocess.run(cleanup, capture_output=True, text=True, timeout=10, check=False)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        return f"Docker test container timed out after {timeout} seconds and cleanup was requested."
    except FileNotFoundError:
        return "Docker CLI disappeared before the test container could start."
    output = (result.stdout + "\\n" + result.stderr).strip()
    return f"Exit code: {result.returncode}\\n{output}"


def run(
    task: str,
    max_rounds: int = 3,
    execute_tests: bool = False,
    docker_image: str = DEFAULT_DOCKER_IMAGE,
    test_timeout: int = 60,
) -> Path:
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")
    if test_timeout < 1:
        raise ValueError("test_timeout must be at least 1 second")
    load_dotenv()
    ais = build_providers()
    run_dir = Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    src_dir = run_dir / "src"
    run_dir.mkdir(parents=True, exist_ok=False)
    src_dir.mkdir(parents=True)
    log = []
    log_lock = threading.Lock()

    def step(role: str, prompt: str) -> str:
        reply = ais[role].ask(ROLE_PROMPTS[role], prompt)
        with log_lock:
            log.append({"role": role, "ai": ais[role].name, "prompt": prompt, "reply": reply})
        return reply

    try:
        plan = step("planner", task)
        (run_dir / "plan.md").write_text(plan, encoding="utf-8")
        feedback = ""
        for round_number in range(1, max_rounds + 1):
            coder_prompt = f"Task:\\n{task}\\n\\nPlan:\\n{plan}\\n\\nPrevious feedback:\\n{feedback or 'None'}"
            code_reply = step("coder", coder_prompt)
            code_files = write_files(code_reply, run_dir, "src")
            source = collect_source(src_dir)
            reviewer_prompt = f"Task:\\n{task}\\n\\nPlan:\\n{plan}\\n\\nSource files:\\n{source}"
            tester_prompt = reviewer_prompt
            with ThreadPoolExecutor(max_workers=2) as pool:
                review_future = pool.submit(step, "reviewer", reviewer_prompt)
                tester_future = pool.submit(step, "tester", tester_prompt)
                review = review_future.result()
                tester_reply = tester_future.result()
            test_files = write_files(tester_reply, run_dir, "tests")
            (run_dir / "review.md").write_text(review, encoding="utf-8")
            (run_dir / "tester.md").write_text(tester_reply, encoding="utf-8")
            execution = run_pytest(run_dir, test_timeout, docker_image) if execute_tests else (
                "Not executed. Use --run-tests only after reviewing generated code; tests run in Docker."
            )
            (run_dir / "test-results.txt").write_text(execution, encoding="utf-8")
            judge_prompt = (
                f"Task:\\n{task}\\n\\nPlan:\\n{plan}\\n\\nSource:\\n{source}\\n\\n"
                f"Review:\\n{review}\\n\\nTester:\\n{tester_reply}\\n\\nExecution:\\n{execution}"
            )
            verdict = step("judge", judge_prompt)
            first_line = next((line.strip() for line in verdict.splitlines() if line.strip()), "").upper()
            print(f"[round {round_number}] source_files={len(code_files)} test_files={len(test_files)} verdict={first_line or '?'}")
            (run_dir / f"round-{round_number}.md").write_text(
                f"# Round {round_number}\\n\\n## Coder\\n\\n{code_reply}\\n\\n## Reviewer\\n\\n{review}\\n\\n"
                f"## Tester\\n\\n{tester_reply}\\n\\n## Test execution\\n\\n{execution}\\n\\n## Judge\\n\\n{verdict}\\n",
                encoding="utf-8",
            )
            if first_line == "DONE":
                break
            feedback = f"Review:\\n{review}\\n\\nTester:\\n{tester_reply}\\n\\nExecution:\\n{execution}\\n\\nJudge:\\n{verdict}"
    finally:
        (run_dir / "log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    return run_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Round Table AI coding team.")
    parser.add_argument("task", help="Plain-English task for the AI team")
    parser.add_argument("--rounds", type=int, default=3, help="Maximum review cycles")
    parser.add_argument("--run-tests", action="store_true", help="Execute generated pytest code in an isolated Docker container")
    parser.add_argument("--docker-image", default=DEFAULT_DOCKER_IMAGE, help="Prebuilt Docker image used for generated tests")
    parser.add_argument("--test-timeout", type=int, default=60, help="Maximum seconds allowed for each Docker test run")
    args = parser.parse_args()
    if args.run_tests:
        print("Warning: generated tests are untrusted; Docker provides defense-in-depth, not a perfect security boundary.")
    print("Run saved to", run(
        args.task, args.rounds, args.run_tests, args.docker_image, args.test_timeout
    ))
