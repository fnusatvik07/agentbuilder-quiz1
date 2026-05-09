"""Tool Calling & ReAct MCQ — FastAPI backend.

Run locally:
  uvicorn app:app --reload --port 8000

Endpoints:
  GET  /                         landing page
  GET  /test/{attempt_id}        test page
  GET  /result/{attempt_id}      marksheet page
  GET  /leaderboard              rank-card page

  POST /api/start                {name, email} -> {attempt_id, started_at, duration_sec, questions, total_marks}
  POST /api/submit               {attempt_id, answers: {qid: 'A'|'B'|'C'|'D'}}
  GET  /api/result/{attempt_id}  marksheet JSON
  GET  /api/leaderboard          [{rank, name, score, total, time_sec, submitted_at}]
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator

from questions import QUESTIONS, TOTAL_MARKS, by_id, public_questions

# ----------------------------------------------------------------------------
# Config

DB_PATH = os.environ.get("QUIZ_DB", str(Path(__file__).parent / "quiz.db"))
DURATION_SEC = 25 * 60          # 25 minutes
GRACE_SEC = 30                  # accept submissions up to 30s past the bell
STATIC_DIR = Path(__file__).parent / "static"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# ----------------------------------------------------------------------------
# DB

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS attempts (
                id           TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                name_lc      TEXT NOT NULL UNIQUE,
                email        TEXT NOT NULL,
                email_lc     TEXT NOT NULL UNIQUE,
                started_at   REAL NOT NULL,
                submitted_at REAL,
                score        INTEGER,
                total        INTEGER,
                time_sec     INTEGER,
                answers_json TEXT,
                breakdown_json TEXT
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_score ON attempts(score DESC, time_sec ASC)")


@contextmanager
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


# ----------------------------------------------------------------------------
# Models

class StartRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120)

    @field_validator("name")
    @classmethod
    def name_clean(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name required")
        return v

    @field_validator("email")
    @classmethod
    def email_clean(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("invalid email format")
        return v


class SubmitRequest(BaseModel):
    attempt_id: str
    answers: dict[str, str]   # {"1": "A", "2": "C", ...}


# ----------------------------------------------------------------------------
# App

app = FastAPI(title="Tool Calling & ReAct MCQ")
init_db()

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---- pages ----------------------------------------------------------------

def _serve(name: str) -> FileResponse:
    return FileResponse(STATIC_DIR / name)


@app.get("/")
def page_index():
    return _serve("index.html")


@app.get("/test/{attempt_id}")
def page_test(attempt_id: str):
    return _serve("test.html")


@app.get("/result/{attempt_id}")
def page_result(attempt_id: str):
    return _serve("result.html")


@app.get("/leaderboard")
def page_leaderboard():
    return _serve("leaderboard.html")


@app.get("/leaderboard/live")
def page_leaderboard_live():
    return _serve("leaderboard_live.html")


# ---- API ------------------------------------------------------------------

@app.post("/api/start")
def api_start(req: StartRequest):
    name_lc = req.name.lower()
    email_lc = req.email
    attempt_id = uuid.uuid4().hex[:12]
    now = time.time()

    with db() as con:
        # uniqueness check (name OR email)
        existing = con.execute(
            "SELECT id, name, email FROM attempts WHERE name_lc = ? OR email_lc = ? LIMIT 1",
            (name_lc, email_lc),
        ).fetchone()
        if existing:
            field = "name" if existing["name"].lower() == name_lc else "email"
            raise HTTPException(
                status_code=409,
                detail=f"This {field} has already started a test. Each candidate may attempt only once.",
            )

        try:
            con.execute(
                """INSERT INTO attempts (id, name, name_lc, email, email_lc, started_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (attempt_id, req.name, name_lc, req.email, email_lc, now),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Duplicate name or email.")

    return {
        "attempt_id": attempt_id,
        "started_at": now,
        "duration_sec": DURATION_SEC,
        "questions": public_questions(),
        "total_marks": TOTAL_MARKS,
        "name": req.name,
    }


@app.post("/api/submit")
def api_submit(req: SubmitRequest):
    now = time.time()

    with db() as con:
        row = con.execute(
            "SELECT * FROM attempts WHERE id = ?", (req.attempt_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="attempt not found")
        if row["submitted_at"] is not None:
            raise HTTPException(status_code=409, detail="already submitted")

        elapsed = now - row["started_at"]
        time_sec = int(min(elapsed, DURATION_SEC))

        # Score the attempt. Late submissions still score, but answers
        # received past DURATION_SEC + GRACE_SEC are scored against the
        # answers payload as-is — server-side timer is enforced by the
        # client; a hard server cap is applied below.
        score = 0
        breakdown = []
        for q in QUESTIONS:
            qid = str(q["id"])
            chosen = req.answers.get(qid)
            correct = (chosen == q["correct"])
            marks = q["marks"] if correct else 0
            score += marks
            breakdown.append({
                "id": q["id"],
                "difficulty": q["difficulty"],
                "marks": q["marks"],
                "awarded": marks,
                "chosen": chosen,
                "correct": q["correct"],
                "explanation": q["explanation"],
            })

        con.execute(
            """UPDATE attempts
                  SET submitted_at = ?, score = ?, total = ?, time_sec = ?,
                      answers_json = ?, breakdown_json = ?
                WHERE id = ?""",
            (now, score, TOTAL_MARKS, time_sec,
             json.dumps(req.answers), json.dumps(breakdown), req.attempt_id),
        )

    return {
        "attempt_id": req.attempt_id,
        "score": score,
        "total": TOTAL_MARKS,
        "time_sec": time_sec,
        "breakdown": breakdown,
    }


@app.get("/api/result/{attempt_id}")
def api_result(attempt_id: str):
    with db() as con:
        row = con.execute(
            "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        if row["submitted_at"] is None:
            raise HTTPException(status_code=409, detail="not submitted")
        breakdown = json.loads(row["breakdown_json"]) if row["breakdown_json"] else []
        # render question stems alongside breakdown for the marksheet
        for entry in breakdown:
            q = by_id(entry["id"])
            if q:
                entry["stem_html"] = q["stem_html"]
                entry["options"] = q["options"]
        # rank
        rank_row = con.execute(
            """SELECT COUNT(*) + 1 AS rank FROM attempts
                WHERE submitted_at IS NOT NULL
                  AND ( score > ?
                        OR (score = ? AND time_sec < ?) )""",
            (row["score"], row["score"], row["time_sec"]),
        ).fetchone()
        total_attempts = con.execute(
            "SELECT COUNT(*) AS n FROM attempts WHERE submitted_at IS NOT NULL"
        ).fetchone()["n"]

    percentile = None
    if total_attempts > 1:
        percentile = round(100.0 * (total_attempts - rank_row["rank"]) / (total_attempts - 1))

    return {
        "attempt_id": attempt_id,
        "name": row["name"],
        "email": row["email"],
        "score": row["score"],
        "total": row["total"],
        "time_sec": row["time_sec"],
        "submitted_at": row["submitted_at"],
        "rank": rank_row["rank"],
        "total_attempts": total_attempts,
        "percentile": percentile,
        "breakdown": breakdown,
    }


@app.get("/api/leaderboard")
def api_leaderboard():
    with db() as con:
        rows = con.execute(
            """SELECT name, score, total, time_sec, submitted_at
                 FROM attempts
                WHERE submitted_at IS NOT NULL
                ORDER BY score DESC, time_sec ASC, submitted_at ASC"""
        ).fetchall()
    out = []
    for i, r in enumerate(rows, 1):
        out.append({
            "rank": i,
            "name": r["name"],
            "score": r["score"],
            "total": r["total"],
            "time_sec": r["time_sec"],
            "submitted_at": r["submitted_at"],
        })
    return out


# health
@app.get("/api/health")
def health():
    return {"ok": True, "questions": len(QUESTIONS), "total_marks": TOTAL_MARKS}
