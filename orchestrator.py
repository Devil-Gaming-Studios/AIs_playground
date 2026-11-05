"""Round Table: Planner -> Coder -> Reviewer/Tester -> Judge."""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from providers import build_providers

ROLE_PROMPTS = {
    "planner": "Turn the task into a specification, acceptance criteria, and numbered plan.",
    "coder": "Implement the plan. Output each file as FILE: relative/path followed by a fenced code block. Put application code under src/.",
    "reviewer": "Review the actual source files. Report bugs and security issues first, with file paths.",
    "tester": "Write pytest tests for the source. Output each test file as FILE: tests/test_name.py followed by a fenced Python block. Do not claim tests ran unless execution output is supplied.",
    "judge": "Judge the implementation. First non-empty line must be exactly DONE or REVISE, followed by a short reason.",
}
FILE_RE = re.compile(r"(?m)^FILE:\s*(\S+)\s*\r?\n```[^\r\n]*\r?\n(.*?)\r?\n```", re.DOTALL)


def write_files(reply: str, output_dir: Path) -> list[str]:
    root = output_dir.resolve()
    written = []
    for relative, body in FILE_RE.findall(reply):
        normalized = relative.replace("\\", "/")
        parts = Path(normalized).parts
        if not parts or Path(normalized).is_absolute() or ".." in parts or ":" in parts[0]:
            continue
        target = root.joinpath(*parts).resolve()
        if target == root or root not in target.parents:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body.rstrip() + "\n", encoding="utf-8")
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
                sections.append(f"FILE: {path.relative_to(source_dir.parent).as_posix()}\n```\n{content}\n```")
    return "\n\n".join(sections) or "(No source files have been generated yet.)"


def run_pytest(run_dir: Path, timeout: int = 60) -> str:
    tests_dir = run_dir / "tests"
    if not tests_dir.exists() or not any(tests_dir.rglob("test_*.py")):
        return "No pytest test files were generated."
    env = os.environ.copy()
    source_dir = str(run_dir / "src")
    env["PYTHONPATH"] = source_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q"],
            cwd=run_dir, env=env, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return f"Pytest timed out after {timeout} seconds."
    output = (result.stdout + "\n" + result.stderr).strip()
    return f"Exit code: {result.returncode}\n{output}"


def run(task: str, max_rounds: int = 3, execute_tests: bool = False) -> Path:
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")
    ais = build_providers()
    run_dir = Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
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
            coder_prompt = f"Task:\n{task}\n\nPlan:\n{plan}\n\nPrevious feedback:\n{feedback or 'None'}"
            code_reply = step("coder", coder_prompt)
            code_files = write_files(code_reply, run_dir)
            source = collect_source(src_dir)
            reviewer_prompt = f"Task:\n{task}\n\nPlan:\n{plan}\n\nSource files:\n{source}"
            tester_prompt = reviewer_prompt
            with ThreadPoolExecutor(max_workers=2) as pool:
                review_future = pool.submit(step, "reviewer", reviewer_prompt)
                tester_future = pool.submit(step, "tester", tester_prompt)
                review = review_future.result()
                tester_reply = tester_future.result()
            test_files = write_files(tester_reply, run_dir)
            (run_dir / "review.md").write_text(review, encoding="utf-8")
            (run_dir / "tester.md").write_text(tester_reply, encoding="utf-8")
            execution = run_pytest(run_dir) if execute_tests else (
                "Not executed. Use --run-tests only in an isolated environment after reviewing generated code."
            )
            (run_dir / "test-results.txt").write_text(execution, encoding="utf-8")
            judge_prompt = (
                f"Task:\n{task}\n\nPlan:\n{plan}\n\nSource:\n{source}\n\n"
                f"Review:\n{review}\n\nTester:\n{tester_reply}\n\nExecution:\n{execution}"
            )
            verdict = step("judge", judge_prompt)
            first_line = next((line.strip() for line in verdict.splitlines() if line.strip()), "").upper()
            print(f"[round {round_number}] source_files={len(code_files)} test_files={len(test_files)} verdict={first_line or '?'}")
            (run_dir / f"round-{round_number}.md").write_text(
                f"# Round {round_number}\n\n## Coder\n\n{code_reply}\n\n## Reviewer\n\n{review}\n\n"
                f"## Tester\n\n{tester_reply}\n\n## Test execution\n\n{execution}\n\n## Judge\n\n{verdict}\n",
                encoding="utf-8",
            )
            if first_line == "DONE":
                break
            feedback = f"Review:\n{review}\n\nTester:\n{tester_reply}\n\nExecution:\n{execution}\n\nJudge:\n{verdict}"
    finally:
        (run_dir / "log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    return run_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Round Table AI coding team.")
    parser.add_argument("task", help="Plain-English task for the AI team")
    parser.add_argument("--rounds", type=int, default=3, help="Maximum review cycles")
    parser.add_argument("--run-tests", action="store_true", help="Execute generated pytest code; use an isolated environment")
    args = parser.parse_args()
    if args.run_tests:
        print("Warning: generated tests execute code. Use an isolated environment.")
    print("Run saved to", run(args.task, args.rounds, args.run_tests))
