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

## Pull and run

Get the latest code and run the team (after the one-time [Setup](#setup) below):

```bash
git pull origin main
pip install -r requirements.txt
python orchestrator.py "Build a CLI todo application"
python viewer.py   # optional: browse the saved runs at http://127.0.0.1:8000
```

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

### Run generated tests in Docker

The `--run-tests` option runs generated pytest files in a dedicated Docker container. Build the sandbox image once from the repository root:

```bash
docker build -f Dockerfile.sandbox -t round-table-test-sandbox:latest .
```

Then run:

```bash
python orchestrator.py "Build a CLI todo application" --run-tests
```

Optional controls:

```bash
python orchestrator.py "Build a CLI todo application" --run-tests --test-timeout 90
python orchestrator.py "Build a CLI todo application" --run-tests --docker-image round-table-test-sandbox:latest
```

The container runs as a non-root user with no network, a read-only root filesystem, read-only mounts limited to generated `src/` and `tests/` (so prompts and logs are not exposed), dropped Linux capabilities, no-new-privileges, and CPU, memory, process-count, and time limits. Only generated source and test directories are mounted, both read-only; `plan.md`, `log.json`, and transcripts are not exposed to generated tests. Tests that need temporary files should use pytest's `tmp_path` fixture or `/tmp`. Pytest output retained for the Judge is capped at 100 KB.

The sandbox image includes pytest. If generated tests need additional third-party packages, add reviewed, pinned dependencies to `Dockerfile.sandbox` and rebuild the image. The image build needs network access to download its base image and Python packages; test execution uses `--network=none`.

**Security:** AI-generated code and tests are untrusted. Docker provides defense-in-depth, not a perfect security boundary. Keep Docker updated, do not mount the Docker socket or sensitive host paths, and use a disposable environment for high-risk workloads. Docker daemon/runtime configuration and host vulnerabilities remain part of the trust boundary.

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

These tests mock Docker; they do not require a Docker daemon or make provider API calls.

## AI-to-AI communication

Read [qna.md](qna.md) before contributing. It contains the AI roster, communication rules, and append-only message board.

## Viewing runs

Browse saved runs in a browser (read-only, localhost only):

```bash
python viewer.py --port 8000
```
