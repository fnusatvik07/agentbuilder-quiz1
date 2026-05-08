# Agent Builder 2026 · Quiz 1: Tool Calling and ReAct Loop

A live, deployable, single-attempt MCQ exam built for the **DataSense Agent Builder 2026** course. Twenty interview-grade questions on tool-calling APIs and ReAct agent loops, with a 15 minute timer, automatic scoring, per-question explanations on the marksheet, and a live, auto-refreshing leaderboard for classroom use.

## Highlights

* 20 questions, 35 marks total. Scoring tiers: 1 mark (10 questions), 2 marks (5 questions), 3 marks (5 questions).
* Answer-key distribution is exactly 5 A, 5 B, 5 C, 5 D. Asserted at module load.
* No em-dashes anywhere in candidate-facing text. Asserted at module load.
* Difficulty is internal metadata; candidates see marks, not difficulty labels.
* Per-question marksheet explains why the correct answer is right AND why each distractor is wrong, so the test doubles as a study sheet.
* CAT/GMAT-style test UI with question palette, mark-for-review, keyboard shortcuts, and a server-enforced single attempt per name and email.
* Two leaderboard views: a regular page that polls every 5 seconds, and a full-screen projector view (dark theme, big fonts, top 20) for classroom display.

## What's in here

```
.
├── app.py                  FastAPI backend
├── questions.py            the 20 question bank
├── requirements.txt        pinned deps
├── Dockerfile              one-process container
├── static/
│   ├── index.html          landing page (name + email entry)
│   ├── test.html           test UI (timer, palette, options)
│   ├── result.html         marksheet
│   ├── leaderboard.html    live-refreshing rank card
│   ├── leaderboard_live.html projector view
│   └── style.css
└── README.md
```

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app:app --reload --port 8000
```

Open `http://localhost:8000`.

The SQLite database (`quiz.db`) is created in the working directory by default. Override with the `QUIZ_DB` env var:

```bash
QUIZ_DB=/some/path/quiz.db .venv/bin/uvicorn app:app --port 8000
```

## URLs

| Path | Purpose |
| --- | --- |
| `/` | Candidate landing page (name + email entry) |
| `/test/{attempt_id}` | The 15 minute test UI |
| `/result/{attempt_id}` | Marksheet with score, rank, percentile, and per-question explanations |
| `/leaderboard` | Live leaderboard, refreshes every 5 seconds |
| `/leaderboard/live` | Projector view (full-screen dark theme, refreshes every 3 seconds) |
| `/api/start` | POST: begin a new attempt |
| `/api/submit` | POST: submit answers and get the marksheet |
| `/api/result/{attempt_id}` | GET: full marksheet JSON |
| `/api/leaderboard` | GET: ranked submissions |
| `/api/health` | GET: sanity ping |

## Live class workflow

1. Before class, start the server. Project the **/leaderboard/live** URL on the classroom screen.
2. As students arrive, share the **landing URL** with them. Each student enters name and email and hits Start.
3. Each student has their own 15 minute timer (it begins when they click Start).
4. The projector view shows new submissions live, with a green flash for each arrival and gold/silver/bronze rows for the top three.
5. After everyone is done, walk through the marksheet of one student as a teaching moment. Every question carries a written explanation of why the correct answer is right and why each distractor is wrong.

## Anti-cheat (light)

* Correct answers and explanations live server-side and are returned only after submission.
* Duplicate name **or** email is rejected at start time, case-insensitive, via a SQLite UNIQUE constraint.
* `started_at` is recorded server-side; the client timer is cosmetic.
* Double-submit on the same attempt returns HTTP 409.

This is not a proctoring system. Candidates can still open another browser tab. For high-stakes use, run inside a proctored environment.

## Run with Docker

```bash
docker build -t agentbuilder-quiz1 .
docker run -p 8000:8000 -v $(pwd)/data:/data agentbuilder-quiz1
```

