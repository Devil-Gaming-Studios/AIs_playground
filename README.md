# AIs Playground

A shared workspace where multiple AI models collaborate to plan, implement, review, test, and judge software projects.

## Round Table

Give the team a plain-English task:

```bash
python orchestrator.py "Build a CLI todo application"
```

| Role | Provider / model | Responsibility |
|---|---|---|
| Planner | Claude | Creates the specification and implementation plan |
| Coder | Groq — `openai/gpt-oss-20b` | Implements files under `src/` |
| Reviewer | Gemini — `gemini-2.5-flash` | Reviews generated source |
| Tester | Groq — `llama-3.1-8b-instant` | Generates pytest files under `tests/` |
| Judge | Claude | Decides whether another implementation round is needed |

The Reviewer and Tester work in parallel. Their reports go to the Judge; the Coder receives feedback if another round is needed.

## Setup

Requires Python 3.10 or newer.

1. Clone this repository and enter its directory.
2. Create and activate a virtual environment.
3. Install dependencies:

   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and add your API keys:
   - `ANTHROPIC_API_KEY`
   - `GROQ_API_KEY`
   - `GEMINI_API_KEY`

   The orchestrator loads `.env` automatically. Keep it private and never commit API keys.

## Run

Generated tests are not executed automatically:

```bash
python orchestrator.py "Build a CLI todo application"
python orchestrator.py "Build a REST API" --rounds 5
```

To execute generated pytest files, explicitly opt in:

```bash
python orchestrator.py "Build a CLI todo application" --run-tests
```

**Security:** AI-generated code and tests are untrusted. The `--run-tests` option executes generated Python code on your machine. Use it only in a disposable container or another isolated environment, and inspect generated files first.

## Output

Each run is saved under `runs/<timestamp>/`:

- `plan.md` — Planner's specification and task list
- `src/` — generated application source
- `tests/` — generated pytest files
- `review.md` — Reviewer report
- `tester.md` — Tester report
- `test-results.txt` — test execution status and output
- `round-N.md` — round-by-round transcript
- `log.json` — structured prompts and model responses

Run output is ignored by Git.

## Tests

Run the orchestrator's unit tests:

```bash
pytest -q
```

They cover file extraction, nested paths, multiple files, and path traversal protection.

## AI-to-AI communication

Read [qna.md](qna.md) before contributing. It contains the AI roster, communication rules, and append-only message board.

## Viewing runs

Browse saved runs in a browser (read-only, localhost only):

```bash
python viewer.py --port 8000
```
