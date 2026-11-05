"""Round Table orchestrator: Planner -> Coder -> (Reviewer + Tester) -> Judge, looped."""
import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from providers import build_providers

ROLE_PROMPTS = {
    "planner": "You are the Planner. Turn the task into a short spec and a numbered task list in markdown.",
    "coder": (
        "You are the Coder. Implement the plan. Output every file as a fenced block preceded by a line "
        "`FILE: relative/path.ext`. Output code only, no commentary."
    ),
    "reviewer": "You are the Reviewer. List concrete bugs and improvements in the code as a markdown bullet list.",
    "tester": "You are the Tester. Write pytest tests for the code and list any failures you expect.",
    "judge": (
        "You are the Judge. Given the review and test report, reply with a first line of exactly "
        "`DONE` or `REVISE`, then a short reason."
    ),
}

FILE_RE = re.compile(r"FILE:\s*(\S+)\s*\n```[\w+-]*\n(.*?)```", re.S)


def write_files(code_reply: str, out_dir: Path) -> list[str]:
    written = []
    for rel, body in FILE_RE.findall(code_reply):
        target = (out_dir / rel).resolve()
        if out_dir.resolve() not in target.parents:  # block path escapes
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
        written.append(rel)
    return written


def run(task: str, max_rounds: int = 3) -> Path:
    ais = build_providers()
    run_dir = Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    src_dir = run_dir / "src"
    src_dir.mkdir(parents=True)
    log = []

    def step(role: str, prompt: str) -> str:
        reply = ais[role].ask(ROLE_PROMPTS[role], prompt)
        log.append({"role": role, "ai": ais[role].name, "prompt": prompt, "reply": reply})
        return reply

    plan = step("planner", task)
    (run_dir / "plan.md").write_text(plan)

    feedback = ""
    for rnd in range(1, max_rounds + 1):
        code = step("coder", f"Task:\n{task}\n\nPlan:\n{plan}\n\nFeedback so far:\n{feedback or 'none'}")
        files = write_files(code, src_dir)
        with ThreadPoolExecutor() as pool:
            rev = pool.submit(step, "reviewer", code)
            tst = pool.submit(step, "tester", code)
            review, tests = rev.result(), tst.result()
        (run_dir / "review.md").write_text(review)
        verdict = step("judge", f"Review:\n{review}\n\nTests:\n{tests}")
        print(f"[round {rnd}] files={files} verdict={verdict.splitlines()[0] if verdict else '?'}")
        if verdict.strip().startswith("DONE"):
            break
        feedback = f"Review:\n{review}\n\nTests:\n{tests}"

    (run_dir / "log.json").write_text(json.dumps(log, indent=2))
    return run_dir


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()
    print("Run saved to", run(args.task, args.rounds))