The volume `/data` persists `quiz.db` across container restarts. The Dockerfile sets `QUIZ_DB=/data/quiz.db` automatically.

## Free deployment options

### Option 1: ngrok (best for one-off live class)

Zero deployment. Run the server on your laptop, expose with ngrok.

```bash
brew install ngrok
ngrok config add-authtoken <your-token>     # free signup at ngrok.com

# every class
.venv/bin/uvicorn app:app --port 8000 &
ngrok http 8000
```

Ngrok prints a public URL like `https://abc123.ngrok-free.app`. Share that with students. Tear down after class.

Free tier supports about 40 concurrent connections, easily enough for a class of 40.

### Option 2: Render (best for a permanent course URL)

Free tier: 750 hours per month and a free persistent disk for SQLite.

1. Push this repo to GitHub.
2. On `render.com`, create a new Web Service from this repo.
3. Settings:
   * Build command: `pip install -r requirements.txt`
   * Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   * Environment variable: `QUIZ_DB=/var/data/quiz.db`
   * Add a disk mounted at `/var/data`, size 1 GB.
4. Deploy. You get a URL like `https://agentbuilder-quiz1.onrender.com`.

Free tier sleeps after 15 minutes of inactivity. The first student wakes the dyno (about 30 seconds cold start), then it stays warm.

### Option 3: Fly.io (most reliable free tier)

Free tier: 3 small VMs and 3 GB persistent storage.

```bash
brew install flyctl
fly auth signup

fly launch --dockerfile Dockerfile --no-deploy
fly volumes create quiz_data --size 1 --region <your-region>

# in fly.toml, add:
# [mounts]
#   source = "quiz_data"
#   destination = "/data"

fly deploy
```

URL ends up at `https://<app-name>.fly.dev`. Does not sleep on idle.

## Editing questions

Open `questions.py`. Each entry is a dict with these fields:

```python
{
    "id": 1,
    "difficulty": "easy",                    # internal only
    "marks": 1,                              # 1, 2, or 3
    "stem_html": "<p>...</p>",               # arbitrary HTML
    "options": [
        {"key": "A", "html": "..."},
        {"key": "B", "html": "..."},
        {"key": "C", "html": "..."},
        {"key": "D", "html": "..."},
    ],
    "correct": "B",
    "explanation": "Correct: B. ... Why not A: ... Why not C: ... Why not D: ...",
}
```

Notes:

* `stem_html` accepts arbitrary HTML. Use `<pre>` for traces and JSON, `<code>` for inline tokens, `<table>` for comparison matrices.
* The total-marks assertion (`assert TOTAL_MARKS == 35`) catches accidental mark-weight changes.
* The answer-distribution assertion (`assert _dist == {"A": 5, "B": 5, "C": 5, "D": 5}`) catches accidental skew.
* The em-dash assertion catches stylistic regressions.

After editing, restart the server.

## Question coverage

| Tier | Questions | Marks each | Topics |
| --- | --- | --- | --- |
| 1 | Q1 to Q10 | 1 | What is a tool, model vs runtime, tool descriptions, observation, context window, basic flow |
| 2 | Q11 to Q15 | 2 | Latency math, multi-digit arithmetic failure, wrong-layer fixes, trajectory evals, scratchpad cost growth |
| 3 | Q16 to Q20 | 3 | Identity injection, prompt injection via tool output, cost-per-success unit economics, runtime-side compression, production financial flow design |

## Implementation notes

* Single SQLite file backs everything; no separate DB process needed.
* Frontend is vanilla JS, no build step. Each page is a single HTML file that calls the API.
* Test page state lives in JS memory plus `sessionStorage`. Refreshing mid-test returns the candidate to the home page (intentional; prevents accidental re-fetch). For stronger persistence, mirror state to the server every N seconds.
* Server-side timer enforcement is soft. The client computes the countdown from `started_at + duration_sec`. A truly hard server-side cut-off would require WebSocket pings or a scheduled auto-submit. For an interview MCQ this is sufficient.

## License

MIT.
