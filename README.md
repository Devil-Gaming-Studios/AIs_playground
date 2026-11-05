# AIs Playground

A shared space where several AI models build one project together, each with a defined role.

## Project: Round Table — a multi-AI code-building pipeline

**Idea:** Give Round Table a plain-English task (e.g. "build a CLI todo app"). Different AIs collaborate on it in turns, using this repo as the shared workspace.

### Roles

| Role | AI | Job |
|------|----|-----|
| Planner | Claude | Turns the task into a spec and a task list (`plan.md`) |
| Coder | Groq (`openai/gpt-oss-20b`) | Writes code for each task |
| Reviewer | Gemini | Reviews the code and leaves comments in `review.md` |
| Tester | Groq (`llama-3.1-8b-instant`) | Writes and runs tests, reports failures |
| Judge | Claude | Decides if the result is done or needs another round |

### How it works

1. Planner reads the task and writes `plan.md`.
2. Coder implements the tasks into `src/`.
3. Reviewer and Tester check the work in parallel.
4. Judge reads their feedback; if issues remain, loop back to step 2 (max N rounds).
5. Every round is logged in `runs/<timestamp>/` so you can see who said what.

### Suggested stack

- Python orchestrator (`orchestrator.py`) with one thin adapter per AI provider (`providers/`)
- Shared state as plain files (markdown + JSON), no database needed
- Simple CLI: `python orchestrator.py "build a CLI todo app"`

### Milestones

- [ ] Provider adapters (Claude, Groq, Gemini) behind one `ask(role, prompt)` interface
- [ ] Planner → Coder loop producing runnable code
- [ ] Reviewer + Tester feedback loop
- [ ] Judge and stop condition
- [ ] Run logs and a small web viewer for the conversation

### Why this is fun

Each model has different strengths, so you can swap roles, compare outputs, and see which combinations build the best code.
